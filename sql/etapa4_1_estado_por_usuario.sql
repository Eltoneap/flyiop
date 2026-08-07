-- ======================================================================
-- NOTA DE ESTADO - 07/08/2026 (Etapa 4.3, Passo 4)
-- STATUS: HISTORICO - NAO RE-RODAR.
-- A ESTRUTURA que este script cria (weekend_leg_user_state,
-- weekend_leg_ceiling_audit, trigger de auditoria e a view
-- weekend_leg_effective) EXISTE em producao desde 01/08/2026 e continua
-- inteiramente valida. O que quebrou foi so a parte que lia o mundo antigo.
-- Em 06/08/2026 (commit ce0d8b3) price_ceiling, status, notes, paid_price
-- e purchased_at foram REMOVIDAS de weekend_legs. Por isso, rodar este
-- arquivo hoje falha na Guarda 1c, que le weekend_legs.price_ceiling; a
-- copia inicial de estado para weekend_leg_user_state, no fim do arquivo,
-- le as mesmas colunas removidas.
-- O erro de "coluna inexistente" e o comportamento ESPERADO, nao um bug.
-- Rota de volta: weekend_legs_legacy_columns_backup (permanente, 132
-- linhas) + receita em sql/etapa4_3_drop_colunas_legadas.sql.
-- Contexto completo: HISTORICO.md, item 18.
-- ======================================================================

-- ============================================================================
-- Etapa 4.1 (iniciativa multi-usuário) — estrutura de decisão pessoal por perna.
-- Aprovado no chat de planejamento em 01/08/2026.
--
-- Esta etapa SÓ CRIA estrutura. Nada em src/ ou docs/js/ passa a ler estes
-- objetos aqui — a virada de leitura/escrita é a Etapa 4.2, e a remoção das
-- colunas antigas de weekend_legs é a 4.3. Depois de rodar este arquivo, o
-- sistema tem que continuar se comportando exatamente como antes.
--
-- Rodar manualmente no SQL Editor do Supabase (mesmo fluxo de system_config.sql).
-- Antes e depois: rodar sql/etapa4_1_verificacao.sql e comparar.
--
-- O arquivo é idempotente de ponta a ponta (if not exists / create or replace /
-- drop policy if exists / on conflict do nothing): se parar no meio por causa de
-- um guarda, pode rodar de novo depois de corrigir a causa.
--
-- Passo 0 já rodado em 01/08/2026: Postgres 17.6 (security_invoker disponível),
-- settings com 1 linha (c72bf50e-16f7-48fd-9c86-7b49dea1551e) e settings_pkey =
-- PRIMARY KEY (user_id), o que torna duplicata de settings impossível.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO 1 — Guardas. Falham alto se o mundo não for o que este arquivo assume.
-- Checagem que protege dado não pode depender de consulta manual.
-- ----------------------------------------------------------------------------
do $$
declare
  n_users    int;
  n_settings int;
  n_fora     int;
begin
  -- (1a) A cópia do Bloco 7 foi desenhada para UMA conta. Com duas, o cross
  -- join replicaria o estado pessoal do usuário atual para o outro usuário.
  select count(*) into n_users from auth.users;
  if n_users <> 1 then
    raise exception
      'Guarda 1a: esperava exatamente 1 conta em auth.users, encontrei %. A cópia desta etapa foi desenhada para 1 conta — revisar antes de rodar.',
      n_users;
  end if;

  -- (1b) Quem manda no cross join do Bloco 7b é settings, não auth.users: é a
  -- tabela que a view usa como registro de usuários. Guarda próprio, porque as
  -- duas podem divergir (conta criada sem linha de settings — ver regra dura da
  -- Etapa 7 no PLANO-ATIVO.md).
  select count(*) into n_settings from settings;
  if n_settings <> 1 then
    raise exception
      'Guarda 1b: esperava exatamente 1 linha em settings, encontrei %. O Bloco 7b faz cross join com settings e replicaria o estado pessoal para cada linha — revisar antes de rodar.',
      n_settings;
  end if;

  -- (1c) Esta etapa NÃO copia teto: assume que todas as pernas estão no valor
  -- padrão (250). Se alguém ajustou um teto à mão, o valor se perderia calado.
  select count(*) into n_fora from weekend_legs where price_ceiling is distinct from 250;
  if n_fora > 0 then
    raise exception
      'Guarda 1c: % perna(s) com price_ceiling <> 250. Esta etapa não copia teto (assume tudo no padrão) — revisar antes de rodar.',
      n_fora;
  end if;
end $$;


-- ----------------------------------------------------------------------------
-- BLOCO 2 — Teto padrão por usuário, em settings (tabela pessoal, RLS per-user).
-- not null default 250 já preenche a linha existente com o valor em uso hoje.
-- ----------------------------------------------------------------------------
alter table settings
  add column if not exists weekend_default_ceiling numeric not null default 250;


-- ----------------------------------------------------------------------------
-- BLOCO 3 — weekend_leg_user_state: a decisão pessoal por (perna × usuário).
--
-- Modelo preguiçoso: a linha só existe quando o usuário decide algo naquela
-- perna. AUSÊNCIA DE LINHA = teto padrão do usuário + monitoring + sem notas +
-- sem valor pago. price_ceiling NULO na linha = "usa meu padrão".
-- ----------------------------------------------------------------------------
create table if not exists weekend_leg_user_state (
  id            uuid primary key default gen_random_uuid(),
  leg_id        uuid not null references weekend_legs(id) on delete cascade,
  user_id       uuid not null default auth.uid() references auth.users(id) on delete cascade,
  price_ceiling numeric,                     -- NULL = usa settings.weekend_default_ceiling
  status        text not null default 'monitoring',
  notes         text,
  paid_price    numeric,
  purchased_at  timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (leg_id, user_id),
  constraint wlus_status_check  check (status in ('monitoring','purchased')),
  constraint wlus_ceiling_check check (price_ceiling is null or price_ceiling > 0)
);

create index if not exists wlus_user_idx on weekend_leg_user_state (user_id);

alter table weekend_leg_user_state enable row level security;

-- RLS: cada usuário só enxerga e escreve as próprias linhas.
-- O default auth.uid() em user_id existe para o frontend não precisar mandar o
-- dono no insert (mesmo padrão de routes); a trava real é o with check, que
-- rejeita insert/update com o uuid de outra pessoa. Para o robô (service_role,
-- auth.uid() nulo) o default não resolve nada: ou manda user_id explícito ou o
-- not null estoura — que é o comportamento desejado.
drop policy if exists "wlus_select_own" on weekend_leg_user_state;
create policy "wlus_select_own" on weekend_leg_user_state
  for select using (user_id = auth.uid());

drop policy if exists "wlus_insert_own" on weekend_leg_user_state;
create policy "wlus_insert_own" on weekend_leg_user_state
  for insert with check (user_id = auth.uid());

drop policy if exists "wlus_update_own" on weekend_leg_user_state;
create policy "wlus_update_own" on weekend_leg_user_state
  for update using (user_id = auth.uid()) with check (user_id = auth.uid());

-- Delete existe porque o modelo preguiçoso implica "limpar minha decisão nessa
-- perna e voltar ao padrão". A trigger de auditoria cobre esse caminho.
drop policy if exists "wlus_delete_own" on weekend_leg_user_state;
create policy "wlus_delete_own" on weekend_leg_user_state
  for delete using (user_id = auth.uid());

-- updated_at só é confiável se alguém escrever nele. Trigger simples, sem
-- security definer: não escreve em outra tabela, só ajusta a própria linha.
create or replace function flyiop_touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists trg_wlus_touch on weekend_leg_user_state;
create trigger trg_wlus_touch
  before update on weekend_leg_user_state
  for each row execute function flyiop_touch_updated_at();


-- ----------------------------------------------------------------------------
-- BLOCO 4 — Auditoria de teto (e só de teto).
--
-- status já tem purchased_at e paid_price não tem pergunta histórica — decisão
-- do chat de planejamento, não ampliar.
--
-- Append-only: sem policy de insert/update/delete para ninguém. Com RLS ligada e
-- sem policy, é impossível escrever ou apagar pela API. Quem grava é a trigger,
-- que roda como dona da tabela (security definer).
-- LIMITE CONHECIDO: quem entra no SQL Editor como postgres é dono da tabela e
-- ainda consegue apagar. Fechar isso exigiria force row level security, que
-- bloquearia também a própria trigger — por isso não foi feito.
-- ----------------------------------------------------------------------------
create table if not exists weekend_leg_ceiling_audit (
  id              uuid primary key default gen_random_uuid(),
  scope           text not null check (scope in ('leg','default')),
  -- Sem FK em leg_id/user_id DE PROPÓSITO: a auditoria precisa sobreviver à
  -- remoção de uma perna ou de uma conta; FK com cascade apagaria justamente o
  -- histórico que a tabela existe para guardar.
  leg_id          uuid,                      -- null quando scope = 'default'
  user_id         uuid not null,             -- DONO da decisão
  old_value       numeric,                   -- teto EFETIVO antes (null só no marco inicial)
  new_value       numeric,                   -- teto EFETIVO depois
  new_is_explicit boolean not null default true,  -- false = voltou a valer o padrão
  changed_at      timestamptz not null default now(),
  changed_by      uuid,                      -- auth.uid() de QUEM editou (null fora do painel)
  origin          text not null,             -- 'app' | 'robo' | 'sql_editor' | 'migracao'
  constraint wlca_scope_check check (
    (scope = 'leg'     and leg_id is not null) or
    (scope = 'default' and leg_id is null)
  )
);

create index if not exists wlca_lookup_idx
  on weekend_leg_ceiling_audit (user_id, leg_id, changed_at desc);

alter table weekend_leg_ceiling_audit enable row level security;

drop policy if exists "wlca_select_own" on weekend_leg_ceiling_audit;
create policy "wlca_select_own" on weekend_leg_ceiling_audit
  for select using (user_id = auth.uid());

revoke insert, update, delete on weekend_leg_ceiling_audit from anon, authenticated;


-- ----------------------------------------------------------------------------
-- BLOCO 5 — Origem da mudança + triggers de auditoria.
--
-- flyiop_audit_origin() deriva a origem do JWT DA REQUISIÇÃO, não do papel do
-- banco. Motivo (correção do chat de planejamento, 01/08/2026): dentro de uma
-- função SECURITY DEFINER, current_user é o DONO da função, não quem chamou —
-- comparar current_user = 'service_role' nunca seria verdade e o robô sairia
-- carimbado como 'sql_editor'. Já request.jwt.claims é variável de SESSÃO,
-- posta pelo PostgREST por requisição, e o security definer não a troca. Pelo
-- mesmo motivo auth.uid() (que lê essa mesma variável) continua funcionando
-- dentro do definer — flyiop_audit_selftest() abaixo existe para provar isso no
-- banco de verdade, sem escrever nada.
-- ----------------------------------------------------------------------------
create or replace function flyiop_audit_origin() returns text
language plpgsql stable security definer set search_path = public, pg_temp as $$
declare
  v_override text;
  v_claims   jsonb;
  v_role     text;
  v_sub      text;
begin
  -- Override explícito de scripts (ex.: 'migracao'). Só quem já tem acesso SQL
  -- consegue setar, e essa pessoa já poderia escrever direto na tabela.
  v_override := coalesce(current_setting('flyiop.audit_origin', true), '');
  if v_override <> '' then
    return v_override;
  end if;

  begin
    v_claims := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
  exception when others then
    v_claims := null;
  end;

  if v_claims is null then
    return 'sql_editor';               -- sem claim nenhum: edição manual
  end if;

  v_role := v_claims ->> 'role';
  v_sub  := v_claims ->> 'sub';

  if v_role = 'service_role' then
    return 'robo';                     -- backend (GitHub Actions)
  end if;

  if v_sub is not null and v_sub <> '' then
    return 'app';                      -- painel, usuário logado
  end if;

  return 'sql_editor';
end $$;

-- Sonda somente-leitura, usada por sql/etapa4_1_verificacao.sql (Bloco G) para
-- provar, dentro de um contexto SECURITY DEFINER real, que auth.uid() e a
-- derivação de origem enxergam o JWT da sessão. Não escreve nada.
-- TEMPORÁRIA: o Bloco H da verificação derruba esta função depois do teste —
-- função definer é a peça mais sensível do conjunto e não fica no ar à toa.
-- Nada em produção depende dela (as triggers usam flyiop_audit_origin()).
-- Para rodar o Bloco G de novo no futuro, basta re-rodar este Bloco 5.
create or replace function flyiop_audit_selftest() returns jsonb
language plpgsql stable security definer set search_path = public, pg_temp as $$
declare v_uid uuid;
begin
  begin v_uid := auth.uid(); exception when others then v_uid := null; end;
  return jsonb_build_object(
    'current_user', current_user,      -- dentro do definer, é o DONO da função
    'auth_uid',     v_uid,             -- tem que refletir o JWT de quem chamou
    'origin',       flyiop_audit_origin()
  );
end $$;

-- Auditoria do teto POR PERNA.
-- security definer é obrigatório: sem ele a trigger tentaria gravar na auditoria
-- com o papel authenticated, que não tem policy de insert, e o salvamento no
-- painel falharia inteiro. search_path fixo é a proteção padrão de definer.
create or replace function flyiop_audit_leg_ceiling() returns trigger
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  v_default  numeric;
  v_old      numeric;
  v_new      numeric;
  v_user     uuid;
  v_leg      uuid;
  v_explicit boolean;
  v_by       uuid;
begin
  v_user := coalesce(new.user_id, old.user_id);
  v_leg  := coalesce(new.leg_id,  old.leg_id);

  -- Teto padrão do DONO da linha, não de quem está editando.
  select s.weekend_default_ceiling into v_default from settings s where s.user_id = v_user;

  begin v_by := auth.uid(); exception when others then v_by := null; end;

  if tg_op = 'INSERT' then
    v_old      := v_default;                             -- antes da linha existir, valia o padrão
    v_new      := coalesce(new.price_ceiling, v_default);
    v_explicit := new.price_ceiling is not null;
  elsif tg_op = 'UPDATE' then
    v_old      := coalesce(old.price_ceiling, v_default);
    v_new      := coalesce(new.price_ceiling, v_default);
    v_explicit := new.price_ceiling is not null;
  else -- DELETE: a perna volta a valer o padrão
    v_old      := coalesce(old.price_ceiling, v_default);
    v_new      := v_default;
    v_explicit := false;
  end if;

  -- Só registra mudança de teto EFETIVO: é a pergunta que a tabela responde
  -- ("que teto estava valendo naquele dia"). Editar nota ou valor pago não gera
  -- linha de auditoria.
  if v_old is distinct from v_new then
    insert into weekend_leg_ceiling_audit
      (scope, leg_id, user_id, old_value, new_value, new_is_explicit, changed_by, origin)
    values
      ('leg', v_leg, v_user, v_old, v_new, v_explicit, v_by, flyiop_audit_origin());
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end $$;

drop trigger if exists trg_audit_leg_ceiling on weekend_leg_user_state;
create trigger trg_audit_leg_ceiling
  after insert or update or delete on weekend_leg_user_state
  for each row execute function flyiop_audit_leg_ceiling();

-- Auditoria do teto PADRÃO (aprovada no chat de planejamento): é a mudança que
-- afeta ~131 pernas de uma vez; deixá-la de fora reconstruiria exatamente a
-- cegueira que travou o diagnóstico de 31/07/2026.
create or replace function flyiop_audit_default_ceiling() returns trigger
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  v_by  uuid;
  v_old numeric;
begin
  begin v_by := auth.uid(); exception when others then v_by := null; end;
  v_old := case when tg_op = 'UPDATE' then old.weekend_default_ceiling else null end;

  insert into weekend_leg_ceiling_audit
    (scope, leg_id, user_id, old_value, new_value, new_is_explicit, changed_by, origin)
  values
    ('default', null, new.user_id, v_old, new.weekend_default_ceiling, true, v_by, flyiop_audit_origin());

  return new;
end $$;

-- São duas triggers porque a cláusula when não pode referenciar old num insert.
-- A de insert dá marco inicial automático para a conta nova da Etapa 7.
drop trigger if exists trg_audit_default_ceiling_ins on settings;
create trigger trg_audit_default_ceiling_ins
  after insert on settings
  for each row execute function flyiop_audit_default_ceiling();

-- A de update é estreita de propósito (update of <coluna> + when): salvar o
-- formulário de Configurações sem mexer no teto padrão não dispara nada. Esta é
-- a única peça da 4.1 que encosta numa tabela viva.
drop trigger if exists trg_audit_default_ceiling_upd on settings;
create trigger trg_audit_default_ceiling_upd
  after update of weekend_default_ceiling on settings
  for each row
  when (old.weekend_default_ceiling is distinct from new.weekend_default_ceiling)
  execute function flyiop_audit_default_ceiling();


-- ----------------------------------------------------------------------------
-- BLOCO 6 — View de resolução do teto efetivo.
--
-- Devolve uma linha por (perna × usuário) MESMO quando não existe linha de
-- estado. settings funciona como registro de usuários (PK = user_id, então não
-- há como duplicar linha por usuário).
--
-- security_invoker = true (Postgres 17.6, confirmado no passo 0): a view roda
-- com a RLS de quem chama.
--  - Usuário logado: a RLS de settings solta só a própria linha, então o cross
--    join produz só as 132 pernas dele; a RLS de weekend_leg_user_state bloqueia
--    o estado alheio no left join.
--  - Robô (service_role, bypassa RLS): vê 132 × nº de usuários, que é o que a
--    Etapa 6 precisa para alertar por (perna × usuário).
-- NÃO existe filtro user_id = auth.uid() escrito aqui, de propósito: com ele, o
-- robô (auth.uid() nulo) veria zero linhas. A RLS das tabelas de baixo é a trava;
-- a view não tem trava própria. Qualquer policy nova em settings ou em
-- weekend_leg_user_state precisa re-rodar os blocos E e F da verificação.
-- ----------------------------------------------------------------------------
drop view if exists weekend_leg_effective;
create view weekend_leg_effective
with (security_invoker = true) as
select
  l.id                                                  as leg_id,
  s.user_id                                             as user_id,
  l.weekend_id,
  l.direction,
  w.outbound_date,
  w.return_sunday,
  w.return_monday,
  coalesce(st.price_ceiling, s.weekend_default_ceiling) as price_ceiling,
  (st.price_ceiling is not null)                        as ceiling_is_explicit,
  coalesce(st.status, 'monitoring')                     as status,
  st.notes,
  st.paid_price,
  st.purchased_at,
  (st.id is not null)                                   as has_state,
  l.current_price,
  l.current_airport,
  l.current_variant,
  l.current_source,
  l.lowest_seen,
  l.lowest_seen_at,
  l.last_live_check_at
from weekend_legs l
join weekends w
  on w.id = l.weekend_id
cross join settings s                      -- settings = registro de usuários
left join weekend_leg_user_state st
  on st.leg_id = l.id and st.user_id = s.user_id;

grant select on weekend_leg_effective to authenticated, service_role;


-- ----------------------------------------------------------------------------
-- BLOCO 7 — Cópia dos dados atuais.
-- ----------------------------------------------------------------------------

-- 7a. Marco inicial do teto na auditoria: uma linha 'default' por usuário, com
-- origem 'migracao'. A auditoria não reconstrói o passado — este é o dia zero.
insert into weekend_leg_ceiling_audit
  (scope, leg_id, user_id, old_value, new_value, new_is_explicit, origin)
select 'default', null, s.user_id, null, s.weekend_default_ceiling, true, 'migracao'
from settings s
where not exists (
  select 1 from weekend_leg_ceiling_audit a
  where a.user_id = s.user_id and a.scope = 'default'
);

-- 7b. Estado pessoal que hoje mora em weekend_legs.
-- Esperado hoje: 5 linhas (as que têm paid_price). O where é genérico de
-- propósito — se aparecer nota ou compra entre a escrita deste arquivo e o dia
-- de rodar, vem junto sem editar o script.
-- As 5 linhas com paid_price preenchido e status 'monitoring' são anomalia
-- conhecida: copiar como estão, sem normalizar nem corrigir status (decisão do
-- chat de planejamento).
-- Teto NÃO é copiado: o guarda 1c garante que todas as pernas estão em 250, que
-- é exatamente o padrão do usuário — price_ceiling nulo já resolve para 250 na
-- view. Por isso estes inserts também não geram linha de auditoria (teto efetivo
-- 250 antes e depois).
-- O cross join só é seguro por causa dos guardas 1a/1b (exatamente 1 usuário).
insert into weekend_leg_user_state
  (leg_id, user_id, price_ceiling, status, notes, paid_price, purchased_at)
select
  l.id,
  s.user_id,
  null,                                   -- teto: usa o padrão do usuário
  l.status,
  l.notes,
  l.paid_price,
  l.purchased_at
from weekend_legs l
cross join settings s
where l.paid_price is not null
   or l.notes is not null
   or l.purchased_at is not null
   or l.status is distinct from 'monitoring'
on conflict (leg_id, user_id) do nothing;


-- Recarrega o cache de schema do PostgREST (a view nova fica visível na API).
notify pgrst, 'reload schema';
