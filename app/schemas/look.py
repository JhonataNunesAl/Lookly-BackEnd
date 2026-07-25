from uuid import UUID
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, field_validator


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
    name: str
    photos: list[str]
    videos: list[str] = []
    description: str | None = None
    price: Decimal | None = None
    buy_link: str | None = None

    _fotos = field_validator("photos")(_validar_fotos)
    _videos = field_validator("videos")(_validar_videos)


class LookUpdate(BaseModel):
    category_id: UUID | None = None
    name: str | None = None
    photos: list[str] | None = None
    videos: list[str] | None = None
    description: str | None = None
    price: Decimal | None = None
    buy_link: str | None = None

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
    likes_count: int = 0
    saves_count: int = 0
    status: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class FeedResponse(BaseModel):
    items: list[LookResponse]
    next_cursor: str | None = None
