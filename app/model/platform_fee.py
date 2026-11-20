from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, SmallInteger, func
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class PlatformFeeConfig(Base):
    """Regra da taxa da plataforma sobre as peças vendidas no app. Uma linha só (id = 1).

    * `demo_ends_at` NULL  -> demo em andamento: 0% para todo mundo.
    * depois do fim da demo, cada loja tem `grace_days` dias a 0%, contados do
      que vier por último: o fim da demo ou o cadastro da loja;
    * passada a carência, vale `fee_percent`.

    A taxa de cada venda fica congelada em `order_items` no momento da aprovação
    do pagamento: mudar a regra aqui nunca altera vendas passadas.
    """

    __tablename__ = "platform_fee_config"

    id = Column(SmallInteger, primary_key=True, default=1)
    demo_ends_at = Column(DateTime(timezone=True), nullable=True)
    fee_percent = Column(Numeric(5, 2), nullable=False, server_default="11")
    grace_days = Column(Integer, nullable=False, server_default="60")
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(UUID, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True)
