from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel


class SellerCreate(BaseModel):
    store_name: str
    store_logo_url: str | None = None
    description: str | None = None
    store_url: str | None = None
    document_number: str | None = None  # CPF ou CNPJ


class SellerUpdate(BaseModel):
    store_name: str | None = None
    store_logo_url: str | None = None
    description: str | None = None
    store_url: str | None = None
    document_number: str | None = None


class SellerResponse(BaseModel):
    id: UUID
    store_name: str
    store_logo_url: str | None = None
    description: str | None = None
    store_url: str | None = None
    document_number: str | None = None
    rating: Decimal | None = None
    total_reviews: int | None = None

    class Config:
        from_attributes = True
