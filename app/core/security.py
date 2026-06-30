from jose import jwt, JWTError
from fastapi import HTTPException, status
from core.config import settings


def verify_supabase_token(token: str) -> dict:
    """Valida um access token emitido pelo Supabase Auth.

    Verifica assinatura (HS256 com o JWT secret do projeto), expiração e a
    audience "authenticated". Retorna o payload (claims) ou levanta 401.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
        )

    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sem identificação de usuário",
        )

    return payload
