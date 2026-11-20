"""Cliente mínimo do Mercado Pago (Checkout Pro) via API REST.

Só duas chamadas: criar a preferência de pagamento de um pedido e reler um
pagamento pelo id (o webhook nunca confia no corpo da notificação: o status vem
sempre daqui). O Access Token fica só no servidor e nunca é logado.
"""

import hashlib
import hmac
import logging
from decimal import Decimal

import httpx
from fastapi import HTTPException, status

from core.config import settings

logger = logging.getLogger(__name__)

API = "https://api.mercadopago.com"
CHECKOUT_URL = "https://www.mercadopago.com.br/checkout/v1/redirect?pref_id={pref_id}"


def _headers(idempotency_key: str | None = None) -> dict[str, str]:
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pagamento ainda não configurado no servidor.",
        )
    h = {
        "Authorization": f"Bearer {settings.MERCADOPAGO_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        h["X-Idempotency-Key"] = idempotency_key
    return h


def url_de_pagamento(preference_id: str) -> str:
    return CHECKOUT_URL.format(pref_id=preference_id)


async def criar_preferencia(
    *,
    order_id: str,
    itens: list[dict],
    email_comprador: str | None,
) -> tuple[str, str]:
    """Cria a preferência e devolve (preference_id, url_de_pagamento).

    `itens`: [{"id", "title", "quantity", "unit_price": Decimal, "picture_url"}].
    """
    site = settings.PUBLIC_SITE_URL
    corpo = {
        "items": [
            {
                "id": str(i["id"]),
                "title": i["title"][:250],
                "quantity": int(i["quantity"]),
                "unit_price": float(Decimal(i["unit_price"])),
                "currency_id": "BRL",
                **({"picture_url": i["picture_url"]} if i.get("picture_url") else {}),
            }
            for i in itens
        ],
        "external_reference": order_id,
        "notification_url": f"{settings.PUBLIC_API_URL}/api/payments/webhook",
        "back_urls": {
            "success": f"{site}/?pagamento=aprovado&pedido={order_id}",
            "pending": f"{site}/?pagamento=pendente&pedido={order_id}",
            "failure": f"{site}/?pagamento=recusado&pedido={order_id}",
        },
        "auto_return": "approved",
        "statement_descriptor": "LOOKLY",
        **({"payer": {"email": email_comprador}} if email_comprador else {}),
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{API}/checkout/preferences", json=corpo, headers=_headers(idempotency_key=order_id)
        )
    if r.status_code >= 300:
        logger.error("Mercado Pago recusou a preferência do pedido %s: %s %s", order_id, r.status_code, r.text[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível iniciar o pagamento. Tente de novo em instantes.",
        )
    dados = r.json()
    return dados["id"], dados.get("init_point") or url_de_pagamento(dados["id"])


async def buscar_pagamento(payment_id: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{API}/v1/payments/{payment_id}", headers=_headers())
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")
    r.raise_for_status()
    return r.json()


def assinatura_valida(x_signature: str | None, x_request_id: str | None, data_id: str) -> bool:
    """Confere o cabeçalho x-signature do webhook (HMAC-SHA256 do manifesto
    `id:{data.id};request-id:{x-request-id};ts:{ts};`). Sem segredo configurado,
    aceita (o status é relido na API de qualquer forma)."""
    segredo = settings.MERCADOPAGO_WEBHOOK_SECRET
    if not segredo:
        return True
    if not x_signature:
        return False
    partes = dict(p.strip().split("=", 1) for p in x_signature.split(",") if "=" in p)
    ts, v1 = partes.get("ts"), partes.get("v1")
    if not ts or not v1:
        return False
    manifesto = f"id:{data_id.lower()};"
    if x_request_id:
        manifesto += f"request-id:{x_request_id};"
    manifesto += f"ts:{ts};"
    esperado = hmac.new(segredo.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, v1)
