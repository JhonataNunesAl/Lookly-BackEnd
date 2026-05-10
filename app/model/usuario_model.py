from sqlalchemy import Column, Integer, String, DateTime
from model.base import Base
from sqlalchemy.dialects.postgresql import UUID
import uuid

class Usuario(Base):
    __tablename__ = "usuarios"
    
    id         = Column(UUID, primary_key=True, default=uuid.uuid4)
    nome       = Column(String, nullable=False)
    email      = Column(String, unique=True, index=True, nullable=False)
    senha      = Column(String, nullable=False)
    estilos    = Column(String, nullable=True)