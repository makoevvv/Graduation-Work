from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import List, Optional

from ....core.database import get_db
from ....api.deps import get_current_active_user
from ....models.models import User, Sensor, Device, Enterprise, UserEnterpriseAccess
from ....models.models import Group
from ....schemas.schemas import SensorCreate, SensorOut

router = APIRouter()

@router.get("/", response_model=List[SensorOut])
async def get_my_sensors(
    group_id: Optional[int] = Query(None, description="Filter by group ID"),
    device_id: Optional[int] = Query(None, description="Filter by device ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Возвращает датчики пользователя (прямые) + датчики устройств доступных предприятий."""
    # Датчики, принадлежащие пользователю напрямую (старая логика)
    query = select(Sensor).where(
        or_(
            Sensor.user_id == current_user.id,
            # Датчики через device → enterprise → access
            Sensor.device_id.in_(
                select(Device.id)
                .join(Enterprise, Enterprise.id == Device.enterprise_id)
                .join(UserEnterpriseAccess, UserEnterpriseAccess.enterprise_id == Enterprise.id)
                .where(UserEnterpriseAccess.user_id == current_user.id)
            )
        )
    )
    if group_id is not None:
        query = query.where(Sensor.group_id == group_id)
    if device_id is not None:
        query = query.where(Sensor.device_id == device_id)
    result = await db.execute(query)
    sensors = result.scalars().all()
    return sensors

@router.post("/", response_model=SensorOut)
async def create_sensor(
    sensor: SensorCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Если указан group_id, проверим, что группа принадлежит пользователю
    if sensor.group_id is not None:
        group_result = await db.execute(select(Group).where(
            Group.id == sensor.group_id,
            Group.user_id == current_user.id
        ))
        group = group_result.scalar_one_or_none()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found or not owned by user")
    
    new_sensor = Sensor(**sensor.model_dump(), user_id=current_user.id)
    db.add(new_sensor)
    await db.commit()
    await db.refresh(new_sensor)
    return new_sensor

@router.get("/{sensor_id}", response_model=SensorOut)
async def get_sensor(
    sensor_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Sensor).where(
        Sensor.id == sensor_id,
        Sensor.user_id == current_user.id
    ))
    sensor = result.scalar_one_or_none()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor

@router.put("/{sensor_id}", response_model=SensorOut)
async def update_sensor(
    sensor_id: int,
    sensor_update: SensorCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Sensor).where(
        Sensor.id == sensor_id,
        Sensor.user_id == current_user.id
    ))
    sensor = result.scalar_one_or_none()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    
    # Если меняется group_id, проверим доступность новой группы
    if sensor_update.group_id is not None:
        group_result = await db.execute(select(Group).where(
            Group.id == sensor_update.group_id,
            Group.user_id == current_user.id
        ))
        if not group_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="New group not found or not owned by user")
    
    for key, value in sensor_update.model_dump().items():
        setattr(sensor, key, value)
    await db.commit()
    await db.refresh(sensor)
    return sensor

@router.delete("/{sensor_id}")
async def delete_sensor(
    sensor_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Sensor).where(
        Sensor.id == sensor_id,
        Sensor.user_id == current_user.id
    ))
    sensor = result.scalar_one_or_none()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    await db.delete(sensor)
    await db.commit()
    return {"ok": True}