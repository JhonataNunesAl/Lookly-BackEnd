"""Upload de imagens para o Supabase Storage, feito PELO servidor.

Por que pelo servidor e não direto do app: gravar em `storage.objects` a partir
do app exigiria policies de RLS no schema `storage` (mais uma superfície de
ataque onde "o que o RLS permite, a internet permite"). Aqui o bucket é público
só para LEITURA; toda escrita passa por esta função, que valida o tipo (pelos
bytes, não pelo que o cliente diz), o tamanho e grava sempre numa pasta com o
id de quem enviou (vem do JWT, não do corpo da requisição).
"""
import logging
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status

from core.config import settings

logger = logging.getLogger(__name__)

MAX_BYTES = 5 * 1024 * 1024  # 5 MB — o app comprime antes; isto é só o teto

# content-type aceito -> extensão do arquivo gravado
_TIPOS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _assinatura_confere(content_type: str, data: bytes) -> bool:
    """Confere os primeiros bytes (magic bytes) com o tipo declarado — um
    arquivo qualquer renomeado para .jpg não passa."""
    if content_type == "image/jpeg":
        return data[:3] == b"\xff\xd8\xff"
    if content_type == "image/png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if content_type == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def validar_imagem(content_type: str | None, data: bytes) -> str:
    """Valida tipo, tamanho e assinatura. Devolve a extensão ou levanta 4xx."""
    tipo = (content_type or "").split(";")[0].strip().lower()
    if tipo not in _TIPOS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Formato de imagem não suportado. Use JPEG, PNG ou WebP.",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Imagem vazia.")
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Imagem grande demais (máximo de 5 MB).",
        )
    if not _assinatura_confere(tipo, data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O arquivo não parece ser uma imagem válida.",
        )
    return _TIPOS[tipo]


def _headers(content_type: str) -> dict[str, str]:
    key = settings.SUPABASE_SERVICE_KEY
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": content_type}


async def _garantir_bucket(client: httpx.AsyncClient) -> None:
    """Cria o bucket público de leitura se ele ainda não existe (idempotente)."""
    resp = await client.post(
        f"{settings.SUPABASE_URL}/storage/v1/bucket",
        headers=_headers("application/json"),
        json={
            "id": settings.STORAGE_BUCKET,
            "name": settings.STORAGE_BUCKET,
            "public": True,
            "file_size_limit": MAX_BYTES,
            "allowed_mime_types": list(_TIPOS),
        },
    )
    # 200 = criado; 400/409 "already exists" = ok
    if resp.status_code >= 400 and "already exists" not in resp.text.lower() and "Duplicate" not in resp.text:
        logger.error("Falha ao criar bucket %s: %s %s", settings.STORAGE_BUCKET, resp.status_code, resp.text[:200])
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Armazenamento indisponível.")


async def upload_imagem(user_id: UUID, content_type: str | None, data: bytes) -> str:
    """Valida e envia a imagem; devolve a URL pública. Caminho:
    `<user_id>/<uuid>.<ext>` — a pasta é sempre a de quem enviou."""
    ext = validar_imagem(content_type, data)
    tipo = (content_type or "").split(";")[0].strip().lower()
    caminho = f"{user_id}/{uuid4().hex}.{ext}"
    url_upload = f"{settings.SUPABASE_URL}/storage/v1/object/{settings.STORAGE_BUCKET}/{caminho}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url_upload, headers=_headers(tipo), content=data)
        if resp.status_code in (400, 404) and "bucket" in resp.text.lower():
            await _garantir_bucket(client)
            resp = await client.post(url_upload, headers=_headers(tipo), content=data)

    if resp.status_code >= 400:
        logger.error("Falha no upload de imagem: %s %s", resp.status_code, resp.text[:200])
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Não foi possível salvar a imagem.")

    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{settings.STORAGE_BUCKET}/{caminho}"


async def remover_pasta_do_usuario(user_id: UUID) -> int:
    """Apaga tudo que o usuário enviou (`<user_id>/...`), usado na exclusão de conta.
    Melhor esforço: erro de rede ou do Storage é logado e NÃO propaga — arquivo
    órfão é aceitável, conta que não consegue ser excluída não é. Devolve quantos
    arquivos foram removidos."""
    if not settings.SUPABASE_SERVICE_KEY or not settings.SUPABASE_URL:
        return 0
    removidos = 0
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for _ in range(10):  # até 10 páginas de 100 arquivos
                lista = await client.post(
                    f"{settings.SUPABASE_URL}/storage/v1/object/list/{settings.STORAGE_BUCKET}",
                    headers=_headers("application/json"),
                    json={"prefix": str(user_id), "limit": 100},
                )
                if lista.status_code != 200:
                    break
                nomes = [f"{user_id}/{o['name']}" for o in lista.json() if o.get("name")]
                if not nomes:
                    break
                rm = await client.request(
                    "DELETE",
                    f"{settings.SUPABASE_URL}/storage/v1/object/{settings.STORAGE_BUCKET}",
                    headers=_headers("application/json"),
                    json={"prefixes": nomes},
                )
                if rm.status_code >= 400:
                    logger.warning("Falha ao remover arquivos de %s: HTTP %s", user_id, rm.status_code)
                    break
                removidos += len(nomes)
    except Exception as e:  # noqa: BLE001 — melhor esforço, ver docstring
        logger.warning("Limpeza do Storage de %s falhou: %s", user_id, type(e).__name__)
    return removidos
