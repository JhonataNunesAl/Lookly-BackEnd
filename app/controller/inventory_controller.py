"""Gestão de estoque da loja. Tudo exige login e uma loja (dono, ou membro
owner/manager); cada consulta filtra pela loja do usuário."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.rate_limiter import limiter
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.inventory import (
    EnvioUpdate,
    ItensEstoqueResponse,
    Metricas,
    MovimentoCreate,
    MovimentoResultado,
    MovimentosResponse,
    OrdemItens,
    Situacao,
    StatusPeca,
    VendasResponse,
)
from schemas.look import LookGestaoResponse
from service import inventory_service

router = APIRouter(prefix="/inventory", tags=["Gestão de estoque"])


@router.get("/items", response_model=ItensEstoqueResponse)
@limiter.limit("60/minute")
async def listar_itens(
    request: Request,
    q: str | None = Query(None, min_length=1, max_length=80, description="nome, descrição ou marca"),
    situacao: Situacao = Query("todos"),
    category_id: UUID | None = Query(None),
    sort: OrdemItens = Query("recentes"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await inventory_service.listar_itens(
        db, user_id, q=q, situacao=situacao, category_id=category_id, sort=sort, limit=limit, offset=offset
    )


@router.post("/items/{look_id}/movements", response_model=MovimentoResultado, status_code=201)
@limiter.limit("120/minute")
async def movimentar(
    request: Request,
    look_id: UUID,
    dados: MovimentoCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Entrada, venda fora do app, ajuste (contagem), perda, devolução, reserva ou liberação."""
    mov, look = await inventory_service.registrar_movimento(db, user_id, look_id, dados)
    return {"movement": mov, "item": look}


@router.patch("/items/{look_id}/status", response_model=LookGestaoResponse)
async def alterar_status(
    look_id: UUID,
    dados: StatusPeca,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Pausar (sai do feed, continua no estoque) ou reativar."""
    return await inventory_service.alterar_status(db, user_id, look_id, dados.status)


@router.get("/movements", response_model=MovimentosResponse)
@limiter.limit("60/minute")
async def listar_movimentos(
    request: Request,
    look_id: UUID | None = Query(None),
    kind: str | None = Query(None, max_length=20),
    limit: int = Query(30, ge=1, le=100),
    cursor: datetime | None = Query(None),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await inventory_service.listar_movimentos(db, user_id, look_id, kind, limit, cursor)


@router.get("/sales", response_model=VendasResponse)
@limiter.limit("60/minute")
async def listar_vendas(
    request: Request,
    situacao: Literal["todos", "pending", "shipped", "delivered"] = Query("todos"),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Pedidos pagos no app com peças desta loja (para separar e enviar)."""
    return await inventory_service.listar_vendas_app(db, user_id, situacao)


@router.patch("/sales/{order_id}")
async def atualizar_envio(
    order_id: UUID,
    dados: EnvioUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await inventory_service.atualizar_envio(db, user_id, order_id, dados)


@router.get("/metrics", response_model=Metricas)
@limiter.limit("30/minute")
async def metricas(
    request: Request,
    days: int = Query(30, description="7, 30, 90 ou 365"),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if days not in (7, 30, 90, 365):
        raise HTTPException(status_code=422, detail="Período inválido: use 7, 30, 90 ou 365 dias.")
    return await inventory_service.metricas(db, user_id, days)
