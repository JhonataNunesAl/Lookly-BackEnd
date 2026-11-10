from typing import Literal
from pydantic import BaseModel, Field, field_validator


class ExcluirContaRequest(BaseModel):
    """Confirmação explícita: um clique perdido ou uma chamada automática não
    apagam a conta — o corpo precisa trazer exatamente esta palavra."""

    confirmacao: Literal["EXCLUIR"]


# ── logs enviados pelo app ─────────────────────────────────────────────────────

def _cortar(limite: int):
    """Texto grande demais é CORTADO, não rejeitado: perder um log de erro por
    ele ser comprido seria o pior jeito de falhar."""

    def _f(v):
        return v[:limite] if isinstance(v, str) else v

    return _f


class ClientLogEntrada(BaseModel):
    nivel: Literal["warn", "error", "fatal"] = "error"
    # js = exceção não tratada · promise = promise rejeitada · boundary = erro de
    # renderização · api = chamada ao servidor que falhou · nativo = outros
    origem: Literal["js", "promise", "boundary", "api", "nativo"] = "js"
    mensagem: str = Field("", max_length=5000)
    pilha: str | None = None
    tela: str | None = None
    ts: str | None = None
    contexto: dict[str, str | int | float | bool | None] = {}

    _msg = field_validator("mensagem", mode="before")(_cortar(1000))
    _pilha = field_validator("pilha", mode="before")(_cortar(4000))
    _tela = field_validator("tela", "ts", mode="before")(_cortar(80))

    @field_validator("contexto", mode="before")
    @classmethod
    def _contexto(cls, v):
        if not isinstance(v, dict):
            return {}
        saida = {}
        for chave, valor in list(v.items())[:10]:
            saida[str(chave)[:40]] = valor[:200] if isinstance(valor, str) else valor
        return saida


class ClientLogLote(BaseModel):
    app_versao: str | None = None
    plataforma: str | None = None
    entradas: list[ClientLogEntrada] = Field(min_length=1, max_length=20)

    _meta = field_validator("app_versao", "plataforma", mode="before")(_cortar(30))


class ClientLogResponse(BaseModel):
    recebidas: int
