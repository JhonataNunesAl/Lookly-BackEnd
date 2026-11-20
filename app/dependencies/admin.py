"""Acesso de administrador do Lookly.

Quem é admin é decidido AQUI, no servidor — o app só esconde/mostra a tela. A
regra: o e-mail da conta está em `ADMIN_EMAILS` (variável de ambiente, separada
por vírgula; padrão: o e-mail do dono do app) E esse e-mail está CONFIRMADO no
Supabase Auth.

Por que não confiar só no e-mail do JWT: o token é assinado pelo Supabase, mas
se a confirmação de e-mail estiver desligada alguém poderia criar conta com o
e-mail do admin antes dele. Por isso a confirmação é relida na fonte
(`auth.users.email_confirmed_at`), com a API admin do Supabase como reserva se o
papel do banco não puder ler o schema `auth`. Sem conseguir confirmar → 503, nunca
"libera por via das dúvidas".

O resultado positivo fica em cache por alguns minutos (o painel faz várias
chamadas seguidas); o negativo não é cacheado.
"""
import logging
import os
import time
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.database import get_db
from dependencies.auth import get_token_payload

logger = logging.getLogger(__name__)

_PADRAO = "yorn.exe@gmail.com"
_CACHE_TTL = 300
_cache: dict[UUID, float] = {}


def emails_admin() -> set[str]:
    bruto = os.getenv("ADMIN_EMAILS", _PADRAO)
    return {e.strip().lower() for e in bruto.split(",") if e.strip()}


def email_do_token(payload: dict) -> str:
    return str(payload.get("email") or "").strip().lower()


async def _confirmado_no_banco(db: AsyncSession, user_id: UUID) -> tuple[str, bool] | None:
    """(email, confirmado) lido de auth.users; None se não deu para ler."""
    try:
        async with db.begin_nested():
            linha = (
                await db.execute(
                    text("SELECT email, email_confirmed_at IS NOT NULL FROM auth.users WHERE id = :id"),
                    {"id": user_id},
                )
            ).first()
    except DBAPIError as e:
        logger.warning("Admin: sem leitura de auth.users (%s) — tentando API do Supabase", type(e).__name__)
        return None
    if linha is None:
        return ("", False)
    return (str(linha[0] or "").lower(), bool(linha[1]))


async def _confirmado_na_api(user_id: UUID) -> tuple[str, bool] | None:
    if not settings.SUPABASE_SERVICE_KEY or not settings.SUPABASE_URL:
        return None
    chave = settings.SUPABASE_SERVICE_KEY
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                headers={"apikey": chave, "Authorization": f"Bearer {chave}"},
            )
    except httpx.HTTPError as e:
        logger.warning("Admin: API do Supabase indisponível (%s)", type(e).__name__)
        return None
    if resp.status_code == 404:
        return ("", False)
    if resp.status_code != 200:
        logger.warning("Admin: API do Supabase respondeu HTTP %s", resp.status_code)
        return None
    dados = resp.json()
    return (str(dados.get("email") or "").lower(), bool(dados.get("email_confirmed_at")))


async def require_admin(
    payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    """Dependência das rotas /api/admin. Devolve o id (profiles.id) do admin."""
    user_id = UUID(payload["sub"])
    admins = emails_admin()
    negado = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito à administração.")

    # Filtro barato antes de ir ao banco: quase toda conta para aqui.
    if email_do_token(payload) not in admins:
        raise negado

    validade = _cache.get(user_id)
    if validade and validade > time.time():
        return user_id

    resultado = await _confirmado_no_banco(db, user_id)
    if resultado is None:
        resultado = await _confirmado_na_api(user_id)
    if resultado is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível confirmar o acesso de administrador agora.",
        )
    email, confirmado = resultado
    if email not in admins or not confirmado:
        logger.warning("Admin: acesso negado para user_id=%s (e-mail não confere ou não confirmado)", user_id)
        raise negado

    _cache[user_id] = time.time() + _CACHE_TTL
    return user_id
