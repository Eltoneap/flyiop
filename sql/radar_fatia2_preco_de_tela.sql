-- ============================================================================
-- Radar de calendário — Fatia 2: preço do radar na tela + persistência da
-- comparação radar×precisão.
--
-- CONTEXTO: `sql/radar_calendario.sql` (Fatia 1, 24/08/2026) criou
-- `weekend_radar_grid` — o radar descobre preço em ~88 pernas por varredura,
-- mas só as 7-10 que viram "candidatas de precisão" (radar_check.py,
-- select_precision_candidates) chegavam a `weekend_legs`. A maioria das
-- pernas na aba Compras mostrava preço de 2-3+ dias, mesmo o radar tendo
-- passado de manhã. Registrado como gargalo em `PLANO-ATIVO.md` (seção
-- "Observação para sessão própria" da correção de 01/09/2026, HISTORICO.md
-- item 25) e fechado nesta sessão de planejamento (04/09/2026).
--
-- DECISÃO QUE ESTE SCRIPT SUSTENTA (dois problemas, duas colunas
-- separadas — Desenho B, não reuso de current_price):
--   1. FRESCOR NA TELA: toda perna dentro do alcance do radar passa a
--      gravar `radar_price`/`radar_price_at`/`radar_airport` a cada
--      varredura, mesmo sem confirmação por SearchFlights.
--   2. DISPARO DE ALERTA: CONTINUA exigindo confirmação. `current_price`/
--      `current_price_at` só são escritos por quem sempre escreveu
--      (SearchFlights via live_check.py, Travelpayouts via weekends.py) —
--      o radar NUNCA escreve nessas colunas, e o caminho de alerta
--      (weekends.py:evaluate_and_record_leg_price, rules.py) nunca lê
--      radar_price. As duas garantias que tornam isso seguro, verificadas
--      por leitura de código nesta sessão: o radar não grava em
--      `weekend_leg_price_history` (contaminaria a média de 90 dias que
--      decide oportunidade/suspeita) nem em `lowest_seen`/`lowest_seen_at`
--      (autoextinguiria o gatilho `new_low` da própria seleção de
--      precisão, radar_check.py:select_precision_candidates).
--
-- `current_price_at` é column nova mesmo para o caminho que já existia:
-- até agora `last_live_check_at` era usado pro rótulo "atualizado há Xh" da
-- aba Compras, mas essa coluna avança em toda TENTATIVA (sucesso ou falha,
-- live_check.py:check_and_evaluate_leg) e não é escrita pelo caminho cache
-- — o rótulo já mentia sobre a idade do preço antes desta fatia. Corrigido
-- aqui: `current_price_at` grava TODA VEZ que `current_price` é escrito
-- (weekends.py:evaluate_and_record_leg_price), mesmo quando o valor
-- repete o de antes — de propósito, não descuido: um preço reconfirmado
-- hoje deve mostrar "atualizado hoje", não a data da última vez que o
-- valor mudou.
--
-- `precision_transfers` (revisão de 04/09/2026, item 3): número de
-- escalas que a PRECISÃO encontrou pra cada comparação — sem ela, o
-- checkpoint de 01/12/2026 (`PLANO-ATIVO.md`) não consegue responder "há
-- comparação em perna com escala": `precision_airport` sozinho só diz
-- GIG/SDU, nunca conexões, e é por isso que a amostra de hoje parece toda
-- voo direto (era literalmente invisível antes desta coluna).
--
-- PERSISTÊNCIA DA DIVERGÊNCIA (item 7, decisão do usuário 04/09/2026):
-- `radar_check.py:log_precision_divergence` só imprime no log do Actions,
-- que expira. O checkpoint de reavaliação de 01/12/2026 (ver
-- `PLANO-ATIVO.md`, seção "Checkpoint — radar como gatilho de alerta")
-- precisa de dado consultável ao longo do tempo. `weekend_radar_precision_log`
-- grava 1 linha por candidata de precisão processada (7-10/run, mesmo
-- volume de sempre) — não adiciona nenhuma consulta nova, só persiste uma
-- comparação que já é calculada em memória.
--
-- ESCOPO: só o banco. Nenhuma linha de `weekend_leg_price_history`,
-- `weekend_leg_user_state`, `weekend_leg_effective` ou `alert_log` é
-- tocada — `weekend_leg_effective` (a view) NÃO é recriada nesta fatia,
-- por decisão explícita: o Dashboard continua lendo só preço confirmado,
-- só a aba Compras (que já faz um segundo select direto em `weekend_legs`,
-- docs/js/compras.js) ganha as colunas novas.
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase. Claude
-- Code não executa SQL (PROTOCOLO-DE-TRABALHO.md).
--
-- ORDEM OBRIGATÓRIA: rodar este script e conferir V1-V4 (e V2b) ANTES de subir o
-- código desta fatia (main.py grava em `weekend_legs.radar_price` e em
-- `weekend_radar_precision_log` a cada execução com `radar_enabled=true`
-- — subir o código antes do SQL faz o PostgREST devolver 400 na primeira
-- escrita, mesma regra de sempre, ex. `sql/radar_calendario.sql`).
--
-- IDEMPOTENTE E RE-RODÁVEL — todo `add column`/`create table` usa
-- `if not exists`.
--
-- RECEITA DE REVERSÃO:
--   alter table weekend_legs drop column if exists radar_price;
--   alter table weekend_legs drop column if exists radar_price_at;
--   alter table weekend_legs drop column if exists radar_airport;
--   alter table weekend_legs drop column if exists current_price_at;
--   drop table if exists weekend_radar_precision_log;
--   (fazer isso só com o código desta fatia fora do ar, ou a próxima
--    execução cai no 400 descrito acima.)
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Bloco 1 — 4 colunas novas em weekend_legs.
--
-- Nenhuma policy nova: weekend_legs já é somente-leitura no navegador desde
-- a Etapa 4.4 (`sql/etapa4_4_weekend_legs_readonly.sql`) — `authenticated`
-- tem SELECT, nunca UPDATE; quem escreve é só o robô (service_role, que
-- bypassa RLS). Coluna nova numa tabela existente herda o mesmo regime, sem
-- passo extra de grant/revoke.
-- ----------------------------------------------------------------------------
alter table weekend_legs add column if not exists radar_price numeric;
alter table weekend_legs add column if not exists radar_price_at timestamptz;
alter table weekend_legs add column if not exists radar_airport text;       -- 'GIG' | 'SDU'
alter table weekend_legs add column if not exists current_price_at timestamptz;


-- ----------------------------------------------------------------------------
-- Bloco 2 — tabela nova: histórico de comparação radar×precisão, por
-- candidata processada. Mesmo padrão de RLS de `weekend_radar_grid`
-- (Fatia 1): só `service_role` lê/escreve, nada de policy pra
-- anon/authenticated — esta fatia não expõe a comparação no painel, é
-- consulta manual via SQL Editor pro checkpoint de 01/12/2026.
--
-- Sem UNIQUE/upsert de propósito: cada execução do laço de precisão
-- (main.py) gera 1 linha nova por candidata — é histórico, não estado
-- corrente (diferente de weekend_radar_grid, que é upsert por chave
-- natural). Volume: mesmo das candidatas de precisão de sempre, 7-10/run,
-- 2 runs/dia — irrelevante.
-- ----------------------------------------------------------------------------
create table if not exists weekend_radar_precision_log (
  id uuid primary key default gen_random_uuid(),
  leg_id uuid not null references weekend_legs(id) on delete cascade,
  travel_date date not null,
  radar_price numeric not null,
  radar_airport text,
  precision_status text not null,       -- 'ok' | 'no_data' (radar_check.check_and_evaluate_leg)
  precision_price numeric,              -- null quando precision_status = 'no_data'
  precision_airport text,
  precision_transfers integer,          -- escalas da PRECISÃO (0 = direto, >=1 = com conexão); null sem precision_price
  diff_pct numeric,                     -- (precision_price - radar_price) / radar_price * 100; null sem precision_price
  checked_at timestamptz not null default now()
);

alter table weekend_radar_precision_log enable row level security;
revoke all on weekend_radar_precision_log from anon, authenticated;


-- ----------------------------------------------------------------------------
-- V1 — as 4 colunas de weekend_legs existem, todas nullable, sem default.
-- ESPERADO: 4 linhas, is_nullable = 'YES' nas 4.
-- ----------------------------------------------------------------------------
select column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public' and table_name = 'weekend_legs'
  and column_name in ('radar_price', 'radar_price_at', 'radar_airport', 'current_price_at')
order by column_name;


-- ----------------------------------------------------------------------------
-- V2 — weekend_radar_precision_log existe, vazia, com RLS ligada e zero
-- privilégio pra anon/authenticated.
-- ESPERADO: linhas = 0, rls_ligada = true, privilegios_anon = 0,
-- privilegios_authenticated = 0.
-- ----------------------------------------------------------------------------
select
  (select count(*) from weekend_radar_precision_log) as linhas,
  (select relrowsecurity from pg_class where oid = 'public.weekend_radar_precision_log'::regclass) as rls_ligada,
  ( (has_table_privilege('anon','public.weekend_radar_precision_log','SELECT')::int) +
    (has_table_privilege('anon','public.weekend_radar_precision_log','INSERT')::int) +
    (has_table_privilege('anon','public.weekend_radar_precision_log','UPDATE')::int) +
    (has_table_privilege('anon','public.weekend_radar_precision_log','DELETE')::int) )
                                                as privilegios_anon,
  ( (has_table_privilege('authenticated','public.weekend_radar_precision_log','SELECT')::int) +
    (has_table_privilege('authenticated','public.weekend_radar_precision_log','INSERT')::int) +
    (has_table_privilege('authenticated','public.weekend_radar_precision_log','UPDATE')::int) +
    (has_table_privilege('authenticated','public.weekend_radar_precision_log','DELETE')::int) )
                                                as privilegios_authenticated;


-- ----------------------------------------------------------------------------
-- V2b — weekend_radar_precision_log tem a coluna precision_transfers
-- (escalas do lado da precisão, item 3 da revisão de 04/09/2026) — sem
-- ela, o checkpoint de 01/12/2026 não consegue responder "há comparação
-- em perna com escala".
-- ESPERADO: 1 linha, data_type = 'integer', is_nullable = 'YES'.
-- ----------------------------------------------------------------------------
select data_type, is_nullable
from information_schema.columns
where table_schema = 'public' and table_name = 'weekend_radar_precision_log'
  and column_name = 'precision_transfers';


-- ----------------------------------------------------------------------------
-- V3 — weekend_legs continua sem privilégio de UPDATE pra anon/authenticated
-- (Etapa 4.4) — as 4 colunas novas não reabrem a superfície de escrita.
-- ESPERADO: authenticated_ainda_pode_update = false, anon_ainda_pode_update
-- = false.
-- ----------------------------------------------------------------------------
select
  has_table_privilege('authenticated','public.weekend_legs','UPDATE') as authenticated_ainda_pode_update,
  has_table_privilege('anon','public.weekend_legs','UPDATE') as anon_ainda_pode_update;


-- ----------------------------------------------------------------------------
-- V4 — a FK de weekend_radar_precision_log aponta pra weekend_legs.id, com
-- ON DELETE CASCADE (perna removida não deixa comparação órfã).
-- ESPERADO: 1 linha, tabela_referenciada = 'weekend_legs', delete_rule =
-- 'CASCADE'.
-- ----------------------------------------------------------------------------
select
  ccu.table_name as tabela_referenciada,
  rc.delete_rule
from information_schema.table_constraints tc
join information_schema.constraint_column_usage ccu
  on ccu.constraint_name = tc.constraint_name and ccu.table_schema = tc.table_schema
join information_schema.referential_constraints rc
  on rc.constraint_name = tc.constraint_name and rc.constraint_schema = tc.table_schema
where tc.table_schema = 'public' and tc.table_name = 'weekend_radar_precision_log'
  and tc.constraint_type = 'FOREIGN KEY';
