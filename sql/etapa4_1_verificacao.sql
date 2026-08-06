-- ============================================================================
-- Etapa 4.1 — verificação.
--
-- Blocos A a G: SOMENTE LEITURA quanto ao que sobrevive (nenhum create; todo
-- bloco com transação termina em rollback — nada persiste). Os blocos F e F2
-- fazem insert transitório dentro da própria transação, só para testar
-- isolamento/RLS; o rollback desfaz tudo antes do commit.
-- Bloco H: LIMPEZA — é a ÚNICA parte deste arquivo que altera o banco de
-- forma persistente. Roda separado, depois de conferir o Bloco G.
--
-- Como usar:
--  1) Rodar os blocos A, B e C ANTES de sql/etapa4_1_estado_por_usuario.sql e
--     guardar o resultado. (D a G ainda não funcionam: os objetos não existem.)
--  2) Rodar o script da 4.1.
--  3) Rodar A a G e comparar: A, B e C têm que sair IDÊNTICOS ao passo 1 — é a
--     prova de que a etapa não mudou comportamento. D, E, F, F2 e G são os
--     blocos que só fazem sentido depois.
--  4) Conferido o G, rodar o Bloco H para tirar a sonda do banco.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO A — Fotografia do mundo antigo. Idêntico antes e depois.
-- ----------------------------------------------------------------------------
select
  count(*)                                        as legs,
  count(*) filter (where price_ceiling = 250)     as teto_250,
  count(*) filter (where status = 'monitoring')   as monitorando,
  count(paid_price)                               as com_pago,
  count(notes)                                    as com_nota
from weekend_legs;
-- Esperado (01/08/2026): 132 | 132 | 132 | 5 | 0


-- ----------------------------------------------------------------------------
-- BLOCO B — Policies de weekend_legs. Texto idêntico antes e depois.
-- A 4.1 não altera policy nenhuma de weekend_legs (isso é a Etapa 4.3/5).
-- ----------------------------------------------------------------------------
select policyname, cmd, qual, with_check
from pg_policies
where tablename = 'weekend_legs'
order by policyname;
-- Esperado: 2 linhas (select e update), ambas com auth.uid() is not null.


-- ----------------------------------------------------------------------------
-- BLOCO C — weekend_legs continua SEM trigger nenhuma.
-- ----------------------------------------------------------------------------
select tgname
from pg_trigger
where tgrelid = 'weekend_legs'::regclass
  and not tgisinternal;
-- Esperado: zero linhas, antes e depois.


-- ----------------------------------------------------------------------------
-- BLOCO D — Estrutura nova populada (rodando como postgres, que IGNORA RLS).
-- Serve só para conferir a cópia de dados. NÃO prova nada sobre o que o usuário
-- logado enxerga — isso é o Bloco F.
-- ----------------------------------------------------------------------------
select count(*) as estado_copiado from weekend_leg_user_state;
-- Esperado: 5

select scope, origin, old_value, new_value, user_id
from weekend_leg_ceiling_audit
order by changed_at;
-- Esperado: 1 linha — scope 'default', origin 'migracao', old null, new 250.

select count(*) as linhas_view from weekend_leg_effective;
-- Esperado: 132 (1 usuário × 132 pernas).

select count(*) filter (where price_ceiling = 250)       as resolvido_250,
       count(*) filter (where ceiling_is_explicit)       as com_teto_proprio,
       count(*) filter (where has_state)                 as com_linha_de_estado,
       count(paid_price)                                 as com_pago
from weekend_leg_effective;
-- Esperado: 132 | 0 | 5 | 5
-- (todos resolvem 250 pelo padrão do usuário, nenhum teto próprio ainda)


-- ----------------------------------------------------------------------------
-- BLOCO E — TESTE NEGATIVO de isolamento (usuário que não é dono de nada).
-- Consolidado numa linha só (o SQL Editor descarta tudo exceto o último select
-- de cada bloco). uid_visto e papel_efetivo são colunas-guarda: se qualquer
-- uma vier errada, os números ao lado não provam nada — o contexto de papel
-- não pegou.
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';
  set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-000000000001","role":"authenticated"}';
  set local role authenticated;

  select
    auth.uid()                                          as uid_visto,      -- esperado: 00000000-...-0001
    current_user                                         as papel_efetivo, -- esperado: authenticated
    (select count(*) from weekend_leg_effective)         as view_esp_0,
    (select count(*) from weekend_leg_user_state)        as estado_esp_0,
    (select count(*) from weekend_leg_ceiling_audit)     as auditoria_esp_0;
rollback;


-- ----------------------------------------------------------------------------
-- BLOCO F — regressão do caminho legítimo + isolamento POSITIVO na auditoria.
--
-- Com uma conta só, "o que o usuário legítimo vê" e "o que o dono do banco vê"
-- coincidem em weekend_leg_effective e weekend_leg_user_state — não é possível
-- provar isolamento nessas duas tabelas até existir uma segunda conta (Etapa 7),
-- porque a view depende de duas linhas em settings, que tem FK para auth.users
-- (confirmado 05/08/2026) — nada aqui simula um segundo dono ali de propósito.
--
-- A auditoria é diferente: user_id sem FK (decisão do Bloco 4 da 4.1), então dá
-- pra semear um dono sintético dentro da própria transação. A última coluna é
-- o único discriminador real do bloco.
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';

  insert into weekend_leg_ceiling_audit
    (scope, leg_id, user_id, old_value, new_value, new_is_explicit, origin)
  values
    ('default', null, '00000000-0000-0000-0000-000000000002', null, 999, true, 'sql_editor');

  set local request.jwt.claims = '{"sub":"c72bf50e-16f7-48fd-9c86-7b49dea1551e","role":"authenticated"}';
  set local role authenticated;

  select
    auth.uid()                                           as uid_visto,       -- esperado: c72bf50e-...
    current_user                                          as papel_efetivo,   -- esperado: authenticated
    (select count(*) from weekend_leg_effective)          as view_esp_132,
    (select count(*) from weekend_leg_user_state)         as estado_esp_5,
    (select count(*) from weekend_leg_ceiling_audit
       where new_value = 999)                             as alienigena_esp_0; -- discriminador real
rollback;


-- ----------------------------------------------------------------------------
-- BLOCO F2 — a RLS de ESCRITA de weekend_leg_user_state bloqueia mesmo em
-- produção (só testado antes num Postgres descartável, nunca no banco real).
--
-- Tenta inserir uma linha com user_id ALHEIO (deve ser rejeitado) e uma com
-- user_id PRÓPRIO (deve ser aceito) — o par junto é o que prova que o
-- "with check (user_id = auth.uid())" está de fato comparando o uuid, e não
-- só bloqueando tudo por outro motivo (o que faria o teste passar por engano).
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';
  set local request.jwt.claims = '{"sub":"c72bf50e-16f7-48fd-9c86-7b49dea1551e","role":"authenticated"}';
  set local role authenticated;

  do $$
  declare v_leg uuid; v_alheio text; v_proprio text;
  begin
    select l.id into v_leg from weekend_legs l
     where not exists (select 1 from weekend_leg_user_state s where s.leg_id = l.id)
     limit 1;

    begin
      insert into weekend_leg_user_state (leg_id, user_id)
      values (v_leg, '00000000-0000-0000-0000-000000000002');
      v_alheio := 'PASSOU — FALHA';
    exception when others then v_alheio := 'bloqueado ' || sqlstate; end;

    begin
      insert into weekend_leg_user_state (leg_id, user_id) values (v_leg, auth.uid());
      v_proprio := 'aceito';
    exception when others then v_proprio := 'BLOQUEADO ' || sqlstate || ' — FALHA'; end;

    perform set_config('flyiop.probe_alheio', v_alheio, true);
    perform set_config('flyiop.probe_proprio', v_proprio, true);
  end $$;

  select
    auth.uid()                                     as uid_visto,
    current_user                                    as papel_efetivo,
    current_setting('flyiop.probe_alheio',  true)  as escrita_alheia_esp_bloqueada,
    current_setting('flyiop.probe_proprio', true)  as escrita_propria_esp_aceita;
rollback;


-- ----------------------------------------------------------------------------
-- BLOCO G — Carimbo de origem e auth.uid() dentro de SECURITY DEFINER.
--
-- flyiop_audit_selftest() é uma sonda somente-leitura que roda como definer,
-- igual às triggers de auditoria. Prova duas coisas de uma vez:
--  - current_user dentro do definer é o DONO da função (por isso a origem NÃO
--    pode ser derivada dele);
--  - auth.uid() e a origem, que leem a variável de sessão request.jwt.claims,
--    continuam enxergando quem chamou.
-- ----------------------------------------------------------------------------
select flyiop_audit_selftest() as como_sql_editor;
-- Esperado: auth_uid null, origin 'sql_editor'

begin;
  set local request.jwt.claims = '{"sub":"c72bf50e-16f7-48fd-9c86-7b49dea1551e","role":"authenticated"}';
  set local role authenticated;
  select flyiop_audit_selftest() as como_painel;
  -- Esperado: auth_uid = c72bf50e-…, origin 'app'
  -- (current_user vem como o dono da função, NÃO como 'authenticated' — é
  --  exatamente esse o motivo de a origem não poder sair de current_user)
rollback;

begin;
  set local request.jwt.claims = '{"role":"service_role"}';
  set local role service_role;
  select flyiop_audit_selftest() as como_robo;
  -- Esperado: auth_uid null, origin 'robo'
rollback;

begin;
  select set_config('flyiop.audit_origin', 'migracao', true);
  select flyiop_audit_selftest() as com_override;
  -- Esperado: origin 'migracao'
rollback;


-- ----------------------------------------------------------------------------
-- BLOCO H — LIMPEZA. ATENÇÃO: única parte deste arquivo que ALTERA o banco.
--
-- Rodar depois de conferir o Bloco G. flyiop_audit_selftest() é uma sonda de
-- teste único e é security definer — função definer é a peça mais sensível do
-- conjunto, e não faz sentido deixar uma no ar depois que ela já respondeu.
--
-- Derrubar a sonda NÃO afeta nada em produção: nenhuma trigger, view ou policy
-- depende dela (as triggers usam flyiop_audit_origin(), que fica).
--
-- Se precisar rodar o Bloco G de novo no futuro (por exemplo, depois de mexer
-- em alguma policy de settings ou de weekend_leg_user_state), a sonda é
-- recriada rodando de novo o Bloco 5 de sql/etapa4_1_estado_por_usuario.sql,
-- que é idempotente.
-- ----------------------------------------------------------------------------
drop function flyiop_audit_selftest();

-- Confirmação: tem que devolver zero linhas.
select proname from pg_proc where proname = 'flyiop_audit_selftest';
