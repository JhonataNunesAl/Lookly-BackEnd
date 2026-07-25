from datetime import datetime
from pydantic import BaseModel


class BodyProfileUpdate(BaseModel):
    """Dados corporais em CLARO, sobre HTTPS, num endpoint já autenticado — o
    servidor cifra antes de gravar (ver `core/crypto.py`). O contrato antigo
    (`weight_kg_enc`/`height_cm_enc`/`measurements_enc` vindos do cliente já
    cifrados) nunca teve cifragem client-side implementada em lugar nenhum;
    nenhuma tela chamava este endpoint. Mesma solução pragmática aplicada ao
    CPF/CNPJ em `sellers_private` — servidor cifra, não é o desenho final
    (o ideal seria envelope encryption com KMS), mas fecha o gap real.
    """

    weight_kg: float | None = None
    height_cm: float | None = None
    measurements: str | None = None
    body_photo_key: str | None = None


class ConsentUpdate(BaseModel):
    consent_version: str


class BodyProfileResponse(BaseModel):
    """Decifrado no servidor antes de responder — endpoint sempre exige o JWT
    do próprio dono (`get_current_user_id`), mesmo nível de confiança de
    qualquer outro dado privado servido por este backend."""

    weight_kg: float | None = None
    height_cm: float | None = None
    measurements: str | None = None
    body_photo_key: str | None = None
    ai_consent_at: datetime | None = None
    ai_consent_revoked_at: datetime | None = None
    consent_version: str | None = None
