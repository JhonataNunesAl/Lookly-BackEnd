import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class Collection(Base):
    """Pasta/coleção do guarda-roupa (ex.: "Looks pro Lollapalooza")."""

    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_collections_user_name"),)

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String, nullable=False)
    cover_url = Column(String, nullable=True)
    is_public = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class CollectionItem(Base):
    """Look pertencente a uma coleção."""

    __tablename__ = "collection_items"

    collection_id = Column(
        UUID, ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    look_id = Column(
        UUID, ForeignKey("looks.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
