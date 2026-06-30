import uuid
from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from model.base import Base


class SavedLook(Base):
    """Armário: looks curtidos/salvos pelo usuário."""

    __tablename__ = "saved_looks"
    __table_args__ = (
        UniqueConstraint("user_id", "look_id", name="uq_saved_looks_user_look"),
    )

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    look_id = Column(UUID, ForeignKey("looks.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
