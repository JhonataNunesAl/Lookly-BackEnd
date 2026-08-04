import uuid
from .base import Base
from sqlalchemy import UUID, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

class Address(Base):
    __tablename__ = "address"

    id: Mapped[uuid.UUID] = mapped_column(UUID, default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    nickname: Mapped[str] = mapped_column(unique= True)
    street: Mapped[str] = mapped_column()
    number: Mapped[str] = mapped_column()
    complement: Mapped[str] = mapped_column()  
    district: Mapped[str] = mapped_column()
    city: Mapped[str] = mapped_column()
    postal_code: Mapped[str] = mapped_column()
    is_default: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default= func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    order = relationship("Orders", back_populates= "orders")
