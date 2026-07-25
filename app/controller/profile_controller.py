from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.profile import ProfileUpdate, ProfileResponse, CategoryAffinityResponse
from service import profile_service

router = APIRouter(prefix="/profiles", tags=["Perfil"])


@router.get("/me", response_model=ProfileResponse)
async def get_meu_perfil(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await profile_service.get_me(db, user_id)


@router.put("/me", response_model=ProfileResponse)
async def atualizar_meu_perfil(
    dados: ProfileUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await profile_service.update_me(db, user_id, dados)


@router.get("/me/category-affinity", response_model=list[CategoryAffinityResponse])
async def minha_afinidade_por_categoria(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await profile_service.get_category_affinity(db, user_id)
