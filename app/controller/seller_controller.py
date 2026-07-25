from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from dependencies.auth import get_current_user_id, get_current_user_id_optional
from schemas.seller import (
    SellerCreate,
    SellerUpdate,
    SellerResponse,
    DocumentInput,
    DocumentVerifyResponse,
    SellerSearchResponse,
)
from schemas.look import FeedResponse
from service import seller_service, look_service
from core.rate_limiter import limiter

router = APIRouter(prefix="/sellers", tags=["Vendedores"])


@router.post("", response_model=SellerResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def criar_loja(
    request: Request,
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


@router.get("/search", response_model=SellerSearchResponse)
@limiter.limit("30/minute")
async def buscar_lojas(
    request: Request,
    q: str | None = Query(None, min_length=1),
    limit: int = Query(20, ge=1, le=50),
    cursor: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await seller_service.search_sellers(db, q, limit, cursor)


@router.post("/verify-document", response_model=DocumentVerifyResponse)
@limiter.limit("10/hour")
async def verificar_documento(
    request: Request,
    dados: DocumentInput,
    user_id: UUID = Depends(get_current_user_id),
):
    """Prévia — não grava nada. Deixa a pessoa confirmar a razão social antes
    de seguir. Autenticado (não público) para não virar oráculo anônimo de
    validação de CNPJ/CPF de terceiros; rate-limitado pelo mesmo motivo."""
    return await seller_service.verify_document(dados)


@router.put("/me/document", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/hour")
async def definir_documento(
    request: Request,
    dados: DocumentInput,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await seller_service.set_document(db, user_id, dados)


# Rotas com {seller_id} vêm por último, depois de todo literal ("/me",
# "/search", ...) — senão um segmento literal seria capturado como valor de
# `seller_id` pela rota genérica, que casa primeiro na ordem de registro.

@router.get("/{seller_id}", response_model=SellerResponse)
async def get_loja_publica(
    seller_id: UUID,
    user_id: UUID | None = Depends(get_current_user_id_optional),
    db: AsyncSession = Depends(get_db),
):
    return await seller_service.get_public_seller(db, seller_id, user_id)


@router.get("/{seller_id}/looks", response_model=FeedResponse)
@limiter.limit("30/minute")
async def looks_da_loja(
    request: Request,
    seller_id: UUID,
    limit: int = Query(20, ge=1, le=50),
    cursor: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await look_service.search_looks(db, None, None, limit, cursor, seller_id=seller_id)
