from sqlalchemy import Column, String, Date, DateTime, func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from .base import Base
from .enums import account_status


class Profile(Base):
    """Perfil do usuário — só dado público. id == auth.users.id.

    Dados corporais (peso, altura, medidas, foto de corpo) ficam em
    body_profiles, com RLS restrita ao dono.
    """

    __tablename__ = "profiles"

    id = Column(UUID, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    # Idade é derivada de birth_date, nunca guardada como número (não envelhece).
    birth_date = Column(Date, nullable=False)
    status = Column(account_status(), nullable=False, server_default="active")
    orders = relationship(
    "Order",
    back_populates="user"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
