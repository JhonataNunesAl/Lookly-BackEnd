from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from model.cart import Cart


async def get_cart_user(
    db: AsyncSession,
    user_id: UUID,
) -> Cart:
    result = await db.execute(
        select(Cart).where(Cart.user_id == user_id)
    )

    cart = result.scalar_one_or_none()

    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart user not found",
        )

    return cart