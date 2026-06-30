from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from model.look import Look
from model.category import Category
from schemas.look import LookCreate, LookUpdate
from service.seller_service import get_seller_or_none


async def _get_look(db: AsyncSession, look_id: UUID) -> Look:
    result = await db.execute(select(Look).where(Look.id == look_id))
    look = result.scalar_one_or_none()
    if not look:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Look não encontrado"
        )
    return look


async def get_look(db: AsyncSession, look_id: UUID) -> Look:
    return await _get_look(db, look_id)


async def create_look(db: AsyncSession, user_id: UUID, dados: LookCreate) -> Look:
    # Apenas vendedores postam looks.
    if not await get_seller_or_none(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas vendedores podem criar looks",
        )

    # Categoria precisa existir.
    cat = await db.execute(select(Category).where(Category.id == dados.category_id))
    if not cat.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Categoria inexistente"
        )

    look = Look(creator_id=user_id, **dados.model_dump())
    db.add(look)
    await db.commit()
    await db.refresh(look)
    return look


async def _get_owned_look(db: AsyncSession, user_id: UUID, look_id: UUID) -> Look:
    look = await _get_look(db, look_id)
    if look.creator_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Este look não é seu"
        )
    return look


async def update_look(
    db: AsyncSession, user_id: UUID, look_id: UUID, dados: LookUpdate
) -> Look:
    look = await _get_owned_look(db, user_id, look_id)

    payload = dados.model_dump(exclude_unset=True)
    if "category_id" in payload:
        cat = await db.execute(
            select(Category).where(Category.id == payload["category_id"])
        )
        if not cat.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Categoria inexistente"
            )

    for campo, valor in payload.items():
        setattr(look, campo, valor)
    await db.commit()
    await db.refresh(look)
    return look


async def delete_look(db: AsyncSession, user_id: UUID, look_id: UUID) -> None:
    look = await _get_owned_look(db, user_id, look_id)
    await db.delete(look)
    await db.commit()


async def get_share_payload(db: AsyncSession, look_id: UUID) -> dict:
    """Monta o payload de compartilhamento externo (WhatsApp/Instagram)."""
    look = await _get_look(db, look_id)
    deep_link = f"lucker://looks/{look.id}"
    texto = "Olha esse look que achei no Lucker!"
    return {
        "look_id": str(look.id),
        "deep_link": deep_link,
        "whatsapp_url": f"https://wa.me/?text={texto} {deep_link}",
        "buy_link": look.buy_link,
    }
