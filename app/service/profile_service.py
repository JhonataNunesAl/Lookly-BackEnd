from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from model.profile import Profile
from model.category import Category
from model.signal import UserCategoryAffinity
from schemas.profile import ProfileUpdate
from service import seller_service


async def _get_profile(db: AsyncSession, user_id: UUID) -> Profile:
    result = await db.execute(select(Profile).where(Profile.id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Perfil não encontrado"
        )
    return profile


async def _with_role(db: AsyncSession, profile: Profile) -> Profile:
    """Anexa o papel real (resolvido no servidor) ao perfil."""
    seller = await seller_service.get_seller_by_owner(db, profile.id)
    profile.is_seller = seller is not None
    profile.seller_id = seller.id if seller else None
    return profile


async def get_me(db: AsyncSession, user_id: UUID) -> Profile:
    return await _with_role(db, await _get_profile(db, user_id))


async def update_me(db: AsyncSession, user_id: UUID, dados: ProfileUpdate) -> Profile:
    profile = await _get_profile(db, user_id)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(profile, campo, valor)
    try:
        await db.commit()
    except IntegrityError as e:
        # Rede de segurança: o Pydantic já valida formato de username e
        # tamanho de bio (schemas/profile.py), mas conflito de unicidade só
        # o banco consegue detectar (duas pessoas escolhendo o mesmo username
        # ao mesmo tempo). Sem isso, essa corrida virava um 500 genérico.
        await db.rollback()
        sqlstate = getattr(getattr(e, "orig", None), "sqlstate", None)
        detail = (
            "Esse nome de usuário já está em uso."
            if sqlstate == "23505"
            else "Não foi possível atualizar o perfil — confira os dados enviados."
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    await db.refresh(profile)
    return await _with_role(db, profile)


async def get_category_affinity(db: AsyncSession, user_id: UUID) -> list[dict]:
    """Placar de afinidade por categoria, do maior para o menor.

    Alimentado só pelos gatilhos do banco (curtir +2, salvar +4) — este
    service apenas lê e junta com o nome da categoria para exibição.
    """
    query = (
        select(
            UserCategoryAffinity.category_id,
            Category.name.label("category_name"),
            UserCategoryAffinity.score,
        )
        .join(Category, Category.id == UserCategoryAffinity.category_id)
        .where(UserCategoryAffinity.user_id == user_id)
        .order_by(UserCategoryAffinity.score.desc())
    )
    result = await db.execute(query)
    return [
        {"category_id": row.category_id, "category_name": row.category_name, "score": row.score}
        for row in result.all()
    ]
