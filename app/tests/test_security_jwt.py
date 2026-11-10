"""Testes da verificação do token do Supabase (core/security.py) com criptografia real.

Gera um par de chaves EC (ES256), monta um JWKS falso e assina tokens de verdade:
é assim que se prova que a verificação REJEITA o que deve rejeitar (expirado,
audience errada, outra chave, algoritmo trocado), não só que aceita o caso feliz.

Roda com: cd app && python -m pytest tests/ -v
"""
import base64
import time
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from core import security

KID = "chave-teste-1"


def _b64u(n: int, tamanho: int = 32) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(tamanho, "big")).rstrip(b"=").decode()


def _par_ec():
    privada = ec.generate_private_key(ec.SECP256R1())
    nums = privada.public_key().public_numbers()
    jwk = {"kty": "EC", "crv": "P-256", "alg": "ES256", "use": "sig", "kid": KID, "x": _b64u(nums.x), "y": _b64u(nums.y)}
    return privada, jwk


PRIVADA, JWK = _par_ec()
OUTRA_PRIVADA, _ = _par_ec()


def _claims(**sobre):
    base = {"sub": str(uuid4()), "aud": "authenticated", "exp": int(time.time()) + 600, "iat": int(time.time())}
    base.update(sobre)
    return {k: v for k, v in base.items() if v is not None}


def _token(claims=None, chave=PRIVADA, alg="ES256", kid=KID):
    return jwt.encode(claims or _claims(), chave, algorithm=alg, headers={"kid": kid} if kid else {})


@pytest.fixture(autouse=True)
def jwks_falso():
    with patch.object(security, "_fetch_jwks", return_value=[JWK]):
        yield


def _rejeita(token, trecho=None):
    with pytest.raises(HTTPException) as e:
        security.verify_supabase_token(token)
    assert e.value.status_code == 401
    if trecho:
        assert trecho in e.value.detail


def test_token_es256_valido_devolve_claims():
    uid = str(uuid4())
    assert security.verify_supabase_token(_token(_claims(sub=uid)))["sub"] == uid


def test_token_expirado_rejeitado():
    _rejeita(_token(_claims(exp=int(time.time()) - 10)))


def test_audience_errada_rejeitada():
    _rejeita(_token(_claims(aud="anon")))


def test_audience_ausente_rejeitada():
    _rejeita(_token(_claims(aud=None)))


def test_sem_exp_rejeitado():
    _rejeita(_token(_claims(exp=None)))


def test_sem_sub_rejeitado():
    _rejeita(_token(_claims(sub=None)))


def test_assinado_por_outra_chave_rejeitado():
    _rejeita(_token(chave=OUTRA_PRIVADA))


def test_kid_desconhecido_rejeitado():
    with patch.object(security, "_fetch_jwks", return_value=[JWK]):
        _rejeita(_token(kid="outro-kid"), "Chave de assinatura")


def test_sem_kid_rejeitado():
    _rejeita(_token(kid=None))


def test_token_malformado_rejeitado():
    _rejeita("isso.nao.eh-um-jwt", "malformado")
    _rejeita("")


def test_alg_none_rejeitado():
    corpo = base64.urlsafe_b64encode(b'{"sub":"x","aud":"authenticated","exp":9999999999}').rstrip(b"=").decode()
    cab = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    _rejeita(f"{cab}.{corpo}.")


# ── confusão de algoritmo ─────────────────────────────────────────────────────

def test_hs256_sem_segredo_configurado_rejeitado():
    token = jwt.encode(_claims(), "qualquer-coisa-com-32-bytes-ou-mais!!", algorithm="HS256")
    with patch.object(security.settings, "SUPABASE_JWT_SECRET", ""):
        _rejeita(token, "SUPABASE_JWT_SECRET")


def test_hs256_com_segredo_correto_aceito():
    segredo = "segredo-legado-de-teste-com-mais-de-32-bytes"
    token = jwt.encode(_claims(), segredo, algorithm="HS256")
    with patch.object(security.settings, "SUPABASE_JWT_SECRET", segredo):
        assert security.verify_supabase_token(token)["aud"] == "authenticated"


def test_hs256_com_segredo_errado_rejeitado():
    token = jwt.encode(_claims(), "um-segredo-que-o-servidor-nao-tem-32bytes", algorithm="HS256")
    with patch.object(security.settings, "SUPABASE_JWT_SECRET", "o-segredo-de-verdade-do-servidor-32bytes!!"):
        _rejeita(token)


def _hs256_manual(claims: dict, segredo: bytes, kid: str) -> str:
    """Monta o JWT HS256 À MÃO: o PyJWT se recusa a assinar HS256 com uma chave
    pública PEM (justamente por causa deste ataque), então o atacante não usaria a
    biblioteca — usaria HMAC direto."""
    import hashlib, hmac, json

    def b64(o):
        return base64.urlsafe_b64encode(json.dumps(o, separators=(",", ":")).encode()).rstrip(b"=").decode()

    corpo = f"{b64({'alg': 'HS256', 'typ': 'JWT', 'kid': kid})}.{b64(claims)}"
    assinatura = hmac.new(segredo, corpo.encode(), hashlib.sha256).digest()
    return corpo + "." + base64.urlsafe_b64encode(assinatura).rstrip(b"=").decode()


def test_hs256_assinado_com_a_chave_publica_nao_vale():
    """O ataque clássico: usar a chave PÚBLICA (que todo mundo tem) como segredo
    HS256. Com segredo configurado diferente, falha; sem segredo configurado, falha;
    e o JWKS nunca valida um token HS256."""
    publica_pem = PRIVADA.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    forjado = _hs256_manual(_claims(), publica_pem, KID)
    with patch.object(security.settings, "SUPABASE_JWT_SECRET", "segredo-de-verdade-com-mais-de-32-bytes!!"):
        _rejeita(forjado)
    with patch.object(security.settings, "SUPABASE_JWT_SECRET", ""):
        _rejeita(forjado)


def test_token_es256_nao_e_aceito_se_a_chave_do_jwks_for_simetrica():
    jwk_oct = {"kty": "oct", "kid": KID, "k": base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()}
    with patch.object(security, "_fetch_jwks", return_value=[jwk_oct]):
        _rejeita(_token())
