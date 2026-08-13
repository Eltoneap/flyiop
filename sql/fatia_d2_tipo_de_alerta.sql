-- ============================================================================
-- Fatia D2 — Parte 1/3 — alert_log ganha tipo de alerta (banco).
--
-- CONTEXTO: bug estrutural documentado em STATE.md, seção 2 (investigação de
-- 12/08/2026) — hoje o cooldown de perna (get_last_weekend_leg_alert) filtra
-- só por leg_id, não por TIPO de alerta (teto vs. oportunidade). Um alerta
-- de oportunidade pode segurar um de teto da mesma perna (e vice-versa) sem
-- que devesse. O bug é real no código mas NÃO produziu perda observável nos
-- últimos 14 dias (zero hits de teto no período — preço travado em R$334
-- contra teto R$300 desde 05/08 — logo nenhuma colisão de fato ocorreu).
-- Não é urgente; precisa ser corrigido antes de D3 (user_id em alert_log) e
-- D4 (avaliação por usuário), que mexem no mesmo schema.
--
-- POR QUE DUAS COLUNAS BOOLEANAS, NÃO UMA COLUNA DE TIPO: existem hoje
-- linhas de alerta com AMBOS os motivos na mesma linha (reason composto por
-- ";" — ex. "abaixo da meta fixa (R$ 250.0); 23.1% abaixo da média histórica
-- (R$ 232.62)"). Uma coluna única de tipo forçaria um valor especial tipo
-- 'both', frágil para quem esquecer de tratá-lo no filtro de cooldown —
-- exatamente a classe de bug que esta fatia corrige. Por isso:
--   is_ceiling_alert     boolean not null default false
--   is_opportunity_alert boolean not null default false
-- `reason` CONVIVE com as colunas novas — não é substituído nem removido,
-- segue como texto livre de forense; as colunas novas são a chave
-- estruturada usada no filtro de cooldown.
--
-- ESCOPO DESTA PARTE: só o banco (2 colunas + 1 índice numa tabela
-- existente, mais o backfill das linhas já gravadas). O código Python que
-- grava/lê as colunas é a Parte 2/3 da mesma fatia.
--
-- ESTA FATIA NÃO MUDA O QUE É ALERTADO NEM O QUE É COLETADO — só ACRESCENTA
-- estrutura para o cooldown decidir com mais precisão QUANDO um alerta já
-- devido é ou não reenviado. weekend_legs, weekend_leg_user_state e
-- weekend_leg_effective não são tocadas por este arquivo.
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase — mesmo
-- fluxo dos scripts anteriores desta iniciativa. Claude Code não executa SQL.
--
-- ⚠️ ORDEM OBRIGATÓRIA E JANELA DE DEPLOY — DIFERENTE DA D1:
-- Na D1 bastava rodar o SQL antes do código (código pedindo coluna
-- inexistente = 400 e execução morre inteira). Aqui existe uma JANELA
-- adicional: entre rodar este SQL e publicar o código da Parte 2, o robô
-- CONTINUA gravando em alert_log pelo caminho antigo (sem as colunas) — a
-- linha nasce com is_ceiling_alert=false e is_opportunity_alert=false por
-- DEFAULT da coluna, mesmo tendo `reason` classificável. Isso é exatamente
-- o que o bloco V2 define como defeito ("órfã com reason classificável").
--   1. Rode este script (Blocos 1-3) e confirme V1-V6 DENTRO da mesma janela
--      entre duas execuções consecutivas do robô — o robô roda 2x/dia
--      (08h/20h BRT); exemplo concreto observado em 13/08/2026: janela
--      segura ~08:40-20:00 BRT, entre a execução primária das 08:37 e a das
--      20h.
--   2. Publique o código da Parte 2 ainda dentro dessa mesma janela.
--   3. Se uma execução do robô cair NO MEIO (SQL rodado, código ainda não
--      publicado): não é defeito, é operação esperada — as linhas gravadas
--      nessa janela nascem false/false por desenho do DEFAULT da coluna.
--      Basta rodar o Bloco 3 (backfill) de novo depois de publicar o
--      código; o guarda de idempotência do Bloco 3 (`where is_ceiling_alert
--      is false and is_opportunity_alert is false`) já cobre esse caso sem
--      sobrescrever nenhuma linha que o código novo já classificou.
--
-- SOBRE GRANTS/RLS: mesma conclusão e mesmo raciocínio do cabeçalho de
-- sql/fatia_d1_janela_compra_telegram.sql:38-46 — `alter table add column`
-- não abre a janela de privilégio default (privilégio é de TABELA em
-- Postgres). A única policy de alert_log (alert_log_select_own_routes_or_any_leg,
-- SELECT, cobrindo route_id/leg_id — Etapa 2, 29/07/2026) não referencia as
-- colunas novas em predicado nenhum. O robô grava como service_role, que
-- ignora RLS. V5 mede e compara com o G0 em vez de presumir.
--
-- ÍNDICE NOVO: (leg_id, sent_at desc) — sem a coluna de tipo. Com poucas
-- linhas por perna, o planner varre a perna já ordenada e aplica o filtro
-- booleano por cima; um índice só serve os dois tipos. Registro explícito,
-- decisão aceita de antemão: a D3 (user_id em alert_log) provavelmente vai
-- querer recriar este índice como (leg_id, user_id, sent_at desc) — não é
-- pendência desta fatia.
--
-- IDEMPOTENTE E RE-RODÁVEL. O Bloco 3 (backfill) só toca linhas ainda não
-- classificadas (false/false) — rodar de novo depois que o código novo já
-- gravou linhas classificadas não sobrescreve nada.
--
-- RECEITA DE REVERSÃO:
--   drop index if exists alert_log_leg_sent_at_idx;
--   alter table alert_log
--     drop column if exists is_ceiling_alert,
--     drop column if exists is_opportunity_alert;
--   (fazer isso só com o código da Parte 2 fora do ar — senão o filtro por
--    tipo em get_last_weekend_leg_alert pede coluna inexistente e o
--    PostgREST devolve 400 na consulta de cooldown.)
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO G0 — Guarda de inventário, só-leitura. Confirma o estado ANTES de
-- agir, para não operar sobre suposição.
--
-- ESPERADO (13/08/2026, medido no chat de planejamento):
--   colunas_alert_log            = id,leg_id,price,reason,route_id,sent_at (6)
--   coluna_is_ceiling_existe     = false
--   coluna_is_opportunity_existe = false
--   linhas_total                 = 74  (52 de perna, 22 de rota)
--   periodo                      = 2026-07-22 a 2026-08-12
--   indices_alert_log            = alert_log_pkey (1 só)
--   rls_ligada                   = true
--   politicas                    = alert_log_select_own_routes_or_any_leg
--   policy_cmd                   = SELECT
--   anon/authenticated/service_role_privilegios = 7/7/7
--
-- CLASSIFICAÇÃO PREVISTA (derivada do `reason`, calculada abaixo — é o que o
-- Bloco 3 vai gravar):
--   perna: só_teto=10, só_oportunidade=40, ambas=2, nenhuma=0
--   rota:  só_teto=17, só_oportunidade=0,  ambas=5, nenhuma=0
--
-- RESSALVA: o robô roda 2x/dia — pode haver 1-2 linhas novas entre a medição
-- de 12/08/2026 e a execução deste script. A execução de 13/08/2026 08:37
-- BRT (pós-deploy D1) não gravou nenhuma linha nova (0 alertas enviados,
-- confirmado no log do Actions) — `linhas_total` deve seguir em 74. Se um
-- número divergir dos esperados acima E linhas_total > 74, isso é
-- crescimento orgânico esperado, não erro — confira que a SOMA
-- (só_teto+só_oport+ambas+nenhuma) ainda bate com o total antes de seguir.
-- Se a soma não bater, ou se nenhuma > 0 para PERNA, PARE e traga ao chat de
-- planejamento antes do Bloco 3.
-- ----------------------------------------------------------------------------
select
  (select string_agg(column_name, ',' order by column_name)
     from information_schema.columns
    where table_schema = 'public' and table_name = 'alert_log'
  )                                                              as colunas_alert_log,
  exists (
    select 1 from information_schema.columns
     where table_schema = 'public' and table_name = 'alert_log'
       and column_name = 'is_ceiling_alert'
  )                                                              as coluna_is_ceiling_existe,
  exists (
    select 1 from information_schema.columns
     where table_schema = 'public' and table_name = 'alert_log'
       and column_name = 'is_opportunity_alert'
  )                                                              as coluna_is_opportunity_existe,
  (select count(*) from alert_log)                               as linhas_total,
  (select count(*) from alert_log where leg_id is not null)      as linhas_perna,
  (select count(*) from alert_log where route_id is not null)    as linhas_rota,
  (select min(sent_at)::date from alert_log)                     as periodo_inicio,
  (select max(sent_at)::date from alert_log)                     as periodo_fim,
  (select string_agg(indexname, ',' order by indexname) from pg_indexes
    where schemaname = 'public' and tablename = 'alert_log')     as indices_alert_log,
  (select relrowsecurity from pg_class where oid = 'public.alert_log'::regclass)
                                                                 as rls_ligada,
  (select string_agg(policyname, ',' order by policyname) from pg_policies
    where schemaname = 'public' and tablename = 'alert_log')     as politicas,
  (select string_agg(distinct cmd, ',') from pg_policies
    where schemaname = 'public' and tablename = 'alert_log')     as policy_cmd,
  ( (has_table_privilege('anon','public.alert_log','SELECT')::int) +
    (has_table_privilege('anon','public.alert_log','INSERT')::int) +
    (has_table_privilege('anon','public.alert_log','UPDATE')::int) +
    (has_table_privilege('anon','public.alert_log','DELETE')::int) +
    (has_table_privilege('anon','public.alert_log','TRUNCATE')::int) +
    (has_table_privilege('anon','public.alert_log','REFERENCES')::int) +
    (has_table_privilege('anon','public.alert_log','TRIGGER')::int)
  )                                                              as anon_privilegios,
  ( (has_table_privilege('authenticated','public.alert_log','SELECT')::int) +
    (has_table_privilege('authenticated','public.alert_log','INSERT')::int) +
    (has_table_privilege('authenticated','public.alert_log','UPDATE')::int) +
    (has_table_privilege('authenticated','public.alert_log','DELETE')::int) +
    (has_table_privilege('authenticated','public.alert_log','TRUNCATE')::int) +
    (has_table_privilege('authenticated','public.alert_log','REFERENCES')::int) +
    (has_table_privilege('authenticated','public.alert_log','TRIGGER')::int)
  )                                                              as authenticated_privilegios,
  ( (has_table_privilege('service_role','public.alert_log','SELECT')::int) +
    (has_table_privilege('service_role','public.alert_log','INSERT')::int) +
    (has_table_privilege('service_role','public.alert_log','UPDATE')::int) +
    (has_table_privilege('service_role','public.alert_log','DELETE')::int) +
    (has_table_privilege('service_role','public.alert_log','TRUNCATE')::int) +
    (has_table_privilege('service_role','public.alert_log','REFERENCES')::int) +
    (has_table_privilege('service_role','public.alert_log','TRIGGER')::int)
  )                                                              as service_role_privilegios;

-- Classificação prevista (perna), derivada do reason — conferir contra
-- 10 / 40 / 2 / 0 antes de rodar o Bloco 3.
select
  count(*) filter (where reason like '%abaixo da meta fixa%' and reason not like '%abaixo da média histórica%')
                                                                 as so_teto,
  count(*) filter (where reason like '%abaixo da média histórica%' and reason not like '%abaixo da meta fixa%')
                                                                 as so_oportunidade,
  count(*) filter (where reason like '%abaixo da meta fixa%' and reason like '%abaixo da média histórica%')
                                                                 as ambas,
  count(*) filter (where (reason is null
                          or (reason not like '%abaixo da meta fixa%'
                              and reason not like '%abaixo da média histórica%')))
                                                                 as nenhuma_orfa
  from alert_log where leg_id is not null;

-- Classificação prevista (rota) — órfãs aqui podem ser legítimas (alerta de
-- rota também dispara por TENDÊNCIA, detect_trend, cujo reason não contém
-- nenhuma das duas substrings) — conferir contra 17 / 0 / 5 / (nenhuma_orfa
-- não tem esperado fixo, é o resíduo de tendência).
select
  count(*) filter (where reason like '%abaixo da meta fixa%' and reason not like '%abaixo da média histórica%')
                                                                 as so_teto,
  count(*) filter (where reason like '%abaixo da média histórica%' and reason not like '%abaixo da meta fixa%')
                                                                 as so_oportunidade,
  count(*) filter (where reason like '%abaixo da meta fixa%' and reason like '%abaixo da média histórica%')
                                                                 as ambas,
  count(*) filter (where (reason is null
                          or (reason not like '%abaixo da meta fixa%'
                              and reason not like '%abaixo da média histórica%')))
                                                                 as nenhuma_orfa_tendencia
  from alert_log where route_id is not null;


-- ----------------------------------------------------------------------------
-- BLOCO 1 — as duas colunas booleanas.
--
-- not null + default false preenche as 74 linhas existentes na mesma
-- instrução, sem `update` separado (Postgres >= 11 não reescreve a tabela
-- para adicionar coluna com default constante). `if not exists` torna
-- idempotente.
-- ----------------------------------------------------------------------------
alter table alert_log
  add column if not exists is_ceiling_alert boolean not null default false,
  add column if not exists is_opportunity_alert boolean not null default false;


-- ----------------------------------------------------------------------------
-- BLOCO 2 — índice (leg_id, sent_at desc). Ver justificativa no cabeçalho
-- (sem a coluna de tipo — um índice só serve os dois tipos de cooldown).
-- ----------------------------------------------------------------------------
create index if not exists alert_log_leg_sent_at_idx on alert_log (leg_id, sent_at desc);


-- ----------------------------------------------------------------------------
-- BLOCO 3 — backfill das linhas existentes, derivado do `reason`.
--
-- As duas substrings vêm literalmente de src/rules.py (evaluate_good_price):
-- "abaixo da meta fixa" (teto) e "abaixo da média histórica" (oportunidade).
--
-- GUARDA DE IDEMPOTÊNCIA: só toca linha com as duas flags ainda em `false`
-- (o default). Rodar de novo depois que o código da Parte 2 já gravou
-- linhas novas classificadas não sobrescreve nada — e é exatamente o
-- procedimento de recuperação se uma execução do robô cair na janela entre
-- o SQL e o deploy do código (ver cabeçalho).
-- ----------------------------------------------------------------------------
update alert_log
   set is_ceiling_alert     = (reason like '%abaixo da meta fixa%'),
       is_opportunity_alert = (reason like '%abaixo da média histórica%')
 where is_ceiling_alert is false
   and is_opportunity_alert is false
   and (reason like '%abaixo da meta fixa%' or reason like '%abaixo da média histórica%');


-- ============================================================================
-- VERIFICAÇÃO — rodar depois do Bloco 3, DENTRO DA MESMA JANELA entre
-- execuções do robô (ver cabeçalho). V1/V2/V4/V5 são asserções; V3 só vale
-- se nenhuma execução do robô ocorreu entre o Bloco 3 e a re-rodada dele; V6
-- é a prova sintética, em transação com rollback, e pode ser rodada a
-- qualquer momento (não altera dado real).
-- ============================================================================


-- ----------------------------------------------------------------------------
-- V1 — as colunas existem, com o tipo/nulidade/default certos, e nenhuma
-- linha ficou com valor nulo (impossível dado not null, é dupla checagem).
--
-- ESPERADO: existe=true/true, tipo=boolean/boolean, aceita_nulo=NO/NO,
-- default_declarado contém false, linhas_com_nulo=0.
-- ----------------------------------------------------------------------------
select
  exists (select 1 from information_schema.columns
           where table_schema='public' and table_name='alert_log' and column_name='is_ceiling_alert')
                                                                 as is_ceiling_existe,
  exists (select 1 from information_schema.columns
           where table_schema='public' and table_name='alert_log' and column_name='is_opportunity_alert')
                                                                 as is_opportunity_existe,
  (select data_type from information_schema.columns
    where table_schema='public' and table_name='alert_log' and column_name='is_ceiling_alert')
                                                                 as tipo_ceiling,
  (select data_type from information_schema.columns
    where table_schema='public' and table_name='alert_log' and column_name='is_opportunity_alert')
                                                                 as tipo_opportunity,
  (select is_nullable from information_schema.columns
    where table_schema='public' and table_name='alert_log' and column_name='is_ceiling_alert')
                                                                 as aceita_nulo_ceiling,
  (select is_nullable from information_schema.columns
    where table_schema='public' and table_name='alert_log' and column_name='is_opportunity_alert')
                                                                 as aceita_nulo_opportunity,
  (select column_default from information_schema.columns
    where table_schema='public' and table_name='alert_log' and column_name='is_ceiling_alert')
                                                                 as default_ceiling,
  (select count(*) from alert_log where is_ceiling_alert is null or is_opportunity_alert is null)
                                                                 as linhas_com_nulo;


-- ----------------------------------------------------------------------------
-- V2 — resultado real do backfill, e a soma bate com o total.
--
-- ESPERADO: perna = 10/40/2/0 (nenhuma_orfa_com_reason_classificavel = 0 —
-- defeito se > 0); rota = 17/0/5/N (nenhuma_orfa_tendencia >= 0, legítima —
-- alerta de rota por tendência não tem reason classificável nas duas
-- substrings, não é bug). Em ambos os casos a SOMA das 4 contagens tem que
-- bater com linhas_perna/linhas_rota do G0 (mais crescimento orgânico, se
-- houver).
-- ----------------------------------------------------------------------------
select
  'perna'                                                        as escopo,
  count(*) filter (where is_ceiling_alert and not is_opportunity_alert)      as so_teto,
  count(*) filter (where is_opportunity_alert and not is_ceiling_alert)      as so_oportunidade,
  count(*) filter (where is_ceiling_alert and is_opportunity_alert)          as ambas,
  count(*) filter (where not is_ceiling_alert and not is_opportunity_alert
                    and (reason like '%abaixo da meta fixa%' or reason like '%abaixo da média histórica%'))
                                                                 as orfa_com_reason_classificavel,
  count(*)                                                       as total
  from alert_log where leg_id is not null
union all
select
  'rota'                                                         as escopo,
  count(*) filter (where is_ceiling_alert and not is_opportunity_alert)      as so_teto,
  count(*) filter (where is_opportunity_alert and not is_ceiling_alert)      as so_oportunidade,
  count(*) filter (where is_ceiling_alert and is_opportunity_alert)          as ambas,
  count(*) filter (where not is_ceiling_alert and not is_opportunity_alert
                    and (reason like '%abaixo da meta fixa%' or reason like '%abaixo da média histórica%'))
                                                                 as orfa_com_reason_classificavel,
  count(*)                                                       as total
  from alert_log where route_id is not null;


-- ----------------------------------------------------------------------------
-- V3 — idempotência: re-rodar o Bloco 3 na sequência retorna UPDATE 0.
--
-- SÓ VALE se nenhuma execução do robô ocorreu entre o Bloco 3 original e
-- esta re-rodada (o robô roda 2x/dia, 08h/20h BRT) — se uma execução caiu no
-- meio, o guarda de idempotência ainda impede sobrescrever linha já
-- classificada, mas pode haver linha NOVA gravada pelo código antigo
-- (false/false com reason classificável) esperando por este mesmo Bloco 3,
-- e nesse caso um UPDATE > 0 é o comportamento CORRETO de recuperação, não
-- falha do bloco.
-- ----------------------------------------------------------------------------
update alert_log
   set is_ceiling_alert     = (reason like '%abaixo da meta fixa%'),
       is_opportunity_alert = (reason like '%abaixo da média histórica%')
 where is_ceiling_alert is false
   and is_opportunity_alert is false
   and (reason like '%abaixo da meta fixa%' or reason like '%abaixo da média histórica%');


-- ----------------------------------------------------------------------------
-- V4 — índice criado com a definição certa. SEM asserção de uso via explain:
-- com ~74 linhas o planner escolhe seqscan de qualquer jeito (é a escolha
-- CERTA do planner nesse volume) — assertar uso seria prova que falha pelo
-- motivo errado.
--
-- ESPERADO: indice_existe = true, indexdef contém "leg_id" e "sent_at DESC",
-- total_indices_alert_log = 2 (PK + este).
-- ----------------------------------------------------------------------------
select
  exists (select 1 from pg_indexes where schemaname='public' and tablename='alert_log'
           and indexname='alert_log_leg_sent_at_idx')            as indice_existe,
  (select indexdef from pg_indexes where schemaname='public' and tablename='alert_log'
    and indexname='alert_log_leg_sent_at_idx')                   as indexdef,
  (select count(*) from pg_indexes where schemaname='public' and tablename='alert_log')
                                                                 as total_indices_alert_log;


-- ----------------------------------------------------------------------------
-- V5 — RLS/grants INALTERADOS, comparados com o que o G0 mediu antes.
--
-- ESPERADO: rls_ligada=true, rls_forcada=false, 1 política
-- (alert_log_select_own_routes_or_any_leg), policy_cmd=SELECT,
-- policies_escrita=0, e os TRÊS contadores de privilégio IDÊNTICOS ao G0
-- (adicionar coluna não concede privilégio novo — privilégio é de tabela).
-- ----------------------------------------------------------------------------
select
  (select relrowsecurity from pg_class where oid = 'public.alert_log'::regclass)
                                                                 as rls_ligada,
  (select relforcerowsecurity from pg_class where oid = 'public.alert_log'::regclass)
                                                                 as rls_forcada,
  (select string_agg(policyname, ',' order by policyname) from pg_policies
    where schemaname='public' and tablename='alert_log')         as politicas,
  (select string_agg(distinct cmd, ',') from pg_policies
    where schemaname='public' and tablename='alert_log')         as policy_cmd,
  (select count(*) from pg_policies
    where schemaname='public' and tablename='alert_log'
      and cmd in ('INSERT','UPDATE','DELETE','ALL'))             as policies_escrita,
  ( (has_table_privilege('anon','public.alert_log','SELECT')::int) +
    (has_table_privilege('anon','public.alert_log','INSERT')::int) +
    (has_table_privilege('anon','public.alert_log','UPDATE')::int) +
    (has_table_privilege('anon','public.alert_log','DELETE')::int) +
    (has_table_privilege('anon','public.alert_log','TRUNCATE')::int) +
    (has_table_privilege('anon','public.alert_log','REFERENCES')::int) +
    (has_table_privilege('anon','public.alert_log','TRIGGER')::int)
  )                                                              as anon_privilegios,
  ( (has_table_privilege('authenticated','public.alert_log','SELECT')::int) +
    (has_table_privilege('authenticated','public.alert_log','INSERT')::int) +
    (has_table_privilege('authenticated','public.alert_log','UPDATE')::int) +
    (has_table_privilege('authenticated','public.alert_log','DELETE')::int) +
    (has_table_privilege('authenticated','public.alert_log','TRUNCATE')::int) +
    (has_table_privilege('authenticated','public.alert_log','REFERENCES')::int) +
    (has_table_privilege('authenticated','public.alert_log','TRIGGER')::int)
  )                                                              as authenticated_privilegios,
  ( (has_table_privilege('service_role','public.alert_log','SELECT')::int) +
    (has_table_privilege('service_role','public.alert_log','INSERT')::int) +
    (has_table_privilege('service_role','public.alert_log','UPDATE')::int) +
    (has_table_privilege('service_role','public.alert_log','DELETE')::int) +
    (has_table_privilege('service_role','public.alert_log','TRUNCATE')::int) +
    (has_table_privilege('service_role','public.alert_log','REFERENCES')::int) +
    (has_table_privilege('service_role','public.alert_log','TRIGGER')::int)
  )                                                              as service_role_privilegios;


-- ----------------------------------------------------------------------------
-- V6 — PROVA SINTÉTICA da semântica de cooldown, transação com ROLLBACK.
-- Mesmo padrão de sql/fatia_c_visibilidade_compra.sql (Blocos de prova com
-- begin/rollback). Cobre o "antes x depois" que nenhum dado de produção dá
-- hoje — o cenário que expõe o bug (colisão teto x oportunidade ENTRE
-- execuções diferentes) não ocorreu nos últimos 14 dias (zero hits de teto).
--
-- O QUE ISTO PROVA: que a consulta NOVA (leg_id + tipo) resolve
-- corretamente os casos onde a consulta VELHA (só leg_id) erraria.
-- O QUE ISTO NÃO PROVA: que o caminho inteiro em produção (robô grava as
-- flags certas E o cooldown da execução seguinte lê certo) funciona de
-- ponta a ponta com dado que o próprio robô escreveu — isso só uma colisão
-- real confirma (não ocorreu ainda; ver nota na documentação da fatia).
--
-- ESPERADO (prints na saída):
--   antes_bug_confundiria_oportunidade_com_teto = 1  <- o BUG: a consulta
--     velha devolveria a linha de oportunidade como se fosse candidata a
--     bloquear um alerta de TETO
--   depois_teto_correto  = 0   <- a CORREÇÃO: filtrando por is_ceiling_alert,
--     não há nenhum alerta de teto recente -> não bloqueia
--   depois_oportunidade_correto = 1, preco = 999.00  <- cooldown do PRÓPRIO
--     tipo continua funcionando
--   composto_ambas_teto = 1, composto_ambas_oportunidade = 1  <- linha
--     composta (as duas flags true) satisfaz as duas consultas -> renova os
--     dois relógios, consequência aceita da DEC-2 (ver documentação da fatia)
--   linhas_apos_rollback = linhas_total do G0 (nada persiste)
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';

  do $$
  declare v_leg uuid;
  begin
    -- perna real sem NENHUMA linha em alert_log ainda, pra não contaminar
    -- com histórico real
    select l.id into v_leg from weekend_legs l
     where not exists (select 1 from alert_log a where a.leg_id = l.id)
     limit 1;

    -- semeia só oportunidade, sem teto
    insert into alert_log (leg_id, price, reason, is_ceiling_alert, is_opportunity_alert)
    values (v_leg, 999.00, '20.0% abaixo da média histórica (R$ 1200.00)', false, true);

    perform set_config('flyiop.probe_bug_velho',
      (select count(*)::text from alert_log where leg_id = v_leg), true);  -- consulta velha: só leg_id
    perform set_config('flyiop.probe_novo_teto',
      (select count(*)::text from alert_log where leg_id = v_leg and is_ceiling_alert is true), true);
    perform set_config('flyiop.probe_novo_oport_count',
      (select count(*)::text from alert_log where leg_id = v_leg and is_opportunity_alert is true), true);
    perform set_config('flyiop.probe_novo_oport_preco',
      (select price::text from alert_log where leg_id = v_leg and is_opportunity_alert is true
        order by sent_at desc limit 1), true);

    -- segunda perna, linha composta (as duas flags true)
    declare v_leg2 uuid;
    begin
      select l.id into v_leg2 from weekend_legs l
       where l.id <> v_leg
         and not exists (select 1 from alert_log a where a.leg_id = l.id)
       limit 1;

      insert into alert_log (leg_id, price, reason, is_ceiling_alert, is_opportunity_alert)
      values (v_leg2, 250.00,
              'abaixo da meta fixa (R$ 300); 23.1% abaixo da média histórica (R$ 232.62)',
              true, true);

      perform set_config('flyiop.probe_composto_teto',
        (select count(*)::text from alert_log where leg_id = v_leg2 and is_ceiling_alert is true), true);
      perform set_config('flyiop.probe_composto_oport',
        (select count(*)::text from alert_log where leg_id = v_leg2 and is_opportunity_alert is true), true);
    end;
  end $$;

  select
    current_setting('flyiop.probe_bug_velho',         true) as antes_bug_confundiria_oportunidade_com_teto,
    current_setting('flyiop.probe_novo_teto',          true) as depois_teto_correto,
    current_setting('flyiop.probe_novo_oport_count',   true) as depois_oportunidade_correto,
    current_setting('flyiop.probe_novo_oport_preco',   true) as depois_oportunidade_preco,
    current_setting('flyiop.probe_composto_teto',      true) as composto_ambas_teto,
    current_setting('flyiop.probe_composto_oport',     true) as composto_ambas_oportunidade;

  select count(*) as linhas_apos_seed from alert_log;  -- deve ser G0.linhas_total + 2, DENTRO da transação
rollback;

-- confirmação final, FORA da transação: nada persistiu.
select count(*) as linhas_apos_rollback from alert_log;  -- deve voltar a bater com G0.linhas_total
