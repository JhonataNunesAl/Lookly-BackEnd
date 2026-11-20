"""Painel de administração (2026-11-20). Sem banco e sem rede.

Roda com: cd app && python -m pytest tests/test_admin.py -v
(O fluxo completo das rotas foi exercitado também contra um Postgres local com o
schema.sql — ver a descrição do PR.)
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from dependencies import admin as adm
from service import admin_service


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _limpa_cache(monkeypatch):
    adm._cache.clear()
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    yield
    adm._cache.clear()


def _payload(uid, email):
    return {"sub": str(uid), "email": email}


def test_email_padrao_do_admin():
    assert adm.emails_admin() == {"yorn.exe@gmail.com"}


def test_admin_emails_por_variavel(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", " A@x.com, b@y.com ,")
    assert adm.emails_admin() == {"a@x.com", "b@y.com"}


def test_conta_comum_e_barrada_sem_ir_ao_banco():
    db = MagicMock()
    with patch.object(adm, "_confirmado_no_banco", AsyncMock()) as banco:
        with pytest.raises(HTTPException) as e:
            run(adm.require_admin(_payload(uuid4(), "cliente@x.com"), db))
    assert e.value.status_code == 403
    banco.assert_not_awaited()


def test_admin_confirmado_passa_e_fica_em_cache():
    uid = uuid4()
    with patch.object(adm, "_confirmado_no_banco", AsyncMock(return_value=("yorn.exe@gmail.com", True))) as banco:
        assert run(adm.require_admin(_payload(uid, "Yorn.Exe@gmail.com"), MagicMock())) == uid
        assert run(adm.require_admin(_payload(uid, "yorn.exe@gmail.com"), MagicMock())) == uid
    assert banco.await_count == 1


def test_email_do_admin_sem_confirmacao_e_barrado():
    with patch.object(adm, "_confirmado_no_banco", AsyncMock(return_value=("yorn.exe@gmail.com", False))):
        with pytest.raises(HTTPException) as e:
            run(adm.require_admin(_payload(uuid4(), "yorn.exe@gmail.com"), MagicMock()))
    assert e.value.status_code == 403


def test_token_diz_admin_mas_conta_tem_outro_email():
    with patch.object(adm, "_confirmado_no_banco", AsyncMock(return_value=("outro@x.com", True))):
        with pytest.raises(HTTPException) as e:
            run(adm.require_admin(_payload(uuid4(), "yorn.exe@gmail.com"), MagicMock()))
    assert e.value.status_code == 403


def test_sem_banco_usa_api_do_supabase():
    uid = uuid4()
    with patch.object(adm, "_confirmado_no_banco", AsyncMock(return_value=None)), \
         patch.object(adm, "_confirmado_na_api", AsyncMock(return_value=("yorn.exe@gmail.com", True))) as api:
        assert run(adm.require_admin(_payload(uid, "yorn.exe@gmail.com"), MagicMock())) == uid
    api.assert_awaited_once()


def test_sem_como_confirmar_nunca_libera():
    with patch.object(adm, "_confirmado_no_banco", AsyncMock(return_value=None)), \
         patch.object(adm, "_confirmado_na_api", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as e:
            run(adm.require_admin(_payload(uuid4(), "yorn.exe@gmail.com"), MagicMock()))
    assert e.value.status_code == 503


def test_toda_rota_admin_barra_conta_comum():
    """Chama TODAS as rotas do painel como conta comum: todas têm que dar 403."""
    import re
    from fastapi.testclient import TestClient
    import main
    from controller import admin_controller
    from dependencies.auth import get_token_payload

    rotas = [(m, r.path) for r in admin_controller.router.routes for m in r.methods]
    assert len(rotas) >= 15
    main.app.dependency_overrides[get_token_payload] = lambda: _payload(uuid4(), "cliente@x.com")
    try:
        cliente = TestClient(main.app)
        for metodo, caminho in rotas:
            url = "/api" + re.sub(r"\{[^}]+\}", str(uuid4()), caminho)
            r = cliente.request(metodo, url, json={})
            assert r.status_code == 403, (metodo, url, r.status_code)
    finally:
        main.app.dependency_overrides.pop(get_token_payload, None)


def test_apagar_exige_confirmacao():
    for ruim in (None, "", "sim", "apaga"):
        with pytest.raises(HTTPException) as e:
            admin_service.exigir_confirmacao(ruim)
        assert e.value.status_code == 400
    admin_service.exigir_confirmacao("APAGAR")
    admin_service.exigir_confirmacao(" apagar ")


def test_slug_da_categoria():
    assert admin_service.slugify("Roupas sessão de Carnaval!") == "roupas-sessao-de-carnaval"
    assert admin_service.slugify("***") == "categoria"


def test_admin_nao_se_apaga():
    uid = uuid4()
    with pytest.raises(HTTPException) as e:
        run(admin_service.apagar_usuario(MagicMock(), uid, uid, "APAGAR"))
    assert e.value.status_code == 400
