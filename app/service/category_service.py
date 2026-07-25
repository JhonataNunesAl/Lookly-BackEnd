from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from model.category import Category


async def list_categories(db: AsyncSession) -> list[Category]:
    result = await db.execute(
        select(Category)
        .where(Category.is_active.is_(True))
        .order_by(Category.sort_order, Category.name)
    )
    return list(result.scalars().all())
