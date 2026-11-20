"""Pedidos: carrinho -> pedido -> pagamento no Mercado Pago -> pago.

Fluxo:
1. `checkout`: lê o carrinho, confere preço/estoque, grava endereço + pedido +
   itens (preço congelado no momento) e cria a preferência no Mercado Pago.
   O carrinho NÃO é esvaziado aqui: se a pessoa desistir na página de pagamento,
   ela volta e o carrinho continua lá.
2. `processar_notificacao` (webhook): relê o pagamento na API do Mercado Pago,
   confere valor e pedido, e só então marca como pago, baixa o estoque e esvazia
   o carrinho. É idempotente: a mesma notificação repetida não baixa estoque 2x.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from model.address import Address
from model.cart import Cart
from model.cart_items import CartItems
from model.look import Look
from model.orders import Order, OrderStatus, PaymentMethod, PaymentStatus
from model.orders_items import OrderItems
from schemas.order import CheckoutRequest, CheckoutResponse, OrderItemOut, OrderOut
from service import inventory_service, platform_fee_service
from service import mercadopago_service as mp

logger = logging.getLogger(__name__)

PREFIXO_PREF = "pref:"


async def checkout(db: AsyncSession, user_id: UUID, dados: CheckoutRequest) -> CheckoutResponse:
    cart = (await db.execute(select(Cart).where(Cart.user_id == user_id))).scalar_one_or_none()
    linhas = []
    if cart:
        linhas = (
            await db.execute(
                select(CartItems, Look).join(Look, Look.id == CartItems.look_id).where(CartItems.cart_id == cart.id)
            )
        ).all()
    if not linhas:
        raise HTTPException(status_code=400, detail="Seu carrinho está vazio.")

    total = Decimal("0")
    itens_mp: list[dict] = []
    itens_pedido: list[tuple[Look, int, Decimal]] = []
    for item, look in linhas:
        if look.price is None:
            raise HTTPException(status_code=400, detail=f'"{look.name}" está sem preço e não pode ser comprado.')
        if look.status != "active":
            raise HTTPException(status_code=400, detail=f'"{look.name}" não está mais disponível.')
        # Unidades reservadas pela loja (ex.: separadas para alguém no Instagram)
        # continuam no estoque, mas não estão à venda no app.
        disponivel = max((look.stock_quantity or 0) - (look.reserved_quantity or 0), 0)
        if disponivel < item.quantity:
            restam = disponivel
            raise HTTPException(
                status_code=400,
                detail=f'Estoque insuficiente para "{look.name}" (restam {restam}).',
            )
        preco = Decimal(look.price)
        total += preco * item.quantity
        itens_pedido.append((look, item.quantity, preco))
        itens_mp.append(
            {
                "id": look.id,
                "title": look.name,
                "quantity": item.quantity,
                "unit_price": preco,
                "picture_url": (look.photos or [None])[0],
            }
        )

    end = dados.address
    order_id = uuid4()
    endereco = Address(
        user_id=user_id,
        # `nickname` é UNIQUE na tabela inteira; um por pedido evita colisão entre pessoas.
        nickname=f"pedido-{order_id}",
        street=end.street,
        number=end.number,
        complement=end.complement or "",
        district=end.district,
        city=f"{end.city}/{end.state.upper()}",
        postal_code=end.postal_code,
        is_default=False,
    )
    db.add(endereco)
    await db.flush()

    pedido = Order(
        id=order_id,
        user_id=user_id,
        address_id=endereco.id,
        status=OrderStatus.PENDING,
        payment_method=PaymentMethod.PIX,  # trocado pelo método real quando o pagamento chega
        payment_status=PaymentStatus.PENDING,
        total_amount=total,
        discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        shipping_address=end.model_dump(),
    )
    db.add(pedido)
    for look, qtd, preco in itens_pedido:
        db.add(OrderItems(order_id=order_id, look_id=look.id, quantity=qtd, unit_price=preco, subtotal=preco * qtd))
    await db.flush()

    pref_id, url = await mp.criar_preferencia(order_id=str(order_id), itens=itens_mp, email_comprador=None)
    pedido.transaction_id = PREFIXO_PREF + pref_id
    await db.commit()
    return CheckoutResponse(order_id=order_id, total=total, payment_url=url)


def _para_saida(pedido: Order) -> OrderOut:
    # Pendente ou recusado: a mesma preferência aceita uma nova tentativa de pagamento.
    pendente = pedido.status == OrderStatus.PENDING and pedido.payment_status in (
        PaymentStatus.PENDING,
        PaymentStatus.REFUSED,
    )
    pref = pedido.transaction_id or ""
    return OrderOut(
        id=pedido.id,
        status=pedido.status.value,
        payment_status=pedido.payment_status.value,
        total=pedido.total_amount,
        shipping_address=pedido.shipping_address or {},
        created_at=pedido.created_at,
        items=[
            OrderItemOut(
                look_id=i.look_id,
                name=i.look.name if i.look else "Peça",
                photo=(i.look.photos or [""])[0] if i.look else "",
                quantity=i.quantity,
                unit_price=i.unit_price,
                subtotal=i.subtotal,
            )
            for i in pedido.items
        ],
        payment_url=mp.url_de_pagamento(pref[len(PREFIXO_PREF):]) if pendente and pref.startswith(PREFIXO_PREF) else None,
    )


def _consulta_pedidos():
    return select(Order).options(selectinload(Order.items).selectinload(OrderItems.look))


async def listar(db: AsyncSession, user_id: UUID) -> list[OrderOut]:
    pedidos = (
        await db.execute(_consulta_pedidos().where(Order.user_id == user_id).order_by(Order.created_at.desc()))
    ).scalars().all()
    return [_para_saida(p) for p in pedidos]


async def obter(db: AsyncSession, user_id: UUID, order_id: UUID) -> OrderOut:
    pedido = (
        await db.execute(_consulta_pedidos().where(Order.id == order_id, Order.user_id == user_id))
    ).scalar_one_or_none()
    if not pedido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado")
    return _para_saida(pedido)


async def _registrar_venda_no_historico(db: AsyncSession, look: Look, item: OrderItems, order_id: UUID) -> None:
    """Linha `venda_app` no histórico de estoque da loja. Num SAVEPOINT e sem
    deixar o erro subir: o histórico nunca pode impedir um pagamento aprovado de
    ser registrado (a baixa de estoque e o pedido pago são o que importa)."""
    try:
        async with db.begin_nested():
            db.add(
                inventory_service.novo_movimento(
                    look, "venda_app", -item.quantity, unit_price=item.unit_price, order_id=order_id
                )
            )
    except Exception:  # noqa: BLE001
        logger.warning("Não foi possível registrar a venda do pedido %s no histórico de estoque", order_id, exc_info=True)


_METODO = {
    "credit_card": PaymentMethod.CREDIT_CARD,
    "debit_card": PaymentMethod.DEBIT_CARD,
    "prepaid_card": PaymentMethod.DEBIT_CARD,
    "bank_transfer": PaymentMethod.PIX,
    "account_money": PaymentMethod.PIX,
}


async def processar_notificacao(db: AsyncSession, payment_id: str) -> None:
    pagamento = await mp.buscar_pagamento(payment_id)
    ref = pagamento.get("external_reference")
    try:
        order_id = UUID(str(ref))
    except (TypeError, ValueError):
        logger.warning("Pagamento %s sem pedido válido em external_reference", payment_id)
        return

    pedido = (
        await db.execute(
            select(Order).options(selectinload(Order.items)).where(Order.id == order_id).with_for_update()
        )
    ).scalar_one_or_none()
    if not pedido:
        logger.warning("Pagamento %s aponta para pedido inexistente %s", payment_id, order_id)
        return

    situacao = pagamento.get("status")
    pago = Decimal(str(pagamento.get("transaction_amount") or "0"))

    if situacao == "approved":
        if pedido.payment_status == PaymentStatus.APPROVED:
            return  # notificação repetida
        if pago < pedido.total_amount:
            logger.error("Pagamento %s menor que o pedido %s (%s < %s)", payment_id, order_id, pago, pedido.total_amount)
            return
        pedido.payment_status = PaymentStatus.APPROVED
        pedido.status = OrderStatus.PAID
        pedido.transaction_id = str(payment_id)
        pedido.payment_method = _METODO.get(pagamento.get("payment_type_id"), pedido.payment_method)
        vendidos: list[tuple[OrderItems, UUID | None]] = []
        for item in pedido.items:
            look = await db.get(Look, item.look_id, with_for_update=True)
            vendidos.append((item, look.seller_id if look is not None else None))
            if look is not None:
                look.stock_quantity = max((look.stock_quantity or 0) - item.quantity, 0)
                look.reserved_quantity = min(look.reserved_quantity or 0, look.stock_quantity)
                await _registrar_venda_no_historico(db, look, item, pedido.id)
        # Taxa da plataforma congelada no momento da venda (0% na demo).
        await platform_fee_service.congelar_taxas(db, vendidos, datetime.now(timezone.utc))
        cart = (await db.execute(select(Cart).where(Cart.user_id == pedido.user_id))).scalar_one_or_none()
        if cart:
            comprados = [i.look_id for i in pedido.items]
            await db.execute(
                delete(CartItems).where(CartItems.cart_id == cart.id, CartItems.look_id.in_(comprados))
            )
    elif situacao in ("rejected", "cancelled"):
        if pedido.payment_status != PaymentStatus.APPROVED:
            pedido.payment_status = PaymentStatus.REFUSED
    elif situacao in ("refunded", "charged_back"):
        pedido.payment_status = PaymentStatus.REFUNDED
        pedido.status = OrderStatus.CANCELED
    # pending / in_process / authorized: continua pendente.
    await db.commit()
