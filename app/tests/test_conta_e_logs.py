"""Testes da exclusão de conta, dos logs enviados pelo app e do guarda de schema.

Sem banco e sem rede: a sessão é falsa e registra o que foi executado, na ordem;
Supabase Auth e Storage são trocados por mocks que registram a chamada. A ordem
importa nesses fluxos (apagar a loja antes do perfil; Auth só depois do commit).

Roda com: cd app && python -m pytest tests/ -v
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError, IntegrityError

from core import log_scrub, schema_guard
from schemas.account import ClientLogLote, ExcluirContaRequest
from service import account_service, auth_admin_service, client_log_service, storage_service


def run(coro):
    return asyncio.run(coro)


# ── limpeza de dados sensíveis ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "sujo",
    [
        "token eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJl vazou",
        "Authorization: Bearer abc.def-123_xyz",
        "chave sb_publishable_ExemploFalso0123456789_abcdefghij",
        "senha=MinhaSenha123 no corpo",
        "password: hunter2",
        "falhou para maria.silva@exemplo.com.br",
        "cpf 123.456.789-09 inválido",
        "cnpj 12.345.678/0001-95 inválido",
        "doc 12345678909 e 12345678000195",
        "apikey=secreta123",
    ],
)
def test_dado_sensivel_vira_redigido(sujo):
    limpo = log_scrub.limpar(sujo)
    assert "[redigido]" in limpo
    for segredo in ("eyJ", "abc.def", "ExemploFalso0123", "MinhaSenha123", "hunter2", "maria.silva", "123.456.789-09",
                    "12.345.678/0001-95", "12345678909", "12345678000195", "secreta123"):
        assert segredo not in limpo


@pytest.mark.parametrize(
    "limpo",
    ["TypeError: undefined is not a function", "Network Error em /looks/search", "pedido 1234567890 (10 dígitos)",
     "preço 289,90 e tamanho 38", ""],
)
def test_texto_comum_passa_intacto(limpo):
    assert log_scrub.limpar(limpo) == limpo


def test_none_passa():
    assert log_scrub.limpar(None) is None


# ── schemas dos logs ──────────────────────────────────────────────────────────

def test_texto_gigante_e_cortado_nao_rejeitado():
    lote = ClientLogLote(entradas=[{"mensagem": "x" * 4000, "pilha": "y" * 9000, "tela": "t" * 500}])
    e = lote.entradas[0]
    assert len(e.mensagem) == 1000 and len(e.pilha) == 4000 and len(e.tela) == 80


def test_contexto_e_limitado():
    ctx = {f"k{i}": "v" * 500 for i in range(30)}
    e = ClientLogLote(entradas=[{"mensagem": "m", "contexto": ctx}]).entradas[0]
    assert len(e.contexto) == 10 and all(len(v) == 200 for v in e.contexto.values())


@pytest.mark.parametrize("entradas", [[], [{"mensagem": "m"}] * 21])
def test_lote_vazio_ou_grande_demais_rejeitado(entradas):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ClientLogLote(entradas=entradas)


def test_nivel_desconhecido_rejeitado():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ClientLogLote(entradas=[{"nivel": "debug", "mensagem": "m"}])


# ── registro no log do servidor ───────────────────────────────────────────────

def test_registrar_nao_vaza_segredo_e_e_uma_linha_so(caplog):
    lote = ClientLogLote(entradas=[{
        "mensagem": "falhou\nlinha forjada INFO fake\nBearer eyJabcde.fghij.klmno",
        "contexto": {"email": "a@b.com"},
    }])
    with caplog.at_level(logging.WARNING, logger="client"):
        n = client_log_service.registrar(lote, None)
    assert n == 1
    registros = [r for r in caplog.records if r.name == "client"]
    assert len(registros) == 1
    texto = registros[0].getMessage()
    assert "\n" not in texto  # quebra de linha virou \n escapado no JSON: nada de linhas forjadas
    assert "eyJabcde" not in texto and "a@b.com" not in texto
    assert registros[0].levelno == logging.ERROR


def test_nivel_do_log_acompanha_o_do_app(caplog):
    lote = ClientLogLote(entradas=[{"nivel": "warn", "mensagem": "a"}, {"nivel": "fatal", "mensagem": "b"}])
    with caplog.at_level(logging.DEBUG, logger="client"):
        client_log_service.registrar(lote, None)
    assert [r.levelno for r in caplog.records if r.name == "client"] == [logging.WARNING, logging.CRITICAL]


# ── camada HTTP dos logs ──────────────────────────────────────────────────────

@pytest.fixture
def http():
    from fastapi.testclient import TestClient
    import main
    yield TestClient(main.app), main
    main.app.dependency_overrides.clear()


def test_http_logs_aceita_sem_login(http, caplog):
    cliente, _ = http
    with caplog.at_level(logging.WARNING, logger="client"):
        r = cliente.post("/api/logs/client", json={"entradas": [{"mensagem": "boom"}], "app_versao": "1.0.0"})
    assert r.status_code == 202 and r.json() == {"recebidas": 1}
    assert '"user_id": null' in caplog.records[-1].getMessage()


def test_http_logs_token_valido_anexa_usuario(http, caplog):
    cliente, _ = http
    uid = uuid4()
    with patch("controller.log_controller.verify_supabase_token", return_value={"sub": str(uid)}):
        with caplog.at_level(logging.WARNING, logger="client"):
            r = cliente.post("/api/logs/client", json={"entradas": [{"mensagem": "boom"}]},
                             headers={"Authorization": "Bearer qualquer"})
    assert r.status_code == 202
    assert str(uid) in caplog.records[-1].getMessage()


def test_http_logs_token_invalido_nao_impede_o_log(http, caplog):
    cliente, _ = http
    with patch("controller.log_controller.verify_supabase_token", side_effect=HTTPException(401, "x")):
        with caplog.at_level(logging.WARNING, logger="client"):
            r = cliente.post("/api/logs/client", json={"entradas": [{"mensagem": "boom"}]},
                             headers={"Authorization": "Bearer vencido"})
    assert r.status_code == 202
    assert '"user_id": null' in caplog.records[-1].getMessage()


def test_http_logs_user_id_do_corpo_e_ignorado(http, caplog):
    cliente, _ = http
    with caplog.at_level(logging.WARNING, logger="client"):
        cliente.post("/api/logs/client", json={"entradas": [{"mensagem": "m", "user_id": str(uuid4())}]})
    assert '"user_id": null' in caplog.records[-1].getMessage()


def test_http_logs_corpo_enorme_413(http):
    cliente, _ = http
    r = cliente.post("/api/logs/client", content=b"x" * 70000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_http_logs_corpo_invalido_422(http):
    cliente, _ = http
    assert cliente.post("/api/logs/client", json={"entradas": []}).status_code == 422


# ── exclusão de conta: HTTP ───────────────────────────────────────────────────

def test_http_excluir_exige_login(http):
    cliente, _ = http
    # sem token: 401 nas versões novas do FastAPI, 403 nas antigas — nunca 2xx
    assert cliente.request("DELETE", "/api/profiles/me", json={"confirmacao": "EXCLUIR"}).status_code in (401, 403)


def test_http_excluir_exige_a_palavra_de_confirmacao(http):
    cliente, main = http
    from dependencies.auth import get_current_user_id
    main.app.dependency_overrides[get_current_user_id] = lambda: uuid4()
    with patch.object(account_service, "excluir_conta", AsyncMock()) as exc:
        assert cliente.request("DELETE", "/api/profiles/me").status_code == 422
        assert cliente.request("DELETE", "/api/profiles/me", json={"confirmacao": "excluir"}).status_code == 422
        assert cliente.request("DELETE", "/api/profiles/me", json={"confirmacao": "SIM"}).status_code == 422
        exc.assert_not_called()


def test_http_excluir_com_confirmacao_204(http):
    cliente, main = http
    from dependencies.auth import get_current_user_id
    from db.database import get_db
    uid = uuid4()
    main.app.dependency_overrides[get_current_user_id] = lambda: uid

    async def _db():
        yield SimpleNamespace()

    main.app.dependency_overrides[get_db] = _db
    with patch.object(account_service, "excluir_conta", AsyncMock()) as exc:
        r = cliente.request("DELETE", "/api/profiles/me", json={"confirmacao": "EXCLUIR"})
    assert r.status_code == 204 and r.content == b""
    assert exc.call_args.args[1] == uid  # o id vem do token, não do corpo


def test_confirmacao_so_aceita_a_palavra_exata():
    from pydantic import ValidationError
    assert ExcluirContaRequest(confirmacao="EXCLUIR")
    with pytest.raises(ValidationError):
        ExcluirContaRequest(confirmacao="Excluir")


# ── exclusão de conta: serviço ────────────────────────────────────────────────

class FakeResultado:
    def __init__(self, valor=None):
        self._v = valor

    def scalar_one_or_none(self):
        return self._v

    def first(self):
        return self._v


class FakeDB:
    """Registra, em ordem, o que foi executado/commitado."""

    def __init__(self, profile=object(), commit_exc=None):
        self.profile = profile
        self.commit_exc = commit_exc
        self.eventos: list[str] = []

    async def execute(self, stmt, params=None):
        texto = str(stmt)
        if texto.lstrip().upper().startswith("SELECT"):
            return FakeResultado(self.profile)
        if "look_views" in texto and "user_id" in texto:
            self.eventos.append("apaga_views_do_usuario")
        elif "look_views" in texto:
            self.eventos.append("apaga_views_das_pecas")
        elif "DELETE FROM sellers" in texto:
            self.eventos.append("apaga_loja")
        elif "DELETE FROM profiles" in texto:
            self.eventos.append("apaga_perfil")
        else:
            self.eventos.append("outro: " + texto[:40])
        return FakeResultado()

    async def commit(self):
        if self.commit_exc:
            raise self.commit_exc
        self.eventos.append("commit")

    async def rollback(self):
        self.eventos.append("rollback")

    @asynccontextmanager
    async def begin_nested(self):
        yield


def servico(db, seller=None, pedidos=False, auth_exc=None):
    """Roda excluir_conta com Auth/Storage/lojas/pedidos trocados por mocks e
    devolve a lista de eventos (inclui as chamadas externas, na ordem)."""
    async def _storage(uid):
        db.eventos.append("storage")
        return 0

    async def _auth(uid):
        db.eventos.append("auth")
        if auth_exc:
            raise auth_exc

    with patch.object(account_service.seller_service, "get_seller_by_owner", AsyncMock(return_value=seller)), \
         patch.object(account_service, "_tem_pedidos", AsyncMock(return_value=pedidos)), \
         patch.object(account_service.storage_service, "remover_pasta_do_usuario", _storage), \
         patch.object(account_service.auth_admin_service, "excluir_usuario", _auth):
        run(account_service.excluir_conta(db, uuid4()))
    return db.eventos


def test_usuario_comum_apaga_views_perfil_e_so_depois_o_auth():
    ev = servico(FakeDB())
    assert ev == ["apaga_views_do_usuario", "apaga_perfil", "commit", "storage", "auth"]


def test_dono_de_loja_apaga_a_loja_antes_do_perfil():
    ev = servico(FakeDB(), seller=SimpleNamespace(id=uuid4()))
    assert ev == ["apaga_views_do_usuario", "apaga_views_das_pecas", "apaga_loja", "apaga_perfil", "commit", "storage", "auth"]
    assert ev.index("apaga_loja") < ev.index("apaga_perfil")  # owner_profile_id é RESTRICT


def test_pedidos_bloqueiam_com_409_sem_apagar_nada():
    db = FakeDB()
    with pytest.raises(HTTPException) as e:
        servico(db, pedidos=True)
    assert e.value.status_code == 409
    assert db.eventos == []  # nem banco, nem Storage, nem Auth


def test_erro_de_integridade_faz_rollback_e_nao_toca_no_auth():
    db = FakeDB(commit_exc=IntegrityError("stmt", {}, Exception("fk")))
    with pytest.raises(HTTPException) as e:
        servico(db)
    assert e.value.status_code == 409
    assert "rollback" in db.eventos and "auth" not in db.eventos and "storage" not in db.eventos


def test_perfil_ja_apagado_ainda_conclui_no_auth():
    ev = servico(FakeDB(profile=None))
    assert ev == ["storage", "auth"]  # repetir a exclusão (após falha do Auth) termina o serviço


def test_falha_no_auth_propaga_depois_do_commit():
    db = FakeDB()
    with pytest.raises(HTTPException) as e:
        servico(db, auth_exc=HTTPException(status_code=502, detail="x"))
    assert e.value.status_code == 502
    assert db.eventos.index("commit") < db.eventos.index("auth")  # dados já saíram: dá para repetir


class BDSemTabelas(FakeDB):
    """Simula banco sem as tabelas de pedido: a consulta levanta ProgrammingError."""

    async def execute(self, stmt, params=None):
        raise DBAPIError("stmt", {}, Exception("relation orders does not exist"))


def test_tabelas_de_pedido_inexistentes_nao_travam_a_exclusao():
    resultado = run(account_service._tem_pedidos(BDSemTabelas(), uuid4(), None))
    assert resultado is False


def test_tem_pedidos_detecta_pedido_do_comprador():
    class DB(FakeDB):
        async def execute(self, stmt, params=None):
            return FakeResultado((1,))
    assert run(account_service._tem_pedidos(DB(), uuid4(), None)) is True


# ── Auth e Storage ────────────────────────────────────────────────────────────

def _cliente_http(status_code):
    client = AsyncMock()
    client.delete.return_value = SimpleNamespace(status_code=status_code)
    client.__aenter__.return_value = client
    return client


@pytest.mark.parametrize("codigo", [200, 204, 404])
def test_auth_aceita_sucesso_e_ja_inexistente(codigo):
    with patch.object(auth_admin_service.httpx, "AsyncClient", return_value=_cliente_http(codigo)), \
         patch.object(auth_admin_service.settings, "SUPABASE_URL", "https://x.supabase.co"), \
         patch.object(auth_admin_service.settings, "SUPABASE_SERVICE_KEY", "chave"):
        run(auth_admin_service.excluir_usuario(uuid4()))


@pytest.mark.parametrize("codigo", [400, 401, 500])
def test_auth_recusa_vira_502(codigo):
    with patch.object(auth_admin_service.httpx, "AsyncClient", return_value=_cliente_http(codigo)), \
         patch.object(auth_admin_service.settings, "SUPABASE_URL", "https://x.supabase.co"), \
         patch.object(auth_admin_service.settings, "SUPABASE_SERVICE_KEY", "chave"):
        with pytest.raises(HTTPException) as e:
            run(auth_admin_service.excluir_usuario(uuid4()))
    assert e.value.status_code == 502


def test_auth_sem_chave_configurada_503():
    with patch.object(auth_admin_service.settings, "SUPABASE_SERVICE_KEY", ""):
        with pytest.raises(HTTPException) as e:
            run(auth_admin_service.excluir_usuario(uuid4()))
    assert e.value.status_code == 503


def test_storage_remove_arquivos_do_usuario_e_nunca_propaga_erro():
    uid = uuid4()
    client = AsyncMock()
    listagens = [
        SimpleNamespace(status_code=200, json=lambda: [{"name": "a.png"}, {"name": "b.jpg"}]),
        SimpleNamespace(status_code=200, json=lambda: []),
    ]
    client.post.side_effect = listagens
    client.request.return_value = SimpleNamespace(status_code=200)
    client.__aenter__.return_value = client
    with patch.object(storage_service.httpx, "AsyncClient", return_value=client), \
         patch.object(storage_service.settings, "SUPABASE_URL", "https://x.supabase.co"), \
         patch.object(storage_service.settings, "SUPABASE_SERVICE_KEY", "chave"):
        assert run(storage_service.remover_pasta_do_usuario(uid)) == 2
    corpo = client.request.call_args.kwargs["json"]
    assert corpo == {"prefixes": [f"{uid}/a.png", f"{uid}/b.jpg"]}  # só a pasta DELE

    boom = AsyncMock()
    boom.__aenter__.side_effect = RuntimeError("rede caiu")
    with patch.object(storage_service.httpx, "AsyncClient", return_value=boom), \
         patch.object(storage_service.settings, "SUPABASE_URL", "https://x.supabase.co"), \
         patch.object(storage_service.settings, "SUPABASE_SERVICE_KEY", "chave"):
        assert run(storage_service.remover_pasta_do_usuario(uid)) == 0


# ── guarda de schema ──────────────────────────────────────────────────────────

class FakeConn:
    def __init__(self, coluna_existe):
        self.coluna_existe = coluna_existe
        self.executados: list[str] = []
        self.commits = 0

    async def execute(self, stmt):
        self.executados.append(str(stmt))
        return FakeResultado((1,) if self.coluna_existe else None)

    async def commit(self):
        self.commits += 1


class FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def connect(self):
        yield self.conn


def test_guarda_nao_mexe_na_tabela_quando_a_coluna_existe(monkeypatch):
    monkeypatch.delenv("SCHEMA_GUARD", raising=False)
    conn = FakeConn(coluna_existe=True)
    assert run(schema_guard.garantir_schema(FakeEngine(conn))) is False
    assert len(conn.executados) == 1 and "information_schema" in conn.executados[0]
    assert conn.commits == 0


def test_guarda_cria_coluna_e_indices_quando_falta(monkeypatch):
    monkeypatch.delenv("SCHEMA_GUARD", raising=False)
    conn = FakeConn(coluna_existe=False)
    assert run(schema_guard.garantir_schema(FakeEngine(conn))) is True
    ddl = " ".join(conn.executados)
    assert "ADD COLUMN IF NOT EXISTS sizes" in ddl and "idx_looks_sizes" in ddl and "idx_looks_price" in ddl
    assert conn.commits == 1


def test_guarda_desligado_por_variavel(monkeypatch):
    monkeypatch.setenv("SCHEMA_GUARD", "0")
    conn = FakeConn(coluna_existe=False)
    assert run(schema_guard.garantir_schema(FakeEngine(conn))) is False
    assert conn.executados == []


def test_subida_do_app_sobrevive_a_banco_indisponivel(caplog):
    import main

    async def banco_pausado(engine):
        raise ConnectionError("connection refused")

    async def subir():
        async with main.lifespan(main.app):
            return "subiu"

    with patch("core.schema_guard.garantir_schema", banco_pausado):
        assert run(subir()) == "subiu"
    assert any("Schema guard" in r.getMessage() for r in caplog.records)
