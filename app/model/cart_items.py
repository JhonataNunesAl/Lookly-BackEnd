from .base import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from decimal import Decimal
from sqlalchemy import func, ForeignKey, UUID
from sqlalchemy import DateTime, Numeric
import uuid


class CartItems(Base):
    __tablename__ = 'cart_items'
    id: Mapped[uuid.UUID] = mapped_column(UUID, default=uuid.uuid4, primary_key=True)
    cart_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cart.id", ondelete='CASCADE'))
    # ATENÇÃO: `unique=True` aqui torna look_id único NA TABELA INTEIRA, não
    # por carrinho — depois que UMA pessoa adiciona este look ao carrinho,
    # mais ninguém consegue adicionar o mesmo look ao próprio carrinho (o
    # INSERT de outro usuário viola essa constraint). Provável correção:
    # trocar por um UniqueConstraint(cart_id, look_id) a nível de tabela.
    look_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("looks.id", ondelete="CASCADE"), unique=True)
    quantity: Mapped[int] = mapped_column(default=1)
    look = relationship(
    "Look",
    back_populates="cart_items"
)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default= func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
