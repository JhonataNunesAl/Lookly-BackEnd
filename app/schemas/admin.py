"""Contratos das rotas /api/admin (painel de administração)."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Palavra que o painel pede para digitar antes de apagar algo. Conferida também
# no servidor: um clique sem querer (ou um script) não apaga nada.
CONFIRMACAO_EXCLUSAO = "APAGAR"

StatusConta = Literal["active", "suspended", "banned"]
StatusConteudo = Literal["draft", "active", "under_review", "removed"]
StatusDenuncia = Literal["open", "reviewing", "resolved", "rejected"]


class AdminMe(BaseModel):
    is_admin: bool = True
    user_id: UUID
    email: str


class Resumo(BaseModel):
    users: int
    users_blocked: int
    stores: int
    stores_inactive: int
    looks_active: int
    looks_total: int
    orders_paid: int
    orders_pending: int
    revenue_paid: Decimal
    reports_open: int
    new_users_7d: int


# ── usuários ──────────────────────────────────────────────────────────────────

class LojaResumida(BaseModel):
    id: UUID
    store_name: str
    status: str


class UsuarioAdmin(BaseModel):
    id: UUID
    username: str
    full_name: str | None = None
    email: str | None = None
    status: str
    created_at: datetime | None = None
    store: LojaResumida | None = None
    orders_count: int = 0
    is_admin: bool = False


class UsuariosResponse(BaseModel):
    items: list[UsuarioAdmin]
    total: int


class UsuarioUpdate(BaseModel):
    status: StatusConta | None = None
    full_name: str | None = Field(None, max_length=120)
    username: str | None = Field(None, pattern=r"^[a-zA-Z0-9_.]{3,30}$")


# ── lojas ─────────────────────────────────────────────────────────────────────

class LojaAdmin(BaseModel):
    id: UUID
    store_name: str
    store_slug: str
    store_logo_url: str | None = None
    description: str | None = None
    status: str
    created_at: datetime | None = None
    owner_id: UUID
    owner_username: str | None = None
    owner_email: str | None = None
    looks_count: int = 0
    items_sold: int = 0
    revenue: Decimal = Decimal("0")


class LojasResponse(BaseModel):
    items: list[LojaAdmin]
    total: int


class LojaUpdate(BaseModel):
    store_name: str | None = Field(None, min_length=2, max_length=80)
    description: str | None = Field(None, max_length=1000)
    status: StatusConteudo | None = None


# ── peças ─────────────────────────────────────────────────────────────────────

class PecaAdmin(BaseModel):
    id: UUID
    name: str
    photo: str | None = None
    price: Decimal | None = None
    stock_quantity: int = 0
    status: str
    created_at: datetime | None = None
    seller_id: UUID
    store_name: str | None = None
    category_name: str | None = None
    times_sold: int = 0


class PecasResponse(BaseModel):
    items: list[PecaAdmin]
    total: int


class PecaUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    price: Decimal | None = Field(None, ge=0, le=Decimal("99999999"))
    status: StatusConteudo | None = None


# ── pedidos ───────────────────────────────────────────────────────────────────

class ItemPedidoAdmin(BaseModel):
    look_id: UUID
    name: str
    store_name: str | None = None
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
    fulfillment_status: str | None = None


class PedidoAdmin(BaseModel):
    id: UUID
    created_at: datetime | None = None
    status: str
    payment_status: str
    total: Decimal
    buyer_id: UUID | None = None
    buyer_username: str | None = None
    buyer_email: str | None = None
    items: list[ItemPedidoAdmin]


class PedidosResponse(BaseModel):
    items: list[PedidoAdmin]
    total: int


# ── categorias ────────────────────────────────────────────────────────────────

class CategoriaAdmin(BaseModel):
    id: UUID
    name: str
    slug: str
    image_url: str | None = None
    is_active: bool
    sort_order: int
    looks_count: int = 0


class CategoriaCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    image_url: str | None = Field(None, max_length=500)
    sort_order: int = Field(0, ge=0, le=10000)


class CategoriaUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=60)
    image_url: str | None = Field(None, max_length=500)
    is_active: bool | None = None
    sort_order: int | None = Field(None, ge=0, le=10000)


# ── denúncias ─────────────────────────────────────────────────────────────────

class DenunciaAdmin(BaseModel):
    id: UUID
    target_type: str
    target_id: UUID
    target_label: str | None = None
    reason: str
    description: str | None = None
    contact_email: str | None = None
    status: str
    created_at: datetime | None = None
    reporter_username: str | None = None


class DenunciasResponse(BaseModel):
    items: list[DenunciaAdmin]
    total: int


class DenunciaUpdate(BaseModel):
    status: StatusDenuncia
