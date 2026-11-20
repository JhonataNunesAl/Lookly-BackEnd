"""Garante, na subida do app, as colunas/tabelas que o código novo lê.

Por quê: o modelo mapeia colunas novas (ex.: `looks.sizes`, `looks.reserved_quantity`).
Se o deploy sair ANTES de alguém rodar o SQL no Supabase, TODA consulta a `looks`
(feed, busca, carrinho) falha com 500. Este guarda remove a ordem de deploy da
equação: para cada passo, se a coluna/tabela já existe, só lê o catálogo (sem lock);
se não existe, aplica o DDL idempotente do passo.

Não é um sistema de migração — o histórico do Alembic divergiu do banco vivo
(ver CLAUDE.md). É uma rede de segurança estreita, com SQL constante (nada vem
de entrada de usuário). Cada passo usa `lock_timeout` curto para nunca ficar
preso atrás de uma transação longa. Nunca derruba a subida: banco
pausado/indisponível só gera um log e a API sobe mesmo assim. Desligue com
`SCHEMA_GUARD=0`.
"""
import logging
import os
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Passo:
    nome: str
    existe: str  # SELECT que devolve linha quando o passo já foi aplicado
    ddl: tuple[str, ...]
    registro: str  # arquivo em sql/ que documenta a mudança


def _coluna(tabela: str, coluna: str) -> str:
    return (
        "SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
        f"AND table_name = '{tabela}' AND column_name = '{coluna}'"
    )


PASSOS: tuple[Passo, ...] = (
    Passo(
        nome="looks.sizes",
        existe=_coluna("looks", "sizes"),
        ddl=(
            "ALTER TABLE public.looks ADD COLUMN IF NOT EXISTS sizes text[] NOT NULL DEFAULT '{}'",
            "CREATE INDEX IF NOT EXISTS idx_looks_sizes ON public.looks USING gin (sizes)",
            "CREATE INDEX IF NOT EXISTS idx_looks_price ON public.looks (price) "
            "WHERE status = 'active' AND price IS NOT NULL",
        ),
        registro="sql/filtros_busca.sql",
    ),
    Passo(
        nome="looks: reserva, custo, condição e marca",
        existe=_coluna("looks", "reserved_quantity"),
        ddl=(
            "ALTER TABLE public.looks "
            "ADD COLUMN IF NOT EXISTS reserved_quantity integer NOT NULL DEFAULT 0, "
            "ADD COLUMN IF NOT EXISTS cost_price numeric(10,2), "
            "ADD COLUMN IF NOT EXISTS condition text, "
            "ADD COLUMN IF NOT EXISTS brand text",
        ),
        registro="sql/gestao_estoque.sql",
    ),
    Passo(
        nome="order_items: envio por item",
        existe=_coluna("order_items", "fulfillment_status"),
        ddl=(
            "ALTER TABLE public.order_items "
            "ADD COLUMN IF NOT EXISTS fulfillment_status text NOT NULL DEFAULT 'pending', "
            "ADD COLUMN IF NOT EXISTS shipped_at timestamptz, "
            "ADD COLUMN IF NOT EXISTS tracking_code text",
        ),
        registro="sql/gestao_estoque.sql",
    ),
    Passo(
        nome="stock_movements",
        existe="SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'stock_movements'",
        ddl=(
            "CREATE TABLE IF NOT EXISTS public.stock_movements ("
            " id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
            " seller_id uuid NOT NULL REFERENCES public.sellers(id) ON DELETE CASCADE,"
            " look_id uuid REFERENCES public.looks(id) ON DELETE SET NULL,"
            " look_name text NOT NULL,"
            " kind text NOT NULL CHECK (kind IN ("
            "'entrada','venda_externa','venda_app','ajuste','perda','devolucao','reserva','liberacao')),"
            " quantity integer NOT NULL,"
            " stock_after integer NOT NULL,"
            " reserved_after integer NOT NULL DEFAULT 0,"
            " unit_price numeric(10,2),"
            " unit_cost numeric(10,2),"
            " channel text,"
            " note text,"
            " order_id uuid REFERENCES public.orders(id) ON DELETE SET NULL,"
            " created_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL,"
            " created_at timestamptz NOT NULL DEFAULT now())",
            "CREATE INDEX IF NOT EXISTS idx_stock_movements_seller ON public.stock_movements (seller_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_stock_movements_look ON public.stock_movements (look_id, created_at DESC)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_movements_venda_app "
            "ON public.stock_movements (order_id, look_id) WHERE kind = 'venda_app'",
            "CREATE INDEX IF NOT EXISTS idx_order_items_look ON public.order_items (look_id)",
            "ALTER TABLE public.stock_movements ENABLE ROW LEVEL SECURITY",
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
            "REVOKE ALL ON public.stock_movements FROM anon; END IF; END $$",
        ),
        registro="sql/gestao_estoque.sql",
    ),
)


async def garantir_schema(engine: AsyncEngine) -> bool:
    """True se criou algo, False se nada era necessário (ou o guarda está desligado).

    Cada passo roda na sua própria transação: se um falhar, os anteriores ficam."""
    if os.getenv("SCHEMA_GUARD", "1") == "0":
        return False
    criou = False
    for passo in PASSOS:
        try:
            async with engine.connect() as conn:
                if (await conn.execute(text(passo.existe))).first():
                    continue
                logger.warning("Schema: '%s' ausente — criando (registro em %s)", passo.nome, passo.registro)
                await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                for ddl in passo.ddl:
                    await conn.execute(text(ddl))
                await conn.commit()
                logger.warning("Schema: '%s' criado", passo.nome)
                criou = True
        except (ConnectionError, OSError):
            raise  # banco fora do ar: os outros passos também falhariam
        except Exception:  # noqa: BLE001
            # Ex.: lock_timeout atrás de uma transação longa. Segue para os próximos
            # passos; na próxima subida tenta de novo.
            logger.exception("Schema: falha ao aplicar '%s' — rode %s no Supabase", passo.nome, passo.registro)
    return criou
