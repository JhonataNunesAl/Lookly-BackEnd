"""Cifragem simétrica para dado sensível em repouso (hoje: CPF/CNPJ em
`sellers_private.document_enc`).

Isto NÃO é o desenho final. O modelo original (`SellerDocument`) previa
envelope encryption feita no CLIENTE, com uma chave gerenciada por KMS — mas
nenhuma das duas peças (KMS, código de cifragem no app) existe hoje, então
nada cifra o documento em lugar nenhum. Cifrar aqui, no servidor, com uma
chave simétrica em variável de ambiente, fecha o gap real ("nada cifra isso
hoje") sem esperar por uma integração de KMS. Trocar para envelope encryption
depois não muda o contrato desta função por fora — só a implementação.
"""

import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core.config import settings

_NONCE_SIZE = 12  # recomendado para AES-GCM


def _load_key() -> bytes:
    raw = settings.DOCUMENT_ENCRYPTION_KEY
    if not raw:
        raise ValueError(
            "DOCUMENT_ENCRYPTION_KEY não está definida — necessária para cifrar "
            "documentos fiscais (CPF/CNPJ) antes de gravar em sellers_private."
        )
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise ValueError(
            "DOCUMENT_ENCRYPTION_KEY precisa decodificar (base64) para 32 bytes "
            "(AES-256). Gere uma com: python -c \"import secrets,base64; "
            "print(base64.b64encode(secrets.token_bytes(32)).decode())\""
        )
    return key


def encrypt(plaintext: str) -> str:
    """Retorna base64(nonce || ciphertext). Um nonce novo por chamada."""
    key = _load_key()
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str) -> str:
    key = _load_key()
    raw = base64.b64decode(token)
    nonce, ciphertext = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
