-- Filtros da busca (preço, tamanho). Rode no SQL Editor do Supabase ANTES de publicar
-- o back-end novo: o modelo `Look` passa a ler a coluna `sizes`, e sem ela TODA consulta
-- a `looks` (feed, busca, carrinho) falha com 500. Idempotente.
--
-- Peças já publicadas ficam com `sizes = '{}'` ("tamanho não informado") e só aparecem
-- no filtro de tamanho depois que a loja editar a peça e marcar os tamanhos.

ALTER TABLE public.looks
  ADD COLUMN IF NOT EXISTS sizes text[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_looks_sizes ON public.looks USING gin (sizes);
CREATE INDEX IF NOT EXISTS idx_looks_price ON public.looks (price)
  WHERE status = 'active' AND price IS NOT NULL;
