from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from model.look import Look
from model.category import Category
from model.signal import LookView


async def get_feed(
    db: AsyncSession,
    user_id: UUID,
    category_slug: str | None = None,
    limit: int = 20,
    cursor: datetime | None = None,
) -> dict:
    """Feed: looks ativos que o usuário ainda não viu.

    O filtro de categoria é OPCIONAL — sem ele, o feed abre espaço para
    ranqueamento futuro em vez de ser uma lista cronológica filtrada.
    """
    seen_subq = select(LookView.look_id).where(LookView.user_id == user_id)

    query = (
        select(Look)
        .where(Look.status == "active")
        .where(~Look.id.in_(seen_subq))
        .order_by(Look.created_at.desc())
    )

    if category_slug:
        query = query.join(Category, Look.category_id == Category.id).where(
            Category.slug == category_slug
        )
    if cursor is not None:
        query = query.where(Look.created_at < cursor)

    query = query.limit(limit)

    result = await db.execute(query)
    looks = list(result.scalars().all())

    next_cursor = looks[-1].created_at.isoformat() if len(looks) == limit else None
    return {"items": looks, "next_cursor": next_cursor}
