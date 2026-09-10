from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.cart_items import *
from service import cart_items_service


router = APIRouter(
    prefix="/cart-items",
    tags=["Carts_Items"],
)


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=CartItemsResponse,
    summary="Adiciona um look no carrinho",
)
async def add_look_cart(dados: CartItemsAdd, user_id: UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):

    return await cart_items_service.add_look_cart(db, dados, user_id)


@router.get(
    "/user/",
    status_code=status.HTTP_200_OK,
    response_model=ListCartItemResponse,
    summary="Retorna todos os looks que estão no carrinho de um usuário específico",
)
async def get_looks_user(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await cart_items_service.get_looks_user(db, user_id)


@router.delete(
    "/user/",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um look do carrinho de um usuário específico",
)
async def delete_look_cart_user(
    dados: DeleteLookCartItemUser,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await cart_items_service.delete_look_cart_user(
        db,
        user_id,
        dados,
    )


@router.put(
    "/remove/{look_id}/",
    status_code=status.HTTP_200_OK,
    response_model=CartItemsResponse,
    summary="Diminui a quantidade de um look específico no carrinho",
)
async def remove_quantity(
    look_id: UUID,
    dados: CartItemsDelete,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await cart_items_service.remove_quantity(
        db,
        user_id,
        look_id,
        dados,
    )


@router.put(
    "/add/{look_id}/",
    status_code=status.HTTP_200_OK,
    response_model=CartItemsResponse,
    summary="Aumenta a quantidade de um look específico no carrinho",
)
async def add_quantity(look_id: UUID, dados: CartItemsAddQuantity, 
                       user_id: UUID = Depends(get_current_user_id), 
                       db: AsyncSession = Depends(get_db)):
    
    return await cart_items_service.add_quantity(
        db,
        user_id,
        look_id,
        dados,
    )