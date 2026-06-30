import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from model.base import Base


class Swipe(Base):
    """Registro de swipe. RIGHT = curtir/salvar, LEFT = descartar."""

    __tablename__ = "swipes"
    __table_args__ = (UniqueConstraint("user_id", "look_id", name="uq_swipes_user_look"),)

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    look_id = Column(UUID, ForeignKey("looks.id", ondelete="CASCADE"), nullable=False)
    direction = Column(String, nullable=False)  # 'RIGHT' | 'LEFT'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
