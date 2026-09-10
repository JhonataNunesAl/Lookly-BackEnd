import sqlalchemy as sa

import uuid
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import UUID, ForeignKey, Numeric, DateTime, func
from enum import Enum
from decimal import Decimal
from datetime import datetime



class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELED = "canceled"


class PaymentMethod(str, Enum):
    PIX = "pix"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REFUSED = "refused"
    REFUNDED = "refunded"
    

class Order(Base):
    __tablename__= "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID, default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey('profiles.id', ondelete='CASCADE'))
    address_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey('address.id', ondelete='CASCADE'))
    status: Mapped[OrderStatus] = mapped_column(sa.Enum(OrderStatus), default= OrderStatus.PENDING, nullable= False)
    payment_method: Mapped[PaymentMethod] = mapped_column(sa.Enum(PaymentMethod), default= PaymentMethod.PIX, nullable= False)
    payment_status: Mapped[PaymentStatus] = mapped_column(sa.Enum(PaymentStatus), default= PaymentStatus.PENDING, nullable= False)
    transaction_id: Mapped[str] = mapped_column(nullable= True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    shipping_address: Mapped[dict] = mapped_column(JSONB, nullable=False)    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default= func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    user = relationship("Profile",  back_populates="orders")
    address = relationship(
    "Address",
    back_populates="orders"
)   
    items = relationship(
    "OrderItems",
    back_populates="order"
)
