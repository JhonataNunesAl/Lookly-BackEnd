import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError

from core.body_limit import ler_corpo_limitado
from core.rate_limiter import limiter
from core.security import verify_supabase_token
from schemas.account import ClientLogLote, ClientLogResponse
from service import client_log_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["Logs"])

MAX_BYTES = 64 * 1024


def _user_id_se_houver(request: Request) -> UUID | None:
    """Anexa o usuário SÓ se o token for válido. Nunca falha: quem está com a
    sessão vencida (ou travou no login) também precisa conseguir reportar o erro."""
    cabecalho = request.headers.get("authorization", "")
    if not cabecalho.lower().startswith("bearer "):
        return None
    try:
        return UUID(verify_supabase_token(cabecalho[7:].strip())["sub"])
    except Exception:
        return None


@router.post("/client", response_model=ClientLogResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("30/minute")
async def receber_logs_do_app(request: Request):
    """Erros e exceções do app (JS, promises, renderização, chamadas à API).
    Público de propósito — um app que quebra antes do login também precisa
    reportar —, por isso: limite de tamanho (verificado ANTES de interpretar o
    JSON), limite de frequência e texto limpo de dados sensíveis antes de ir ao
    log. Não grava em banco."""
    corpo = await ler_corpo_limitado(request, MAX_BYTES, "Log grande demais.")
    try:
        lote = ClientLogLote.model_validate_json(corpo)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=e.errors(include_url=False, include_context=False, include_input=False)[0]["msg"],
        )
    n = client_log_service.registrar(lote, _user_id_se_houver(request))
    return ClientLogResponse(recebidas=n)
