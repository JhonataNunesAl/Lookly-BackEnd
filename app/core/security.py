import logging
import time
import httpx
import jwt
from jwt import PyJWK, PyJWTError
from fastapi import HTTPException, status
from core.config import settings

logger = logging.getLogger(__name__)

# Cache do JWKS. Buscar a cada request seria um round-trip extra por chamada;
# o Supabase rotaciona chaves raramente, então um TTL curto já basta.
_JWKS_TTL_SECONDS = 600
_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}


def _fetch_jwks(force: bool = False) -> list[dict]:
    agora = time.time()
    if (
        not force
        and _jwks_cache["keys"] is not None
        and agora - _jwks_cache["fetched_at"] < _JWKS_TTL_SECONDS
    ):
        return _jwks_cache["keys"]

    try:
        resp = httpx.get(settings.SUPABASE_JWKS_URL, timeout=10)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
    except (httpx.HTTPError, ValueError) as e:
        # Se a rede falhar mas houver cache antigo, é melhor usá-lo do que
        # derrubar toda a autenticação. De qualquer forma isso é sinal de um
        # problema real de rede/Supabase — sem log, os dois casos abaixo
        # aconteciam em silêncio total.
        if _jwks_cache["keys"] is not None:
            logger.warning("JWKS indisponível (%s), usando cache antigo", e)
            return _jwks_cache["keys"]
        logger.warning("JWKS indisponível (%s) e sem cache — autenticação vai falhar", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível obter as chaves de verificação do Supabase",
        )

    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = agora
    return keys


def _key_for(kid: str | None) -> dict | None:
    for key in _fetch_jwks():
        if key.get("kid") == kid:
            return key
    # kid desconhecido pode ser rotação de chave: recarrega uma vez.
    for key in _fetch_jwks(force=True):
        if key.get("kid") == kid:
            return key
    return None


# Algoritmos aceitos POR TIPO DE CHAVE. Misturar tudo numa lista só abre a
# "confusão de algoritmo": um token HS256 assinado com a chave PÚBLICA (que é, bem,
# pública) como se fosse segredo. Aqui a chave decide a lista: a do JWKS só valida
# assinatura assimétrica; o segredo compartilhado só valida HS256.
_ALG_ASSIMETRICOS = ["ES256", "RS256"]
_ALG_SIMETRICOS = ["HS256"]


def verify_supabase_token(token: str) -> dict:
    """Valida um access token emitido pelo Supabase Auth.

    Projetos novos assinam com chave ASSIMÉTRICA (ES256) — a verificação usa a
    chave pública do JWKS, casada pelo `kid` do cabeçalho. Projetos legados
    assinam com HS256 usando o JWT secret compartilhado.
    """
    try:
        header = jwt.get_unverified_header(token)
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token malformado"
        )

    if header.get("alg") == "HS256":
        chave = settings.SUPABASE_JWT_SECRET
        algoritmos = _ALG_SIMETRICOS
        if not chave:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token HS256 recebido mas SUPABASE_JWT_SECRET não está configurado",
            )
    else:
        jwk = _key_for(header.get("kid"))
        if not jwk:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Chave de assinatura do token não encontrada",
            )
        algoritmos = _ALG_ASSIMETRICOS
        try:
            chave = PyJWK(jwk).key
        except (PyJWTError, ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Chave de assinatura do token inválida",
            )

    try:
        payload = jwt.decode(
            token,
            chave,
            algorithms=algoritmos,
            audience=settings.JWT_AUDIENCE,
            options={"require": ["exp", "sub", "aud"]},
        )
    except (PyJWTError, ValueError, TypeError):
        # ValueError/TypeError: chave do JWKS incompatível com o algoritmo do token
        # (a biblioteca de criptografia levanta isso em vez de um erro de JWT) —
        # tem que virar 401, nunca 500.
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
