from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.swipe import SwipeCreate, SwipeResponse
from service import swipe_service

router = APIRouter(prefix="/swipes", tags=["Swipe"])


@router.post("", response_model=SwipeResponse, status_code=status.HTTP_201_CREATED)
async def dar_swipe(
    dados: SwipeCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await swipe_service.create_swipe(db, user_id, dados)
