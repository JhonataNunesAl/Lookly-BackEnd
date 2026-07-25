from uuid import UUID
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from model.body_profile import BodyProfile
from schemas.body_profile import BodyProfileUpdate, BodyProfileResponse
from core import crypto


async def _get_or_create(db: AsyncSession, user_id: UUID) -> BodyProfile:
    result = await db.execute(
        select(BodyProfile).where(BodyProfile.profile_id == user_id)
    )
    body = result.scalar_one_or_none()
    if not body:
        body = BodyProfile(profile_id=user_id)
        db.add(body)
    return body


def _decrypt_optional(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return crypto.decrypt(value)
    except Exception:
        # Dado corrompido ou chave trocada — não derruba o endpoint, só
        # devolve vazio (a pessoa redigita e regrava).
        return None


def _to_response(body: BodyProfile) -> BodyProfileResponse:
    peso = _decrypt_optional(body.weight_kg_enc)
    altura = _decrypt_optional(body.height_cm_enc)
    return BodyProfileResponse(
        weight_kg=float(peso) if peso is not None else None,
        height_cm=float(altura) if altura is not None else None,
        measurements=_decrypt_optional(body.measurements_enc),
        body_photo_key=body.body_photo_key,
        ai_consent_at=body.ai_consent_at,
        ai_consent_revoked_at=body.ai_consent_revoked_at,
        consent_version=body.consent_version,
    )


async def get_me(db: AsyncSession, user_id: UUID) -> BodyProfileResponse:
    body = await _get_or_create(db, user_id)
    return _to_response(body)


async def update_me(
    db: AsyncSession, user_id: UUID, dados: BodyProfileUpdate
) -> BodyProfileResponse:
    body = await _get_or_create(db, user_id)
    payload = dados.model_dump(exclude_unset=True)

    if "weight_kg" in payload:
        v = payload["weight_kg"]
        body.weight_kg_enc = crypto.encrypt(str(v)) if v is not None else None
    if "height_cm" in payload:
        v = payload["height_cm"]
        body.height_cm_enc = crypto.encrypt(str(v)) if v is not None else None
    if "measurements" in payload:
        v = payload["measurements"]
        body.measurements_enc = crypto.encrypt(v) if v is not None else None
    if "body_photo_key" in payload:
        body.body_photo_key = payload["body_photo_key"]

    await db.commit()
    await db.refresh(body)
    return _to_response(body)


async def grant_consent(
    db: AsyncSession, user_id: UUID, consent_version: str
) -> BodyProfileResponse:
    body = await _get_or_create(db, user_id)
    body.ai_consent_at = func.now()
    body.ai_consent_revoked_at = None
    body.consent_version = consent_version
    await db.commit()
    await db.refresh(body)
    return _to_response(body)


async def revoke_consent(db: AsyncSession, user_id: UUID) -> BodyProfileResponse:
    body = await _get_or_create(db, user_id)
    body.ai_consent_revoked_at = func.now()
    await db.commit()
    await db.refresh(body)
    return _to_response(body)
