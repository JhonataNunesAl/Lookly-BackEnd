from uuid import UUID
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.swipe import SwipeCreate, SwipeResponse
from service import swipe_service
from core.rate_limiter import limiter

router = APIRouter(prefix="/swipes", tags=["Swipe"])


@router.post("", response_model=SwipeResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def dar_swipe(
    request: Request,
    dados: SwipeCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # RIGHT curte, mas NÃO salva no armário — salvar é um gesto separado.
    return await swipe_service.record_swipe(db, user_id, dados)
