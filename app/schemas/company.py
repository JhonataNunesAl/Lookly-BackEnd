from pydantic import BaseModel, EmailStr
from uuid import UUID


class CompanyCreate(BaseModel):
    nome: str
    CNPJ: str
    senha: str
    descricao: str | None = None
    segmento: str | None = None
    email: EmailStr
    logo: str | None = None
    
    
class CompanyResponse(BaseModel):
    id: UUID
    nome: str
    CNPJ: str
    descricao: str | None = None
    segmento: str | None = None
    email: EmailStr
    logo: str | None = None

    class Config:
        from_attributes = True
        
        
class CompanyLogin(BaseModel):
    email: EmailStr
    senha: str
    