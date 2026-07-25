from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel


class SellerCreate(BaseModel):
    store_name: str
    store_slug: str
    store_logo_url: str | None = None
    description: str | None = None
    store_url: str | None = None


class SellerUpdate(BaseModel):
    store_name: str | None = None
    store_slug: str | None = None
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
