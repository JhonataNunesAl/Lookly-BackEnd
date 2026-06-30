from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from model.swipe import Swipe
from model.saved_look import SavedLook
from model.look import Look
from schemas.swipe import SwipeCreate, SwipeDirection


async def create_swipe(db: AsyncSession, user_id: UUID, dados: SwipeCreate) -> Swipe:
    # Look precisa existir.
    look = await db.execute(select(Look).where(Look.id == dados.look_id))
    if not look.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Look não encontrado"
        )

    swipe = Swipe(
        user_id=user_id, look_id=dados.look_id, direction=dados.direction.value
    )
    db.add(swipe)

    # Direita = curtir/salvar: grava também no armário.
    saved = False
    if dados.direction == SwipeDirection.RIGHT:
        db.add(SavedLook(user_id=user_id, look_id=dados.look_id))
        saved = True

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Você já deu swipe neste look",
        )

    await db.refresh(swipe)
    swipe.saved = saved  # atributo transitório para a resposta
    return swipe
