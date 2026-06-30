from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, field_validator


class LookCreate(BaseModel):
    category_id: UUID  # categoria obrigatória
    photos: list[str]
    videos: list[str] | None = None
    description: str | None = None
    buy_link: str | None = None

    @field_validator("photos")
    @classmethod
    def validar_fotos(cls, v: list[str]) -> list[str]:
        if not 1 <= len(v) <= 6:
            raise ValueError("Um look deve ter de 1 a 6 fotos.")
        return v

    @field_validator("videos")
    @classmethod
    def validar_videos(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) > 2:
            raise ValueError("Um look pode ter no máximo 2 vídeos.")
        return v


class LookUpdate(BaseModel):
    category_id: UUID | None = None
    photos: list[str] | None = None
    videos: list[str] | None = None
    description: str | None = None
    buy_link: str | None = None

    @field_validator("photos")
    @classmethod
    def validar_fotos(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and not 1 <= len(v) <= 6:
            raise ValueError("Um look deve ter de 1 a 6 fotos.")
        return v

    @field_validator("videos")
    @classmethod
    def validar_videos(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) > 2:
            raise ValueError("Um look pode ter no máximo 2 vídeos.")
        return v


class LookResponse(BaseModel):
    id: UUID
    category_id: UUID
    creator_id: UUID | None = None
    photos: list[str]
    videos: list[str] | None = None
    description: str | None = None
    buy_link: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class FeedResponse(BaseModel):
    items: list[LookResponse]
    next_cursor: str | None = None
