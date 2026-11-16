-- Prepara as peças de EXEMPLO (as que usam fotos de placehold.co) para um teste de verdade.
-- Rode no SQL Editor do Supabase. É idempotente: pode rodar de novo sem estragar nada, e só
-- toca em peças cuja foto vem de placehold.co — peças reais das lojas não são alteradas.
--
-- Dois problemas das peças de exemplo, os dois vistos no banco vivo em 2026-11-11:
--
--  1. As fotos são `https://placehold.co/600x800?text=...`, sem extensão. Sem extensão a
--     placehold.co responde SVG, e o React Native não renderiza SVG (o app mostra "Foto
--     indisponível"). Com `.png` depois do tamanho, o mesmo placeholder vem em PNG.
--  2. Todas estão com estoque 0 e sem tamanhos: não dá para pôr no carrinho, e o filtro
--     "só em estoque" e o de tamanho nunca as encontram.
--
-- Veja antes o que será alterado:
--   SELECT id, name, stock_quantity, sizes, photos FROM public.looks WHERE photos::text LIKE '%placehold.co%';

-- 1) Fotos: placehold.co/600x800?text=X  ->  placehold.co/600x800.png?text=X
UPDATE public.looks
SET photos = ARRAY(
  SELECT regexp_replace(f, '(placehold\.co/[0-9]+x[0-9]+)(\.[a-z]+)?(\?|$)', '\1.png\3')
  FROM unnest(photos) AS f
)
WHERE photos::text LIKE '%placehold.co%'
  AND photos::text ~ 'placehold\.co/[0-9]+x[0-9]+(\.svg|\?|"|,|})';

-- 2) Estoque e tamanhos para o teste (só onde ainda está zerado / vazio)
UPDATE public.looks
SET stock_quantity = 8
WHERE photos::text LIKE '%placehold.co%'
  AND stock_quantity = 0;

UPDATE public.looks
SET sizes = ARRAY['P', 'M', 'G']
WHERE photos::text LIKE '%placehold.co%'
  AND (sizes IS NULL OR cardinality(sizes) = 0);
