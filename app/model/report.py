import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from model.base import Base
from model.enums import report_target, report_status


class Report(Base):
    """Denúncia de conteúdo (perfil, loja ou look). Gestão pela moderação
    é service_role apenas; o usuário só cria e lê as próprias.
    """

    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint(
            "reporter_id", "target_type", "target_id", name="uq_reports_reporter_target"
        ),
    )

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    reporter_id = Column(UUID, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True)
    target_type = Column(report_target(), nullable=False)  # profile|seller|look
    target_id = Column(UUID, nullable=False)
    reason = Column(String, nullable=False)
    description = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    status = Column(report_status(), nullable=False, server_default="open")
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
