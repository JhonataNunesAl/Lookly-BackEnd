from uuid import UUID
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.body_profile import (
    BodyProfileUpdate,
    BodyProfileResponse,
    ConsentUpdate,
)
from service import body_profile_service
from core.rate_limiter import limiter

router = APIRouter(prefix="/body-profile", tags=["Dados corporais"])


@router.get("/me", response_model=BodyProfileResponse)
async def get_meus_dados(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await body_profile_service.get_me(db, user_id)


@router.put("/me", response_model=BodyProfileResponse)
@limiter.limit("20/hour")
async def atualizar_meus_dados(
    request: Request,
    dados: BodyProfileUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await body_profile_service.update_me(db, user_id, dados)


@router.post("/me/consent", response_model=BodyProfileResponse)
@limiter.limit("20/hour")
async def dar_consentimento_ia(
    request: Request,
    dados: ConsentUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await body_profile_service.grant_consent(db, user_id, dados.consent_version)


@router.delete("/me/consent", response_model=BodyProfileResponse)
@limiter.limit("20/hour")
async def revogar_consentimento_ia(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await body_profile_service.revoke_consent(db, user_id)
