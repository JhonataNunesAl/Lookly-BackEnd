from fastapi import APIRouter, Depends, HTTPException, status
from schemas.company import CompanyCreate, CompanyResponse, CompanyLogin
from service import usuario_service
from dependencies.auth import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db


router = APIRouter(prefix="/company", tags=["Company"])

@router.post("/cadastro", response_model=CompanyCreate, status_code=status.HTTP_201_CREATED)
async def cadastro_company(dados: CompanyCreate, db: AsyncSession = Depends(get_db)):
    return await usuario_service.cadastrar(dados, db)


@router.post("/login", response_model=CompanyLogin, status_code=status.HTTP_200_OK)
async def login_company(dados: CompanyLogin, db: AsyncSession = Depends(get_db)):
    return await usuario_service.login(dados, db)

@router.post("/logout")
async def logout_company(usuario = Depends(get_current_user)):
    return await usuario_service.logout(usuario)