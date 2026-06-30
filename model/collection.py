import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from model.base import Base


class Collection(Base):
    """Pasta/coleção do armário (ex.: "Looks pro Lollapalooza")."""

    __tablename__ = "collections"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CollectionItem(Base):
    """Look pertencente a uma coleção."""

    __tablename__ = "collection_items"
    __table_args__ = (
        UniqueConstraint(
            "collection_id", "look_id", name="uq_collection_items_collection_look"
        ),
    )

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    collection_id = Column(
        UUID, ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    look_id = Column(UUID, ForeignKey("looks.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
