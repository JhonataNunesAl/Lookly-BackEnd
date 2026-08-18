from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from model.cart import Cart
from model.cart_items import CartItems
from model.look import Look
from schemas.cart_items import (
    CartItemsAdd,
    CartItemsAddQuantity,
    CartItemsDelete,
    CartItemsResponse,
    ListCartItemResponse,
    DeleteLookCartItemUser,
)


async def _get_cart(db: AsyncSession, cart_id: UUID) -> Cart:

    result = await db.execute(
        select(Cart).where(Cart.id == cart_id)
    )

    cart = result.scalar_one_or_none()

    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart not found",
        )

    
    return cart


async def _get_cart_by_user(db: AsyncSession, user_id: UUID) -> Cart:
    result = await db.execute(
        select(Cart).where(Cart.user_id == user_id)
    )

    cart = result.scalar_one_or_none()

    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart not found",
        )

    return cart


async def _get_look(db: AsyncSession, look_id: UUID) -> Look:

    result = await db.execute(
        select(Look).where(Look.id == look_id)
    )

    look = result.scalar_one_or_none()

    if not look:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Look not found",
        )

    return look


async def _get_cart_item(
    db: AsyncSession,
    cart_id: UUID,
    look_id: UUID,
) -> CartItems:
    result = await db.execute(
        select(CartItems).where(
            (CartItems.cart_id == cart_id)
            & (CartItems.look_id == look_id)
        )
    )

    cart_item = result.scalar_one_or_none()

    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Look not found in cart",
        )

    return cart_item


async def add_look_cart(db: AsyncSession, dados: CartItemsAdd, user_id:UUID) -> CartItems:

    cart = await _get_cart_by_user(db, user_id)
    look = await _get_look(db, dados.look_id)

    # TODO(estoque): quando `Look.stock_quantity` existir aqui (a coluna já
    # existe em nem_schema.sql; falta o campo em `model/look.py` e nos
    # schemas), validar antes de criar o CartItems:
    #   - 400 se look.stock_quantity <= 0 ("Sem estoque disponível")
    #   - 400 se dados.quantity > look.stock_quantity
    # Validação otimista (não reserva): o checkout deve reconfirmar o
    # estoque no momento da compra, porque o saldo pode mudar entre o
    # carrinho e a finalização do pedido.

    result = await db.execute(
        select(CartItems).where(
            (CartItems.cart_id == cart.id)
            & (CartItems.look_id == dados.look_id)
        )
    )

    look_in_cart = result.scalar_one_or_none()

    if look_in_cart:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Look already exists in cart",
        )

    cart_item = CartItems(
        cart_id=cart.id,
        look_id=dados.look_id,
        quantity=dados.quantity,
    )

    db.add(cart_item)

    await db.commit()
    await db.refresh(cart_item)

    return cart_item


async def get_looks_user(db: AsyncSession,user_id: UUID) -> ListCartItemResponse:

    cart = await _get_cart_by_user(db, user_id)

    result = await db.execute(
        select(CartItems)
        .options(joinedload(CartItems.look))
        .where(CartItems.cart_id == cart.id)
    )

    cart_items = list(result.scalars().all())

    price_total = Decimal("0.00")

    for item in cart_items:
        item.price_quantity_total = (
            item.look.price * item.quantity
            if item.look.price
            else Decimal("0.00")
        )

        price_total += item.price_quantity_total

    return {
        "looks": cart_items,
        "price_total": price_total,
    }


async def delete_look_cart_user(
    db: AsyncSession,
    user_id: UUID,
    dados: DeleteLookCartItemUser,
) -> None:
    cart = await _get_cart_by_user(db, user_id)

    cart_item = await _get_cart_item(
        db,
        cart_id=cart.id,
        look_id=dados.look_id,
    )

    await db.delete(cart_item)
    await db.commit()


async def remove_quantity(db: AsyncSession, user_id: UUID, look_id: UUID, dados: CartItemsDelete) -> CartItems | None:

    cart = await _get_cart_by_user(db, user_id)


    cart_item = await _get_cart_item(
        db,
        cart_id=cart.id,
        look_id=look_id,
    )

    if dados.quantity > cart_item.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The quantity sent for removal cannot be greater "
                "than the current quantity."
            ),
        )

    cart_item.quantity -= dados.quantity

    if cart_item.quantity == 0:
        await db.delete(cart_item)
        await db.commit()
        return None

    await db.commit()
    await db.refresh(cart_item)

    return cart_item


async def add_quantity(db: AsyncSession, user_id: UUID, look_id: UUID, dados: CartItemsAddQuantity) -> CartItems:

    cart = await _get_cart_by_user(db, user_id)

    cart_item = await _get_cart_item(
        db,
        cart_id=cart.id,
        look_id=look_id,
    )

    # TODO(estoque): antes de somar, buscar o look (`_get_look`) e bloquear
    # com 400 se `cart_item.quantity + dados.quantity > look.stock_quantity`.
    cart_item.quantity += dados.quantity

    await db.commit()
    await db.refresh(cart_item)

    return cart_item