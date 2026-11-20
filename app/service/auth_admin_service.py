"""Operações administrativas no Supabase Auth (chave service_role — só no servidor)."""
import logging
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from core.config import settings

logger = logging.getLogger(__name__)


async def excluir_usuario(user_id: UUID) -> None:
    """Apaga o usuário do Supabase Auth, o que encerra o login dele para sempre.
    404 conta como sucesso (já não existe — assim repetir a exclusão é seguro).
    Qualquer outra falha vira 502: os dados do app já foram apagados antes, então
    quem chamou pode tentar de novo."""
    if not settings.SUPABASE_SERVICE_KEY or not settings.SUPABASE_URL:
        logger.error("Exclusão de conta sem SUPABASE_URL/SUPABASE_SERVICE_KEY configurados")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Exclusão indisponível no momento.")
    chave = settings.SUPABASE_SERVICE_KEY
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.delete(
                f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                headers={"apikey": chave, "Authorization": f"Bearer {chave}"},
            )
    except httpx.HTTPError as e:
        logger.error("Falha de rede ao excluir usuário %s no Auth: %s", user_id, type(e).__name__)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Não foi possível concluir a exclusão. Tente novamente.")
    if resp.status_code in (200, 204, 404):
        return
    logger.error("Auth recusou excluir %s: HTTP %s", user_id, resp.status_code)
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Não foi possível concluir a exclusão. Tente novamente.")


# "Para sempre" no formato do Supabase (duração Go). "none" tira o bloqueio.
_BAN_PERMANENTE = "876000h"


async def bloquear_login(user_id: UUID, bloquear: bool) -> None:
    """Bloqueia (ou libera) o login da conta no Supabase Auth. Quem está logado
    perde o acesso quando o token atual expirar (até ~1h) — o bloqueio de dados
    imediato é o `profiles.status`, gravado por quem chama."""
    if not settings.SUPABASE_SERVICE_KEY or not settings.SUPABASE_URL:
        logger.error("Bloqueio de login sem SUPABASE_URL/SUPABASE_SERVICE_KEY configurados")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Bloqueio de conta indisponível no momento.")
    chave = settings.SUPABASE_SERVICE_KEY
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.put(
                f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                headers={"apikey": chave, "Authorization": f"Bearer {chave}"},
                json={"ban_duration": _BAN_PERMANENTE if bloquear else "none"},
            )
    except httpx.HTTPError as e:
        logger.error("Falha de rede ao (des)bloquear %s no Auth: %s", user_id, type(e).__name__)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Não foi possível alterar o acesso da conta. Tente novamente.")
    if resp.status_code == 200:
        return
    if resp.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada no login.")
    logger.error("Auth recusou (des)bloquear %s: HTTP %s", user_id, resp.status_code)
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Não foi possível alterar o acesso da conta. Tente novamente.")
