-- ============================================================================
-- Perna dispensada ("Não preciso") + usuário fora do monitoramento — 20/11/2026
--
-- Mesma raiz das duas demandas: "quem ainda quer esta perna?".
--   A) status novo 'dismissed' em weekend_leg_user_state — reversível pelo
--      painel ("Voltar a monitorar" grava 'monitoring' de novo).
--   B) settings.monitoring_active (default true) — false tira o usuário da
--      fila do robô, do fan-out de alertas de preço e do resumo de segunda,
--      com o login preservado. Alterado SÓ pelo SQL Editor (sem UI):
--      sql/usuario_monitoramento_desligar_gustavo.sql / _religar_gustavo.sql.
--
-- ADITIVA E COMPATÍVEL COM O CÓDIGO ATUAL: só amplia o CHECK, acrescenta uma
-- coluna com default e acrescenta uma coluna NO FIM da view (create or
-- replace — grants e dependências preservados). O robô/painel de antes desta
-- fatia continuam funcionando (selecionam colunas nomeadas; ninguém grava
-- 'dismissed' até o painel novo subir).
--
-- ORDEM DE IMPLANTAÇÃO: rodar ESTE arquivo ANTES do push do código novo —
-- o robô novo pede `monitoring_active` à view e quebraria sem a coluna.
--
-- RLS: nenhuma policy nova ou alterada.
--   - weekend_leg_user_state: as policies *_own continuam cobrindo o novo
--     valor de status (a trava é user_id = auth.uid(), não o status).
--   - settings: coluna nova herda as policies existentes da tabela.
--   - A view é recriada COM `security_invoker = true` (sem isso ela rodaria
--     como dono e furaria a RLS de settings/weekend_leg_user_state).
--   - Trigger flyiop_sync_purchase_shared (fatia_c): status <> 'purchased'
--     já remove a projeção — 'dismissed' cai nesse ramo, sem mudança.
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase. Claude Code
-- NÃO executa SQL. Rodar BLOCO A BLOCO (o SQL Editor só mostra o resultado
-- do último statement). Desfazer: sql/perna_dispensada_usuario_ativo_ROLLBACK.sql
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO 0 — prévia (só leitura). Quem ganharia linha nova em settings no
-- BLOCO 3. ESPERADO: 0 linhas (Elton e Gustavo já têm linha — o Gustavo desde
-- a E7-2, sql/etapa7_2_insert_settings_gustavo.sql). Se aparecer alguém,
-- ATENÇÃO: linha nova em settings = usuário passa a monitorar as 132 pernas e
-- a receber alerta (é o que "sem linha conta como ativo" significa). Decidir
-- antes de rodar o BLOCO 3.
-- ----------------------------------------------------------------------------
select u.id, u.email, u.created_at
  from auth.users u
  left join settings s on s.user_id = u.id
 where s.user_id is null;


-- ----------------------------------------------------------------------------
-- BLOCO 1 — status 'dismissed'.
-- ----------------------------------------------------------------------------
alter table weekend_leg_user_state drop constraint if exists wlus_status_check;
alter table weekend_leg_user_state
  add constraint wlus_status_check check (status in ('monitoring','purchased','dismissed'));


-- ----------------------------------------------------------------------------
-- BLOCO 2 — usuário participa do monitoramento? (default true = todos seguem
-- como hoje).
-- ----------------------------------------------------------------------------
alter table settings
  add column if not exists monitoring_active boolean not null default true;


-- ----------------------------------------------------------------------------
-- BLOCO 3 — todo usuário existente tem linha em settings (as demais colunas
-- são NOT NULL com default seguro, E7-0/Q1). Idempotente.
-- ----------------------------------------------------------------------------
insert into settings (user_id)
select u.id from auth.users u
on conflict (user_id) do nothing;


-- ----------------------------------------------------------------------------
-- BLOCO 4 — view: EXPÕE monitoring_active, NÃO filtra (quem decide é o robô e
-- o painel). Mesma definição de sql/etapa4_1_estado_por_usuario.sql (Bloco 6)
-- + 1 coluna no fim. `create or replace` só permite acrescentar no fim — por
-- isso a posição.
-- ----------------------------------------------------------------------------
create or replace view weekend_leg_effective
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
  l.last_live_check_at,
  s.monitoring_active                                   as monitoring_active
from weekend_legs l
join weekends w
  on w.id = l.weekend_id
cross join settings s                      -- settings = registro de usuários
left join weekend_leg_user_state st
  on st.leg_id = l.id and st.user_id = s.user_id;

grant select on weekend_leg_effective to authenticated, service_role;


-- ----------------------------------------------------------------------------
-- BLOCO 5 — verificação (só leitura).
-- ESPERADO: check_aceita_dismissed = true; view_security_invoker = true;
-- usuarios_sem_settings = 0; gustavo_tem_linha = true; usuarios_ativos = 2;
-- linhas_view = 132 × nº de linhas em settings (264 hoje); dismissed = 0.
-- ----------------------------------------------------------------------------
select
  (select pg_get_constraintdef(oid) like '%dismissed%'
     from pg_constraint where conname = 'wlus_status_check')              as check_aceita_dismissed,
  (select coalesce('security_invoker=true' = any(reloptions), false)
     from pg_class where relname = 'weekend_leg_effective')               as view_security_invoker,
  (select count(*) from auth.users u
     where not exists (select 1 from settings s where s.user_id = u.id))  as usuarios_sem_settings,
  exists (select 1 from settings
           where user_id = '2446ec67-06b8-478c-bc5d-6a17eab1fe76')        as gustavo_tem_linha,
  (select count(*) from settings where monitoring_active)                 as usuarios_ativos,
  (select count(*) from weekend_leg_effective)                            as linhas_view,
  (select count(*) from weekend_leg_user_state where status = 'dismissed') as dismissed;
