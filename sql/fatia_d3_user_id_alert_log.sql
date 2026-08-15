-- ============================================================================
-- Fatia D3 — Parte 1/3 — alert_log ganha user_id (banco).
--
-- CONTEXTO: hoje o cooldown e o histórico de alerta são globais — alert_log
-- não tem dono. A D3 acrescenta a coluna, preparando a D4 (avaliação por
-- usuário, que aposenta o MIN de teto em weekends.resolve_effective_leg_state)
-- e a Etapa 7 (segunda conta). ESTA FATIA NÃO MUDA O QUE É ALERTADO NEM O QUE
-- É COLETADO, e não individualiza nada ainda: só cria a coluna e preenche o
-- que é derivável hoje.
--
-- O PONTO CENTRAL — PREENCHIMENTO ASSIMÉTRICO, POR DESENHO:
--   linha com route_id -> dono trivial (routes.user_id). Backfill preenche.
--   linha com leg_id   -> NÃO tem dono derivável. Fica NULL, de propósito.
-- Por quê: weekend_legs não tem user_id (as 4 colunas de decisão pessoal
-- saíram para weekend_leg_user_state na Etapa 4.1 e foram removidas de
-- weekend_legs na 4.3). Quem resolve "quem monitora esta perna" é a view
-- weekend_leg_effective, que faz CROSS JOIN com settings
-- (sql/etapa4_1_estado_por_usuario.sql:387-414): a perna não tem UM dono, tem
-- N (todos os usuários registrados), e o robô colapsa esses N num alerta só
-- via MIN de teto (src/weekends.py:149-188, regra provisória da Etapa 4.2).
-- weekend_leg_user_state também não resolve: é modelo preguiçoso (linha só
-- nasce quando o usuário decide algo) — o G0 mede isso, e a medição de
-- 14/08/2026 deu 31 pernas já alertadas contra apenas 4 com linha de estado.
-- Com uma conta só, escrever o user_id atual nas linhas de perna pareceria
-- certo — seria inventar dono a partir de um acidente de N=1, e a D4 teria de
-- desconfiar de toda linha anterior. NÃO SE INVENTA DONO DE LINHA DE PERNA.
--
-- SEM CHECK, SEM NOT NULL, SEM UNIQUE — E O MOTIVO É DE PRODUÇÃO, NÃO DE
-- ESTILO: os dois inserts em alert_log (src/main.py:468 rota, src/main.py:486
-- perna) acontecem DEPOIS de a mensagem do Telegram já ter sido enviada. Antes
-- da Parte 2 desta fatia eles não têm try/except — qualquer constraint nova
-- capaz de rejeitar o insert derrubaria a execução com a mensagem já enviada.
-- No caminho de perna é pior: o insert está dentro de um laço (main.py:482-489),
-- então morrer na primeira perna cancela os alertas das demais, o resumo
-- semanal de segunda e o exit code correto. Portanto a DDL desta fatia é
-- incapaz de rejeitar um insert que hoje passa.
--
-- FK COM `on delete set null` — LEIA A RESSALVA: a cláusula é a declaração de
-- intenção correta ("apagar conta não deve destruir o registro forense"), mas
-- NÃO é garantia de preservação de histórico e não deve ser lida como tal. As
-- FKs existentes de alert_log (route_id -> routes, leg_id -> weekend_legs) são
-- `on delete cascade`; apagar a conta apaga routes e CASCATEIA as linhas de
-- rota de alert_log de qualquer forma, antes de o `set null` ter qualquer
-- efeito. O `set null` só vale para caminhos que não passam por routes.
--
-- ÍNDICE: esta fatia NÃO recria alert_log_leg_sent_at_idx. A documentação da
-- D2 previu recriá-lo como (leg_id, user_id, sent_at desc) na D3; a previsão
-- foi revista: com as linhas de perna 100% NULL, user_id no meio do índice não
-- serve nenhuma consulta existente, e a forma útil depende do formato final da
-- consulta da D4. A forma final do índice é decisão da D4. O bloco V4 existe
-- justamente para PROVAR que a D3 não tocou no índice que a D2 criou.
--
-- RLS: esta fatia NÃO altera policy nem grant. A policy atual
-- (alert_log_select_own_routes_or_any_leg) trata leg_id como "qualquer
-- autenticado vê". Apertar isso para user_id = auth.uid() com user_id NULL em
-- toda linha de perna esconderia 100% do histórico de perna de qualquer
-- usuário — o predicado só passa a ser expressável quando a D4 escrever dono
-- em linha de perna. Fora isso, alert_log não tem consumidor além do robô
-- (grep em docs/: zero referências; o robô usa service_role, que ignora RLS).
--
-- ESCOPO DESTA PARTE: só o banco (1 coluna + backfill do lado rota). O código
-- Python que grava a coluna é a Parte 2/3 da mesma fatia.
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase — mesmo fluxo
-- dos scripts anteriores desta iniciativa. Claude Code não executa SQL.
--
-- ORDEM DE DEPLOY — JANELA MAIS FOLGADA QUE A DA D2:
--   1. Rodar este script (G0 -> Bloco 1 -> Bloco 2) e conferir V1-V6.
--   2. Publicar o código da Parte 2.
--   3. Se uma execução do robô cair entre 1 e 2: NÃO é defeito. A coluna é
--      nullable e o código antigo simplesmente não a envia — a linha de rota
--      nasce com user_id NULL e é recuperada re-rodando o Bloco 2, que
--      preenche por join com routes. Não existe aqui o análogo da "órfã
--      classificável" da D2 (lá o DEFAULT false criava um valor plausível e
--      errado; aqui NULL é honesto e recuperável).
--
-- MARCA D'ÁGUA DO DEPLOY (bloco V6) — POR QUE ELA EXISTE: depois da D4,
-- user_id NULL numa linha de perna passa a ter DOIS significados possíveis
-- (linha anterior à individualização vs. linha nova em que a gravação do dono
-- falhou), e a D4 não terá como separar os dois. O V6 congela a fronteira:
-- total de linhas e max(sent_at) no momento do deploy. `id` de alert_log é
-- uuid (sql/etapa3_cooldown.sql:5, gen_random_uuid()), que NÃO ordena — por
-- isso a marca d'água é por sent_at, e max(id) não é registrado.
--
--   >>> PREENCHER APÓS A EXECUÇÃO REAL (copiar o resultado do V6 para cá e
--   >>> para a subseção "Fatia D3" do PLANO-ATIVO.md):
--       marca_dagua_em          = ____________________
--       linhas_total            = ____________________
--       linhas_perna_sem_dono   = ____________________
--       max_sent_at             = ____________________
--
-- IDEMPOTENTE E RE-RODÁVEL de ponta a ponta (`if not exists` no Bloco 1,
-- guarda `user_id is null` no Bloco 2).
--
-- RECEITA DE REVERSÃO:
--   alter table alert_log drop column if exists user_id;
--   (fazer isso só com o código da Parte 2 fora do ar — senão todo insert de
--    rota passa a mandar uma coluna inexistente e o PostgREST devolve 400. Com
--    o try/except da Parte 2 já publicado isso NÃO derruba mais a execução:
--    vira `had_error` + linha "[alert_log] FALHA AO GRAVAR" no log, e o
--    cooldown de rota para de ser alimentado em silêncio até alguém olhar.)
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO G0 — Guarda de inventário, SÓ LEITURA. Confirma o estado ANTES de
-- agir, para não operar sobre suposição.
--
-- ESPERADO (medido em produção em 14/08/2026, no chat de planejamento):
--   Q1 colunas_alert_log  = id,is_ceiling_alert,is_opportunity_alert,leg_id,
--                           price,reason,route_id,sent_at  (8)
--      coluna_user_id_existe = false ; tipo_da_coluna_id = uuid
--      constraints contendo alert_log_pkey e alert_log_route_or_leg_check
--   Q2 total = 75 (53 perna, 22 rota, 0 ambos, 0 nenhum)
--   Q3 orfas_rota = 0 ; orfas_perna = 0
--   Q4 rotas_total = 3 ; rotas_sem_dono = 0 ; user_id_aceita_nulo = NO ;
--      donos_distintos = 1 ; fk_routes_para_auth_users = 1 ;
--      linhas_rota_sem_dono_derivavel = 0
--   Q5 indices = alert_log_leg_sent_at_idx,alert_log_pkey (2)
--   Q6 rls_ligada = true ; politicas = alert_log_select_own_routes_or_any_leg ;
--      policy_cmd = SELECT ; policies_escrita = 0 ; privilégios 7/7/7
--   Q7 1 linha de resultado (1 usuário), 5 linhas / 5 pernas
--   Q8 pernas_total = 132 ; usuarios_settings = 1 ; contas_auth = 1 ;
--      linhas_efetivas = 132 ; pernas_com_alerta = 31 ;
--      pernas_com_alerta_e_estado = 4
--
-- RESSALVA DE CRESCIMENTO ORGÂNICO: o robô roda 2x/dia e grava ~1-3 linhas por
-- dia. Números MAIORES que os acima em Q2/Q8 são crescimento esperado, não
-- erro — o que tem de bater sempre é a ESTRUTURA: ambos = 0, nenhum = 0,
-- órfãs = 0, rotas_sem_dono = 0, user_id_aceita_nulo = NO. Se qualquer um
-- desses cinco divergir, PARE e leve ao chat de planejamento antes do Bloco 1.
-- ----------------------------------------------------------------------------

-- Q1 — inventário de colunas e constraints de alert_log.
select
  (select string_agg(column_name, ',' order by column_name)
     from information_schema.columns
    where table_schema='public' and table_name='alert_log')          as colunas_alert_log,
  exists (select 1 from information_schema.columns
           where table_schema='public' and table_name='alert_log'
             and column_name='user_id')                              as coluna_user_id_existe,
  (select data_type from information_schema.columns
    where table_schema='public' and table_name='alert_log'
      and column_name='id')                                          as tipo_da_coluna_id,
  (select string_agg(conname, ',' order by conname) from pg_constraint
    where conrelid='public.alert_log'::regclass)                     as constraints_alert_log;

-- Q2 — quantas linhas de cada natureza (é o denominador de todas as
-- verificações depois — anotar o total).
select
  count(*)                                                                   as total,
  count(*) filter (where leg_id is not null and route_id is null)            as so_perna,
  count(*) filter (where route_id is not null and leg_id is null)            as so_rota,
  count(*) filter (where leg_id is not null and route_id is not null)        as ambos,
  count(*) filter (where leg_id is null and route_id is null)                as nenhum,
  min(sent_at)::date                                                         as periodo_inicio,
  max(sent_at)::date                                                         as periodo_fim
  from alert_log;

-- Q3 — órfãs. As FKs são on delete cascade, então o esperado é 0/0; a consulta
-- MEDE em vez de presumir.
select
  (select count(*) from alert_log a where a.route_id is not null
     and not exists (select 1 from routes r where r.id = a.route_id))        as orfas_rota,
  (select count(*) from alert_log a where a.leg_id is not null
     and not exists (select 1 from weekend_legs l where l.id = a.leg_id))    as orfas_perna;

-- Q4 — O GATE: o dono do lado rota é mesmo derivável e obrigatório? É o que
-- sustenta o backfill do Bloco 2 e a decisão de não criar CHECK.
select
  (select count(*) from routes)                                              as rotas_total,
  (select count(*) from routes where user_id is null)                        as rotas_sem_dono,
  (select is_nullable from information_schema.columns
    where table_schema='public' and table_name='routes'
      and column_name='user_id')                                             as user_id_aceita_nulo,
  (select count(distinct user_id) from routes)                               as donos_distintos,
  (select count(*) from pg_constraint
    where conrelid='public.routes'::regclass and contype='f'
      and confrelid='auth.users'::regclass)                                  as fk_routes_para_auth_users,
  (select count(*) from alert_log a join routes r on r.id = a.route_id
    where r.user_id is null)                                                 as linhas_rota_sem_dono_derivavel;

-- Q5 — índices atuais (linha de base do V4).
select
  (select string_agg(indexname, ',' order by indexname) from pg_indexes
    where schemaname='public' and tablename='alert_log')                     as indices_alert_log,
  (select count(*) from pg_indexes
    where schemaname='public' and tablename='alert_log')                     as total_indices;

-- Q6 — RLS, policies e grants (linha de base do V5; mesma medição do V5 da D2).
select
  (select relrowsecurity from pg_class where oid='public.alert_log'::regclass)     as rls_ligada,
  (select relforcerowsecurity from pg_class where oid='public.alert_log'::regclass) as rls_forcada,
  (select string_agg(policyname, ',' order by policyname) from pg_policies
    where schemaname='public' and tablename='alert_log')                     as politicas,
  (select string_agg(distinct cmd, ',') from pg_policies
    where schemaname='public' and tablename='alert_log')                     as policy_cmd,
  (select count(*) from pg_policies where schemaname='public'
     and tablename='alert_log' and cmd in ('INSERT','UPDATE','DELETE','ALL')) as policies_escrita,
  ( (has_table_privilege('anon','public.alert_log','SELECT')::int) +
    (has_table_privilege('anon','public.alert_log','INSERT')::int) +
    (has_table_privilege('anon','public.alert_log','UPDATE')::int) +
    (has_table_privilege('anon','public.alert_log','DELETE')::int) +
    (has_table_privilege('anon','public.alert_log','TRUNCATE')::int) +
    (has_table_privilege('anon','public.alert_log','REFERENCES')::int) +
    (has_table_privilege('anon','public.alert_log','TRIGGER')::int) )         as anon_privilegios,
  ( (has_table_privilege('authenticated','public.alert_log','SELECT')::int) +
    (has_table_privilege('authenticated','public.alert_log','INSERT')::int) +
    (has_table_privilege('authenticated','public.alert_log','UPDATE')::int) +
    (has_table_privilege('authenticated','public.alert_log','DELETE')::int) +
    (has_table_privilege('authenticated','public.alert_log','TRUNCATE')::int) +
    (has_table_privilege('authenticated','public.alert_log','REFERENCES')::int) +
    (has_table_privilege('authenticated','public.alert_log','TRIGGER')::int) ) as authenticated_privilegios,
  ( (has_table_privilege('service_role','public.alert_log','SELECT')::int) +
    (has_table_privilege('service_role','public.alert_log','INSERT')::int) +
    (has_table_privilege('service_role','public.alert_log','UPDATE')::int) +
    (has_table_privilege('service_role','public.alert_log','DELETE')::int) +
    (has_table_privilege('service_role','public.alert_log','TRUNCATE')::int) +
    (has_table_privilege('service_role','public.alert_log','REFERENCES')::int) +
    (has_table_privilege('service_role','public.alert_log','TRIGGER')::int) )  as service_role_privilegios;

-- Q7 — weekend_leg_user_state por usuário: o modelo preguiçoso, medido.
select user_id,
       count(*)                                            as linhas,
       count(distinct leg_id)                              as pernas,
       count(*) filter (where status='purchased')          as compradas,
       count(*) filter (where price_ceiling is not null)   as com_teto_override
  from weekend_leg_user_state
 group by user_id
 order by user_id;

-- Q8 — o número que fecha a discussão do dono de perna: mesmo tentando derivar
-- dono por weekend_leg_user_state, a grande maioria das pernas já alertadas
-- não tem linha lá (medido em 14/08/2026: 31 alertadas, 4 com estado).
select
  (select count(*) from weekend_legs)                                        as pernas_total,
  (select count(*) from weekend_leg_user_state)                              as linhas_estado,
  (select count(*) from settings)                                            as usuarios_settings,
  (select count(*) from auth.users)                                          as contas_auth,
  (select count(*) from weekend_leg_effective)                               as linhas_efetivas,
  (select count(distinct leg_id) from alert_log where leg_id is not null)    as pernas_com_alerta,
  (select count(distinct a.leg_id) from alert_log a
    where a.leg_id is not null
      and exists (select 1 from weekend_leg_user_state s
                   where s.leg_id = a.leg_id))                               as pernas_com_alerta_e_estado;


-- ----------------------------------------------------------------------------
-- BLOCO 1 — a coluna.
--
-- Nullable (metade das linhas não tem verdade a preencher), sem CHECK, sem
-- UNIQUE — ver o motivo de produção no cabeçalho. `if not exists` torna
-- idempotente. Adicionar coluna nullable sem default não reescreve a tabela.
-- ----------------------------------------------------------------------------
alter table alert_log
  add column if not exists user_id uuid references auth.users(id) on delete set null;


-- ----------------------------------------------------------------------------
-- BLOCO 2 — backfill, SÓ do lado rota.
--
-- GUARDA DE IDEMPOTÊNCIA: `user_id is null` — re-rodar depois que o código da
-- Parte 2 já gravou não sobrescreve nada, e é exatamente o procedimento de
-- recuperação se uma execução do robô cair entre este script e o deploy do
-- código (ver cabeçalho).
--
-- Linha de perna NÃO é tocada aqui, nem agora nem depois: fica NULL por
-- desenho. Quem escreve dono em linha de perna é a D4.
-- ----------------------------------------------------------------------------
update alert_log a
   set user_id = r.user_id
  from routes r
 where r.id = a.route_id
   and a.route_id is not null
   and a.user_id is null;


-- ============================================================================
-- VERIFICAÇÃO — rodar depois do Bloco 2. V1/V2/V4/V5 são asserções; V3 é a
-- prova de idempotência; V6 é a marca d'água do deploy (o resultado dele vai
-- para o cabeçalho deste arquivo e para o PLANO-ATIVO.md).
-- ============================================================================


-- ----------------------------------------------------------------------------
-- V1 — a coluna existe, com tipo/nulidade certos, e a FK com a delete rule
-- pedida.
--
-- ESPERADO: existe = true ; tipo = uuid ; aceita_nulo = YES ;
--           default_declarado = NULL (não tem default, de propósito) ;
--           fk_para_auth_users = 1 ; fk_delete_rule = SET NULL.
-- ----------------------------------------------------------------------------
select
  exists (select 1 from information_schema.columns
           where table_schema='public' and table_name='alert_log'
             and column_name='user_id')                              as coluna_existe,
  (select data_type from information_schema.columns
    where table_schema='public' and table_name='alert_log'
      and column_name='user_id')                                     as tipo,
  (select is_nullable from information_schema.columns
    where table_schema='public' and table_name='alert_log'
      and column_name='user_id')                                     as aceita_nulo,
  (select column_default from information_schema.columns
    where table_schema='public' and table_name='alert_log'
      and column_name='user_id')                                     as default_declarado,
  (select count(*) from pg_constraint
    where conrelid='public.alert_log'::regclass and contype='f'
      and confrelid='auth.users'::regclass)                          as fk_para_auth_users,
  (select rc.delete_rule
     from information_schema.referential_constraints rc
     join information_schema.key_column_usage k
       on k.constraint_name = rc.constraint_name
      and k.constraint_schema = rc.constraint_schema
    where k.table_schema='public' and k.table_name='alert_log'
      and k.column_name='user_id')                                   as fk_delete_rule;


-- ----------------------------------------------------------------------------
-- V2 — resultado real do backfill, linha a linha.
--
-- ESPERADO: escopo 'rota'  -> com_dono = 22 (mais qualquer linha de rota nova
--             gravada entre a medição de 14/08 e a execução), sem_dono = 0.
--             sem_dono > 0 é DEFEITO — significa rota sem user_id, o que Q4
--             disse ser impossível.
--           escopo 'perna' -> com_dono = 0, sem_dono = 53+ (100% NULL, POR
--             DESENHO — não é defeito, é a decisão central desta fatia).
--           A soma dos dois totais tem de bater com o total do Q2.
-- ----------------------------------------------------------------------------
select
  'rota'                                                   as escopo,
  count(*) filter (where user_id is not null)              as com_dono,
  count(*) filter (where user_id is null)                  as sem_dono,
  count(*)                                                 as total
  from alert_log where route_id is not null
union all
select
  'perna'                                                  as escopo,
  count(*) filter (where user_id is not null)              as com_dono,
  count(*) filter (where user_id is null)                  as sem_dono,
  count(*)                                                 as total
  from alert_log where leg_id is not null;


-- ----------------------------------------------------------------------------
-- V3 — idempotência: re-rodar o Bloco 2 na sequência devolve UPDATE 0.
--
-- Se uma execução do robô caiu entre o Bloco 2 e esta re-rodada, um UPDATE > 0
-- aqui é o comportamento CORRETO de recuperação (linha de rota nova gravada
-- pelo código antigo, ainda sem dono), não falha do bloco.
-- ----------------------------------------------------------------------------
update alert_log a
   set user_id = r.user_id
  from routes r
 where r.id = a.route_id
   and a.route_id is not null
   and a.user_id is null;


-- ----------------------------------------------------------------------------
-- V4 — ÍNDICES INALTERADOS. Esta fatia não recria o índice da D2 (ver
-- cabeçalho); este bloco é a prova.
--
-- ESPERADO: idênticos ao Q5 — alert_log_leg_sent_at_idx,alert_log_pkey (2).
--           A definição do índice da D2 continua (leg_id, sent_at DESC), sem
--           user_id.
-- ----------------------------------------------------------------------------
select
  (select string_agg(indexname, ',' order by indexname) from pg_indexes
    where schemaname='public' and tablename='alert_log')             as indices_alert_log,
  (select count(*) from pg_indexes
    where schemaname='public' and tablename='alert_log')             as total_indices,
  (select indexdef from pg_indexes where schemaname='public'
     and tablename='alert_log' and indexname='alert_log_leg_sent_at_idx')
                                                                     as indexdef_da_d2;


-- ----------------------------------------------------------------------------
-- V5 — RLS/policies/grants INALTERADOS, comparados com o Q6.
--
-- ESPERADO: TUDO idêntico ao Q6 — rls_ligada = true, rls_forcada = false, 1
-- política (alert_log_select_own_routes_or_any_leg), policy_cmd = SELECT,
-- policies_escrita = 0, privilégios 7/7/7. Adicionar coluna não cria objeto
-- novo nem concede privilégio (privilégio é de TABELA em Postgres); os 7/7/7
-- são o padrão de fábrica do Supabase, já registrado como achado de higiene
-- aceito (STATE.md, 08/08/2026) — a barreira real é a policy de linha. Este
-- bloco existe para PROVAR que a D3 não mexeu nessa postura, não para alterá-la.
-- ----------------------------------------------------------------------------
select
  (select relrowsecurity from pg_class where oid='public.alert_log'::regclass)     as rls_ligada,
  (select relforcerowsecurity from pg_class where oid='public.alert_log'::regclass) as rls_forcada,
  (select string_agg(policyname, ',' order by policyname) from pg_policies
    where schemaname='public' and tablename='alert_log')                     as politicas,
  (select string_agg(distinct cmd, ',') from pg_policies
    where schemaname='public' and tablename='alert_log')                     as policy_cmd,
  (select count(*) from pg_policies where schemaname='public'
     and tablename='alert_log' and cmd in ('INSERT','UPDATE','DELETE','ALL')) as policies_escrita,
  ( (has_table_privilege('anon','public.alert_log','SELECT')::int) +
    (has_table_privilege('anon','public.alert_log','INSERT')::int) +
    (has_table_privilege('anon','public.alert_log','UPDATE')::int) +
    (has_table_privilege('anon','public.alert_log','DELETE')::int) +
    (has_table_privilege('anon','public.alert_log','TRUNCATE')::int) +
    (has_table_privilege('anon','public.alert_log','REFERENCES')::int) +
    (has_table_privilege('anon','public.alert_log','TRIGGER')::int) )         as anon_privilegios,
  ( (has_table_privilege('authenticated','public.alert_log','SELECT')::int) +
    (has_table_privilege('authenticated','public.alert_log','INSERT')::int) +
    (has_table_privilege('authenticated','public.alert_log','UPDATE')::int) +
    (has_table_privilege('authenticated','public.alert_log','DELETE')::int) +
    (has_table_privilege('authenticated','public.alert_log','TRUNCATE')::int) +
    (has_table_privilege('authenticated','public.alert_log','REFERENCES')::int) +
    (has_table_privilege('authenticated','public.alert_log','TRIGGER')::int) ) as authenticated_privilegios,
  ( (has_table_privilege('service_role','public.alert_log','SELECT')::int) +
    (has_table_privilege('service_role','public.alert_log','INSERT')::int) +
    (has_table_privilege('service_role','public.alert_log','UPDATE')::int) +
    (has_table_privilege('service_role','public.alert_log','DELETE')::int) +
    (has_table_privilege('service_role','public.alert_log','TRUNCATE')::int) +
    (has_table_privilege('service_role','public.alert_log','REFERENCES')::int) +
    (has_table_privilege('service_role','public.alert_log','TRIGGER')::int) )  as service_role_privilegios;


-- ----------------------------------------------------------------------------
-- V6 — MARCA D'ÁGUA DO DEPLOY. Rodar o mais perto possível do momento em que o
-- código da Parte 2 entra no ar.
--
-- POR QUE: depois da D4, user_id NULL numa linha de perna passa a ter dois
-- significados possíveis (anterior à individualização vs. gravação de dono que
-- falhou) e a D4 não terá como separar os dois olhando só o dado. Estes
-- números são a fronteira: toda linha de perna com sent_at <= max_sent_at
-- abaixo é, por definição, do mundo pré-D4.
--
-- `id` é uuid (gen_random_uuid()) e não ordena — por isso max(id) NÃO é
-- registrado; a marca d'água é por sent_at.
--
-- SEM ESPERADO FIXO: é medição, não asserção. COPIAR O RESULTADO para o
-- cabeçalho deste arquivo e para a subseção "Fatia D3" do PLANO-ATIVO.md.
-- ----------------------------------------------------------------------------
select
  now()                                                              as marca_dagua_em,
  count(*)                                                           as linhas_total,
  count(*) filter (where leg_id is not null)                         as linhas_perna,
  count(*) filter (where leg_id is not null and user_id is null)     as linhas_perna_sem_dono,
  count(*) filter (where route_id is not null and user_id is not null) as linhas_rota_com_dono,
  max(sent_at)                                                       as max_sent_at
  from alert_log;
