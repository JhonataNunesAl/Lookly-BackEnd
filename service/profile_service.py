from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from model.profile import Profile
from schemas.profile import ProfileUpdate


async def _get_profile(db: AsyncSession, user_id: UUID) -> Profile:
    result = await db.execute(select(Profile).where(Profile.id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Perfil não encontrado"
        )
    return profile


async def get_me(db: AsyncSession, user_id: UUID) -> Profile:
    return await _get_profile(db, user_id)


async def update_me(db: AsyncSession, user_id: UUID, dados: ProfileUpdate) -> Profile:
    profile = await _get_profile(db, user_id)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(profile, campo, valor)
    await db.commit()
    await db.refresh(profile)
    return profile
