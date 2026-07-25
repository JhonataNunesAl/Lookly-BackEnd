from uuid import UUID
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.report import ReportCreate, ReportResponse
from service import report_service
from core.rate_limiter import limiter

router = APIRouter(prefix="/reports", tags=["Denúncias"])


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def denunciar(
    request: Request,
    dados: ReportCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await report_service.create_report(db, user_id, dados)


@router.get("", response_model=list[ReportResponse])
async def minhas_denuncias(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await report_service.list_my_reports(db, user_id)
