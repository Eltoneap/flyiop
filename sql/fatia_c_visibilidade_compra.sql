-- ============================================================================
-- Fatia C — Parte 1/2 — visibilidade de compra entre usuários (banco).
--
-- CONTEXTO: com o segundo usuário chegando (Etapa 7), falta a única
-- informação que os dois QUEREM compartilhar: que o outro já comprou uma
-- perna, e em qual voo — inclusive para logística de táxi (nota registrada
-- em PLANO-ATIVO.md, "Nota (08/08/2026) — motivo adicional para visibilidade
-- cruzada de compra").
--
-- REGRA DE PRODUTO (aprovada no chat de planejamento): o outro usuário vê
-- QUE você comprou uma perna e EM QUAL VOO. Nunca quanto você pagou, qual
-- seu teto, nem seu localizador. Visibilidade só depois de
-- status = 'purchased' — nunca antes.
--
-- MECANISMO: TABELA DE PROJEÇÃO mantida por trigger. Avaliadas e
-- DESCARTADAS: a view `security definer` (`security_invoker = off`) e a
-- função RPC `security definer` — as duas são bypass de RLS. O diagnóstico
-- mostrou que TODO OBJETO NOVO em `public` neste projeto nasce com os 7
-- privilégios (select/insert/update/delete/truncate/references/trigger)
-- para `anon` e `authenticated` — o Supabase aplica
-- `alter default privileges grant all` no schema public (mesmo achado que
-- fechou sql/etapa4_4_weekend_legs_readonly.sql). Um `security definer`
-- soma bypass de RLS a isso; não reabrir essa decisão.
--
-- PRINCÍPIO: o dado sensível não deve ESTAR na tabela compartilhada. A
-- garantia é ESTRUTURAL — não depende de nenhum WHERE estar correto.
--
-- ESCOPO DESTA PARTE: só o banco (colunas de snapshot, tabela de projeção,
-- trigger de sincronização, RLS/grants, backfill). Parte 2 (frontend) é
-- prompt separado. Telegram fica para a Etapa 6.
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase — mesmo
-- fluxo dos scripts anteriores desta iniciativa.
--
-- NOTA OPERACIONAL — janela de privilégio default: rode os Blocos 2, 4 e 5
-- NUMA ÚNICA EXECUÇÃO (cole o trecho de uma vez só, ou embrulhe em
-- begin/commit explícito). Entre o `create table` do Bloco 2 e o
-- `revoke all` do Bloco 4, a tabela existe no ar com os 7 privilégios
-- padrão para `anon` — a janela é de milissegundos e não há mais ninguém
-- conectado ao banco hoje, mas não há motivo para ela existir.
--
-- RECEITA DE REVERSÃO (nesta ordem — trigger antes da tabela, senão
-- qualquer escrita em weekend_leg_user_state passa a estourar por
-- depender de uma função que não existe mais):
--   drop trigger if exists trg_sync_purchase_shared on weekend_leg_user_state;
--   drop function if exists flyiop_sync_purchase_shared();
--   drop table if exists weekend_leg_purchase_shared;
--   alter table weekend_leg_user_state
--     drop column if exists purchased_airline,
--     drop column if exists purchased_airport,
--     drop column if exists purchased_departure_time;
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO G0 — Guarda de inventário, só-leitura. Confirma o estado ANTES de
-- agir, para não operar sobre suposição (há trabalho em paralelo possível
-- neste projeto).
--
-- ESPERADO (09/08/2026): colunas_snapshot_hoje = 0, projecao_existe_hoje =
-- false, compradas_hoje = 0, linhas_estado_hoje = 5, pernas_hoje = 132,
-- triggers_wlus_hoje = trg_audit_leg_ceiling,trg_wlus_touch.
--
-- Se qualquer valor divergir do esperado: PARAR e trazer o resultado ao
-- chat de planejamento antes de continuar.
-- ----------------------------------------------------------------------------
select
  (select count(*) from information_schema.columns
    where table_schema = 'public' and table_name = 'weekend_leg_user_state'
      and column_name in ('purchased_airline','purchased_airport','purchased_departure_time')
  )                                                              as colunas_snapshot_hoje,
  exists (
    select 1 from information_schema.tables
     where table_schema = 'public' and table_name = 'weekend_leg_purchase_shared'
  )                                                              as projecao_existe_hoje,
  (select count(*) from weekend_leg_user_state where status = 'purchased') as compradas_hoje,
  (select count(*) from weekend_leg_user_state)                  as linhas_estado_hoje,
  (select count(*) from weekend_legs)                            as pernas_hoje,
  (select string_agg(tgname, ',' order by tgname)
     from pg_trigger
    where tgrelid = 'weekend_leg_user_state'::regclass
      and not tgisinternal)                                      as triggers_wlus_hoje;


-- ----------------------------------------------------------------------------
-- BLOCO 1 — Snapshot em weekend_leg_user_state: fotografia do voo comprado,
-- congelada no ato da compra, deliberadamente independente das colunas
-- current_* (que o robô reescreve a cada raspagem). Todas nullable.
--
-- Três ALTER separados com `if not exists` cada (armadilha conhecida neste
-- repo: `add column` sem guarda falha alto se rodado duas vezes).
--
-- Sem CHECK em purchased_airport: weekend_legs.current_airport é text livre
-- (hoje só 'GIG'/'SDU', mas não é enforced na origem); uma restrição aqui
-- divergiria da fonte.
--
-- Não altera flyiop_audit_leg_ceiling (só reage a mudança de teto EFETIVO,
-- colunas nomeadas, coluna nova é invisível pra ela) nem
-- flyiop_touch_updated_at (só mexe em updated_at). Nenhuma das duas é
-- tocada por este arquivo.
-- ----------------------------------------------------------------------------
alter table weekend_leg_user_state add column if not exists purchased_airline text;
alter table weekend_leg_user_state add column if not exists purchased_airport text;
alter table weekend_leg_user_state add column if not exists purchased_departure_time timestamptz;


-- ============================================================================
-- ATENÇÃO — rodar os BLOCOS 2, 4 e 5 abaixo NUMA ÚNICA EXECUÇÃO (ver nota
-- operacional no cabeçalho). O Bloco 3 (a função da trigger) pode ficar no
-- meio sem problema: ele só CRIA a função, não relaxa privilégio nenhum.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO 2 — Tabela de projeção: só o que atravessa entre usuários.
--
-- Chave (leg_id, user_id) — mesma chave de weekend_leg_user_state. FKs com
-- on delete cascade: perna removida ou conta removida não deixa órfão.
-- Campos de voo com os MESMOS NOMES da origem, de propósito — sincronização
-- sem tradução mental.
--
-- NADA de price_ceiling, paid_price ou notes aqui: é o ponto inteiro do
-- desenho. Sem índice extra: a PK já começa por leg_id, que é como o
-- painel vai consultar ("quem mais comprou esta perna?").
-- ----------------------------------------------------------------------------
create table if not exists weekend_leg_purchase_shared (
  leg_id                    uuid not null references weekend_legs(id) on delete cascade,
  user_id                   uuid not null references auth.users(id) on delete cascade,
  purchased_airline         text,
  purchased_airport         text,
  purchased_departure_time  timestamptz,
  purchased_at              timestamptz not null default now(),
  updated_at                timestamptz not null default now(),
  primary key (leg_id, user_id)
);


-- ----------------------------------------------------------------------------
-- BLOCO 3 — Trigger de sincronização. Mesmo padrão de flyiop_audit_leg_ceiling
-- (sql/etapa4_1_estado_por_usuario.sql, Bloco 5): security definer com
-- search_path fixado, porque sem isso a trigger tentaria escrever na
-- projeção com o papel authenticated, que não tem policy de insert/update, e
-- o salvamento no painel falharia inteiro.
--
-- Regra: status = 'purchased' grava/atualiza a linha da projeção; qualquer
-- outro status OU delete REMOVE a linha — o botão "desfazer" do painel limpa
-- a projeção sozinho, sem código de frontend. UPDATE que muda leg_id/user_id
-- (não deve acontecer, mas tratado): remove a linha da chave ANTIGA primeiro,
-- depois decide se grava a chave NOVA — evita órfão.
-- ----------------------------------------------------------------------------
create or replace function flyiop_sync_purchase_shared() returns trigger
language plpgsql security definer set search_path = public, pg_temp as $$
begin
  -- DELETE, ou UPDATE que trocou a chave: remove a linha da chave ANTIGA.
  if tg_op = 'DELETE' or (tg_op = 'UPDATE' and (new.leg_id, new.user_id) is distinct from (old.leg_id, old.user_id)) then
    delete from weekend_leg_purchase_shared
     where leg_id = old.leg_id and user_id = old.user_id;
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;

  -- INSERT, ou UPDATE (já com a chave nova, se mudou): decide sobre a linha
  -- ATUAL. status <> 'purchased' remove (idempotente: já pode não existir).
  if new.status = 'purchased' then
    insert into weekend_leg_purchase_shared
      (leg_id, user_id, purchased_airline, purchased_airport, purchased_departure_time, updated_at)
    values
      (new.leg_id, new.user_id, new.purchased_airline, new.purchased_airport, new.purchased_departure_time, now())
    on conflict (leg_id, user_id) do update set
      purchased_airline        = excluded.purchased_airline,
      purchased_airport        = excluded.purchased_airport,
      purchased_departure_time = excluded.purchased_departure_time,
      updated_at                = now();
  else
    delete from weekend_leg_purchase_shared
     where leg_id = new.leg_id and user_id = new.user_id;
  end if;

  return new;
end $$;

drop trigger if exists trg_sync_purchase_shared on weekend_leg_user_state;
create trigger trg_sync_purchase_shared
  after insert or update or delete on weekend_leg_user_state
  for each row execute function flyiop_sync_purchase_shared();


-- ----------------------------------------------------------------------------
-- BLOCO 4 — RLS e grants. A parte que mais importa: o objeto nasce com os 7
-- privilégios para anon/authenticated (default do Supabase) — revoke tem que
-- vir ANTES de qualquer grant, e é requisito, não capricho.
--
-- Nenhuma policy de insert/update/delete: só a trigger escreve (roda como
-- dona da tabela, ignora RLS). relforcerowsecurity fica false de propósito —
-- forçar bloquearia a própria trigger (mesmo limite já documentado em
-- weekend_leg_ceiling_audit). service_role não é tocado: bypassa RLS por
-- padrão e a Etapa 6 (Telegram) vai precisar dele.
--
-- Alvo final: anon com ZERO privilégio sobre esta tabela.
-- ----------------------------------------------------------------------------
alter table weekend_leg_purchase_shared enable row level security;

revoke all on weekend_leg_purchase_shared from anon, authenticated;

grant select on weekend_leg_purchase_shared to authenticated;

drop policy if exists "wlps_select_authenticated" on weekend_leg_purchase_shared;
create policy "wlps_select_authenticated" on weekend_leg_purchase_shared
  for select to authenticated
  using (auth.uid() is not null);


-- ----------------------------------------------------------------------------
-- BLOCO 5 — Backfill idempotente: reconstrói a projeção a partir do que já
-- está 'purchased' hoje (0 linhas — ninguém comprou ainda). Existe para o
-- script ser corretamente re-rodável se for aplicado mais tarde, sobre um
-- estado com compras reais.
-- ----------------------------------------------------------------------------
insert into weekend_leg_purchase_shared
  (leg_id, user_id, purchased_airline, purchased_airport, purchased_departure_time)
select
  s.leg_id, s.user_id, s.purchased_airline, s.purchased_airport, s.purchased_departure_time
from weekend_leg_user_state s
where s.status = 'purchased'
on conflict (leg_id, user_id) do update set
  purchased_airline        = excluded.purchased_airline,
  purchased_airport        = excluded.purchased_airport,
  purchased_departure_time = excluded.purchased_departure_time,
  updated_at                = now();

-- Limpa projeção órfã (linha na projeção sem estado 'purchased' correspondente
-- em weekend_leg_user_state) — não deveria existir com a trigger em dia, mas
-- o backfill fica correto mesmo se rodado depois de uma intervenção manual.
delete from weekend_leg_purchase_shared p
where not exists (
  select 1 from weekend_leg_user_state s
   where s.leg_id = p.leg_id and s.user_id = p.user_id and s.status = 'purchased'
);

-- Recarrega o cache de schema do PostgREST (a tabela nova fica visível na API).
notify pgrst, 'reload schema';


-- ============================================================================
-- VERIFICAÇÃO — cada bloco abaixo termina num ÚNICO select (o SQL Editor só
-- mostra o resultado do último select de um bloco). Valores esperados
-- declarados em comentário ANTES do SQL.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- V1 — estrutura: as 3 colunas de snapshot existem; a projeção existe com
-- as colunas esperadas e SEM as sensíveis; triggers de weekend_leg_user_state
-- incluem a nova, sem perder as duas antigas.
--
-- ESPERADO: colunas_snapshot = 3, projecao_existe = true,
-- colunas_projecao = 7, colunas_sensiveis_na_projecao = 0,
-- triggers_wlus = trg_audit_leg_ceiling,trg_sync_purchase_shared,trg_wlus_touch.
-- ----------------------------------------------------------------------------
select
  (select count(*) from information_schema.columns
    where table_schema='public' and table_name='weekend_leg_user_state'
      and column_name in ('purchased_airline','purchased_airport','purchased_departure_time')
  )                                                              as colunas_snapshot,
  exists (
    select 1 from information_schema.tables
     where table_schema='public' and table_name='weekend_leg_purchase_shared'
  )                                                              as projecao_existe,
  (select count(*) from information_schema.columns
    where table_schema='public' and table_name='weekend_leg_purchase_shared'
  )                                                              as colunas_projecao,
  (select count(*) from information_schema.columns
    where table_schema='public' and table_name='weekend_leg_purchase_shared'
      and column_name in ('price_ceiling','paid_price','notes')
  )                                                              as colunas_sensiveis_na_projecao,
  (select string_agg(tgname, ',' order by tgname)
     from pg_trigger
    where tgrelid = 'weekend_leg_user_state'::regclass
      and not tgisinternal)                                      as triggers_wlus;


-- ----------------------------------------------------------------------------
-- V2 — grants e policies, usando has_table_privilege (privilégio EFETIVO —
-- mais forte que ler role_table_grants, que não enxerga grant a PUBLIC).
--
-- ESPERADO: anon_privilegios = 0, authenticated_privilegios = 1,
-- authenticated_so_select = true, rls_ligada = true, rls_forcada = false,
-- policies = 1, policy_cmd = SELECT.
-- ----------------------------------------------------------------------------
select
  ( (has_table_privilege('anon','public.weekend_leg_purchase_shared','SELECT')::int) +
    (has_table_privilege('anon','public.weekend_leg_purchase_shared','INSERT')::int) +
    (has_table_privilege('anon','public.weekend_leg_purchase_shared','UPDATE')::int) +
    (has_table_privilege('anon','public.weekend_leg_purchase_shared','DELETE')::int) +
    (has_table_privilege('anon','public.weekend_leg_purchase_shared','TRUNCATE')::int) +
    (has_table_privilege('anon','public.weekend_leg_purchase_shared','REFERENCES')::int) +
    (has_table_privilege('anon','public.weekend_leg_purchase_shared','TRIGGER')::int)
  )                                                                as anon_privilegios,
  ( (has_table_privilege('authenticated','public.weekend_leg_purchase_shared','SELECT')::int) +
    (has_table_privilege('authenticated','public.weekend_leg_purchase_shared','INSERT')::int) +
    (has_table_privilege('authenticated','public.weekend_leg_purchase_shared','UPDATE')::int) +
    (has_table_privilege('authenticated','public.weekend_leg_purchase_shared','DELETE')::int) +
    (has_table_privilege('authenticated','public.weekend_leg_purchase_shared','TRUNCATE')::int) +
    (has_table_privilege('authenticated','public.weekend_leg_purchase_shared','REFERENCES')::int) +
    (has_table_privilege('authenticated','public.weekend_leg_purchase_shared','TRIGGER')::int)
  )                                                                as authenticated_privilegios,
  has_table_privilege('authenticated','public.weekend_leg_purchase_shared','SELECT')
    as authenticated_so_select,
  (select relrowsecurity from pg_class where oid = 'public.weekend_leg_purchase_shared'::regclass)
    as rls_ligada,
  (select relforcerowsecurity from pg_class where oid = 'public.weekend_leg_purchase_shared'::regclass)
    as rls_forcada,
  (select count(*) from pg_policies
    where schemaname='public' and tablename='weekend_leg_purchase_shared')
    as policies,
  (select string_agg(cmd, ',') from pg_policies
    where schemaname='public' and tablename='weekend_leg_purchase_shared')
    as policy_cmd;


-- ----------------------------------------------------------------------------
-- V3 — prova de comportamento, transação com ROLLBACK: nada persiste.
--
-- Sobre uma perna sem estado hoje: marca 'purchased' (projeção deve ganhar
-- 1 linha, com o voo gravado), volta a 'monitoring' (projeção volta a 0),
-- marca 'purchased' de novo (volta a 1) e por fim DELETE da linha de estado
-- (projeção volta a 0) — cobre os três ramos da trigger (insert-purchased,
-- update-sai-de-purchased, delete).
--
-- ESPERADO: apos_compra = 1, voo_gravado = 'LATAM,GIG,<algum timestamp>',
-- apos_desfazer = 0, apos_recomprar = 1, apos_delete_estado = 0.
--
-- user_id vai como o UUID real do usuário (mesmo usado no Bloco F da
-- verificação 4.1), em vez de auth.uid(): rodado como postgres, sem JWT na
-- sessão, auth.uid() retorna null, e user_id é not null em
-- weekend_leg_user_state — o insert estouraria antes mesmo de testar a
-- trigger.
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';

  do $$
  declare v_leg uuid;
  begin
    select l.id into v_leg from weekend_legs l
     where not exists (select 1 from weekend_leg_user_state s where s.leg_id = l.id)
     limit 1;

    insert into weekend_leg_user_state
      (leg_id, user_id, status, purchased_airline, purchased_airport, purchased_departure_time)
    values
      (v_leg, 'c72bf50e-16f7-48fd-9c86-7b49dea1551e', 'purchased', 'LATAM', 'GIG', now() + interval '30 days');
    perform set_config('flyiop.probe_apos_compra',
      (select count(*)::text from weekend_leg_purchase_shared where leg_id = v_leg), true);
    perform set_config('flyiop.probe_voo',
      (select purchased_airline || ',' || purchased_airport || ',' || purchased_departure_time::text
         from weekend_leg_purchase_shared where leg_id = v_leg), true);

    update weekend_leg_user_state set status = 'monitoring' where leg_id = v_leg;
    perform set_config('flyiop.probe_apos_desfazer',
      (select count(*)::text from weekend_leg_purchase_shared where leg_id = v_leg), true);

    update weekend_leg_user_state set status = 'purchased' where leg_id = v_leg;
    perform set_config('flyiop.probe_apos_recomprar',
      (select count(*)::text from weekend_leg_purchase_shared where leg_id = v_leg), true);

    delete from weekend_leg_user_state where leg_id = v_leg;
    perform set_config('flyiop.probe_apos_delete',
      (select count(*)::text from weekend_leg_purchase_shared where leg_id = v_leg), true);
  end $$;

  select
    current_setting('flyiop.probe_apos_compra',    true) as apos_compra,
    current_setting('flyiop.probe_voo',            true) as voo_gravado,
    current_setting('flyiop.probe_apos_desfazer',  true) as apos_desfazer,
    current_setting('flyiop.probe_apos_recomprar', true) as apos_recomprar,
    current_setting('flyiop.probe_apos_delete',    true) as apos_delete_estado;
rollback;


-- ----------------------------------------------------------------------------
-- V4 — prova de isolamento, transação com ROLLBACK. Técnica idêntica ao
-- Bloco F de sql/etapa4_1_verificacao.sql: semeia uma compra transitória
-- como dono do banco (ignora RLS), depois personifica um usuário fictício
-- (00000000-0000-0000-0000-000000000001) via request.jwt.claims + set local
-- role authenticated.
--
-- uid_visto e papel_efetivo são colunas-guarda: se qualquer uma vier errada,
-- os números ao lado não provam nada — o contexto de papel não pegou.
--
-- ESPERADO: uid_visto = 00000000-...-0001, papel_efetivo = authenticated,
-- projecao_esp_1 = 1 (o que atravessa — asserção positiva),
-- estado_pessoal_esp_0 = 0 (o que NÃO atravessa — é esta a asserção com
-- valor probatório de isolamento do bloco), escrita_direta_esp_bloqueada =
-- 'bloqueado <sqlstate>'.
--
-- view_efetiva_esp_0_sem_valor_probatorio também deve vir 0, mas ESSE ZERO
-- NÃO PROVA ISOLAMENTO POR RLS: weekend_leg_effective faz cross join com
-- settings, e o UUID fictício não tem linha em settings — o resultado
-- seria 0 mesmo com a RLS inteira desligada (mesma fraqueza de prova já
-- registrada sobre os blocos E/F de sql/etapa4_1_verificacao.sql, revisão
-- de 02/08/2026). Mantida no select por ser informação útil, mas ao
-- registrar o resultado real no PLANO-ATIVO.md este número NÃO deve ser
-- descrito como prova de isolamento — quem prova isolamento aqui é
-- estado_pessoal_esp_0.
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';

  insert into weekend_leg_user_state
    (leg_id, user_id, status, purchased_airline, purchased_airport, purchased_departure_time)
  select l.id, 'c72bf50e-16f7-48fd-9c86-7b49dea1551e', 'purchased', 'GOL', 'SDU', now() + interval '10 days'
    from weekend_legs l
   where not exists (select 1 from weekend_leg_user_state s where s.leg_id = l.id)
   limit 1;

  set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-000000000001","role":"authenticated"}';
  set local role authenticated;

  do $$
  declare v_alheio text;
  begin
    begin
      insert into weekend_leg_purchase_shared (leg_id, user_id, purchased_airline)
      values ((select leg_id from weekend_leg_purchase_shared limit 1),
              '00000000-0000-0000-0000-000000000001', 'INTRUSO');
      v_alheio := 'PASSOU — FALHA';
    exception when others then v_alheio := 'bloqueado ' || sqlstate; end;
    perform set_config('flyiop.probe_escrita', v_alheio, true);
  end $$;

  select
    auth.uid()                                          as uid_visto,
    current_user                                         as papel_efetivo,
    (select count(*) from weekend_leg_purchase_shared)   as projecao_esp_1,
    (select count(*) from weekend_leg_user_state)        as estado_pessoal_esp_0,
    (select count(*) from weekend_leg_effective)         as view_efetiva_esp_0_sem_valor_probatorio,
    current_setting('flyiop.probe_escrita', true)        as escrita_direta_esp_bloqueada;
rollback;
