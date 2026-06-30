from sqlalchemy import Column, String, Integer, Numeric, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from model.base import Base


class Profile(Base):
    """Perfil do usuário. id == auth.users.id (gerenciado pelo Supabase Auth)."""

    __tablename__ = "profiles"

    id = Column(UUID, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    full_body_photo_url = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    weight_kg = Column(Numeric(5, 2), nullable=True)
    height_cm = Column(Integer, nullable=True)
    body_measurements = Column(JSONB, nullable=True)
    # Preferências básicas de estilo (ex.: ["gótica", "streetwear"]).
    style_preferences = Column(ARRAY(String), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
