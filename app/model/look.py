import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from model.base import Base


class Look(Base):
    """Conteúdo do feed. Pertence a uma categoria e é criado por um seller."""

    __tablename__ = "looks"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    category_id = Column(
        UUID, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    creator_id = Column(UUID, ForeignKey("sellers.id", ondelete="CASCADE"))
    # Regra de negócio (validada na API): 1 a 6 fotos, até 2 vídeos.
    photos = Column(ARRAY(String), nullable=False)
    videos = Column(ARRAY(String), nullable=True)
    description = Column(String, nullable=True)
    buy_link = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
