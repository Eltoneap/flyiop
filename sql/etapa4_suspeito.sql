-- Etapa 4 do PLAN-FASE-A.md: autocheck estatístico anti-preço-fantasma.
-- Rodar no SQL Editor do Supabase ANTES do push do código desta etapa.

alter table settings
  add column if not exists suspicious_below_avg_pct numeric not null default 50;
