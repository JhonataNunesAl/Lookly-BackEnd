-- Taxa da plataforma sobre as peças vendidas no app (2026-11-20).
-- Aplicado automaticamente na subida da API por core/schema_guard.py; este
-- arquivo é o registro (e serve para rodar à mão no SQL Editor do Supabase).
--
-- Regra (service/platform_fee_service.py):
--   * demo_ends_at NULL (ou no futuro) -> demo: 0% para todas as lojas;
--   * depois da demo, cada loja tem grace_days dias a 0%, contados do que vier
--     por último entre o fim da demo e o cadastro da loja;
--   * depois disso, fee_percent (11%).

CREATE TABLE IF NOT EXISTS public.platform_fee_config (
  id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  demo_ends_at timestamptz,
  fee_percent numeric(5,2) NOT NULL DEFAULT 11 CHECK (fee_percent >= 0 AND fee_percent <= 50),
  grace_days integer NOT NULL DEFAULT 60 CHECK (grace_days >= 0 AND grace_days <= 730),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL
);
INSERT INTO public.platform_fee_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
ALTER TABLE public.platform_fee_config ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
  REVOKE ALL ON public.platform_fee_config FROM anon; END IF; END $$;

-- Taxa congelada em cada peça vendida + situação do repasse para a loja.
ALTER TABLE public.order_items
  ADD COLUMN IF NOT EXISTS platform_fee_percent numeric(5,2),
  ADD COLUMN IF NOT EXISTS platform_fee_amount numeric(10,2),
  ADD COLUMN IF NOT EXISTS seller_net_amount numeric(10,2),
  ADD COLUMN IF NOT EXISTS fee_rule text,
  ADD COLUMN IF NOT EXISTS payout_status text NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS paid_out_at timestamptz;

-- Tudo o que já foi vendido até aqui foi na demo: 0%, a loja recebe o valor inteiro.
UPDATE public.order_items oi
   SET platform_fee_percent = 0, platform_fee_amount = 0,
       seller_net_amount = oi.subtotal, fee_rule = 'demo'
  FROM public.orders o
 WHERE o.id = oi.order_id
   AND upper(o.payment_status::text) = 'APPROVED'
   AND oi.platform_fee_percent IS NULL;
