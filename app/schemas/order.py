from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class EnderecoEntrega(BaseModel):
    """Endereço digitado no checkout. Vai para `address` e, como foto do momento,
    para `orders.shipping_address` (o pedido não muda se a pessoa editar depois)."""

    street: str = Field(min_length=2, max_length=200)
    number: str = Field(min_length=1, max_length=20)
    complement: str = Field(default="", max_length=120)
    district: str = Field(min_length=2, max_length=120)
    city: str = Field(min_length=2, max_length=120)
    state: str = Field(min_length=2, max_length=2)
    postal_code: str = Field(min_length=8, max_length=9, pattern=r"^\d{5}-?\d{3}$")


class CheckoutRequest(BaseModel):
    address: EnderecoEntrega


class CheckoutResponse(BaseModel):
    order_id: UUID
    total: Decimal
    # Página de pagamento do Mercado Pago (Pix, cartão, boleto). O app só abre a URL.
    payment_url: str


class OrderItemOut(BaseModel):
    look_id: UUID
    name: str
    photo: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


class OrderOut(BaseModel):
    id: UUID
    status: str
    payment_status: str
    total: Decimal
    shipping_address: dict
    created_at: datetime
    items: list[OrderItemOut]
    # Só para pedido ainda pendente: retomar o pagamento.
    payment_url: str | None = None
