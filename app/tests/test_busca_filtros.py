"""Testes dos filtros da busca de looks (preço, tamanho, estoque, ordem).

Sem banco: a sessão falsa captura a query que o service monta, e a comparamos
como SQL com literais embutidos (mesma técnica de test_audit_fixes.py). Isso
prova a QUERY — que o Postgres a execute certo é garantido pelo próprio banco.

Roda com: cd app && python -m pytest tests/ -v
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from schemas.look import LookCreate, LookFiltros, LookUpdate, normalizar_tamanhos
from service import look_service


def run(coro):
    return asyncio.run(coro)


class _Resultado:
    def __init__(self, itens):
        self._itens = itens

    def scalars(self):
        return SimpleNamespace(all=lambda: self._itens)


class SessaoCaptura:
    """Guarda a query e devolve os itens combinados."""

    def __init__(self, itens=()):
        self.itens = list(itens)
        self.query = None

    async def execute(self, query):
        self.query = query
        return _Resultado(self.itens)


def sql(sessao) -> str:
    return str(sessao.query.compile(compile_kwargs={"literal_binds": True}))


def buscar(filtros=None, cursor=None, limit=20, itens=()):
    s = SessaoCaptura(itens)
    resultado = run(look_service.search_looks(s, None, None, limit, cursor, filtros=filtros))
    return s, resultado


def look(created="2026-10-01T10:00:00+00:00"):
    return SimpleNamespace(created_at=datetime.fromisoformat(created))


# ── tamanhos ──────────────────────────────────────────────────────────────────

def test_tamanhos_sao_normalizados_e_ordenados():
    assert normalizar_tamanhos(["g", " M ", "p", "m"]) == ["P", "M", "G"]


def test_tamanho_unico_aceita_sem_acento():
    assert normalizar_tamanhos(["unico"]) == ["Único"]


def test_tamanho_numerico_valido():
    assert normalizar_tamanhos(["38", "40"]) == ["38", "40"]


@pytest.mark.parametrize("ruim", [["XXL"], ["medio"], ["32"], ["49"], [""], ["P", "banana"]])
def test_tamanho_invalido_rejeitado(ruim):
    with pytest.raises(ValueError):
        normalizar_tamanhos(ruim)


def test_look_aceita_e_normaliza_sizes():
    dados = LookCreate(
        category_id="00000000-0000-0000-0000-000000000001",
        name="Camisa", photos=["https://x/a.jpg"], sizes=["g", "m"],
    )
    assert dados.sizes == ["M", "G"]


def test_look_sem_sizes_fica_vazio():
    dados = LookCreate(
        category_id="00000000-0000-0000-0000-000000000001", name="Camisa", photos=["https://x/a.jpg"],
    )
    assert dados.sizes == []


def test_look_update_sizes_invalido_rejeitado():
    with pytest.raises(ValidationError):
        LookUpdate(sizes=["GGGG"])


def test_look_update_sem_sizes_nao_toca_no_campo():
    assert "sizes" not in LookUpdate(name="Novo nome").model_dump(exclude_unset=True)


# ── filtros: validação ────────────────────────────────────────────────────────

def test_faixa_de_preco_invertida_rejeitada():
    with pytest.raises(ValidationError):
        LookFiltros(price_min=Decimal("200"), price_max=Decimal("100"))


def test_faixa_de_preco_igual_aceita():
    LookFiltros(price_min=Decimal("100"), price_max=Decimal("100"))


def test_preco_negativo_rejeitado():
    with pytest.raises(ValidationError):
        LookFiltros(price_min=Decimal("-1"))


def test_ordem_desconhecida_rejeitada():
    with pytest.raises(ValidationError):
        LookFiltros(sort="aleatoria")


def test_filtros_ativo():
    assert not LookFiltros().ativo
    assert not LookFiltros(sort="price_asc").ativo  # ordem sozinha não é filtro
    assert LookFiltros(in_stock=True).ativo
    assert LookFiltros(sizes=["M"]).ativo
    assert LookFiltros(price_max=Decimal("50")).ativo


# ── query montada ─────────────────────────────────────────────────────────────

def test_sem_filtros_busca_igual_a_de_antes():
    s, _ = buscar()
    q = sql(s)
    assert "looks.status = 'active'" in q
    assert "ORDER BY looks.created_at DESC" in q
    onde = q.split("WHERE")[1].split("ORDER BY")[0]  # a lista de colunas do SELECT cita price/sizes
    assert "price" not in onde and "sizes" not in onde and "stock" not in onde


def test_preco_minimo_e_maximo():
    s, _ = buscar(LookFiltros(price_min=Decimal("100"), price_max=Decimal("300")))
    q = sql(s)
    assert "looks.price >= 100" in q
    assert "looks.price <= 300" in q


def test_so_preco_maximo_nao_cria_minimo():
    s, _ = buscar(LookFiltros(price_max=Decimal("300")))
    q = sql(s)
    assert "looks.price <= 300" in q and "looks.price >=" not in q


def test_tamanho_usa_sobreposicao_de_arrays():
    s, _ = buscar(LookFiltros(sizes=["M", "G"]))
    q = sql(s)
    assert "looks.sizes &&" in q
    assert "'M'" in q and "'G'" in q


def test_so_com_estoque():
    s, _ = buscar(LookFiltros(in_stock=True))
    assert "looks.stock_quantity > 0" in sql(s)


def test_filtros_combinam_com_and():
    s, _ = buscar(LookFiltros(price_min=Decimal("10"), sizes=["P"], in_stock=True))
    q = sql(s).split("ORDER BY")[0]
    assert q.count("AND") >= 3


@pytest.mark.parametrize(
    "ordem,trecho",
    [
        ("price_asc", "looks.price ASC NULLS LAST"),
        ("price_desc", "looks.price DESC NULLS LAST"),
        ("popular", "looks.likes_count + 2 * looks.saves_count"),
    ],
)
def test_ordens(ordem, trecho):
    s, _ = buscar(LookFiltros(sort=ordem))
    q = sql(s)
    assert trecho in q
    assert "looks.id ASC" in q  # desempate: páginas por deslocamento não repetem itens


# ── paginação ─────────────────────────────────────────────────────────────────

def test_recent_pagina_por_data():
    s, r = buscar(limit=2, itens=[look("2026-10-02T00:00:00+00:00"), look("2026-10-01T00:00:00+00:00")])
    assert r["next_cursor"] == "2026-10-01T00:00:00+00:00"


def test_recent_usa_cursor_como_data_de_corte():
    s, _ = buscar(cursor="2026-10-01T00:00:00+00:00")
    assert "looks.created_at < '2026-10-01 00:00:00+00:00'" in sql(s)


def test_recent_aceita_cursor_datetime_do_endpoint_da_loja():
    s, _ = buscar(cursor=datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert "looks.created_at <" in sql(s)


def test_outras_ordens_paginam_por_deslocamento():
    f = LookFiltros(sort="price_asc")
    s1, r1 = buscar(f, limit=2, itens=[look(), look()])
    assert r1["next_cursor"] == "2"
    s2, r2 = buscar(f, cursor="2", limit=2, itens=[look(), look()])
    assert "OFFSET 2" in sql(s2)
    assert r2["next_cursor"] == "4"


def test_ultima_pagina_sem_proximo_cursor():
    _, r = buscar(LookFiltros(sort="popular"), limit=5, itens=[look()])
    assert r["next_cursor"] is None


def test_cursor_invalido_vira_400():
    with pytest.raises(HTTPException) as e:
        buscar(cursor="isso-nao-e-data")
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e2:
        buscar(LookFiltros(sort="price_asc"), cursor="abc")
    assert e2.value.status_code == 400


def test_cursor_negativo_vira_zero():
    s, _ = buscar(LookFiltros(sort="price_asc"), cursor="-5")
    assert "OFFSET" not in sql(s)


# ── camada HTTP (parâmetros da query → filtros) ───────────────────────────────

@pytest.fixture
def cliente_http():
    """TestClient do app com o banco trocado pela sessão que captura a query."""
    from fastapi.testclient import TestClient

    import main
    from db.database import get_db

    sessao = SessaoCaptura()

    async def _db():
        yield sessao

    main.app.dependency_overrides[get_db] = _db
    yield TestClient(main.app), sessao
    main.app.dependency_overrides.clear()


def test_http_filtros_chegam_na_query(cliente_http):
    cliente, sessao = cliente_http
    r = cliente.get("/api/looks/search?sizes=M&sizes=g&price_min=100&price_max=300&sort=price_asc&in_stock=true")
    assert r.status_code == 200
    q = sql(sessao)
    assert "looks.price >= 100" in q and "looks.price <= 300" in q
    assert "looks.sizes && ARRAY['M', 'G']" in q  # "g" foi normalizado
    assert "looks.stock_quantity > 0" in q
    assert "ORDER BY looks.price ASC NULLS LAST" in q


def test_http_sem_parametros_continua_a_busca_de_sempre(cliente_http):
    cliente, sessao = cliente_http
    assert cliente.get("/api/looks/search").status_code == 200
    assert "ORDER BY looks.created_at DESC" in sql(sessao)


@pytest.mark.parametrize(
    "qs,codigo",
    [
        ("sizes=XXL", 422),
        ("price_min=300&price_max=100", 422),
        ("price_min=-1", 422),
        ("sort=aleatoria", 422),
        ("cursor=lixo", 400),
        ("sort=price_asc&cursor=abc", 400),
    ],
)
def test_http_parametros_invalidos(cliente_http, qs, codigo):
    cliente, _ = cliente_http
    assert cliente.get(f"/api/looks/search?{qs}").status_code == codigo
