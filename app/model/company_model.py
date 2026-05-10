from uuid import uuid4
from sqlalchemy import Column, String
from model.base import Base
from sqlalchemy.dialects.postgresql import UUID


class Company(Base):
    __tablename__ = "companies"
    
    id = Column(UUID, primary_key=True, default=uuid4)
    nome = Column(String, nullable=False)
    CNPJ = Column(String, unique=True, index=True, nullable=False)
    senha = Column(String, nullable=False)
    descricao = Column(String, nullable=True)
    segmento = Column(String, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    logo = Column(String, nullable=True)
    