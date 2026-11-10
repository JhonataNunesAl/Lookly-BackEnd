-- Manutenção de `look_views` (particionada por mês). Rode no SQL Editor do Supabase.
-- Idempotente: pode rodar de novo sem erro.
--
-- 1) Partições de 2027. As existentes vão até 2026-12 (+ a DEFAULT, que só evita o 500;
--    deixar registros na DEFAULT atrapalha criar a partição do mês depois).
DO $$
DECLARE
  inicio date := date '2027-01-01';
  mes date;
BEGIN
  FOR i IN 0..11 LOOP
    mes := inicio + (i || ' months')::interval;
    EXECUTE format(
      'CREATE TABLE IF NOT EXISTS public.look_views_%s PARTITION OF public.look_views FOR VALUES FROM (%L) TO (%L)',
      to_char(mes, 'YYYY_MM'), mes, (mes + interval '1 month')::date
    );
  END LOOP;
END $$;

-- 2) Job mensal (pg_cron): cria a partição do mês seguinte e a do próximo, no dia 1.
--    Habilite a extensão em Database > Extensions > pg_cron antes de rodar.
-- SELECT cron.schedule(
--   'look_views_partitions',
--   '0 3 1 * *',
--   $job$
--   DO $$
--   DECLARE mes date;
--   BEGIN
--     FOR i IN 1..2 LOOP
--       mes := (date_trunc('month', now()) + (i || ' months')::interval)::date;
--       EXECUTE format(
--         'CREATE TABLE IF NOT EXISTS public.look_views_%s PARTITION OF public.look_views FOR VALUES FROM (%L) TO (%L)',
--         to_char(mes, 'YYYY_MM'), mes, (mes + interval '1 month')::date
--       );
--     END LOOP;
--   END $$;
--   $job$
-- );
