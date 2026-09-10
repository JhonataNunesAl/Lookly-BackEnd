from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.look import FeedResponse
from service import feed_service
from core.rate_limiter import limiter

router = APIRouter(prefix="/feed", tags=["Feed"])


@router.get("", response_model=FeedResponse)
@limiter.limit("30/minute")
async def get_feed(
    request: Request,
    category: str | None = Query(None, description="slug da categoria (filtro opcional)"),
    limit: int = Query(20, ge=1, le=50),
    cursor: datetime | None = Query(None, description="created_at do último item da página anterior"),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await feed_service.get_feed(db, user_id, category, limit, cursor)
