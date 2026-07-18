-- Etapa 2 do PLAN-FASE-A.md: portão de frescor nos alertas.
-- Rodar no SQL Editor do Supabase ANTES do push do código desta etapa.
-- (O código tem fallback pros defaults se as colunas ainda não existirem,
--  mas a UI de Configurações só salva depois disso rodar.)

alter table settings
  add column if not exists freshness_hours integer not null default 24;

alter table settings
  add column if not exists stale_alert_policy text not null default 'warn';

-- Nenhuma mudança de RLS necessária: as políticas existentes da tabela
-- settings já cobrem as colunas novas (RLS é por linha, não por coluna).
