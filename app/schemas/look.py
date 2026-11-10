from uuid import UUID
from decimal import Decimal
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


# Tamanhos aceitos — espelhado em lookly-front/src/utils/tamanhos.ts. Lista fechada
# de propósito: com texto livre ("m", "M ", "medio") o filtro por tamanho nunca casa.
TAMANHOS_LETRAS = ["PP", "P", "M", "G", "GG", "XG"]
TAMANHOS_NUMEROS = [str(n) for n in range(33, 49)]  # calçado (33–44) e roupa (34–48)
TAMANHO_UNICO = "Único"
TAMANHOS_VALIDOS = TAMANHOS_LETRAS + TAMANHOS_NUMEROS + [TAMANHO_UNICO]
_CANONICO = {t.upper(): t for t in TAMANHOS_VALIDOS} | {"UNICO": TAMANHO_UNICO}
MAX_TAMANHOS = 12


def normalizar_tamanhos(v: list[str] | None) -> list[str] | None:
    """Aceita caixa/acento diferentes ("m", "unico"), devolve a forma canônica,
    sem repetidos e na ordem canônica. Valor desconhecido é erro (422)."""
    if v is None:
        return v
    achados: set[str] = set()
    for t in v:
        canonico = _CANONICO.get(str(t).strip().upper())
        if canonico is None:
            raise ValueError(f"Tamanho inválido: {t!r}. Use: {', '.join(TAMANHOS_VALIDOS)}.")
        achados.add(canonico)
    if len(achados) > MAX_TAMANHOS:
        raise ValueError(f"No máximo {MAX_TAMANHOS} tamanhos por peça.")
    return [t for t in TAMANHOS_VALIDOS if t in achados]


def _validar_fotos(v: list[str]) -> list[str]:
    if not 1 <= len(v) <= 6:
        raise ValueError("Um look deve ter de 1 a 6 fotos.")
    return v


def _validar_videos(v: list[str] | None) -> list[str] | None:
    if v is not None and len(v) > 2:
        raise ValueError("Um look pode ter no máximo 2 vídeos.")
    return v


class LookCreate(BaseModel):
    category_id: UUID  # categoria obrigatória
    # min/max espelham o CHECK de public.looks.name em nem_schema.sql —
    # sem isso, um nome fora da faixa só falhava no commit (IntegrityError
    # não tratada = 500 genérico, ver look_service.create_look).
    name: str = Field(min_length=2, max_length=120)
    photos: list[str]
    videos: list[str] = []
    description: str | None = None
    # ge=0 espelha o CHECK de public.looks.price — mesma lógica do name acima.
    price: Decimal | None = Field(None, ge=0)
    buy_link: str | None = None
    stock_quantity: int = Field(0, ge=0)
    sizes: list[str] = []

    _fotos = field_validator("photos")(_validar_fotos)
    _videos = field_validator("videos")(_validar_videos)
    _tamanhos = field_validator("sizes")(normalizar_tamanhos)


class LookUpdate(BaseModel):
    category_id: UUID | None = None
    name: str | None = Field(None, min_length=2, max_length=120)
    photos: list[str] | None = None
    videos: list[str] | None = None
    description: str | None = None
    price: Decimal | None = Field(None, ge=0)
    buy_link: str | None = None
    stock_quantity: int | None = Field(None, ge=0)
    sizes: list[str] | None = None

    _tamanhos = field_validator("sizes")(normalizar_tamanhos)

    @field_validator("photos")
    @classmethod
    def _fotos(cls, v: list[str] | None) -> list[str] | None:
        return _validar_fotos(v) if v is not None else v

    _videos = field_validator("videos")(_validar_videos)


class LookResponse(BaseModel):
    id: UUID
    seller_id: UUID
    category_id: UUID
    name: str
    description: str | None = None
    photos: list[str]
    videos: list[str] = []
    price: Decimal | None = None
    buy_link: str | None = None
    stock_quantity: int = 0
    sizes: list[str] = []
    likes_count: int = 0
    saves_count: int = 0
    status: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class FeedResponse(BaseModel):
    items: list[LookResponse]
    next_cursor: str | None = None


# ── filtros da busca (GET /looks/search) ───────────────────────────────────────

OrdemBusca = Literal["recent", "price_asc", "price_desc", "popular"]


class LookFiltros(BaseModel):
    """Filtros e ordenação da busca de looks. Tudo opcional: sem nenhum, a busca
    é a de sempre (mais recentes primeiro)."""

    price_min: Decimal | None = Field(None, ge=0)
    price_max: Decimal | None = Field(None, ge=0)
    # Casa se a peça tem QUALQUER um dos tamanhos pedidos.
    sizes: list[str] = []
    in_stock: bool = False
    sort: OrdemBusca = "recent"

    _tamanhos = field_validator("sizes")(normalizar_tamanhos)

    @model_validator(mode="after")
    def _faixa_de_preco(self):
        if self.price_min is not None and self.price_max is not None and self.price_min > self.price_max:
            raise ValueError("O preço mínimo não pode ser maior que o máximo.")
        return self

    @property
    def ativo(self) -> bool:
        return bool(
            self.price_min is not None or self.price_max is not None or self.sizes or self.in_stock
        )
