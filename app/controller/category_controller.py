from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.category import CategoryCreate, CategoryResponse
from service import category_service

router = APIRouter(prefix="/categories", tags=["Categorias"])


@router.get("", response_model=list[CategoryResponse])
async def listar_categorias(db: AsyncSession = Depends(get_db)):
    return await category_service.list_categories(db)


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def criar_categoria(
    dados: CategoryCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await category_service.create_category(db, dados)
