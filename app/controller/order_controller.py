import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from dependencies.auth import get_current_user_id
from schemas.order import CheckoutRequest, CheckoutResponse, OrderOut
from service import mercadopago_service, order_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pedidos e pagamento"])


@router.post("/orders/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
async def checkout(
    dados: CheckoutRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Cria o pedido a partir do carrinho e devolve a URL de pagamento do Mercado Pago."""
    return await order_service.checkout(db, user_id, dados)


@router.get("/orders", response_model=list[OrderOut])
async def listar_pedidos(user_id: UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    return await order_service.listar(db, user_id)


@router.get("/orders/{order_id}", response_model=OrderOut)
async def obter_pedido(
    order_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await order_service.obter(db, user_id, order_id)


@router.post("/payments/webhook", include_in_schema=False)
async def webhook_mercadopago(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_signature: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
):
    """Notificação do Mercado Pago. Sempre responde 200 rápido (senão o MP reenvia
    por dias); o status real é relido na API do MP dentro do serviço."""
    q = request.query_params
    try:
        corpo = await request.json()
    except Exception:  # noqa: BLE001
        corpo = {}
    tipo = corpo.get("type") or corpo.get("topic") or q.get("type") or q.get("topic")
    payment_id = str((corpo.get("data") or {}).get("id") or q.get("data.id") or q.get("id") or "")

    if tipo != "payment" or not payment_id:
        return Response(status_code=200)
    if not mercadopago_service.assinatura_valida(x_signature, x_request_id, payment_id):
        logger.warning("Webhook do Mercado Pago com assinatura inválida (pagamento %s)", payment_id)
        return Response(status_code=401)
    try:
        await order_service.processar_notificacao(db, payment_id)
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao processar o pagamento %s", payment_id)
        return Response(status_code=500)  # o MP tenta de novo depois
    return Response(status_code=200)
