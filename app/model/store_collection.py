import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class StoreCollection(Base):
    """Coleção da LOJA: um conjunto de peças com nome livre, criado pelo lojista
    para se organizar (ex.: "Roupas sessão de carnaval", "Lote da feira").

    Diferente de `collections`, que são as pastas do armário de quem compra.
    Uma peça pode estar em várias coleções.
    """

    __tablename__ = "store_collections"
    __table_args__ = (UniqueConstraint("seller_id", "name", name="uq_store_collections_seller_name"),)

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID, ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StoreCollectionItem(Base):
    __tablename__ = "store_collection_items"

    collection_id = Column(UUID, ForeignKey("store_collections.id", ondelete="CASCADE"), primary_key=True)
    look_id = Column(UUID, ForeignKey("looks.id", ondelete="CASCADE"), primary_key=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
