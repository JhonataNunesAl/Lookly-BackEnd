from uuid import UUID
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


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

    _fotos = field_validator("photos")(_validar_fotos)
    _videos = field_validator("videos")(_validar_videos)


class LookUpdate(BaseModel):
    category_id: UUID | None = None
    name: str | None = Field(None, min_length=2, max_length=120)
    photos: list[str] | None = None
    videos: list[str] | None = None
    description: str | None = None
    price: Decimal | None = Field(None, ge=0)
    buy_link: str | None = None
    stock_quantity: int | None = Field(None, ge=0)

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
    likes_count: int = 0
    saves_count: int = 0
    status: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class FeedResponse(BaseModel):
    items: list[LookResponse]
    next_cursor: str | None = None
