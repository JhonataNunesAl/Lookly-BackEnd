"""Garante, na subida do app, as colunas que o código novo lê.

Por quê: o `Look` passou a mapear colunas novas (`looks.sizes` para o filtro de
tamanho, `looks.sku` para a importação em massa). Se o deploy sair ANTES de
alguém rodar o SQL correspondente no Supabase, TODA consulta a `looks` (feed,
busca, carrinho) falha com 500. Este guarda remove a ordem de deploy da equação:
para cada coluna, se ela não existe, cria (idempotente); se existe, só lê o
catálogo de colunas e não toca na tabela (sem lock).

Não é um sistema de migração — o histórico do Alembic divergiu do banco vivo
(ver CLAUDE.md). É uma rede de segurança estreita, com SQL constante (nada vem
de entrada de usuário). Nunca derruba a subida: banco pausado/indisponível só
gera um log e a API sobe mesmo assim. Desligue com `SCHEMA_GUARD=0`.

Para uma coluna nova: acrescente um `_Passo` em `PASSOS` (tabela, coluna, DDLs
idempotentes e o script de `sql/` que registra a mudança).
"""
import logging
import os
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

_EXISTE = text(
    "SELECT 1 FROM information_schema.columns "
    "WHERE table_schema = 'public' AND table_name = :tabela AND column_name = :coluna"
)


@dataclass(frozen=True)
class _Passo:
    tabela: str
    coluna: str
    ddls: tuple
    script: str


PASSOS: list[_Passo] = [
    _Passo(
        "looks",
        "sizes",
        (
            text("ALTER TABLE public.looks ADD COLUMN IF NOT EXISTS sizes text[] NOT NULL DEFAULT '{}'"),
            text("CREATE INDEX IF NOT EXISTS idx_looks_sizes ON public.looks USING gin (sizes)"),
            text(
                "CREATE INDEX IF NOT EXISTS idx_looks_price ON public.looks (price) "
                "WHERE status = 'active' AND price IS NOT NULL"
            ),
        ),
        "sql/filtros_busca.sql",
    ),
    _Passo(
        "looks",
        "sku",
        (
            text("ALTER TABLE public.looks ADD COLUMN IF NOT EXISTS sku text"),
            text(
                "DO $$ BEGIN "
                "ALTER TABLE public.looks ADD CONSTRAINT looks_sku_len "
                "CHECK (sku IS NULL OR char_length(sku) BETWEEN 1 AND 60); "
                "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
            ),
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_looks_seller_sku "
                "ON public.looks (seller_id, sku) WHERE sku IS NOT NULL"
            ),
        ),
        "sql/importacao_em_massa.sql",
    ),
]


async def garantir_schema(engine: AsyncEngine) -> bool:
    """True se criou algo, False se nada era necessário (ou o guarda está desligado)."""
    if os.getenv("SCHEMA_GUARD", "1") == "0":
        return False
    criou = False
    async with engine.connect() as conn:
        for passo in PASSOS:
            existe = (await conn.execute(_EXISTE, {"tabela": passo.tabela, "coluna": passo.coluna})).first()
            if existe:
                continue
            logger.warning(
                "Coluna %s.%s ausente — criando (rode %s para registrar a mudança)",
                passo.tabela, passo.coluna, passo.script,
            )
            for ddl in passo.ddls:
                await conn.execute(ddl)
            await conn.commit()
            logger.warning("Coluna %s.%s criada", passo.tabela, passo.coluna)
            criou = True
    return criou
