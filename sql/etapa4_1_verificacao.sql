-- ============================================================================
-- Etapa 4.1 — verificação.
--
-- Blocos A a G: SOMENTE LEITURA (nenhum insert/update/delete; nenhum create;
-- os blocos com transação terminam em rollback). Podem rodar antes do script
-- principal sem criar objeto nenhum no banco.
-- Bloco H: LIMPEZA — é a ÚNICA parte deste arquivo que altera o banco. Roda
-- separado, depois de conferir o Bloco G.
--
-- Como usar:
--  1) Rodar os blocos A, B e C ANTES de sql/etapa4_1_estado_por_usuario.sql e
--     guardar o resultado. (D a G ainda não funcionam: os objetos não existem.)
--  2) Rodar o script da 4.1.
--  3) Rodar A a G e comparar: A, B e C têm que sair IDÊNTICOS ao passo 1 — é a
--     prova de que a etapa não mudou comportamento. D, E, F e G são os blocos
--     que só fazem sentido depois.
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
--
-- Finge um usuário inexistente no nível da sessão, sem criar conta (a regra dura
-- da iniciativa é: nenhuma conta nova antes da Etapa 7). Se QUALQUER contagem
-- aqui vier > 0, a estrutura vaza dado entre usuários e a 4.1 não sobe.
-- ----------------------------------------------------------------------------
begin;
  set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-000000000001","role":"authenticated"}';
  set local role authenticated;

  select auth.uid() as uid_falso;
  -- Esperado: 00000000-0000-0000-0000-000000000001
  -- (se vier null, o teste abaixo não vale nada — o ambiente não aplicou o claim)

  select count(*) as view_deve_ser_zero    from weekend_leg_effective;
  select count(*) as estado_deve_ser_zero  from weekend_leg_user_state;
  select count(*) as audit_deve_ser_zero   from weekend_leg_ceiling_audit;
  -- Esperado: 0 | 0 | 0
rollback;


-- ----------------------------------------------------------------------------
-- BLOCO F — TESTE POSITIVO (usuário real, c72bf50e-…).
--
-- Simétrico ao E e igualmente obrigatório: o modo de falha clássico do
-- security_invoker é a view devolver ZERO para o usuário legítimo. Sem este
-- bloco, a 4.1 passaria em tudo e a quebra só apareceria na 4.2, com o painel
-- vazio.
-- ----------------------------------------------------------------------------
begin;
  set local request.jwt.claims = '{"sub":"c72bf50e-16f7-48fd-9c86-7b49dea1551e","role":"authenticated"}';
  set local role authenticated;

  select auth.uid() as uid_real;
  -- Esperado: c72bf50e-16f7-48fd-9c86-7b49dea1551e

  select count(*) as view_deve_ser_132   from weekend_leg_effective;
  select count(*) as estado_deve_ser_5   from weekend_leg_user_state;
  select count(*) as audit_deve_ser_1    from weekend_leg_ceiling_audit;
  -- Esperado: 132 | 5 | 1

  select count(*) filter (where price_ceiling = 250) as resolvido_250,
         count(paid_price)                           as com_pago
  from weekend_leg_effective;
  -- Esperado: 132 | 5  (o teto padrão do usuário resolveu para todas as pernas)
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
