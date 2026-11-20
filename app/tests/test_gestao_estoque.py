"""Gestão de estoque da loja (2026-11-20). Sem banco e sem rede.

Roda com: cd app && python -m pytest tests/test_gestao_estoque.py -v
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from core import schema_guard
from schemas.inventory import MovimentoCreate
from schemas.look import LookCreate, LookGestaoResponse, LookResponse
from service import inventory_service as inv
from service import look_service


def run(coro):
    return asyncio.run(coro)


# ── regra das movimentações ───────────────────────────────────────────────────

def test_entrada_e_devolucao_somam():
    assert inv.aplicar_movimento(2, 0, "entrada", 3) == inv.Efeito(5, 0, 3)
    assert inv.aplicar_movimento(0, 0, "devolucao", 1) == inv.Efeito(1, 0, 1)


def test_venda_externa_pode_consumir_a_reserva():
    # 2 em estoque, 2 reservadas (separadas no Instagram): vender 1 corta a reserva para 1
    assert inv.aplicar_movimento(2, 2, "venda_externa", 1) == inv.Efeito(1, 1, -1)


def test_venda_ou_perda_acima_do_estoque_400():
    for tipo in ("venda_externa", "perda"):
        with pytest.raises(HTTPException) as e:
            inv.aplicar_movimento(1, 0, tipo, 2)
        assert e.value.status_code == 400 and "Só há 1" in e.value.detail


def test_ajuste_define_o_total_e_corta_reserva():
    assert inv.aplicar_movimento(5, 4, "ajuste", 2) == inv.Efeito(2, 2, -3)
    with pytest.raises(HTTPException):
        inv.aplicar_movimento(5, 0, "ajuste", 5)  # nada mudou


def test_reserva_so_do_que_esta_disponivel():
    assert inv.aplicar_movimento(3, 1, "reserva", 2) == inv.Efeito(3, 3, 2)
    with pytest.raises(HTTPException) as e:
        inv.aplicar_movimento(3, 1, "reserva", 3)
    assert "2 disponível" in e.value.detail


def test_liberacao_nao_passa_do_reservado():
    assert inv.aplicar_movimento(3, 2, "liberacao", 2) == inv.Efeito(3, 0, -2)
    with pytest.raises(HTTPException):
        inv.aplicar_movimento(3, 2, "liberacao", 3)


def test_payload_de_movimento():
    with pytest.raises(ValidationError):
        MovimentoCreate(kind="entrada", quantity=0)
    with pytest.raises(ValidationError):
        MovimentoCreate(kind="venda_app", quantity=1)  # só o webhook grava venda_app
    assert MovimentoCreate(kind="ajuste", quantity=0).quantity == 0  # zerar no inventário


def test_novo_movimento_guarda_foto_do_estado():
    look = SimpleNamespace(id=uuid4(), seller_id=uuid4(), name="Jaqueta", stock_quantity=4,
                           reserved_quantity=1, cost_price=Decimal("30"))
    m = inv.novo_movimento(look, "venda_externa", -1, unit_price=Decimal("90"), channel="instagram")
    assert (m.look_name, m.stock_after, m.reserved_after, m.unit_cost) == ("Jaqueta", 4, 1, Decimal("30"))


# ── período e série das métricas ──────────────────────────────────────────────

def test_inicio_do_periodo_e_meia_noite_de_brasilia():
    agora = datetime(2026, 11, 20, 2, 0, tzinfo=timezone.utc)  # 19/11 23h em Brasília
    inicio = inv.inicio_do_periodo(7, agora)
    assert inicio == datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)  # 13/11 00h em Brasília


def test_serie_completa_dias_sem_venda_com_zero():
    inicio = datetime(2026, 11, 14, 3, 0, tzinfo=timezone.utc)
    pontos = {datetime(2026, 11, 15).date(): (Decimal("80"), 1)}
    serie = inv.serie_diaria(pontos, inicio, 7)
    assert len(serie) == 7
    assert serie[1]["revenue"] == Decimal("80") and serie[0]["revenue"] == Decimal("0")


def test_envio_do_pedido_e_o_do_item_mais_atrasado():
    assert inv._envio_do_conjunto(["shipped", "pending"]) == "pending"
    assert inv._envio_do_conjunto(["shipped", "delivered"]) == "shipped"
    assert inv._envio_do_conjunto(["delivered"]) == "delivered"


# ── custo nunca vai nas respostas públicas ────────────────────────────────────

def test_custo_so_na_visao_da_loja():
    assert "cost_price" not in LookResponse.model_fields
    assert "cost_price" in LookGestaoResponse.model_fields


def test_condicao_da_peca_validada():
    base = dict(category_id=uuid4(), name="Saia", photos=["x"])
    assert LookCreate(**base, condition="vintage").condition == "vintage"
    with pytest.raises(ValidationError):
        LookCreate(**base, condition="quase novo")


# ── peça vendida não pode ser apagada ─────────────────────────────────────────

class _Res:
    def __init__(self, valor):
        self.valor = valor

    def scalar_one_or_none(self):
        return self.valor


def test_apagar_peca_com_pedido_409():
    look = SimpleNamespace(id=uuid4())
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Res(uuid4()))
    db.delete = AsyncMock()
    look_service._get_manageable_look, original = AsyncMock(return_value=look), look_service._get_manageable_look
    try:
        with pytest.raises(HTTPException) as e:
            run(look_service.delete_look(db, uuid4(), look.id))
    finally:
        look_service._get_manageable_look = original
    assert e.value.status_code == 409
    db.delete.assert_not_awaited()


# ── guarda de schema: um passo falhando não trava os outros ──────────────────

class _ConnPassoQuebrado:
    def __init__(self):
        self.executados = []
        self.commits = 0

    async def execute(self, stmt):
        sql = str(stmt)
        self.executados.append(sql)
        if "order_items ADD COLUMN" in sql:
            raise RuntimeError("canceling statement due to lock timeout")
        return SimpleNamespace(first=lambda: None)

    async def commit(self):
        self.commits += 1


def test_guarda_segue_quando_um_passo_falha(monkeypatch):
    monkeypatch.delenv("SCHEMA_GUARD", raising=False)
    conn = _ConnPassoQuebrado()

    class _Engine:
        @asynccontextmanager
        async def connect(self):
            yield conn

    assert run(schema_guard.garantir_schema(_Engine())) is True
    assert conn.commits == len(schema_guard.PASSOS) - 1
    assert any("CREATE TABLE IF NOT EXISTS public.stock_movements" in s for s in conn.executados)


# ── coleções da loja ──────────────────────────────────────────────────────────

def test_nome_da_colecao_normaliza_espacos():
    from service import collection_service

    assert collection_service._nome("  Roupas   sessão de carnaval ") == "Roupas sessão de carnaval"
    with pytest.raises(HTTPException):
        collection_service._nome("   ")


def test_payload_de_colecao():
    from schemas.inventory import ColecaoCreate, ColecaoPecas

    with pytest.raises(ValidationError):
        ColecaoCreate(name="")
    with pytest.raises(ValidationError):
        ColecaoCreate(name="x" * 61)
    with pytest.raises(ValidationError):
        ColecaoPecas(look_ids=[])


def test_guarda_cria_tabelas_de_colecao(monkeypatch):
    ddl = " ".join(d for p in schema_guard.PASSOS for d in p.ddl)
    assert "store_collections" in ddl and "store_collection_items" in ddl
