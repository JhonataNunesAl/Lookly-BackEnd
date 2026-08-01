from sqlalchemy import Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class SavedLook(Base):
    """Guarda-roupa: salvar é um gesto DELIBERADO, separado da curtida.

    saves_count em looks é mantido por gatilho no banco (sync_save_count).
    """

    __tablename__ = "saved_looks"

    user_id = Column(
        UUID, ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    look_id = Column(
        UUID, ForeignKey("looks.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
