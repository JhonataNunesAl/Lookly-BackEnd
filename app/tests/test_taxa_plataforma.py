"""Taxa da plataforma (2026-11-20). Sem banco e sem rede.

Roda com: cd app && python -m pytest tests/test_taxa_plataforma.py -v
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core import schema_guard
from schemas.platform_fee import PlatformFeeConfigUpdate
from service import platform_fee_service as svc

UTC = timezone.utc
FIM_DEMO = datetime(2027, 1, 31, 12, 0, tzinfo=UTC)
REGRA = svc.Regra(demo_ends_at=FIM_DEMO, fee_percent=Decimal("11"), grace_days=60)


def run(coro):
    return asyncio.run(coro)


# ── regra ─────────────────────────────────────────────────────────────────────

def test_sem_fim_de_demo_e_zero_para_todos():
    t = svc.taxa_em(svc.REGRA_PADRAO, datetime(2020, 1, 1, tzinfo=UTC), datetime(2030, 1, 1, tzinfo=UTC))
    assert t.percent == 0 and t.fase == "demo" and t.fim_carencia is None


def test_antes_do_fim_da_demo_e_zero():
    t = svc.taxa_em(REGRA, datetime(2026, 11, 1, tzinfo=UTC), FIM_DEMO - timedelta(seconds=1))
    assert t.percent == 0 and t.fase == "demo"


def test_loja_da_demo_ganha_60_dias_a_partir_do_fim_da_demo():
    loja = datetime(2026, 11, 1, tzinfo=UTC)  # entrou na demo
    t = svc.taxa_em(REGRA, loja, FIM_DEMO + timedelta(days=59))
    assert t.percent == 0 and t.fase == "carencia"
    assert t.fim_carencia == FIM_DEMO + timedelta(days=60)
    t = svc.taxa_em(REGRA, loja, FIM_DEMO + timedelta(days=60))
    assert t.percent == Decimal("11") and t.fase == "padrao"


def test_loja_nova_depois_da_demo_conta_do_cadastro():
    loja = FIM_DEMO + timedelta(days=100)
    assert svc.taxa_em(REGRA, loja, loja + timedelta(days=30)).fase == "carencia"
    assert svc.taxa_em(REGRA, loja, loja + timedelta(days=61)).percent == Decimal("11")


def test_datas_sem_fuso_sao_utc():
    t = svc.taxa_em(REGRA, None, datetime(2030, 1, 1))  # orders.created_at é timestamp sem fuso
    assert t.fase == "padrao"


def test_divisao_em_centavos():
    assert svc.dividir(Decimal("100.00"), Decimal("11")) == (Decimal("11.00"), Decimal("89.00"))
    assert svc.dividir(Decimal("59.90"), Decimal("11")) == (Decimal("6.59"), Decimal("53.31"))
    assert svc.dividir(Decimal("59.90"), Decimal("0")) == (Decimal("0.00"), Decimal("59.90"))


# ── por peça ──────────────────────────────────────────────────────────────────

def _item(**kw):
    base = dict(subtotal=Decimal("200.00"), platform_fee_percent=None, platform_fee_amount=None,
                seller_net_amount=None, fee_rule=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_aplicar_no_item_congela_a_taxa():
    item = _item()
    svc.aplicar_no_item(item, REGRA, None, FIM_DEMO + timedelta(days=90))
    assert item.platform_fee_percent == Decimal("11")
    assert item.platform_fee_amount == Decimal("22.00") and item.seller_net_amount == Decimal("178.00")
    assert item.fee_rule == "padrao"


def test_taxa_gravada_vence_a_regra_atual():
    item = _item(platform_fee_percent=Decimal("0"), platform_fee_amount=Decimal("0"),
                 seller_net_amount=Decimal("200.00"), fee_rule="demo")
    assert svc.taxa_do_item(item, REGRA, None, datetime(2030, 1, 1)) == (0, 0, Decimal("200.00"), "demo")


def test_sem_taxa_gravada_usa_a_regra_na_data_do_pedido():
    pct, taxa, liquido, fase = svc.taxa_do_item(_item(), REGRA, None, datetime(2030, 1, 1))
    assert (pct, taxa, liquido, fase) == (Decimal("11"), Decimal("22.00"), Decimal("178.00"), "padrao")


class _Savepoint:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _db(linha):
    db = MagicMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: linha))
    db.begin_nested = MagicMock(side_effect=lambda: _Savepoint())
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


def test_congelar_taxas_usa_cadastro_de_cada_loja():
    linha = SimpleNamespace(demo_ends_at=FIM_DEMO, fee_percent=Decimal("11"), grace_days=60)
    antiga, nova = uuid4(), uuid4()
    db = _db(linha)
    criadas = {antiga: datetime(2026, 11, 1, tzinfo=UTC), nova: FIM_DEMO + timedelta(days=80)}
    db.get = AsyncMock(side_effect=lambda cls, sid: SimpleNamespace(created_at=criadas[sid]))
    a, b = _item(), _item()
    run(svc.congelar_taxas(db, [(a, antiga), (b, nova)], FIM_DEMO + timedelta(days=90)))
    assert a.fee_rule == "padrao" and a.platform_fee_amount == Decimal("22.00")
    assert b.fee_rule == "carencia" and b.platform_fee_amount == Decimal("0.00")
    assert db.get.await_count == 2


def test_congelar_taxas_nunca_derruba_o_pagamento():
    db = _db(None)
    db.execute = AsyncMock(side_effect=RuntimeError("relation platform_fee_config does not exist"))
    item = _item()
    run(svc.congelar_taxas(db, [(item, uuid4())], datetime.now(UTC)))  # não levanta
    assert item.platform_fee_percent is None


def test_regra_atual_sem_tabela_e_demo():
    db = _db(None)
    db.execute = AsyncMock(side_effect=RuntimeError("boom"))
    assert run(svc.regra_atual(db)) == svc.REGRA_PADRAO


# ── admin ─────────────────────────────────────────────────────────────────────

def test_encerrar_demo_agora_e_mudar_percentual():
    linha = SimpleNamespace(demo_ends_at=None, fee_percent=Decimal("11"), grace_days=60, updated_at=None, updated_by=None)
    db = _db(linha)
    admin = uuid4()
    r = run(svc.atualizar_config(db, PlatformFeeConfigUpdate(end_demo_now=True, fee_percent=Decimal("9.5")), admin))
    assert linha.demo_ends_at is not None and linha.fee_percent == Decimal("9.5") and linha.updated_by == admin
    assert r["demo_active"] is False
    db.commit.assert_awaited()


def test_reabrir_demo_com_null():
    linha = SimpleNamespace(demo_ends_at=FIM_DEMO, fee_percent=Decimal("11"), grace_days=60, updated_at=None, updated_by=None)
    db = _db(linha)
    r = run(svc.atualizar_config(db, PlatformFeeConfigUpdate(demo_ends_at=None), uuid4()))
    assert linha.demo_ends_at is None and r["demo_active"] is True


def test_campo_nao_enviado_nao_muda():
    linha = SimpleNamespace(demo_ends_at=FIM_DEMO, fee_percent=Decimal("11"), grace_days=60, updated_at=None, updated_by=None)
    run(svc.atualizar_config(_db(linha), PlatformFeeConfigUpdate(grace_days=90), uuid4()))
    assert linha.demo_ends_at == FIM_DEMO and linha.grace_days == 90


@pytest.mark.parametrize("dados", [
    {"fee_percent": "60"}, {"fee_percent": "-1"}, {"grace_days": 1000},
    {"end_demo_now": True, "demo_ends_at": "2027-01-31T12:00:00Z"},
    {"demo_ends_at": "2027-01-31T12:00:00"},  # sem fuso
])
def test_atualizacao_invalida(dados):
    with pytest.raises(ValidationError):
        PlatformFeeConfigUpdate(**dados)


# ── o que a loja vê ───────────────────────────────────────────────────────────

def test_mensagem_da_loja_por_fase():
    loja = datetime(2026, 11, 1, tzinfo=UTC)
    demo = svc.taxa_da_loja(svc.REGRA_PADRAO, loja)
    assert demo["phase"] == "demo" and demo["current_percent"] == 0 and "valor inteiro" in demo["message"]
    car = svc.taxa_da_loja(REGRA, loja, FIM_DEMO + timedelta(days=1))
    assert car["phase"] == "carencia" and "01/04/2027" in car["message"]
    pad = svc.taxa_da_loja(REGRA, loja, FIM_DEMO + timedelta(days=61))
    assert pad["current_percent"] == Decimal("11") and "11%" in pad["message"]


def test_guarda_de_schema_tem_o_passo_da_taxa():
    passo = schema_guard.PASSOS[-1]
    assert "order_items" in passo.existe and "payout_status" in passo.existe
    sql = " ".join(passo.ddl)
    assert "platform_fee_config" in sql and "seller_net_amount" in sql and "fee_rule = 'demo'" in sql
