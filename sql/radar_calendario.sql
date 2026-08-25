-- ============================================================================
-- Radar de calendário — schema (fatia 1: implementação, radar_enabled=false).
--
-- CONTEXTO: Etapa 0 (24/08/2026, HISTORICO.md item 24) provou em produção
-- real que `fli.search.dates.SearchDates` devolve o MESMO preço que
-- `SearchFlights` (0,0% de diferença), que 1 bloco de <=61 dias custa 1
-- requisição HTTP, e que a lib só aciona paralelismo interno quando o
-- INTERVALO PEDIDO passa de 61 dias — fatiando na mão, sequencial e
-- espaçado, nunca aciona esse caminho. Este script cria as 3 colunas de
-- config e a tabela nova que sustentam a arquitetura de dois níveis
-- decidida a partir daquele achado: RADAR (esta tabela, grade de
-- calendário, barata) descobre preço; PRECISÃO (SearchFlights, o caminho
-- de sempre) roda só nas datas que o radar apontar perto do teto, e é
-- sempre ela que vira alerta.
--
-- ESCOPO DESTE SCRIPT: só o banco. Nenhuma linha de `weekend_legs`,
-- `weekend_leg_user_state`, `weekend_leg_effective` ou `alert_log` é
-- tocada — a grade do radar é uma tabela nova, isolada, sem FK pra nada
-- do domínio de pernas (chave natural própria: origin/destination/data).
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase. Claude
-- Code não executa SQL (PROTOCOLO-DE-TRABALHO.md).
--
-- ORDEM OBRIGATÓRIA: rodar este script e conferir V1-V3 ANTES de subir o
-- código (radar_check.py, live_check.py, main.py). `get_system_config()`
-- (supabase_client.py) já pede as 3 colunas novas explicitamente na lista
-- de select — subir o código antes do SQL faz o PostgREST devolver 400 e a
-- execução do dia morre inteira, antes de gravar qualquer preço (mesma
-- regra já escrita em sql/fatia_d1_janela_compra_telegram.sql).
--
-- KILL-SWITCH PRÓPRIO: `radar_enabled` nasce `false`, separado de
-- `fast_flights_enabled` (o kill-switch do lote fli já em produção) —
-- desligar um nunca desliga o outro. Nada muda em produção até o usuário
-- rodar manualmente `update system_config set radar_enabled = true` (ver
-- RUNBOOK.md), depois de revisar a primeira varredura real no Actions.
--
-- IDEMPOTENTE E RE-RODÁVEL — todo `add column`/`create table` usa
-- `if not exists`.
--
-- RECEITA DE REVERSÃO:
--   alter table system_config drop column if exists radar_enabled;
--   alter table system_config drop column if exists radar_sweeps_per_day;
--   alter table system_config drop column if exists radar_precision_max_per_run;
--   drop table if exists weekend_radar_grid;
--   (fazer isso só com o código desta fatia fora do ar, ou a próxima
--    execução cai no 400 descrito acima.)
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Bloco 1 — 3 colunas novas em system_config (linha única já existente,
-- sql/system_config.sql). Mesma RLS da tabela (system_config_select_authenticated,
-- SELECT pra autenticado, sem policy de update — edição é via SQL Editor,
-- RUNBOOK.md). Privilégio é de tabela em Postgres, cobre coluna nova sem
-- passo extra de grant.
-- ----------------------------------------------------------------------------
alter table system_config add column if not exists radar_enabled boolean not null default false;
alter table system_config add column if not exists radar_sweeps_per_day integer not null default 2;
alter table system_config add column if not exists radar_precision_max_per_run integer not null default 10;


-- ----------------------------------------------------------------------------
-- Bloco 2 — tabela nova: grade de mercado do radar. Upsert por chave natural
-- (origin, destination, flight_date) — cada varredura sobrescreve o preço
-- mais recente daquela data, nunca acumula linha duplicada por dia (o upsert
-- em si é feito pelo código Python, supabase_client.upsert_weekend_radar_grid,
-- com Prefer: resolution=merge-duplicates + on_conflict=origin,destination,
-- flight_date — não SQL solto).
--
-- Deliberadamente SEPARADA de weekend_leg_price_history: esta tabela é
-- mercado agregado por (aeroporto, data), não preço por perna monitorada —
-- não pode contaminar a média histórica que evaluate_good_price usa
-- (weekends.py). Sem FK pra weekend_legs/weekends: sobrevive independente
-- da vida de qualquer perna, e várias pernas (ida e volta, fins de semana
-- diferentes com a mesma data) podem compartilhar a mesma linha.
-- ----------------------------------------------------------------------------
create table if not exists weekend_radar_grid (
  origin text not null,
  destination text not null,
  flight_date date not null,
  price numeric not null,
  currency text not null default 'BRL',
  swept_at timestamptz not null default now(),
  primary key (origin, destination, flight_date)
);

-- RLS + revoke (adição desta revisão, não estava no prompt original — mesmo
-- par aplicado a toda tabela nova do projeto: Fatia C,
-- sql/fatia_c_visibilidade_compra.sql Bloco 4; Etapa 4.4,
-- sql/etapa4_4_weekend_legs_readonly.sql). Sem o revoke, uma tabela nova
-- nasce legível pelo `anon` por privilégio default do schema `public`. O
-- robô roda como `service_role` (bypassa RLS, sql/system_config.sql segue o
-- mesmo modelo) — nenhuma policy é necessária porque nem `anon` nem
-- `authenticated` devem ler esta tabela ainda (o frontend não a usa nesta
-- fatia).
alter table weekend_radar_grid enable row level security;
revoke all on weekend_radar_grid from anon, authenticated;


-- ----------------------------------------------------------------------------
-- V1 — as 3 colunas de system_config existem, com o default certo, na linha
-- única já existente.
-- ESPERADO: 1 linha, radar_enabled = false, radar_sweeps_per_day = 2,
-- radar_precision_max_per_run = 10.
-- ----------------------------------------------------------------------------
select
  id, radar_enabled, radar_sweeps_per_day, radar_precision_max_per_run
from system_config;


-- ----------------------------------------------------------------------------
-- V2 — weekend_radar_grid existe, vazia, com RLS ligada e zero privilégio
-- pra anon/authenticated (nenhuma policy criada de propósito — só
-- service_role, que bypassa RLS, deve conseguir ler/escrever agora).
-- ESPERADO: linhas = 0, rls_ligada = true, privilegios_anon = 0,
-- privilegios_authenticated = 0.
-- ----------------------------------------------------------------------------
select
  (select count(*) from weekend_radar_grid) as linhas,
  (select relrowsecurity from pg_class where oid = 'public.weekend_radar_grid'::regclass) as rls_ligada,
  ( (has_table_privilege('anon','public.weekend_radar_grid','SELECT')::int) +
    (has_table_privilege('anon','public.weekend_radar_grid','INSERT')::int) +
    (has_table_privilege('anon','public.weekend_radar_grid','UPDATE')::int) +
    (has_table_privilege('anon','public.weekend_radar_grid','DELETE')::int) )
                                                as privilegios_anon,
  ( (has_table_privilege('authenticated','public.weekend_radar_grid','SELECT')::int) +
    (has_table_privilege('authenticated','public.weekend_radar_grid','INSERT')::int) +
    (has_table_privilege('authenticated','public.weekend_radar_grid','UPDATE')::int) +
    (has_table_privilege('authenticated','public.weekend_radar_grid','DELETE')::int) )
                                                as privilegios_authenticated;


-- ----------------------------------------------------------------------------
-- V3 — chave primária composta é mesmo (origin, destination, flight_date) —
-- confirma que o upsert por chave natural do código Python (Bloco 2, acima)
-- vai bater na constraint certa (on_conflict=origin,destination,flight_date).
-- ESPERADO: 1 linha, colunas_chave = 'destination,flight_date,origin'
-- (ordem alfabética do information_schema, não a ordem de declaração).
-- ----------------------------------------------------------------------------
select
  tc.constraint_name,
  string_agg(kcu.column_name, ',' order by kcu.column_name) as colunas_chave
from information_schema.table_constraints tc
join information_schema.key_column_usage kcu
  on kcu.constraint_name = tc.constraint_name and kcu.table_schema = tc.table_schema
where tc.table_schema = 'public' and tc.table_name = 'weekend_radar_grid' and tc.constraint_type = 'PRIMARY KEY'
group by tc.constraint_name;
