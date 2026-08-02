from fastapi import APIRouter, Depends, status, HTTPException
from db.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from model.cart_items import CartItems
from model.cart import Cart
from model.look import Look
from sqlalchemy.orm import joinedload
from decimal import Decimal
from schemas.cart_items import CartItemsAdd, CartItemsResponse, ListCartItemResponse, DeleteLookCartItemUser, CartItemsDelete
from sqlalchemy import select



router = APIRouter(prefix='/cart-items', tags=['Carts_Items'])


@router.post(path='/',
             status_code= status.HTTP_201_CREATED,
             response_model=CartItemsResponse,
             summary="Adiciona um look no carrinho")
async def add_look_cart(dados: CartItemsAdd, db: AsyncSession = Depends(get_db)):

    look_in_cart = db.scalar(select(CartItems).where(CartItems.look_id == dados.look_id))
    if look_in_cart:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = 'Look already exists in Cart of User')

    new_look_in_cart = CartItems(
        cart_id = dados.cart_id,
        look_id = dados.look_id
    )

    db.add(new_look_in_cart)
    await db.commit()
    await db.refresh(new_look_in_cart)
    return new_look_in_cart


@router.get(
    path='/{user_id}/',
    status_code=status.HTTP_200_OK,
    response_model=ListCartItemResponse,
    summary="Retorna todos os looks que estão no carrinho de um usuário específico"
)
async def get_looks_user(user_id: str, db: AsyncSession = Depends(get_db)):
    cart_user = await db.scalar(
        select(Cart).where(Cart.user_id == user_id)
    )

    if cart_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Carrinho não encontrado."
        )

    result = await db.scalars(
        select(CartItems)
        .options(joinedload(CartItems.look))
        .where(CartItems.cart_id == cart_user.id)
    )

    cart_items = result.all()

    price_total = Decimal("0.00")

    for item in cart_items:
        if item.look.price:
            price_total += item.look.price

    return {
        "looks": cart_items,
        "price_total": price_total
    }


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


@router.put(path='/{look_id}/',
             status_code= status.HTTP_200_OK,
             response_model=CartItemsResponse,
             summary="Diminui a quantidade de peças no carrinho")
async def delete_one_look_cart(dados: CartItemsDelete, db: AsyncSession = Depends(get_db)):

    cart_user = await db.scalar(select(Cart).where(Cart.id == dados.cart_id))
    look = await db.scalar(select(CartItems).where(CartItems.cart_id == cart_user.id and CartItems.look_id == dados.look_id))
    look.quantity -= 1
    if look.quantity == 0:
        await db.delete(look)
        await db.commit()
        raise HTTPException(
        status_code=400,
        detail="Quantity item look is zero"
    )
    return look
