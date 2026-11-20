-- Gestão de estoque da loja (2026-11-20). Idempotente: pode rodar mais de uma vez.
--
-- Não precisa rodar antes do deploy: o back-end cria o que faltar sozinho na subida
-- (app/core/schema_guard.py). Este arquivo é o registro da mudança e serve para
-- aplicar à mão no SQL Editor do Supabase, se preferir.
--
-- Segurança da migração:
--   * só ADD COLUMN com default constante (Postgres 11+ não reescreve a tabela) e
--     CREATE TABLE/INDEX novos; nenhuma coluna existente muda ou some;
--   * peças antigas ficam com reserved_quantity = 0 e custo/condição/marca vazios,
--     ou seja, nada muda para quem compra;
--   * itens de pedido antigos ficam com fulfillment_status = 'pending'.

SET lock_timeout = '5s';

-- 1. Peças: reserva, custo, condição e marca
ALTER TABLE public.looks
  ADD COLUMN IF NOT EXISTS reserved_quantity integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cost_price numeric(10,2),
  ADD COLUMN IF NOT EXISTS condition text,
  ADD COLUMN IF NOT EXISTS brand text;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'looks_reserved_quantity_check') THEN
    ALTER TABLE public.looks ADD CONSTRAINT looks_reserved_quantity_check CHECK (reserved_quantity >= 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'looks_cost_price_check') THEN
    ALTER TABLE public.looks ADD CONSTRAINT looks_cost_price_check CHECK (cost_price IS NULL OR cost_price >= 0);
  END IF;
END $$;

-- 2. Envio por item do pedido (cada loja despacha as suas peças)
ALTER TABLE public.order_items
  ADD COLUMN IF NOT EXISTS fulfillment_status text NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS shipped_at timestamptz,
  ADD COLUMN IF NOT EXISTS tracking_code text;

-- 3. Histórico de movimentações de estoque
CREATE TABLE IF NOT EXISTS public.stock_movements (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seller_id      uuid NOT NULL REFERENCES public.sellers(id) ON DELETE CASCADE,
  look_id        uuid REFERENCES public.looks(id) ON DELETE SET NULL,
  look_name      text NOT NULL,
  kind           text NOT NULL CHECK (kind IN (
                   'entrada','venda_externa','venda_app','ajuste','perda','devolucao','reserva','liberacao')),
  quantity       integer NOT NULL,
  stock_after    integer NOT NULL,
  reserved_after integer NOT NULL DEFAULT 0,
  unit_price     numeric(10,2),
  unit_cost      numeric(10,2),
  channel        text,
  note           text,
  order_id       uuid REFERENCES public.orders(id) ON DELETE SET NULL,
  created_by     uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stock_movements_seller ON public.stock_movements (seller_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_movements_look   ON public.stock_movements (look_id, created_at DESC);
-- Webhook repetido do Mercado Pago não duplica a venda no histórico.
CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_movements_venda_app
  ON public.stock_movements (order_id, look_id) WHERE kind = 'venda_app';
CREATE INDEX IF NOT EXISTS idx_order_items_look ON public.order_items (look_id);

-- RLS ligado como nas demais tabelas públicas. O back-end acessa com o dono da
-- tabela (ignora RLS); pelo PostgREST só quem gerencia a loja lê o histórico.
ALTER TABLE public.stock_movements ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.stock_movements FROM anon;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'stock_movements' AND policyname = 'stock_movements_read_store') THEN
    CREATE POLICY "stock_movements_read_store" ON public.stock_movements
      FOR SELECT TO authenticated USING (public.can_manage_store(seller_id));
  END IF;
END $$;
