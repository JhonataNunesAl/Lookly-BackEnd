"""Verificação real de CNPJ contra a BrasilAPI (dados públicos da Receita
Federal). Gratuito, sem chave — e por isso sem SLA: se o serviço estiver
fora do ar, falhamos fechado (o chamador trata isso como "tente de novo",
nunca como "deixa passar sem checar").

Só CNPJ tem registro público consultável assim; CPF não passa por aqui — a
verificação de CPF continua sendo só o dígito verificador (ver
`service/seller_service.py`).
"""

import httpx

_BRASILAPI_URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
_TIMEOUT_SECONDS = 8


class CNPJLookupError(Exception):
    """A consulta não pôde ser concluída (rede/timeout/erro do serviço).

    Diferente de "CNPJ não existe" — isso é "não sei responder agora".
    """


class CNPJLookupResult:
    def __init__(self, exists: bool, active: bool, legal_name: str | None):
        self.exists = exists
        self.active = active
        self.legal_name = legal_name


async def lookup_cnpj(cnpj_digits: str) -> CNPJLookupResult:
    """`cnpj_digits`: só os 14 dígitos, sem pontuação."""
    url = _BRASILAPI_URL.format(cnpj=cnpj_digits)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(url)
    except httpx.HTTPError as e:
        raise CNPJLookupError("Não foi possível consultar o CNPJ agora.") from e

    if resp.status_code == 404:
        return CNPJLookupResult(exists=False, active=False, legal_name=None)
    if resp.status_code != 200:
        raise CNPJLookupError(
            f"BrasilAPI respondeu {resp.status_code} ao consultar o CNPJ."
        )

    data = resp.json()
    situacao = (data.get("descricao_situacao_cadastral") or "").upper()
    return CNPJLookupResult(
        exists=True,
        active=situacao == "ATIVA",
        legal_name=data.get("razao_social"),
    )
