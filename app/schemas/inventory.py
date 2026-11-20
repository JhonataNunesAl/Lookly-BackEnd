"""Contratos da gestão de estoque da loja (`/api/inventory/*`)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from schemas.look import LookGestaoResponse

# ── itens ─────────────────────────────────────────────────────────────────────

Situacao = Literal["todos", "disponivel", "acabando", "esgotado", "reservado", "pausado", "parado"]
OrdemItens = Literal[
    "recentes", "antigos", "nome", "preco_asc", "preco_desc",
    "estoque_asc", "estoque_desc", "mais_vendidos", "parados",
]


class ItemEstoque(LookGestaoResponse):
    """Peça vista pela loja, com o que o estoque precisa: disponível, vendas e
    há quanto tempo está parada."""

    available_quantity: int = 0
    units_sold: int = 0
    revenue: Decimal = Decimal("0")
    last_sale_at: datetime | None = None
    days_without_sale: int | None = None
    collection_ids: list[UUID] = []


class ItensEstoqueResponse(BaseModel):
    items: list[ItemEstoque]
    total: int
    next_offset: int | None = None
    # Contagem por situação, para os chips de filtro (sem depender da página).
    counts: dict[str, int]


class StatusPeca(BaseModel):
    """Pausar (sai do feed, continua no estoque) ou reativar uma peça."""

    status: Literal["active", "draft"]


# ── movimentações ─────────────────────────────────────────────────────────────

TipoMovimento = Literal[
    "entrada", "venda_externa", "ajuste", "perda", "devolucao", "reserva", "liberacao",
]
Canal = Literal["instagram", "whatsapp", "loja_fisica", "feira", "site", "outro"]


class MovimentoCreate(BaseModel):
    """Uma mudança de estoque feita pela loja.

    `quantity` é sempre positivo; o tipo diz a direção. Em `ajuste`, `quantity`
    é o NOVO total contado (inventário), não a diferença.
    `venda_app` não aparece aqui: só o webhook do pagamento grava esse tipo.
    """

    kind: TipoMovimento
    quantity: int = Field(ge=0, le=100000)
    unit_price: Decimal | None = Field(None, ge=0)  # venda externa: por quanto vendeu
    channel: Canal | None = None
    note: str | None = Field(None, max_length=280)

    @model_validator(mode="after")
    def _quantidade(self):
        if self.kind != "ajuste" and self.quantity < 1:
            raise ValueError("A quantidade precisa ser pelo menos 1.")
        return self


class MovimentoOut(BaseModel):
    id: UUID
    look_id: UUID | None = None
    look_name: str
    kind: str
    quantity: int
    stock_after: int
    reserved_after: int
    unit_price: Decimal | None = None
    channel: str | None = None
    note: str | None = None
    order_id: UUID | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class MovimentoResultado(BaseModel):
    movement: MovimentoOut
    item: LookGestaoResponse


class MovimentosResponse(BaseModel):
    items: list[MovimentoOut]
    next_cursor: str | None = None


# ── vendas do app (pedidos a enviar) ──────────────────────────────────────────

Envio = Literal["pending", "shipped", "delivered"]


class ItemVenda(BaseModel):
    order_item_id: UUID
    look_id: UUID
    name: str
    photo: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
    fulfillment_status: str
    tracking_code: str | None = None
    shipped_at: datetime | None = None


class VendaApp(BaseModel):
    order_id: UUID
    created_at: datetime
    buyer_name: str | None = None
    shipping_address: dict
    payment_status: str
    order_status: str
    # Só as peças DESTA loja no pedido, e o total delas.
    items: list[ItemVenda]
    total: Decimal
    fulfillment_status: str


class VendasResponse(BaseModel):
    items: list[VendaApp]
    counts: dict[str, int]


class EnvioUpdate(BaseModel):
    fulfillment_status: Literal["shipped", "delivered"]
    tracking_code: str | None = Field(None, max_length=60)


# ── métricas ──────────────────────────────────────────────────────────────────

class PontoSerie(BaseModel):
    day: date
    revenue: Decimal
    units: int


class PecaMetrica(BaseModel):
    look_id: UUID
    name: str
    photo: str | None = None
    value: Decimal | int
    detail: str | None = None


class Metricas(BaseModel):
    period_days: int
    since: datetime
    # vendas no período
    revenue: Decimal
    revenue_prev: Decimal
    units_sold: int
    units_sold_prev: int
    sales_count: int
    avg_ticket: Decimal | None = None
    revenue_app: Decimal
    revenue_external: Decimal
    revenue_by_channel: dict[str, Decimal]
    gross_profit: Decimal | None = None  # só peças com custo informado
    revenue_with_cost: Decimal
    series: list[PontoSerie]
    # estoque agora
    pieces_total: int
    pieces_active: int
    pieces_paused: int
    units_in_stock: int
    units_reserved: int
    out_of_stock: int
    low_stock: int
    stock_value_price: Decimal
    stock_value_cost: Decimal
    pieces_without_cost: int
    # giro
    sell_through_pct: float | None = None
    avg_days_to_sell: float | None = None
    stale_count: int
    stale_days: int
    # engajamento
    views: int | None = None
    likes: int
    saves: int
    to_ship: int
    top_sold: list[PecaMetrica]
    top_viewed: list[PecaMetrica]
    stale: list[PecaMetrica]


# ── coleções da loja ──────────────────────────────────────────────────────────

class ColecaoCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str | None = Field(None, max_length=280)


class ColecaoUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=60)
    description: str | None = Field(None, max_length=280)
    sort_order: int | None = None


class ColecaoOut(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    sort_order: int = 0
    item_count: int = 0
    # Até 3 capas das peças, para a miniatura da coleção.
    covers: list[str] = []
    created_at: datetime | None = None


class ColecaoPecas(BaseModel):
    look_ids: list[UUID] = Field(min_length=1, max_length=500)


class ColecoesDaPeca(BaseModel):
    """Define em quais coleções a peça está (substitui a lista inteira)."""

    collection_ids: list[UUID] = Field(default_factory=list, max_length=100)
