"""Garante, na subida do app, as colunas que o código novo lê.

Por quê: o `Look` passou a mapear `looks.sizes` (filtro de tamanho). Se o deploy
sair ANTES de alguém rodar `sql/filtros_busca.sql` no Supabase, TODA consulta a
`looks` (feed, busca, carrinho) falha com 500. Este guarda remove a ordem de
deploy da equação: se a coluna não existe, cria (idempotente); se existe, só lê o
catálogo de colunas e não toca na tabela (sem lock).

Não é um sistema de migração — o histórico do Alembic divergiu do banco vivo
(ver CLAUDE.md). É uma rede de segurança estreita, com SQL constante (nada vem
de entrada de usuário). Nunca derruba a subida: banco pausado/indisponível só
gera um log e a API sobe mesmo assim. Desligue com `SCHEMA_GUARD=0`.
"""
import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

_EXISTE = text(
    "SELECT 1 FROM information_schema.columns "
    "WHERE table_schema = 'public' AND table_name = 'looks' AND column_name = 'sizes'"
)
_DDL = [
    text("ALTER TABLE public.looks ADD COLUMN IF NOT EXISTS sizes text[] NOT NULL DEFAULT '{}'"),
    text("CREATE INDEX IF NOT EXISTS idx_looks_sizes ON public.looks USING gin (sizes)"),
    text(
        "CREATE INDEX IF NOT EXISTS idx_looks_price ON public.looks (price) "
        "WHERE status = 'active' AND price IS NOT NULL"
    ),
]


async def garantir_schema(engine: AsyncEngine) -> bool:
    """True se criou algo, False se nada era necessário (ou o guarda está desligado)."""
    if os.getenv("SCHEMA_GUARD", "1") == "0":
        return False
    async with engine.connect() as conn:
        if (await conn.execute(_EXISTE)).first():
            return False
        logger.warning("Coluna looks.sizes ausente — criando (rode sql/filtros_busca.sql para registrar a mudança)")
        for ddl in _DDL:
            await conn.execute(ddl)
        await conn.commit()
        logger.warning("Coluna looks.sizes criada")
        return True
