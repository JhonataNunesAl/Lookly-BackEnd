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
    look_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("looks.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(default=1)
    look = relationship(
    "Look",
    back_populates="cart_items"
)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default= func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
