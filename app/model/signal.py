from sqlalchemy import Column, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from .base import Base
from .enums import swipe_direction


class LookLike(Base):
    """Curtida (swipe RIGHT). Volume baixo, valor permanente."""

    __tablename__ = "look_likes"

    user_id = Column(
        UUID, ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    look_id = Column(
        UUID, ForeignKey("looks.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LookView(Base):
    """Todo swipe (RIGHT/LEFT). Volume enorme, valor efêmero.

    Tabela particionada por mês no banco (sem FK, por custo de escrita).
    Usada pelo feed para excluir looks que o usuário já viu.
    """

    __tablename__ = "look_views"

    user_id = Column(UUID, primary_key=True)
    look_id = Column(UUID, primary_key=True)
    direction = Column(swipe_direction(), nullable=False)  # 'RIGHT' | 'LEFT'
    created_at = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())


class UserCategoryAffinity(Base):
    """Placar de afinidade por categoria — fundação do algoritmo de feed.

    Só leitura pela aplicação: quem escreve são os gatilhos
    `trg_affinity_like`/`trg_affinity_save` (SECURITY DEFINER) em
    `look_likes`/`saved_looks`. Nenhum service escreve aqui diretamente.
    """

    __tablename__ = "user_category_affinity"

    user_id = Column(
        UUID, ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    category_id = Column(
        UUID, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )
    score = Column(Integer, nullable=False, server_default="0")
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
