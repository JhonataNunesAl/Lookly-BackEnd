"""Rotas de importação, exportação e edição em massa de peças.

Registrado ANTES do `look_controller` (ver routers.py): `GET /looks/export`
seria capturado por `GET /looks/{look_id}` se a rota genérica viesse primeiro.
"""
from typing import Literal
from uuid import UUID
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.body_limit import ler_corpo_limitado
from core.rate_limiter import limiter
from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.importacao import (
    EdicaoEmMassa,
    EdicaoEmMassaResponse,
    LoteRequest,
    LoteResponse,
    PreviaResponse,
)
from service import importacao_service

router = APIRouter(prefix="/looks", tags=["Importação em massa"])

Formato = Literal["xlsx", "csv"]


def _arquivo(corpo: bytes, tipo: str, nome: str) -> Response:
    return Response(
        content=corpo,
        media_type=tipo,
        headers={
            "Content-Disposition": f"attachment; filename=\"{nome}\"; filename*=UTF-8''{quote(nome)}",
            "Cache-Control": "no-store",
        },
    )


@router.get("/import/template")
@limiter.limit("30/minute")
async def baixar_modelo(
    request: Request,
    formato: Formato = Query("xlsx", description="xlsx (com instruções e lista de categorias) ou csv"),
    db: AsyncSession = Depends(get_db),
):
    """Planilha modelo para importar peças. Pública: não tem dado de ninguém,
    só as colunas e a lista de categorias (já pública em `GET /categories`)."""
    return _arquivo(*await importacao_service.gerar_modelo(db, formato))


@router.post("/import/preview", response_model=PreviaResponse)
@limiter.limit("20/minute")
async def previa_importacao(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Recebe a planilha CRUA no corpo (`Content-Type: text/csv` ou o tipo do
    .xlsx — sem multipart, como o upload de imagem), valida linha a linha e
    devolve a prévia. Não grava nada."""
    corpo = await ler_corpo_limitado(
        request, importacao_service.MAX_BYTES_PLANILHA, "Planilha grande demais (máximo de 5 MB)."
    )
    return await importacao_service.gerar_previa(db, user_id, request.headers.get("content-type"), corpo)


@router.post("/bulk", response_model=LoteResponse)
@limiter.limit("60/minute")
async def gravar_lote(
    request: Request,
    dados: LoteRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Cria/atualiza até 1000 peças por chamada. Linhas inválidas voltam em
    `erros` (com o número da linha) e não impedem as válidas."""
    return await importacao_service.gravar_lote(db, user_id, dados)


@router.patch("/bulk", response_model=EdicaoEmMassaResponse)
@limiter.limit("30/minute")
async def editar_em_massa(
    request: Request,
    dados: EdicaoEmMassa,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Mesmo ajuste (preço, reajuste %, estoque, soma ao estoque, situação ou
    categoria) em até 500 peças da loja de uma vez."""
    return await importacao_service.editar_em_massa(db, user_id, dados)


@router.get("/export")
@limiter.limit("10/minute")
async def exportar_catalogo(
    request: Request,
    formato: Formato = Query("xlsx"),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Catálogo inteiro da loja na planilha de importação (com `id`): edite no
    Excel e importe de volta para atualizar em massa."""
    return _arquivo(*await importacao_service.exportar_catalogo(db, user_id, formato))
