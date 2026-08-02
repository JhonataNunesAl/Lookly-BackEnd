from .base import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Uuid, ForeignKey, func, DateTime
from datetime import datetime

import uuid


class Cart(Base):
    __tablename__ = 'cart'

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey('profiles.id', ondelete='CASCADE'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default= func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default= func.now(), onupdate= func.now())


