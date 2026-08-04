from fastapi import APIRouter, Depends, status, HTTPException
from db.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from model.cart_items import CartItems
from model.cart import Cart
from uuid import UUID
from sqlalchemy.orm import joinedload
from decimal import Decimal
from schemas.cart_items import *
from sqlalchemy import select



router = APIRouter(prefix='/cart-items', tags=['Carts_Items'])


@router.post(path='/',
             status_code= status.HTTP_201_CREATED,
             response_model=CartItemsResponse,
             summary="Adiciona um look no carrinho")
async def add_look_cart(dados: CartItemsAdd, db: AsyncSession = Depends(get_db)):

    look_in_cart = await db.scalar(select(CartItems).where(CartItems.look_id == dados.look_id))

    if look_in_cart:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail = 'Look already exists in Cart of User')

    new_look_in_cart = CartItems(
        cart_id = dados.cart_id,
        look_id = dados.look_id,
        quantity = dados.quantity
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
        item.price_quantity_total = item.look.price * item.quantity
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
    
    look = await db.scalar(select(CartItems).where(CartItems.look_id == dados.look_id and CartItems.cart_id == cart_user.id))

    await db.delete(look)
    await db.commit()


@router.put(path='/remove/{look_id}/',
             status_code= status.HTTP_200_OK,
             response_model=CartItemsResponse,
             summary="Diminui a quantidade de um look especifico no carrinho")
async def delete_one_look_cart(look_id:UUID, dados: CartItemsDelete, db: AsyncSession = Depends(get_db)):
    cart_user = await db.scalar(select(Cart).where(Cart.id == dados.cart_id))
    if cart_user == None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail = "Cart User not found")
    look = await db.scalar(select(CartItems).where((CartItems.cart_id == cart_user.id) & (CartItems.look_id == look_id)))

    if look == None:
        raise HTTPException(status_code= status.HTTP_404_NOT_FOUND,
                            detail = "Look not found in Cart of user")


    if dados.quantity > look.quantity:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="The quantity sent for removal cannot be greater than the current quantity.")

    look.quantity -= dados.quantity

    if look.quantity == 0:
        await db.delete(look)
        await db.commit()
        raise HTTPException(
        status_code=status.HTTP_200_OK,
        detail="The quantity of the item look is equal to zero. We removed it from the cart."
        )
    
    await db.commit()
    return look


@router.put(path='/add/{look_id}/',
             status_code= status.HTTP_200_OK,
             response_model=CartItemsResponse,
             summary="Aumenta a quantidade de um look especifico no carrinho")
async def add_one_more_look_cart(look_id:UUID, dados: CartItemsAddQuantity, db: AsyncSession = Depends(get_db)):
    cart_user = await db.scalar(select(Cart).where(Cart.id == dados.cart_id))
    look = await db.scalar(select(CartItems).where((CartItems.cart_id == cart_user.id) & (CartItems.look_id == look_id)))
    look.quantity += dados.quantity
    await db.commit()
    await db.refresh(look)
    return look
