from uuid import UUID
from datetime import date, timedelta
from pydantic import BaseModel, field_validator

# Aproximação de 18 anos (validação fina fica no CHECK do banco).
_MIN_AGE_DAYS = 18 * 365


class ProfileUpdate(BaseModel):
    """Campos editáveis do perfil (atualização parcial)."""

    username: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    birth_date: date | None = None

    @field_validator("birth_date")
    @classmethod
    def maior_de_idade(cls, v: date | None) -> date | None:
        if v is not None and v > date.today() - timedelta(days=_MIN_AGE_DAYS):
            raise ValueError("É necessário ter 18 anos ou mais.")
        return v


class ProfileResponse(BaseModel):
    id: UUID
    username: str
    full_name: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    birth_date: date | None = None
    status: str
    # Papel resolvido no servidor — nunca declarado pelo cliente.
    is_seller: bool = False
    seller_id: UUID | None = None

    class Config:
        from_attributes = True


class CategoryAffinityResponse(BaseModel):
    """Um item do placar de afinidade — ver `user_category_affinity`.

    Só leitura: quem escreve são os gatilhos no banco (curtir/salvar), nunca
    o service diretamente.
    """

    category_id: UUID
    category_name: str
    score: int
