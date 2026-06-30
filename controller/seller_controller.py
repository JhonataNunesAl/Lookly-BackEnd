from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.seller import SellerCreate, SellerUpdate, SellerResponse
from service import seller_service

router = APIRouter(prefix="/sellers", tags=["Vendedores"])


@router.post("", response_model=SellerResponse, status_code=status.HTTP_201_CREATED)
async def virar_vendedor(
    dados: SellerCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await seller_service.become_seller(db, user_id, dados)


@router.get("/me", response_model=SellerResponse)
async def get_minha_loja(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await seller_service.get_me(db, user_id)


@router.put("/me", response_model=SellerResponse)
async def atualizar_minha_loja(
    dados: SellerUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await seller_service.update_me(db, user_id, dados)
