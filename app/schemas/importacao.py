"""Contratos da importação e da edição em massa de peças (looks).

Fluxo pensado para quem tem centenas ou milhares de peças:

1. `GET  /looks/import/template`  → planilha modelo (XLSX ou CSV).
2. `POST /looks/import/preview`   → envia a planilha; o servidor lê, valida cada
   linha e devolve a prévia (o que vai ser criado/atualizado e os erros por linha).
   Não grava nada.
3. `POST /looks/bulk`             → grava as linhas válidas (até `MAX_ITENS_LOTE`
   por chamada; o app manda em lotes).

Edição em massa: `PATCH /looks/bulk` (mesmo ajuste em várias peças) ou reimportar
a planilha exportada em `GET /looks/export` (atualiza pelo `id` ou pelo código).
"""
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.look import normalizar_sku, normalizar_tamanhos

MAX_ITENS_LOTE = 1000
MAX_IDS_EDICAO = 500

# Condição da peça (brechó). A coluna vem da gestão de estoque; enquanto ela não
# existir no banco, o valor é aceito na planilha e simplesmente não é gravado.
CONDICOES = ("novo", "seminovo", "usado", "vintage")


def _validar_fotos_url(v: list[str] | None) -> list[str] | None:
    if v is None:
        return v
    if not 1 <= len(v) <= 6:
        raise ValueError("Uma peça deve ter de 1 a 6 fotos.")
    for url in v:
        if not url.lower().startswith("https://"):
            raise ValueError(f"Foto precisa ser um link https:// (recebido: {url[:60]!r}).")
        if len(url) > 2000:
            raise ValueError("Link de foto longo demais.")
    return v


class ItemLote(BaseModel):
    """Uma peça do lote. Sem `id` e sem código já existente → cria (aí nome,
    categoria e fotos são obrigatórios). Com `id`, ou com `sku` de uma peça que
    já existe na loja → atualiza só os campos enviados."""

    linha: int | None = Field(None, description="linha da planilha, só para casar os erros")
    id: UUID | None = None
    sku: str | None = None
    category_id: UUID | None = None
    name: str | None = Field(None, min_length=2, max_length=120)
    description: str | None = Field(None, max_length=5000)
    photos: list[str] | None = None
    price: Decimal | None = Field(None, ge=0, le=Decimal("99999999.99"))
    buy_link: str | None = Field(None, max_length=2000)
    stock_quantity: int | None = Field(None, ge=0, le=1_000_000)
    sizes: list[str] | None = None
    # Campos da gestão de estoque (gravados só quando a coluna existir no modelo).
    cost_price: Decimal | None = Field(None, ge=0, le=Decimal("99999999.99"))
    condition: str | None = None
    brand: str | None = Field(None, max_length=80)

    _sku = field_validator("sku")(normalizar_sku)
    _tamanhos = field_validator("sizes")(normalizar_tamanhos)
    _fotos = field_validator("photos")(_validar_fotos_url)

    @field_validator("condition")
    @classmethod
    def _condicao(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in CONDICOES:
            raise ValueError(f"Condição inválida: {v!r}. Use: {', '.join(CONDICOES)}.")
        return v


class LoteRequest(BaseModel):
    itens: list[dict] = Field(..., min_length=1, max_length=MAX_ITENS_LOTE)
    # Situação das peças CRIADAS. `draft` = rascunho (fora do feed até publicar).
    status: Literal["active", "draft"] = "active"


class ErroLote(BaseModel):
    indice: int
    linha: int | None = None
    mensagem: str


class LoteResponse(BaseModel):
    criados: int
    atualizados: int
    ids: list[UUID] = []
    erros: list[ErroLote] = []


# ── prévia ────────────────────────────────────────────────────────────────────

class LinhaPrevia(BaseModel):
    linha: int
    acao: Literal["criar", "atualizar"]
    look_id: UUID | None = None
    # Campos prontos para `POST /looks/bulk` (fotos por nome de arquivo ficam em
    # `fotos_pendentes` até o app enviá-las e trocar pelos links).
    dados: dict
    fotos_pendentes: list[str] = []
    erros: list[str] = []


class PreviaResponse(BaseModel):
    total_linhas: int
    validas: int
    com_erro: int
    a_criar: int
    a_atualizar: int
    # Nomes de arquivo de foto citados na planilha (o app pede para a pessoa
    # escolher esses arquivos e os envia antes de gravar).
    arquivos_de_foto: list[str] = []
    colunas_ignoradas: list[str] = []
    linhas: list[LinhaPrevia]


# ── edição em massa ───────────────────────────────────────────────────────────

class EdicaoEmMassa(BaseModel):
    """Mesmo ajuste em várias peças da loja. Envie só o que muda."""

    ids: list[UUID] = Field(..., min_length=1, max_length=MAX_IDS_EDICAO)
    price: Decimal | None = Field(None, ge=0, le=Decimal("99999999.99"))
    # Reajuste percentual: 10 = +10%, -20 = 20% de desconto. Peças sem preço ficam sem.
    price_percent: Decimal | None = Field(None, ge=-90, le=500)
    stock_quantity: int | None = Field(None, ge=0, le=1_000_000)
    # Soma (ou subtrai) do estoque atual; nunca fica abaixo de zero.
    stock_delta: int | None = Field(None, ge=-1_000_000, le=1_000_000)
    status: Literal["active", "draft"] | None = None
    category_id: UUID | None = None

    @model_validator(mode="after")
    def _coerente(self):
        if self.price is not None and self.price_percent is not None:
            raise ValueError("Use preço fixo OU reajuste percentual, não os dois.")
        if self.stock_quantity is not None and self.stock_delta is not None:
            raise ValueError("Use estoque fixo OU soma ao estoque, não os dois.")
        if all(
            v is None
            for v in (self.price, self.price_percent, self.stock_quantity, self.stock_delta, self.status, self.category_id)
        ):
            raise ValueError("Nada para alterar.")
        return self


class EdicaoEmMassaResponse(BaseModel):
    atualizados: int
    ignorados: int = 0
