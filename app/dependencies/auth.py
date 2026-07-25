from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core.security import verify_supabase_token

_bearer = HTTPBearer(auto_error=True)
_bearer_optional = HTTPBearer(auto_error=False)


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> UUID:
    """Valida o JWT do Supabase e retorna o id do usuário (auth.users.id).

    Esse UUID corresponde a profiles.id e é usado para filtrar todas as
    queries por dono.
    """
    payload = verify_supabase_token(credentials.credentials)
    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sem identificação de usuário válida",
        )


def get_current_user_id_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
) -> UUID | None:
    """Como `get_current_user_id`, mas retorna None sem token em vez de 401.

    Usado em rotas públicas (ex.: ver um look) que precisam saber QUEM está
    pedindo só para decidir visibilidade de conteúdo não-ativo — nunca para
    autorizar uma escrita.
    """
    if credentials is None:
        return None
    payload = verify_supabase_token(credentials.credentials)
    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError):
        return None
