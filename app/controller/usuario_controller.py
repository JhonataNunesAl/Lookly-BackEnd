from fastapi import APIRouter, Depends, HTTPException, status
from schemas.usuario import UsuarioCreate, UsuarioLogin, UsuarioResponse
from service import usuario_service
from dependencies.auth import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db

router = APIRouter(prefix="/usuarios", tags=["Usuários"])


@router.post("/cadastro", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
async def cadastro(dados: UsuarioCreate, db: AsyncSession = Depends(get_db)):
    return await usuario_service.cadastrar(dados, db)


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(dados: UsuarioLogin, db: AsyncSession = Depends(get_db)):
    return await usuario_service.login(dados, db)


@router.post("/logout")
async def logout(usuario = Depends(get_current_user)):
    return await usuario_service.logout(usuario)

