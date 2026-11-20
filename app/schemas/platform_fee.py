from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Fase = Literal["demo", "carencia", "padrao"]


class PlatformFeeConfig(BaseModel):
    """Regra em vigor (para o painel de admin)."""

    demo_active: bool
    demo_ends_at: datetime | None = None  # NULL = demo sem data para acabar
    fee_percent: Decimal
    grace_days: int
    updated_at: datetime | None = None


class PlatformFeeConfigUpdate(BaseModel):
    """Só os campos enviados mudam. `end_demo_now` encerra a demo agora;
    `demo_ends_at` agenda (ou, com null, reabre) a demo."""

    fee_percent: Decimal | None = Field(None, ge=0, le=50, max_digits=5, decimal_places=2)
    grace_days: int | None = Field(None, ge=0, le=730)
    demo_ends_at: datetime | None = None
    end_demo_now: bool = False

    @model_validator(mode="after")
    def _uma_forma_de_encerrar(self):
        if self.end_demo_now and "demo_ends_at" in self.model_fields_set:
            raise ValueError("Use end_demo_now OU demo_ends_at, não os dois.")
        if self.demo_ends_at is not None and self.demo_ends_at.tzinfo is None:
            raise ValueError("demo_ends_at precisa de fuso horário (ex.: 2027-01-31T23:59:00-03:00).")
        return self


class TaxaDaLoja(BaseModel):
    """O que a loja vê: quanto paga hoje e o que vem depois."""

    phase: Fase
    current_percent: Decimal
    standard_percent: Decimal
    grace_days: int
    demo_ends_at: datetime | None = None
    grace_ends_at: datetime | None = None  # só depois do fim da demo
    message: str


class RepassePendente(BaseModel):
    """Saldo a repassar para uma loja (soma dos líquidos com payout pendente)."""

    seller_id: str
    store_name: str
    items: int
    gross: Decimal
    fees: Decimal
    net: Decimal
