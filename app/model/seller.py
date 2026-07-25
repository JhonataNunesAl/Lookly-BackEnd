import uuid
from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from model.base import Base
from model.enums import content_status, store_role


class Seller(Base):
    """Loja. `owner_profile_id` é separado do `id`: a loja não É o usuário —
    ela tem dono (transferível) e pode ter equipe (store_members).
    """

    __tablename__ = "sellers"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    owner_profile_id = Column(
        UUID,
        ForeignKey("profiles.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    store_name = Column(String, nullable=False)
    store_slug = Column(String, unique=True, nullable=False)
    store_logo_url = Column(String, nullable=True)
    description = Column(String, nullable=True)
    store_url = Column(String, nullable=True)
    rating = Column(Numeric(3, 2), nullable=False, server_default="0")
    total_reviews = Column(Integer, nullable=False, server_default="0")
    highlights = Column(JSONB, nullable=False, server_default="[]")
    status = Column(content_status(), nullable=False, server_default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class SellerPrivate(Base):
    """Documento fiscal do vendedor — ciphertext + hash de lookup."""

    __tablename__ = "sellers_private"

    seller_id = Column(
        UUID, ForeignKey("sellers.id", ondelete="CASCADE"), primary_key=True
    )
    document_enc = Column(String, nullable=False)
    document_hash = Column(String, unique=True, nullable=False)
    document_type = Column(String, nullable=False)  # 'CPF' | 'CNPJ'
    verified_at = Column(DateTime(timezone=True), nullable=True)
    payout_provider_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class StoreMember(Base):
    """Equipe da loja. Substitui a ideia de 'senha da loja': acesso é um papel."""

    __tablename__ = "store_members"

    seller_id = Column(
        UUID, ForeignKey("sellers.id", ondelete="CASCADE"), primary_key=True
    )
    profile_id = Column(
        UUID, ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    role = Column(store_role(), nullable=False, server_default="staff")  # owner|manager|staff
    created_at = Column(DateTime(timezone=True), server_default=func.now())
