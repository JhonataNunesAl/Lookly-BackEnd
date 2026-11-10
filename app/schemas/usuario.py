from pydantic import BaseModel, EmailStr
from uuid import UUID

class UsuarioCreate(BaseModel):
    nome: str
    email: EmailStr
    senha: str
    estilos: str | None = None
    
class UsuarioLogin(BaseModel):
    email: EmailStr
    senha: str
    
class UsuarioResponse(BaseModel):
    id: UUID
    nome: str
    email: EmailStr

    class Config:
        from_attributes = True 

        
        