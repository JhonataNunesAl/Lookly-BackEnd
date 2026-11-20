-- Importação em massa de peças (2026-11-20): coluna `looks.sku` (código da peça).
--
-- O back-end já cria isto sozinho na subida (core/schema_guard.py), então rodar
-- este script é só para registrar a mudança. Idempotente: pode rodar mais de uma vez.
--
-- `sku` é opcional. Quando preenchido, é único dentro da loja: é a chave usada
-- pela reimportação da planilha para ATUALIZAR uma peça já cadastrada (preço,
-- estoque etc.) em vez de criar uma nova.

ALTER TABLE public.looks
  ADD COLUMN IF NOT EXISTS sku text;

DO $$ BEGIN
  ALTER TABLE public.looks ADD CONSTRAINT looks_sku_len
    CHECK (sku IS NULL OR char_length(sku) BETWEEN 1 AND 60);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_looks_seller_sku
  ON public.looks (seller_id, sku)
  WHERE sku IS NOT NULL;
