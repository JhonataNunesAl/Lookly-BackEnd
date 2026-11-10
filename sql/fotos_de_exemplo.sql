-- As peças de exemplo usam fotos `placehold.co/...svg`, que o React Native não renderiza
-- (o app mostra "Foto indisponível"). Trocar a extensão por .png resolve — a placehold.co
-- serve o mesmo placeholder em PNG. Rode no SQL Editor do Supabase.
--
-- Veja antes o que será alterado:
--   SELECT id, name, photos FROM public.looks WHERE photos::text LIKE '%.svg%';
UPDATE public.looks
SET photos = ARRAY(
  SELECT replace(f, '.svg', '.png') FROM unnest(photos) AS f
)
WHERE photos::text LIKE '%.svg%';
