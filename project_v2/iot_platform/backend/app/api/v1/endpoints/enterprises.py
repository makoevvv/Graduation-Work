from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from ....core.database import get_db
from ....api.deps import get_current_active_user
from ....models.models import User, Enterprise, UserEnterpriseAccess, Device
from ....schemas.schemas import (
    EnterpriseCreate, EnterpriseOut, EnterpriseOutWithDevices,
    UserEnterpriseAccessCreate, UserEnterpriseAccessOut,
)

router = APIRouter()


def _check_role(access: UserEnterpriseAccess | None, required: str = "viewer") -> None:
    """Проверяет наличие доступа и достаточность роли."""
    order = {"viewer": 0, "admin": 1, "owner": 2}
    if not access:
        raise HTTPException(status_code=403, detail="No access to this enterprise")
    if order.get(access.role, -1) < order.get(required, 0):
        raise HTTPException(status_code=403, detail=f"Role '{required}' required, got '{access.role}'")


async def _get_access(
    enterprise_id: int,
    user: User,
    db: AsyncSession,
) -> UserEnterpriseAccess | None:
    result = await db.execute(
        select(UserEnterpriseAccess).where(
            UserEnterpriseAccess.enterprise_id == enterprise_id,
            UserEnterpriseAccess.user_id == user.id,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# CRUD предприятий
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[EnterpriseOut])
async def list_my_enterprises(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Список предприятий, к которым у пользователя есть доступ."""
    result = await db.execute(
        select(Enterprise)
        .join(UserEnterpriseAccess, UserEnterpriseAccess.enterprise_id == Enterprise.id)
        .where(UserEnterpriseAccess.user_id == current_user.id)
    )
    return result.scalars().all()


@router.post("/", response_model=EnterpriseOut, status_code=status.HTTP_201_CREATED)
async def create_enterprise(
    data: EnterpriseCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать предприятие. Создатель автоматически получает роль owner."""
    enterprise = Enterprise(**data.model_dump(), owner_id=current_user.id)
    db.add(enterprise)
    await db.flush()  # получаем enterprise.id до commit

    # Автоматически выдаём создателю роль owner
    access = UserEnterpriseAccess(
        user_id=current_user.id,
        enterprise_id=enterprise.id,
        role="owner",
    )
    db.add(access)
    await db.commit()
    await db.refresh(enterprise)
    return enterprise


@router.get("/{enterprise_id}", response_model=EnterpriseOutWithDevices)
async def get_enterprise(
    enterprise_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Детальная информация о предприятии (с устройствами)."""
    access = await _get_access(enterprise_id, current_user, db)
    _check_role(access, "viewer")

    result = await db.execute(select(Enterprise).where(Enterprise.id == enterprise_id))
    enterprise = result.scalar_one_or_none()
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    return enterprise


@router.put("/{enterprise_id}", response_model=EnterpriseOut)
async def update_enterprise(
    enterprise_id: int,
    data: EnterpriseCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Обновить предприятие. Требуется роль admin или owner."""
    access = await _get_access(enterprise_id, current_user, db)
    _check_role(access, "admin")

    result = await db.execute(select(Enterprise).where(Enterprise.id == enterprise_id))
    enterprise = result.scalar_one_or_none()
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")

    for key, value in data.model_dump().items():
        setattr(enterprise, key, value)
    await db.commit()
    await db.refresh(enterprise)
    return enterprise


@router.delete("/{enterprise_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_enterprise(
    enterprise_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Удалить предприятие. Требуется роль owner."""
    access = await _get_access(enterprise_id, current_user, db)
    _check_role(access, "owner")

    result = await db.execute(select(Enterprise).where(Enterprise.id == enterprise_id))
    enterprise = result.scalar_one_or_none()
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")

    await db.delete(enterprise)
    await db.commit()


# ---------------------------------------------------------------------------
# Управление доступом
# ---------------------------------------------------------------------------

@router.get("/{enterprise_id}/access", response_model=List[UserEnterpriseAccessOut])
async def list_access(
    enterprise_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Список пользователей с доступом к предприятию. Требуется роль admin+."""
    access = await _get_access(enterprise_id, current_user, db)
    _check_role(access, "admin")

    result = await db.execute(
        select(UserEnterpriseAccess).where(UserEnterpriseAccess.enterprise_id == enterprise_id)
    )
    return result.scalars().all()


@router.post("/{enterprise_id}/access", response_model=UserEnterpriseAccessOut, status_code=status.HTTP_201_CREATED)
async def grant_access(
    enterprise_id: int,
    data: UserEnterpriseAccessCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Выдать доступ пользователю. Требуется роль admin+.
    Owner не может выдать роль owner другому пользователю."""
    my_access = await _get_access(enterprise_id, current_user, db)
    _check_role(my_access, "admin")

    if data.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot grant 'owner' role via API")

    # Проверяем, нет ли уже записи
    existing = await db.execute(
        select(UserEnterpriseAccess).where(
            UserEnterpriseAccess.enterprise_id == enterprise_id,
            UserEnterpriseAccess.user_id == data.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User already has access")

    new_access = UserEnterpriseAccess(
        user_id=data.user_id,
        enterprise_id=enterprise_id,
        role=data.role,
    )
    db.add(new_access)
    await db.commit()
    await db.refresh(new_access)
    return new_access


@router.delete("/{enterprise_id}/access/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_access(
    enterprise_id: int,
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Отозвать доступ пользователя. Требуется роль admin+. Нельзя отозвать owner."""
    my_access = await _get_access(enterprise_id, current_user, db)
    _check_role(my_access, "admin")

    result = await db.execute(
        select(UserEnterpriseAccess).where(
            UserEnterpriseAccess.enterprise_id == enterprise_id,
            UserEnterpriseAccess.user_id == user_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Access record not found")
    if target.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot revoke owner access")

    await db.delete(target)
    await db.commit()
