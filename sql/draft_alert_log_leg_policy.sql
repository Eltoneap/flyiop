-- DRAFT — NÃO EXECUTAR ainda. Preparado na Etapa 1 da iniciativa
-- multi-usuário (29/07/2026), pendente de revisão no chat de planejamento
-- (Etapa 2). Ver AUDITORIA-MULTIUSUARIO.md, seção "Etapa 1".
--
-- Corrige sql/etapa3_cooldown.sql: a policy de select de alert_log só
-- cobria route_id (rotas flexíveis). Quando pernas_desacopladas.sql
-- introduziu leg_id como alternativa (alert_log_route_or_leg_check),
-- nenhuma migration atualizou esta policy — linhas gravadas via leg_id
-- (todo alerta de fim de semana, insert_weekend_alert_log) ficam
-- invisíveis sob RLS pra qualquer usuário autenticado hoje.
--
-- Mesmo padrão de permissividade já usado em weekend_legs/weekends/
-- bot_state (auth.uid() is not null) — não tenta resolver ownership por
-- usuário aqui, isso é assunto da Etapa 4/5 (weekend_leg_user_state +
-- redesenho de RLS de update).

drop policy if exists "alert_log_select_own_routes" on alert_log;

create policy "alert_log_select_own_routes_or_any_leg"
  on alert_log for select
  using (
    (route_id is not null and route_id in (select id from routes where user_id = auth.uid()))
    or (leg_id is not null and auth.uid() is not null)
  );
