import uuid
from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from model.base import Base
from model.enums import content_status


class Look(Base):
    """Conteúdo do feed E o produto. Publicado por uma loja (seller_id).

    Regras de mídia (1–6 fotos, ≤2 vídeos) também são CHECK no banco, não só
    validação no Pydantic. Contadores (likes_count, saves_count) são cache
    mantido por gatilhos/funções — nunca fonte de verdade.
    """

    __tablename__ = "looks"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    seller_id = Column(
        UUID, ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False
    )
    category_id = Column(
        UUID, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    photos = Column(ARRAY(String), nullable=False)
    videos = Column(ARRAY(String), nullable=False, server_default="{}")
    price = Column(Numeric(10, 2), nullable=True)
    buy_link = Column(String, nullable=True)
    likes_count = Column(Integer, nullable=False, server_default="0")
    saves_count = Column(Integer, nullable=False, server_default="0")
    status = Column(content_status(), nullable=False, server_default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())