from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from ....core.database import get_db
from ....api.deps import get_current_active_user
from ....models.models import User, Group
from ....schemas.schemas import GroupCreate, GroupOut

router = APIRouter()

@router.get("/", response_model=List[GroupOut])
async def get_my_groups(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Group).where(Group.user_id == current_user.id))
    groups = result.scalars().all()
    return groups

@router.post("/", response_model=GroupOut)
async def create_group(
    group: GroupCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    new_group = Group(**group.model_dump(), user_id=current_user.id)
    db.add(new_group)
    await db.commit()
    await db.refresh(new_group)
    return new_group

@router.get("/{group_id}", response_model=GroupOut)
async def get_group(
    group_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Group).where(
        Group.id == group_id,
        Group.user_id == current_user.id
    ))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group

@router.put("/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: int,
    group_update: GroupCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Group).where(
        Group.id == group_id,
        Group.user_id == current_user.id
    ))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    group.name = group_update.name
    group.description = group_update.description
    await db.commit()
    await db.refresh(group)
    return group

@router.delete("/{group_id}")
async def delete_group(
    group_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Group).where(
        Group.id == group_id,
        Group.user_id == current_user.id
    ))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    await db.delete(group)
    await db.commit()
    return {"ok": True}