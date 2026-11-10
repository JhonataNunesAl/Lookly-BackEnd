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
