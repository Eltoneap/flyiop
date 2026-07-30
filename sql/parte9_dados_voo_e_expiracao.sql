-- Parte 9 (28/07/2026): companhia aérea e horário de partida, gravados a
-- partir de agora só pela fonte 'live' (fli) — a Travelpayouts ('cache')
-- não devolve esses campos, ficam null nesse caminho. Sem backfill do que
-- já foi perdido, só parar de descartar dado novo.
--
-- ATENÇÃO: rodar este arquivo no SQL Editor do Supabase ANTES do deploy do
-- código desta parte. O código novo grava nessas colunas a cada checagem
-- via fli; se elas não existirem ainda, o insert quebra em produção.

alter table weekend_leg_price_history add column if not exists airline text;
alter table weekend_leg_price_history add column if not exists departure_time timestamptz;

alter table weekend_legs add column if not exists current_airline text;
alter table weekend_legs add column if not exists current_departure_time timestamptz;
