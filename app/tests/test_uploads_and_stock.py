"""Testes do upload de imagem e da validação de estoque do carrinho (2026-10-29).

Sem banco e sem rede: o upload valida bytes/tamanho/tipo antes de qualquer
chamada ao Storage, e o estoque é uma função pura sobre o `Look`.

Roda com: cd app && python -m pytest tests/ -v
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from service import cart_items_service, storage_service
from schemas.cart_items import CartItemsAdd, CartItemsAddQuantity

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 32


def run(coro):
    return asyncio.run(coro)


# ── validação da imagem ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "tipo,dados,ext",
    [("image/jpeg", JPEG, "jpg"), ("image/png", PNG, "png"), ("image/webp", WEBP, "webp"),
     ("image/jpeg; charset=binary", JPEG, "jpg")],
)
def test_imagem_valida_devolve_extensao(tipo, dados, ext):
    assert storage_service.validar_imagem(tipo, dados) == ext


@pytest.mark.parametrize("tipo", [None, "", "text/plain", "application/pdf", "image/gif", "image/svg+xml"])
def test_tipo_nao_suportado_415(tipo):
    with pytest.raises(HTTPException) as e:
        storage_service.validar_imagem(tipo, JPEG)
    assert e.value.status_code == 415


def test_arquivo_renomeado_nao_passa():
    # declara JPEG mas os bytes são de um executável/texto
    with pytest.raises(HTTPException) as e:
        storage_service.validar_imagem("image/jpeg", b"MZ\x90\x00" + b"0" * 32)
    assert e.value.status_code == 400


def test_tipo_declarado_diferente_dos_bytes_nao_passa():
    with pytest.raises(HTTPException) as e:
        storage_service.validar_imagem("image/png", JPEG)
    assert e.value.status_code == 400


def test_imagem_vazia_400():
    with pytest.raises(HTTPException) as e:
        storage_service.validar_imagem("image/jpeg", b"")
    assert e.value.status_code == 400


def test_imagem_acima_do_teto_413():
    with pytest.raises(HTTPException) as e:
        storage_service.validar_imagem("image/jpeg", JPEG + b"0" * storage_service.MAX_BYTES)
    assert e.value.status_code == 413


def test_upload_grava_na_pasta_do_usuario_e_devolve_url_publica():
    uid = uuid4()
    resp = SimpleNamespace(status_code=200, text="")
    client = AsyncMock()
    client.post.return_value = resp
    client.__aenter__.return_value = client
    with patch.object(storage_service.httpx, "AsyncClient", return_value=client), \
         patch.object(storage_service.settings, "SUPABASE_URL", "https://x.supabase.co"), \
         patch.object(storage_service.settings, "SUPABASE_SERVICE_KEY", "chave"):
        url = run(storage_service.upload_imagem(uid, "image/png", PNG))
    assert url.startswith(f"https://x.supabase.co/storage/v1/object/public/{storage_service.settings.STORAGE_BUCKET}/{uid}/")
    assert url.endswith(".png")
    enviado = client.post.call_args
    assert str(uid) in enviado.args[0]
    assert enviado.kwargs["content"] == PNG


def test_upload_cria_bucket_quando_nao_existe_e_tenta_de_novo():
    nao_achou = SimpleNamespace(status_code=404, text='{"message":"Bucket not found"}')
    criado = SimpleNamespace(status_code=200, text="{}")
    ok = SimpleNamespace(status_code=200, text="")
    client = AsyncMock()
    client.post.side_effect = [nao_achou, criado, ok]
    client.__aenter__.return_value = client
    with patch.object(storage_service.httpx, "AsyncClient", return_value=client), \
         patch.object(storage_service.settings, "SUPABASE_URL", "https://x.supabase.co"), \
         patch.object(storage_service.settings, "SUPABASE_SERVICE_KEY", "chave"):
        run(storage_service.upload_imagem(uuid4(), "image/jpeg", JPEG))
    assert client.post.call_count == 3


def test_falha_do_storage_vira_502():
    client = AsyncMock()
    client.post.return_value = SimpleNamespace(status_code=500, text="boom")
    client.__aenter__.return_value = client
    with patch.object(storage_service.httpx, "AsyncClient", return_value=client), \
         patch.object(storage_service.settings, "SUPABASE_URL", "https://x.supabase.co"), \
         patch.object(storage_service.settings, "SUPABASE_SERVICE_KEY", "chave"):
        with pytest.raises(HTTPException) as e:
            run(storage_service.upload_imagem(uuid4(), "image/jpeg", JPEG))
    assert e.value.status_code == 502


# ── estoque no carrinho ───────────────────────────────────────────────────────

def test_estoque_zerado_bloqueia():
    with pytest.raises(HTTPException) as e:
        cart_items_service._checar_estoque(SimpleNamespace(stock_quantity=0), 1)
    assert e.value.status_code == 400 and "Sem estoque" in e.value.detail


def test_quantidade_acima_do_estoque_bloqueia():
    with pytest.raises(HTTPException) as e:
        cart_items_service._checar_estoque(SimpleNamespace(stock_quantity=2), 3)
    assert e.value.status_code == 400 and "insuficiente" in e.value.detail


def test_quantidade_no_limite_do_estoque_passa():
    cart_items_service._checar_estoque(SimpleNamespace(stock_quantity=2), 2)


def test_somar_quantidade_respeita_estoque():
    item = SimpleNamespace(quantity=2)
    look = SimpleNamespace(stock_quantity=2)
    db = AsyncMock()
    with patch.object(cart_items_service, "_get_cart_by_user", AsyncMock(return_value=SimpleNamespace(id=uuid4()))), \
         patch.object(cart_items_service, "_get_cart_item", AsyncMock(return_value=item)), \
         patch.object(cart_items_service, "_get_look", AsyncMock(return_value=look)):
        with pytest.raises(HTTPException) as e:
            run(cart_items_service.add_quantity(db, uuid4(), uuid4(), CartItemsAddQuantity(quantity=1)))
    assert e.value.status_code == 400
    assert item.quantity == 2  # não somou
    db.commit.assert_not_called()


def test_adicionar_ao_carrinho_sem_estoque_bloqueia():
    look = SimpleNamespace(stock_quantity=0)
    db = AsyncMock()
    with patch.object(cart_items_service, "_get_cart_by_user", AsyncMock(return_value=SimpleNamespace(id=uuid4()))), \
         patch.object(cart_items_service, "_get_look", AsyncMock(return_value=look)):
        with pytest.raises(HTTPException) as e:
            run(cart_items_service.add_look_cart(db, CartItemsAdd(look_id=uuid4(), quantity=1), uuid4()))
    assert e.value.status_code == 400 and "Sem estoque" in e.value.detail


# ── limite de tamanho no endpoint (corpo "chunked", sem Content-Length) ───────

def _cliente_com_login():
    from fastapi.testclient import TestClient

    import main
    from dependencies.auth import get_current_user_id

    main.app.dependency_overrides[get_current_user_id] = lambda: uuid4()
    return TestClient(main.app), main


def test_upload_chunked_acima_do_teto_413_sem_chamar_o_storage():
    cliente, main = _cliente_com_login()
    try:
        def corpo():  # gerador => requisição chunked, sem Content-Length
            for _ in range(6):
                yield b"x" * (1024 * 1024)

        with patch.object(storage_service, "upload_imagem", AsyncMock()) as up:
            r = cliente.post("/api/uploads/image", content=corpo(), headers={"Content-Type": "image/jpeg"})
        assert r.status_code == 413
        up.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


def test_upload_pequeno_passa_ate_o_service():
    cliente, main = _cliente_com_login()
    try:
        with patch.object(storage_service, "upload_imagem", AsyncMock(return_value="https://x/y.jpg")) as up:
            r = cliente.post("/api/uploads/image", content=JPEG, headers={"Content-Type": "image/jpeg"})
        assert r.status_code == 201 and r.json() == {"url": "https://x/y.jpg"}
        assert up.call_args.args[2] == JPEG
    finally:
        main.app.dependency_overrides.clear()
