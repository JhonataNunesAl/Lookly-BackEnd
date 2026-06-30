from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from model.look import Look
from model.category import Category
from model.swipe import Swipe


async def get_feed(
    db: AsyncSession,
    user_id: UUID,
    category_slug: str,
    limit: int = 20,
    cursor: datetime | None = None,
) -> dict:
    """Feed core: looks de uma categoria que o usuário ainda não deu swipe.

    Filtro rígido por categoria e paginação por cursor (created_at desc).
    """
    swiped_subq = select(Swipe.look_id).where(Swipe.user_id == user_id)

    query = (
        select(Look)
        .join(Category, Look.category_id == Category.id)
        .where(Category.slug == category_slug)
        .where(~Look.id.in_(swiped_subq))
        .order_by(Look.created_at.desc())
    )
    if cursor is not None:
        query = query.where(Look.created_at < cursor)

    query = query.limit(limit)

    result = await db.execute(query)
    looks = list(result.scalars().all())

    next_cursor = looks[-1].created_at.isoformat() if len(looks) == limit else None
    return {"items": looks, "next_cursor": next_cursor}
