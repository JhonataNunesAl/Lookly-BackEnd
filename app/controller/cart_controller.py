from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.cart import CartUserResponse
from service import cart_service


router = APIRouter(
    prefix="/cart",
    tags=["Cart"],
)


@router.get(
    "/user/",
    status_code=status.HTTP_200_OK,
    response_model=CartUserResponse,
    summary="Busca o carrinho do usuário através do seu ID",
)
async def get_cart_user(user_id: UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    
    return await cart_service.get_cart_user(
        db=db,
        user_id=user_id,
    )