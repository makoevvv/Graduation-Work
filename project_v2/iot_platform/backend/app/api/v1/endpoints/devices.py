from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from ....core.database import get_db
from ....api.deps import get_current_active_user
from ....models.models import User, Device, Enterprise, UserEnterpriseAccess, Sensor
from ....schemas.schemas import DeviceCreate, DeviceOut, DeviceOutWithSensors

router = APIRouter()


async def _check_enterprise_access(
    enterprise_id: int,
    user: User,
    db: AsyncSession,
    required_role: str = "viewer",
) -> UserEnterpriseAccess:
    """Проверяет доступ пользователя к предприятию и возвращает запись доступа."""
    order = {"viewer": 0, "admin": 1, "owner": 2}
    result = await db.execute(
        select(UserEnterpriseAccess).where(
            UserEnterpriseAccess.enterprise_id == enterprise_id,
            UserEnterpriseAccess.user_id == user.id,
        )
    )
    access = result.scalar_one_or_none()
    if not access:
        raise HTTPException(status_code=403, detail="No access to this enterprise")
    if order.get(access.role, -1) < order.get(required_role, 0):
        raise HTTPException(status_code=403, detail=f"Role '{required_role}' required")
    return access


async def _get_device_with_access(
    device_id: int,
    user: User,
    db: AsyncSession,
    required_role: str = "viewer",
) -> Device:
    """Получает устройство и проверяет доступ через предприятие."""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    await _check_enterprise_access(device.enterprise_id, user, db, required_role)
    return device


# ---------------------------------------------------------------------------
# CRUD устройств
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[DeviceOut])
async def list_devices(
    enterprise_id: Optional[int] = Query(None, description="Filter by enterprise ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Список устройств. Если enterprise_id не указан — все устройства доступных предприятий."""
    if enterprise_id is not None:
        await _check_enterprise_access(enterprise_id, current_user, db, "viewer")
        result = await db.execute(
            select(Device).where(Device.enterprise_id == enterprise_id)
        )
    else:
        # Все устройства предприятий, к которым есть доступ
        result = await db.execute(
            select(Device)
            .join(Enterprise, Enterprise.id == Device.enterprise_id)
            .join(UserEnterpriseAccess, UserEnterpriseAccess.enterprise_id == Enterprise.id)
            .where(UserEnterpriseAccess.user_id == current_user.id)
        )
    return result.scalars().all()


@router.post("/", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def create_device(
    data: DeviceCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать устройство в предприятии. Требуется роль admin+."""
    await _check_enterprise_access(data.enterprise_id, current_user, db, "admin")

    device = Device(**data.model_dump())
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@router.get("/{device_id}", response_model=DeviceOutWithSensors)
async def get_device(
    device_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Детальная информация об устройстве (с датчиками)."""
    device = await _get_device_with_access(device_id, current_user, db, "viewer")
    return device


@router.put("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: int,
    data: DeviceCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Обновить устройство. Требуется роль admin+."""
    device = await _get_device_with_access(device_id, current_user, db, "admin")

    # Если меняется enterprise_id — проверяем доступ к новому предприятию
    if data.enterprise_id != device.enterprise_id:
        await _check_enterprise_access(data.enterprise_id, current_user, db, "admin")

    for key, value in data.model_dump().items():
        setattr(device, key, value)
    await db.commit()
    await db.refresh(device)
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Удалить устройство. Требуется роль admin+."""
    device = await _get_device_with_access(device_id, current_user, db, "admin")
    await db.delete(device)
    await db.commit()


# ---------------------------------------------------------------------------
# Датчики устройства
# ---------------------------------------------------------------------------

@router.get("/{device_id}/sensors", response_model=List)
async def list_device_sensors(
    device_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Список датчиков устройства."""
    await _get_device_with_access(device_id, current_user, db, "viewer")
    result = await db.execute(
        select(Sensor).where(Sensor.device_id == device_id)
    )
    sensors = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "type": s.type,
            "unit": s.unit,
            "device_id": s.device_id,
            "group_id": s.group_id,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sensors
    ]
