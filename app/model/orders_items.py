import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Numeric, DateTime, func, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class OrderItems(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        primary_key=True,
        default=uuid.uuid4
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False
    )

    look_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey("looks.id", ondelete="CASCADE"),
        nullable=False
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False
    )

    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relacionamentos
    order = relationship("Order", back_populates="items")

    look = relationship(
        "Look",
        back_populates="order_items"
    )   