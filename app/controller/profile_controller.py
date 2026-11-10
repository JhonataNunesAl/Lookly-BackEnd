from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.profile import ProfileUpdate, ProfileResponse, CategoryAffinityResponse
from schemas.account import ExcluirContaRequest
from service import profile_service, account_service
from core.rate_limiter import limiter

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


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("3/hour")
async def excluir_minha_conta(
    request: Request,
    dados: ExcluirContaRequest,  # exige {"confirmacao": "EXCLUIR"}
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Exclui a conta e os dados da pessoa (e a loja dela, se tiver). Irreversível.
    409 se houver pedidos. Ver `service/account_service.py` para o que sai e em que ordem."""
    await account_service.excluir_conta(db, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
