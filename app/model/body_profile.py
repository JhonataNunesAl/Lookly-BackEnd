from sqlalchemy import Column, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


class BodyProfile(Base):
    """Dados corporais do usuário (sensíveis). RLS só para o dono.

    Os campos *_enc guardam CIPHERTEXT — a cifragem (envelope encryption
    com KMS) deve acontecer na aplicação antes de gravar. A foto de corpo
    é uma CHAVE de bucket privado (body_photo_key), servida por signed URL
    de curta duração, nunca URL pública.
    """

    __tablename__ = "body_profiles"

    profile_id = Column(
        UUID, ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    weight_kg_enc = Column(String, nullable=True)
    height_cm_enc = Column(String, nullable=True)
    measurements_enc = Column(String, nullable=True)
    body_photo_key = Column(String, nullable=True)
    # Consentimento de IA explícito, versionado e revogável (LGPD).
    ai_consent_at = Column(DateTime(timezone=True), nullable=True)
    ai_consent_revoked_at = Column(DateTime(timezone=True), nullable=True)
    consent_version = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
