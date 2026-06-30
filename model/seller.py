from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from model.base import Base


class Seller(Base):
    """Vendedor/loja. Extensão do perfil para quem posta looks (marcas/empresas)."""

    __tablename__ = "sellers"

    id = Column(UUID, ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    store_name = Column(String, nullable=False)
    store_logo_url = Column(String, nullable=True)
    description = Column(String, nullable=True)
    store_url = Column(String, nullable=True)
    document_number = Column(String, nullable=True)  # CPF ou CNPJ
    rating = Column(Numeric(3, 2), default=0)
    total_reviews = Column(Integer, default=0)
    highlights = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
