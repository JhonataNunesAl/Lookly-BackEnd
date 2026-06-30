from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field


class ProfileUpdate(BaseModel):
    """Campos editáveis do perfil. Todos opcionais (atualização parcial)."""

    username: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None
    full_body_photo_url: str | None = None
    age: int | None = Field(default=None, ge=18)
    weight_kg: Decimal | None = None
    height_cm: int | None = None
    body_measurements: dict | None = None
    style_preferences: list[str] | None = None


class ProfileResponse(BaseModel):
    id: UUID
    username: str
    full_name: str | None = None
    avatar_url: str | None = None
    full_body_photo_url: str | None = None
    age: int | None = None
    weight_kg: Decimal | None = None
    height_cm: int | None = None
    body_measurements: dict | None = None
    style_preferences: list[str] | None = None

    class Config:
        from_attributes = True
