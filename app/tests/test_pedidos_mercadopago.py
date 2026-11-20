"""Pedidos + Mercado Pago (2026-11-20). Sem banco e sem rede: a API do MP e a
sessão do banco são trocadas por dublês.

Roda com: cd app && python -m pytest tests/test_pedidos_mercadopago.py -v
"""
import asyncio
import hashlib
import hmac
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from core.config import settings
from model.orders import OrderStatus, PaymentMethod, PaymentStatus
from schemas.order import CheckoutRequest
from service import mercadopago_service as mp
from service import order_service


def run(coro):
    return asyncio.run(coro)


ENDERECO = {
    "street": "Rua A", "number": "10", "complement": "", "district": "Centro",
    "city": "São Paulo", "state": "SP", "postal_code": "01001-000",
}


# ── assinatura do webhook ─────────────────────────────────────────────────────

def _assinar(segredo, data_id, req_id, ts="1700000000"):
    manifesto = f"id:{data_id};request-id:{req_id};ts:{ts};"
    v1 = hmac.new(segredo.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


def test_assinatura_sem_segredo_aceita(monkeypatch):
    monkeypatch.setattr(settings, "MERCADOPAGO_WEBHOOK_SECRET", "")
    assert mp.assinatura_valida(None, None, "123")


def test_assinatura_correta_e_errada(monkeypatch):
    monkeypatch.setattr(settings, "MERCADOPAGO_WEBHOOK_SECRET", "segredo")
    assert mp.assinatura_valida(_assinar("segredo", "123", "req"), "req", "123")
    assert not mp.assinatura_valida(_assinar("outro", "123", "req"), "req", "123")
    assert not mp.assinatura_valida(None, "req", "123")


def test_sem_access_token_responde_503(monkeypatch):
    monkeypatch.setattr(settings, "MERCADOPAGO_ACCESS_TOKEN", "")
    with pytest.raises(HTTPException) as e:
        mp._headers()
    assert e.value.status_code == 503


# ── checkout ──────────────────────────────────────────────────────────────────

class _Resultado:
    def __init__(self, um=None, todos=None):
        self._um, self._todos = um, todos or []

    def scalar_one_or_none(self):
        return self._um

    def all(self):
        return self._todos


def _sessao(*resultados):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(resultados))
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


def test_checkout_carrinho_vazio_400():
    db = _sessao(_Resultado(um=None))
    with pytest.raises(HTTPException) as e:
        run(order_service.checkout(db, uuid4(), CheckoutRequest(address=ENDERECO)))
    assert e.value.status_code == 400


def _look(**kw):
    base = dict(id=uuid4(), name="Jaqueta", price=Decimal("159.00"), status="active",
                stock_quantity=5, reserved_quantity=0, photos=["https://x/foto.jpg"])
    base.update(kw)
    return SimpleNamespace(**base)


def test_checkout_sem_estoque_400():
    cart = SimpleNamespace(id=uuid4())
    item = SimpleNamespace(quantity=3)
    db = _sessao(_Resultado(um=cart), _Resultado(todos=[(item, _look(stock_quantity=1), "active")]))
    with pytest.raises(HTTPException) as e:
        run(order_service.checkout(db, uuid4(), CheckoutRequest(address=ENDERECO)))
    assert e.value.status_code == 400
    assert "restam 1" in e.value.detail


def test_checkout_cria_pedido_e_devolve_url():
    cart = SimpleNamespace(id=uuid4())
    look = _look()
    db = _sessao(_Resultado(um=cart), _Resultado(todos=[(SimpleNamespace(quantity=2), look, "active")]))
    with patch.object(mp, "criar_preferencia", AsyncMock(return_value=("PREF123", "https://mp/pagar"))) as criar:
        r = run(order_service.checkout(db, uuid4(), CheckoutRequest(address=ENDERECO)))
    assert r.total == Decimal("318.00")
    assert r.payment_url == "https://mp/pagar"
    itens = criar.call_args.kwargs["itens"]
    assert itens[0]["quantity"] == 2 and itens[0]["unit_price"] == Decimal("159.00")
    pedido = next(o for o in (c.args[0] for c in db.add.call_args_list) if type(o).__name__ == "Order")
    assert pedido.transaction_id == "pref:PREF123"
    assert pedido.status == OrderStatus.PENDING
    db.commit.assert_awaited()


# ── webhook / notificação ─────────────────────────────────────────────────────

def _pedido(total="318.00", pago=False):
    return SimpleNamespace(
        id=uuid4(), user_id=uuid4(), total_amount=Decimal(total),
        payment_status=PaymentStatus.APPROVED if pago else PaymentStatus.PENDING,
        status=OrderStatus.PAID if pago else OrderStatus.PENDING,
        payment_method=PaymentMethod.PIX, transaction_id="pref:X",
        items=[SimpleNamespace(look_id=uuid4(), quantity=2, unit_price=Decimal("159.00"), subtotal=Decimal("318.00"),
                               platform_fee_percent=None, platform_fee_amount=None, seller_net_amount=None, fee_rule=None,
                               mp_fee_amount=None)],
    )


def test_pagamento_aprovado_marca_pago_baixa_estoque_e_limpa_carrinho():
    pedido = _pedido()
    look = SimpleNamespace(id=uuid4(), seller_id=uuid4(), name="Jaqueta", stock_quantity=5,
                           reserved_quantity=4, cost_price=None)
    # pedido, config da taxa (sem linha = demo), carrinho, delete dos itens
    db = _sessao(_Resultado(um=pedido), _Resultado(um=None), _Resultado(um=SimpleNamespace(id=uuid4())), MagicMock())
    db.get = AsyncMock(side_effect=lambda cls, *a, **k: look if cls.__name__ == "Look" else SimpleNamespace(created_at=None))
    db.begin_nested = MagicMock(side_effect=lambda: _Savepoint())
    pagamento = {"status": "approved", "external_reference": str(pedido.id),
                 "transaction_amount": 318.0, "payment_type_id": "credit_card",
                 "fee_details": [{"type": "mercadopago_fee", "amount": 15.84, "fee_payer": "collector"}]}
    with patch.object(mp, "buscar_pagamento", AsyncMock(return_value=pagamento)):
        run(order_service.processar_notificacao(db, "999"))
    assert pedido.payment_status == PaymentStatus.APPROVED
    assert pedido.status == OrderStatus.PAID
    assert pedido.payment_method == PaymentMethod.CREDIT_CARD
    assert pedido.transaction_id == "999"
    assert look.stock_quantity == 3
    assert look.reserved_quantity == 3  # reserva nunca passa do estoque
    mov = next(o for o in (c.args[0] for c in db.add.call_args_list) if type(o).__name__ == "StockMovement")
    assert mov.kind == "venda_app" and mov.quantity == -2 and mov.order_id == pedido.id
    assert mov.stock_after == 3 and mov.unit_price == Decimal("159.00")
    assert db.execute.await_count == 4  # pedido, config da taxa, carrinho, delete dos itens
    item = pedido.items[0]
    assert item.platform_fee_percent == 0 and item.platform_fee_amount == 0
    # demo: 0% de taxa Lookly, mas a tarifa do MP sai do repasse
    assert pedido.mp_fee_amount == Decimal("15.84") and item.mp_fee_amount == Decimal("15.84")
    assert item.seller_net_amount == Decimal("302.16") and item.fee_rule == "demo"
    db.commit.assert_awaited()


class _Savepoint:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _SavepointQueFalha(_Savepoint):
    async def __aexit__(self, *exc):
        raise RuntimeError("relation stock_movements does not exist")


def test_historico_falhando_nao_impede_o_pagamento():
    """Se gravar no histórico de estoque falhar, o pedido ainda é marcado pago."""
    pedido = _pedido()
    look = SimpleNamespace(id=uuid4(), seller_id=uuid4(), name="Jaqueta", stock_quantity=5,
                           reserved_quantity=0, cost_price=None)
    db = _sessao(_Resultado(um=pedido), _Resultado(um=None), _Resultado(um=None))
    db.get = AsyncMock(return_value=look)
    db.begin_nested = MagicMock(side_effect=lambda: _SavepointQueFalha())
    pagamento = {"status": "approved", "external_reference": str(pedido.id), "transaction_amount": 318.0}
    with patch.object(mp, "buscar_pagamento", AsyncMock(return_value=pagamento)):
        run(order_service.processar_notificacao(db, "999"))
    assert pedido.payment_status == PaymentStatus.APPROVED
    assert look.stock_quantity == 3
    db.commit.assert_awaited()


def test_checkout_respeita_reserva_da_loja():
    cart = SimpleNamespace(id=uuid4())
    db = _sessao(_Resultado(um=cart), _Resultado(todos=[(SimpleNamespace(quantity=1), _look(stock_quantity=2, reserved_quantity=2), "active")]))
    with pytest.raises(HTTPException) as e:
        run(order_service.checkout(db, uuid4(), CheckoutRequest(address=ENDERECO)))
    assert e.value.status_code == 400 and "restam 0" in e.value.detail


def test_checkout_recusa_peca_de_loja_tirada_do_ar():
    cart = SimpleNamespace(id=uuid4())
    db = _sessao(_Resultado(um=cart), _Resultado(todos=[(SimpleNamespace(quantity=1), _look(), "under_review")]))
    with pytest.raises(HTTPException) as e:
        run(order_service.checkout(db, uuid4(), CheckoutRequest(address=ENDERECO)))
    assert e.value.status_code == 400 and "não está mais disponível" in e.value.detail


def test_notificacao_repetida_nao_baixa_estoque_de_novo():
    pedido = _pedido(pago=True)
    db = _sessao(_Resultado(um=pedido))
    db.get = AsyncMock()
    pagamento = {"status": "approved", "external_reference": str(pedido.id), "transaction_amount": 318.0}
    with patch.object(mp, "buscar_pagamento", AsyncMock(return_value=pagamento)):
        run(order_service.processar_notificacao(db, "999"))
    db.get.assert_not_awaited()


def test_valor_menor_que_o_pedido_nao_aprova():
    pedido = _pedido()
    db = _sessao(_Resultado(um=pedido))
    pagamento = {"status": "approved", "external_reference": str(pedido.id), "transaction_amount": 1.0}
    with patch.object(mp, "buscar_pagamento", AsyncMock(return_value=pagamento)):
        run(order_service.processar_notificacao(db, "999"))
    assert pedido.payment_status == PaymentStatus.PENDING


def test_pagamento_recusado():
    pedido = _pedido()
    db = _sessao(_Resultado(um=pedido))
    pagamento = {"status": "rejected", "external_reference": str(pedido.id), "transaction_amount": 318.0}
    with patch.object(mp, "buscar_pagamento", AsyncMock(return_value=pagamento)):
        run(order_service.processar_notificacao(db, "999"))
    assert pedido.payment_status == PaymentStatus.REFUSED


# ── rota do webhook ───────────────────────────────────────────────────────────

def test_rota_webhook_le_corpo_e_query(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    from db.database import get_db

    async def _db():
        yield MagicMock()

    main.app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(settings, "MERCADOPAGO_WEBHOOK_SECRET", "")
    try:
        with patch.object(order_service, "processar_notificacao", AsyncMock()) as proc:
            c = TestClient(main.app)
            assert c.post("/api/payments/webhook", json={"type": "payment", "data": {"id": "42"}}).status_code == 200
            assert c.post("/api/payments/webhook?topic=payment&id=43", json={}).status_code == 200
            assert c.post("/api/payments/webhook", json={"type": "merchant_order", "data": {"id": "1"}}).status_code == 200
        assert [call.args[1] for call in proc.await_args_list] == ["42", "43"]
    finally:
        main.app.dependency_overrides.clear()


def test_tarifa_do_pagamento():
    assert mp.tarifa_do_pagamento({"fee_details": [
        {"amount": 4.98, "fee_payer": "collector"}, {"amount": 2.0, "fee_payer": "payer"}]}) == Decimal("4.98")
    assert mp.tarifa_do_pagamento({"transaction_amount": 100,
                                   "transaction_details": {"net_received_amount": 99.01}}) == Decimal("0.99")
    assert mp.tarifa_do_pagamento({"transaction_amount": 100}) is None
