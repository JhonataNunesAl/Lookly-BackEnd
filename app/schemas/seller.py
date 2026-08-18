from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

# Espelham os CHECKs de public.sellers em nem_schema.sql — sem isso, um
# slug/nome fora do formato só falhava no commit (IntegrityError não
# tratada), e a mensagem de erro dizia "já está em uso" mesmo quando o
# problema era formato, não conflito (ver seller_service).
_SLUG_PATTERN = r"^[a-z0-9-]{3,50}$"


class SellerCreate(BaseModel):
    store_name: str = Field(min_length=2, max_length=80)
    store_slug: str = Field(pattern=_SLUG_PATTERN)
    store_logo_url: str | None = None
    description: str | None = None
    store_url: str | None = None


class SellerUpdate(BaseModel):
    store_name: str | None = Field(None, min_length=2, max_length=80)
    store_slug: str | None = Field(None, pattern=_SLUG_PATTERN)
    store_logo_url: str | None = None
    description: str | None = None
    store_url: str | None = None


class SellerResponse(BaseModel):
    id: UUID
    owner_profile_id: UUID
    store_name: str
    store_slug: str
    store_logo_url: str | None = None
    description: str | None = None
    store_url: str | None = None
    rating: Decimal | None = None
    total_reviews: int | None = None
    status: str

    class Config:
        from_attributes = True


class DocumentInput(BaseModel):
    """Número em claro, sobre HTTPS, para um endpoint já autenticado — o
    servidor cifra e faz o hash (ver core/crypto.py). O desenho anterior
    (`SellerDocument`, com `document_enc`/`document_hash` vindos do cliente)
    nunca teve implementação real de cifragem no app, então foi substituído:
    nenhuma tela chamava esse contrato, sem custo de migração.
    """

    document_number: str
    document_type: Literal["CPF", "CNPJ"]


class DocumentVerifyResponse(BaseModel):
    """Resposta de `POST /sellers/verify-document` — só uma prévia, não grava
    nada. Deixa a pessoa confirmar a razão social antes de seguir."""

    valid: bool
    active: bool | None = None
    legal_name: str | None = None
    message: str


class SellerSearchResponse(BaseModel):
    items: list[SellerResponse]
    next_cursor: str | None = None
