from fastapi import APIRouter, Depends, status
from db.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from model.cart_items import CartItems
from model.cart import Cart
from schemas.cart_items import CartItemsAdd, CartItemsResponse, ListCartItemResponse, DeleteLookCartItemUser
from sqlalchemy import select



router = APIRouter(prefix='/cart-items', tags=['Carts_Items'])


@router.post(path='/',
             status_code= status.HTTP_201_CREATED,
             response_model=CartItemsResponse,
             summary="Adiciona um look no carrinho")
async def add_look_cart(dados: CartItemsAdd, db: AsyncSession = Depends(get_db)):

    new_look_in_cart = CartItems(
        cart_id = dados.cart_id,
        look_id = dados.look_id
    )
    
    db.add(new_look_in_cart)
    await db.commit()
    await db.refresh(new_look_in_cart)
    return new_look_in_cart


@router.get(path='/{user_id}/', 
            status_code=status.HTTP_200_OK,
            response_model=ListCartItemResponse,
            summary="Retorna todos os looks que estao no carrinho de um usuario especifico")
async def get_looks_user(user_id:str, db: AsyncSession = Depends(get_db)):
    cart_user = await db.scalar(select(Cart).where(Cart.user_id == user_id))
    looks = await db.scalars(select(CartItems).where(CartItems.cart_id == cart_user.id))
    return {'looks': looks.all()}


@router.delete(path='/',
               status_code=status.HTTP_204_NO_CONTENT,
               summary="Exclui um look do carrinho de um usuario especifico")
async def delete_look_cart_user(dados:DeleteLookCartItemUser, db: AsyncSession = Depends(get_db)):
    cart_user = await db.scalar(select(Cart).where(Cart.user_id == dados.user_id))
    print(cart_user.id)
    look = await db.scalar(select(CartItems).where(CartItems.look_id == dados.look_id and CartItems.cart_id == cart_user.id))
    print(look)
    await db.delete(look)
    await db.commit()

