import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from .base import Base


# Tipos de movimentação. Os que mexem no estoque têm `quantity` com sinal
# (+ entra, - sai); `reserva`/`liberacao` mexem só na reserva (quantity = variação
# da reserva). `venda_app` é gravada pelo webhook do Mercado Pago.
TIPOS_MOVIMENTO = (
    "entrada",        # chegou peça / reposição
    "venda_externa",  # vendeu fora do app (Instagram, WhatsApp, loja física, feira)
    "venda_app",      # vendeu pelo app (pagamento aprovado)
    "ajuste",         # contagem/inventário: estoque passa a ser X
    "perda",          # avaria, furto, doação
    "devolucao",      # cliente devolveu, peça volta ao estoque
    "reserva",        # separou unidades para alguém
    "liberacao",      # desfez a reserva
)


class StockMovement(Base):
    """Histórico de estoque da loja — cada mudança vira uma linha (quem, quando,
    quanto, por quê). É daqui que saem as vendas feitas FORA do app nas métricas.

    `look_id` vira NULL se a peça for apagada; `look_name` guarda o nome para o
    histórico continuar legível.
    """

    __tablename__ = "stock_movements"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID, ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False)
    look_id = Column(UUID, ForeignKey("looks.id", ondelete="SET NULL"), nullable=True)
    look_name = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    stock_after = Column(Integer, nullable=False)
    reserved_after = Column(Integer, nullable=False, server_default="0")
    unit_price = Column(Numeric(10, 2), nullable=True)
    unit_cost = Column(Numeric(10, 2), nullable=True)
    channel = Column(String, nullable=True)
    note = Column(String, nullable=True)
    order_id = Column(UUID, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(UUID, ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
