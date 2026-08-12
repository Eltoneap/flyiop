-- ============================================================================
-- Fatia D1 — Parte 1/3 — janela de compra no Telegram (banco).
--
-- CONTEXTO: decisão de 11/08/2026 (STATE.md, seção 2) — o Telegram passa a
-- respeitar a janela de compra (fins de semana >= 29/01/2027) nos dois
-- caminhos onde hoje não respeita: alerta de perna e resumo semanal (as duas
-- listas + o denominador do contador de compradas). Ajuste de 12/08/2026: o
-- filtro vale para os DOIS tipos de alerta (teto e oportunidade), não só
-- oportunidade — alertar teto sobre um fim de semana fora da janela mandaria
-- "compre" algo que por regra de escopo nunca será comprado.
--
-- POR QUE A DATA VEM PARA O BANCO: hoje ela só existe em
-- docs/js/dashboard.js:83 (const BUYING_CUTOFF_DATE), inacessível do lado
-- Python. Duplicar a constante em Python recriaria exatamente a
-- inconsistência que esta fatia existe para corrigir (Dashboard contando a
-- partir de 29/01/2027 e Telegram contando as 132 pernas inteiras —
-- STATE.md:305). O `system_config` é a linha única sem dono já usada para
-- config de sistema, editável só via SQL Editor (RUNBOOK.md).
--
-- ESCOPO DESTA PARTE: só o banco (uma coluna em tabela existente). O código
-- Python que lê a coluna é a Parte 2/3 da mesma fatia. A migração do
-- docs/js/dashboard.js para ler daqui é a Fatia D1b, prompt separado — até
-- lá a duplicação do valor entre banco e JS é consciente e aprovada.
--
-- ESTA FATIA MUDA O QUE É ALERTADO, NUNCA O QUE É COLETADO. Nenhuma perna
-- sai da rotação; `weekend_legs`, `weekend_leg_user_state` e
-- `weekend_leg_effective` não são tocadas por este arquivo.
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase — mesmo
-- fluxo dos scripts anteriores desta iniciativa. Claude Code não executa SQL.
--
-- ORDEM OBRIGATÓRIA: rodar este script e conferir V1/V2/V3 ANTES de subir o
-- código da Parte 2/3. Invertido, `get_system_config()` pede uma coluna que
-- não existe, o PostgREST devolve 400 e a execução do dia morre inteira
-- (antes de gravar qualquer preço). Mesma regra já escrita em
-- sql/system_config.sql:2.
--
-- SOBRE GRANTS: este script NÃO cria nenhum objeto novo — é uma coluna numa
-- tabela que já existe. Em Postgres o privilégio é de tabela e já cobre
-- colunas novas, então não há a janela de privilégio default que obrigou o
-- `revoke all` da Fatia C (sql/fatia_c_visibilidade_compra.sql, Bloco 4) e
-- da Etapa 4.4. A postura de acesso de `system_config` não muda: quem
-- governa aqui é a RLS (`system_config_select_authenticated`,
-- sql/system_config.sql:11-14) — usuário logado lê, `anon` não passa, e não
-- existe policy de UPDATE (edição é via SQL Editor, RUNBOOK.md). O bloco V2
-- prova que nada mudou, comparando com o que o G0 mediu antes.
--
-- IDEMPOTENTE E RE-RODÁVEL. De propósito NÃO existe `update` do valor: se
-- você mover o corte depois pelo RUNBOOK.md, re-rodar este script não pode
-- desfazer sua decisão em silêncio. A primeira execução preenche a linha
-- existente pelo DEFAULT da própria coluna.
--
-- RECEITA DE REVERSÃO:
--   alter table system_config drop column if exists weekend_buying_cutoff_date;
--   (fazer isso só com o código da Parte 2/3 fora do ar, ou a execução
--    seguinte cai no 400 descrito acima.)
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO G0 — Guarda de inventário, só-leitura. Confirma o estado ANTES de
-- agir, para não operar sobre suposição.
--
-- `system_config` nunca apareceu em nenhum diagnóstico deste projeto — esta
-- é a primeira leitura da estrutura real dela. Os 3 contadores de privilégio
-- NÃO têm valor esperado declarado: são a primeira medição, e o V2 compara
-- contra o que sair aqui (anote o resultado).
--
-- ESPERADO (12/08/2026):
--   colunas_system_config    = fast_flights_daily_batch_size,fast_flights_enabled,
--                              id,suspicious_below_avg_pct,updated_at
--   coluna_corte_existe      = false
--   linhas_system_config     = 1
--   rls_ligada               = true
--   politicas_system_config  = system_config_select_authenticated
--   weekends_hoje            = 66
--   pernas_hoje              = 132
--   weekends_na_janela       = 45
--   pernas_na_janela         = 90
--   anon/authenticated/service_role_privilegios = sem valor esperado (1ª medição)
--
-- 45/90 vêm de contar o seed de sql/pernas_desacopladas.sql (66 fins de
-- semana, 21 deles anteriores a 2027-01-29). É valor de CONFERÊNCIA, não
-- número que vai para o código — STATE.md:302 pede exatamente isso
-- ("não hardcodar um número novo; confirmar o valor real na implementação").
--
-- Se qualquer valor divergir do esperado: PARAR e trazer o resultado ao chat
-- de planejamento antes de continuar.
-- ----------------------------------------------------------------------------
select
  (select string_agg(column_name, ',' order by column_name)
     from information_schema.columns
    where table_schema = 'public' and table_name = 'system_config'
  )                                                              as colunas_system_config,
  exists (
    select 1 from information_schema.columns
     where table_schema = 'public' and table_name = 'system_config'
       and column_name = 'weekend_buying_cutoff_date'
  )                                                              as coluna_corte_existe,
  (select count(*) from system_config)                           as linhas_system_config,
  (select relrowsecurity from pg_class where oid = 'public.system_config'::regclass)
                                                                 as rls_ligada,
  (select string_agg(policyname, ',' order by policyname) from pg_policies
    where schemaname = 'public' and tablename = 'system_config')
                                                                 as politicas_system_config,
  (select count(*) from weekends)                                as weekends_hoje,
  (select count(*) from weekend_legs)                            as pernas_hoje,
  (select count(*) from weekends where outbound_date >= date '2027-01-29')
                                                                 as weekends_na_janela,
  (select count(*) from weekend_legs l join weekends w on w.id = l.weekend_id
    where w.outbound_date >= date '2027-01-29')                  as pernas_na_janela,
  ( (has_table_privilege('anon','public.system_config','SELECT')::int) +
    (has_table_privilege('anon','public.system_config','INSERT')::int) +
    (has_table_privilege('anon','public.system_config','UPDATE')::int) +
    (has_table_privilege('anon','public.system_config','DELETE')::int) +
    (has_table_privilege('anon','public.system_config','TRUNCATE')::int) +
    (has_table_privilege('anon','public.system_config','REFERENCES')::int) +
    (has_table_privilege('anon','public.system_config','TRIGGER')::int)
  )                                                              as anon_privilegios,
  ( (has_table_privilege('authenticated','public.system_config','SELECT')::int) +
    (has_table_privilege('authenticated','public.system_config','INSERT')::int) +
    (has_table_privilege('authenticated','public.system_config','UPDATE')::int) +
    (has_table_privilege('authenticated','public.system_config','DELETE')::int) +
    (has_table_privilege('authenticated','public.system_config','TRUNCATE')::int) +
    (has_table_privilege('authenticated','public.system_config','REFERENCES')::int) +
    (has_table_privilege('authenticated','public.system_config','TRIGGER')::int)
  )                                                              as authenticated_privilegios,
  ( (has_table_privilege('service_role','public.system_config','SELECT')::int) +
    (has_table_privilege('service_role','public.system_config','INSERT')::int) +
    (has_table_privilege('service_role','public.system_config','UPDATE')::int) +
    (has_table_privilege('service_role','public.system_config','DELETE')::int) +
    (has_table_privilege('service_role','public.system_config','TRUNCATE')::int) +
    (has_table_privilege('service_role','public.system_config','REFERENCES')::int) +
    (has_table_privilege('service_role','public.system_config','TRIGGER')::int)
  )                                                              as service_role_privilegios;


-- ----------------------------------------------------------------------------
-- BLOCO 1 — A coluna da data de corte da janela de compra.
--
-- Tipo `date`, não `text`: valor malformado fica impossível na origem, e o
-- PostgREST devolve sempre 'YYYY-MM-DD' — o lado Python compara string com
-- string, do mesmo jeito que docs/js/dashboard.js já compara.
--
-- `not null` + `default` preenche a linha existente na mesma instrução; não
-- é preciso (nem desejável) um `update` separado — ver nota de idempotência
-- no cabeçalho.
--
-- O `insert ... on conflict do nothing` é a mesma linha de sql/system_config.sql:15
-- e existe só para garantir que a linha 1 esteja lá antes do ALTER, caso a
-- tabela esteja vazia (o G0 acusaria isso, mas custa nada ser explícito).
-- Todas as demais colunas têm default, então o insert só com `id` é válido.
--
-- Nome `weekend_buying_cutoff_date` e NÃO `buying_window_*`: src/buying_window.py
-- já existe no projeto e significa outra coisa (janela recomendada de
-- ANTECEDÊNCIA de compra, 30–60 dias nacional). Colidir os dois nomes
-- confundiria dois conceitos que não têm relação.
-- ----------------------------------------------------------------------------
insert into system_config (id) values (1) on conflict (id) do nothing;

alter table system_config
  add column if not exists weekend_buying_cutoff_date date not null default date '2027-01-29';


-- ============================================================================
-- VERIFICAÇÃO — rodar depois do Bloco 1 e conferir contra os valores
-- ESPERADOS declarados em cada bloco. V1/V2/V3 são asserções; V4 é linha de
-- base informativa.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- V1 — a coluna existe, com o tipo, a nulidade e o valor certos.
--
-- ESPERADO: coluna_existe = true, tipo = date, aceita_nulo = NO,
-- default_declarado contém 2027-01-29, valor_atual = 2027-01-29, linhas = 1.
-- ----------------------------------------------------------------------------
select
  exists (
    select 1 from information_schema.columns
     where table_schema = 'public' and table_name = 'system_config'
       and column_name = 'weekend_buying_cutoff_date'
  )                                                              as coluna_existe,
  (select data_type from information_schema.columns
    where table_schema = 'public' and table_name = 'system_config'
      and column_name = 'weekend_buying_cutoff_date')            as tipo,
  (select is_nullable from information_schema.columns
    where table_schema = 'public' and table_name = 'system_config'
      and column_name = 'weekend_buying_cutoff_date')            as aceita_nulo,
  (select column_default from information_schema.columns
    where table_schema = 'public' and table_name = 'system_config'
      and column_name = 'weekend_buying_cutoff_date')            as default_declarado,
  (select weekend_buying_cutoff_date from system_config where id = 1)
                                                                 as valor_atual,
  (select count(*) from system_config)                           as linhas;


-- ----------------------------------------------------------------------------
-- V2 — privilégios e RLS INALTERADOS. Usa has_table_privilege (privilégio
-- EFETIVO — mais forte que role_table_grants, que não enxerga grant a
-- PUBLIC), mesma técnica do V2 da Fatia C.
--
-- ESPERADO: rls_ligada = true, rls_forcada = false,
-- politicas = system_config_select_authenticated, policy_cmd = SELECT,
-- policies_update = 0 (edição só via SQL Editor, RUNBOOK.md), e os TRÊS
-- contadores de privilégio IDÊNTICOS aos que o G0 mostrou antes do ALTER.
--
-- Não há valor absoluto esperado para os contadores: `alter table add column`
-- não concede privilégio nenhum, então a asserção é de IGUALDADE com o G0,
-- não de um número. Se anon_privilegios vier > 0, isso é postura pré-existente
-- de system_config (todo objeto em `public` neste projeto nasce com os 7
-- privilégios — achado da Etapa 4.4 e da Fatia C), NÃO efeito deste script:
-- a RLS é que barra `anon` aqui. Registrar e levar ao chat de planejamento
-- como assunto próprio; não tratar nesta fatia.
-- ----------------------------------------------------------------------------
select
  (select relrowsecurity from pg_class where oid = 'public.system_config'::regclass)
                                                                 as rls_ligada,
  (select relforcerowsecurity from pg_class where oid = 'public.system_config'::regclass)
                                                                 as rls_forcada,
  (select string_agg(policyname, ',' order by policyname) from pg_policies
    where schemaname = 'public' and tablename = 'system_config')  as politicas,
  (select string_agg(distinct cmd, ',') from pg_policies
    where schemaname = 'public' and tablename = 'system_config')  as policy_cmd,
  (select count(*) from pg_policies
    where schemaname = 'public' and tablename = 'system_config'
      and cmd in ('UPDATE','ALL'))                               as policies_update,
  ( (has_table_privilege('anon','public.system_config','SELECT')::int) +
    (has_table_privilege('anon','public.system_config','INSERT')::int) +
    (has_table_privilege('anon','public.system_config','UPDATE')::int) +
    (has_table_privilege('anon','public.system_config','DELETE')::int) +
    (has_table_privilege('anon','public.system_config','TRUNCATE')::int) +
    (has_table_privilege('anon','public.system_config','REFERENCES')::int) +
    (has_table_privilege('anon','public.system_config','TRIGGER')::int)
  )                                                              as anon_privilegios,
  ( (has_table_privilege('authenticated','public.system_config','SELECT')::int) +
    (has_table_privilege('authenticated','public.system_config','INSERT')::int) +
    (has_table_privilege('authenticated','public.system_config','UPDATE')::int) +
    (has_table_privilege('authenticated','public.system_config','DELETE')::int) +
    (has_table_privilege('authenticated','public.system_config','TRUNCATE')::int) +
    (has_table_privilege('authenticated','public.system_config','REFERENCES')::int) +
    (has_table_privilege('authenticated','public.system_config','TRIGGER')::int)
  )                                                              as authenticated_privilegios,
  ( (has_table_privilege('service_role','public.system_config','SELECT')::int) +
    (has_table_privilege('service_role','public.system_config','INSERT')::int) +
    (has_table_privilege('service_role','public.system_config','UPDATE')::int) +
    (has_table_privilege('service_role','public.system_config','DELETE')::int) +
    (has_table_privilege('service_role','public.system_config','TRUNCATE')::int) +
    (has_table_privilege('service_role','public.system_config','REFERENCES')::int) +
    (has_table_privilege('service_role','public.system_config','TRIGGER')::int)
  )                                                              as service_role_privilegios;


-- ----------------------------------------------------------------------------
-- V3 — o denominador novo do resumo semanal, provado no banco, lendo o corte
-- da própria coluna recém-criada (não de um literal).
--
-- Espelha a lógica nova de supabase_client.get_weekend_leg_counts(): conta
-- pernas DISTINTAS de weekend_leg_effective (a view é perna × usuário) cujo
-- fim de semana está na janela, e considera comprada só a perna em que TODOS
-- os usuários que a monitoram marcaram 'purchased' (regra da pendência 9 da
-- Etapa 4.2, aplicada ao complemento — mesma do código).
--
-- O recorte é pela `outbound_date` do FIM DE SEMANA (âncora), tanto para ida
-- quanto para volta — mesma coluna que docs/js/dashboard.js:167/:247 usa. Os
-- dois têm de responder igual; era essa a inconsistência de STATE.md:305.
--
-- ESPERADO: pernas_na_janela = 90, compradas_na_janela = 0,
-- pernas_totais = 132 (a COLETA não muda — nenhuma perna sai da rotação),
-- corte_lido = 2027-01-29.
-- ----------------------------------------------------------------------------
with corte as (
  select weekend_buying_cutoff_date as d from system_config where id = 1
),
por_perna as (
  select e.leg_id,
         bool_and(e.status = 'purchased') as todos_compraram
    from weekend_leg_effective e, corte c
   where e.outbound_date >= c.d
   group by e.leg_id
)
select
  (select d from corte)                                          as corte_lido,
  (select count(*) from por_perna)                               as pernas_na_janela,
  (select count(*) from por_perna where todos_compraram)         as compradas_na_janela,
  (select count(distinct leg_id) from weekend_leg_effective)     as pernas_totais;


-- ----------------------------------------------------------------------------
-- V4 — LINHA DE BASE, INFORMATIVO. Não é asserção e não prova nada; serve só
-- para comparar depois que o código da Parte 2/3 estiver no ar.
--
-- Todos os alertas de PERNA (alert_log com leg_id não nulo) dos últimos 14
-- dias, separados por dentro/fora da janela — sem distinguir teto de
-- oportunidade, já que o filtro passa a valer para os dois tipos (ajuste de
-- 12/08/2026).
--
-- SEM VALOR ESPERADO DECLARADO. Expectativa qualitativa, com base no
-- diagnóstico de 12/08/2026 registrado no STATE.md (~30 alertas enviados em
-- 14 dias, teto com zero hits no período): a esmagadora maioria deve estar
-- FORA da janela. Depois do deploy, `fora_da_janela` deve parar de crescer —
-- é essa a asserção, e ela se faz rodando este mesmo bloco de novo no dia
-- seguinte, não agora.
-- ----------------------------------------------------------------------------
select
  count(*)                                                       as alertas_perna_14d,
  count(*) filter (where w.outbound_date >= (select weekend_buying_cutoff_date
                                               from system_config where id = 1))
                                                                 as dentro_da_janela,
  count(*) filter (where w.outbound_date <  (select weekend_buying_cutoff_date
                                               from system_config where id = 1))
                                                                 as fora_da_janela,
  min(a.sent_at)                                                 as primeiro,
  max(a.sent_at)                                                 as ultimo
from alert_log a
join weekend_legs l on l.id = a.leg_id
join weekends w on w.id = l.weekend_id
where a.leg_id is not null
  and a.sent_at >= now() - interval '14 days';
