from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from model.seller import Seller
from schemas.seller import SellerCreate, SellerUpdate


async def get_seller_or_none(db: AsyncSession, user_id: UUID) -> Seller | None:
    result = await db.execute(select(Seller).where(Seller.id == user_id))
    return result.scalar_one_or_none()


async def get_me(db: AsyncSession, user_id: UUID) -> Seller:
    seller = await get_seller_or_none(db, user_id)
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Você ainda não é um vendedor"
        )
    return seller


async def become_seller(db: AsyncSession, user_id: UUID, dados: SellerCreate) -> Seller:
    if await get_seller_or_none(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Você já é um vendedor"
        )
    seller = Seller(id=user_id, **dados.model_dump())
    db.add(seller)
    await db.commit()
    await db.refresh(seller)
    return seller


async def update_me(db: AsyncSession, user_id: UUID, dados: SellerUpdate) -> Seller:
    seller = await get_me(db, user_id)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(seller, campo, valor)
    await db.commit()
    await db.refresh(seller)
    return seller
