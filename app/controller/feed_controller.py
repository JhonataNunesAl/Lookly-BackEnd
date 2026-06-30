from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.look import FeedResponse
from service import feed_service

router = APIRouter(prefix="/feed", tags=["Feed"])


@router.get("", response_model=FeedResponse)
async def get_feed(
    category: str = Query(..., description="slug da categoria (filtro rígido)"),
    limit: int = Query(20, ge=1, le=50),
    cursor: datetime | None = Query(None, description="created_at do último item da página anterior"),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await feed_service.get_feed(db, user_id, category, limit, cursor)
