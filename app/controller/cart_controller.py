from fastapi import APIRouter, Depends, status, HTTPException
from db.database import get_db
from dependencies.auth import get_current_user_id
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.cart import CartUserResponse
from sqlalchemy import select
from model.cart import Cart
from uuid import UUID

router = APIRouter(prefix='/cart',
    tags=['Cart',])


@router.get(path='/user/', 
             status_code=status.HTTP_200_OK,
             response_model=CartUserResponse, 
             summary= 'Busca o carrinho do usuario atraves do seu id')
async def get_cart_user(user_id: UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    cart_user = await db.scalar(select(Cart).where(Cart.user_id == user_id))
    if cart_user:
        return cart_user
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail='Cart user not found')
