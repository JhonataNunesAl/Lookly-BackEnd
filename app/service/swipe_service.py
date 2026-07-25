from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from model.signal import LookLike, LookView
from model.look import Look
from schemas.swipe import SwipeCreate, SwipeDirection


async def record_swipe(db: AsyncSession, user_id: UUID, dados: SwipeCreate) -> dict:
    """Registra o swipe. Réplica de record_swipe() do banco.

    Grava a view (todo swipe) e, se RIGHT, a curtida — incrementando
    likes_count só quando a curtida é nova. NÃO salva no guarda-roupa:
    salvar é um gesto deliberado e separado (ver saved_looks).
    """
    exists = await db.execute(
        select(Look.id).where(Look.id == dados.look_id, Look.status == "active")
    )
    if not exists.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Look não encontrado"
        )

    await db.execute(
        pg_insert(LookView.__table__)
        .values(
            user_id=user_id, look_id=dados.look_id, direction=dados.direction.value
        )
        .on_conflict_do_nothing()
    )

    liked = False
    if dados.direction == SwipeDirection.RIGHT:
        inserted = await db.execute(
            pg_insert(LookLike.__table__)
            .values(user_id=user_id, look_id=dados.look_id)
            .on_conflict_do_nothing()
            .returning(LookLike.user_id)
        )
        if inserted.first() is not None:
            liked = True
            await db.execute(
                update(Look)
                .where(Look.id == dados.look_id)
                .values(likes_count=Look.likes_count + 1)
            )

    await db.commit()
    return {
        "look_id": dados.look_id,
        "direction": dados.direction,
        "liked": liked,
    }
