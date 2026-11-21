-- ============================================================================
-- ROLLBACK de sql/perna_dispensada_usuario_ativo.sql
--
-- PRÉ-REQUISITO: reverter (git revert) o código que lê monitoring_active e
-- grava 'dismissed' ANTES de rodar o BLOCO 3 — o robô novo pede a coluna à
-- view e quebraria sem ela.
--
-- O que NÃO é desfeito: linhas criadas em settings pelo BLOCO 3 da migração
-- (o BLOCO 0 de lá mostrou quais; esperado nenhuma). Apagar linha de settings
-- apaga o usuário do registro — fazer à mão, se for o caso.
--
-- EXECUÇÃO: 100% MANUAL, no SQL Editor, bloco a bloco.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO 1 — pernas dispensadas voltam a 'monitoring' (perde-se só a marca de
-- "Não preciso"; teto, notas e valor pago da linha ficam intactos). Precisa vir
-- antes do CHECK antigo, que rejeitaria as linhas 'dismissed'.
-- ----------------------------------------------------------------------------
update weekend_leg_user_state set status = 'monitoring', updated_at = now()
 where status = 'dismissed';

alter table weekend_leg_user_state drop constraint if exists wlus_status_check;
alter table weekend_leg_user_state
  add constraint wlus_status_check check (status in ('monitoring','purchased'));


-- ----------------------------------------------------------------------------
-- BLOCO 2 — view volta à definição original (Etapa 4.1, Bloco 6). Remover
-- coluna de view exige drop + create; security_invoker = true mantido.
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
-- BLOCO 3 — coluna monitoring_active sai (depois da view, que dependia dela).
-- ----------------------------------------------------------------------------
alter table settings drop column if exists monitoring_active;


-- ----------------------------------------------------------------------------
-- BLOCO 4 — verificação. ESPERADO: check_sem_dismissed = true,
-- view_security_invoker = true, coluna_existe = false.
-- ----------------------------------------------------------------------------
select
  (select pg_get_constraintdef(oid) not like '%dismissed%'
     from pg_constraint where conname = 'wlus_status_check')   as check_sem_dismissed,
  (select coalesce('security_invoker=true' = any(reloptions), false)
     from pg_class where relname = 'weekend_leg_effective')    as view_security_invoker,
  exists (select 1 from information_schema.columns
           where table_name = 'settings' and column_name = 'monitoring_active') as coluna_existe;
