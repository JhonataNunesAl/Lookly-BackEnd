import re
from uuid import UUID
from datetime import date, timedelta
from pydantic import BaseModel, Field, field_validator

# Aproximação de 18 anos (validação fina fica no CHECK do banco).
_MIN_AGE_DAYS = 18 * 365
# Espelha o CHECK de public.profiles.username em nem_schema.sql — validar
# aqui dá um 422 claro em vez de deixar a violação estourar como
# IntegrityError não tratada no commit (ver profile_service.update_me).
_USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,30}$")


class ProfileUpdate(BaseModel):
    """Campos editáveis do perfil (atualização parcial)."""

    username: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None
    bio: str | None = Field(None, max_length=300)  # espelha CHECK de profiles.bio
    birth_date: date | None = None

    @field_validator("username")
    @classmethod
    def formato_username(cls, v: str | None) -> str | None:
        if v is not None and not _USERNAME_RE.match(v):
            raise ValueError(
                "Usuário precisa ter 3-30 caracteres: letras minúsculas, números, _ ou ."
            )
        return v

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
