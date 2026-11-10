"""Limpeza de texto antes de ir para o log.

O log em arquivo/console não tem o controle de acesso do banco (ver
`logging_config.setup_logging`): nada sensível pode chegar lá. Mensagens de erro
do app podem carregar sem querer um token, um e-mail, um CPF/CNPJ ou o valor de
um campo de senha — esta função troca tudo isso por `[redigido]`. É um filtro de
segurança em profundidade, não uma garantia: quem escreve o log continua sem
poder mandar dado sensível de propósito.
"""
import re

_PADROES = [
    # JWT (header.payload.assinatura) e "Bearer <qualquer coisa>"
    re.compile(r"eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]*"),
    re.compile(r"(?i)bearer\s+[\w.~+/=-]+"),
    # chaves do Supabase / provedores
    re.compile(r"\bsb_(?:publishable|secret)_[\w-]+"),
    re.compile(r"(?i)\b(?:apikey|api_key|access_token|refresh_token|authorization)\s*[=:]\s*\S+"),
    # senha em "senha=...", "password: ..."
    re.compile(r"(?i)\b(?:senha|password|passwd|pwd)\s*[=:]\s*\S+"),
    # e-mail
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    # CPF / CNPJ formatados e só dígitos (11 ou 14)
    re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
    re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"),
    re.compile(r"(?<!\d)(?:\d{11}|\d{14})(?!\d)"),
]

REDIGIDO = "[redigido]"


def limpar(texto: str | None) -> str | None:
    if texto is None:
        return None
    for padrao in _PADROES:
        texto = padrao.sub(REDIGIDO, texto)
    return texto
