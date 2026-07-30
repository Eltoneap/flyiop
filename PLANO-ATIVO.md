# Plano Ativo — FlyIop

_Atualizado em 24/07/2026. Contém só o que está em execução ou pendente de aprovação/implementação. Tudo que já foi entregue (com data e decisões tomadas) está em `HISTORICO.md` — referencie por lá em vez de reproduzir aqui._

**Regra de apresentação (24/07/2026):** ao apresentar um plano ou atualização no chat, mostrar só a seção nova/alterada, nunca o arquivo inteiro. Para contexto, referenciar a seção pelo nome (ex.: "ver Parte 8 no HISTORICO.md") em vez de reproduzir. O arquivo completo fica no disco; o chat recebe só o delta. (Ver também `PROTOCOLO-DE-TRABALHO.md`.)

---

## Iniciativa: suporte a segundo usuário (multi-usuário)

Decidido no chat de planejamento (29/07/2026): um amigo também vai comprar
RIO↔BSB em 2027. Escopo completo (alertas + painel próprio + aba Compras
própria). Telegram: grupo único compartilhado (não bot/chat separado por
pessoa) — mensagem identifica nome + valor do teto de quem disparou.
Detalhe da investigação em `AUDITORIA-MULTIUSUARIO.md` (fora dos três
arquivos oficiais, arquivo de trabalho desta iniciativa).

**Regra de trabalho:** cada etapa exige revisão explícita no chat de
planejamento antes de rodar. Nunca encadear etapas sozinho.

### Ordem de execução

1. ✅ **Concluída (29/07/2026).** Consolidar baseline do schema legado +
   investigar uso real das colunas de `settings` (arquivo:linha) + preparar
   (sem aplicar) correção da policy de `alert_log`. Resultado completo em
   `AUDITORIA-MULTIUSUARIO.md` (seção "Etapa 1"): `routes`/`settings` têm
   RLS per-user confirmada; colunas de `settings` se dividem em 3 grupos
   (legado puro / compartilhadas via `cooldown_blocks_alert` / lidas como
   globais mas hoje per-user — `weekend_opportunity_pct`,
   `suspicious_below_avg_pct`, `fast_flights_enabled`,
   `fast_flights_daily_batch_size`); rascunho da correção de `alert_log` em
   `sql/draft_alert_log_leg_policy.sql` (não aplicado). **Aguardando revisão
   no chat de planejamento antes de liberar a Etapa 2.**
2. ✅ **Concluída (29/07/2026).** Policy de `alert_log` corrigida e aplicada
   em produção (cobre `route_id` e `leg_id`).
3. ✅ **Concluída (29/07/2026).** Separada `settings`: sistema (config
   única) × pessoal (per-user). Divisão final:
   - **Sistema** (agora em `system_config`, linha única, sem dono):
     `suspicious_below_avg_pct`, `fast_flights_enabled`,
     `fast_flights_daily_batch_size`.
   - **Pessoal** (continua em `settings`, per-user): `window_3d_pct`,
     `window_7d_pct`, `freshness_hours`, `stale_alert_policy`,
     `notification_mode`, `realert_drop_pct`, `realert_days`,
     `weekend_opportunity_pct`.
   - **Fora de escopo**: `cost_per_thousand_brl` (sem consumidor, fica como
     está).
   Implementado: `sql/system_config.sql` (rodado manualmente pelo usuário
   no SQL Editor do Supabase), `src/supabase_client.py`/`src/main.py` lendo
   de `system_config`, formulário de Configurações sem os 3 campos
   (edição agora é só via SQL Editor — ver `RUNBOOK.md`),
   `docs/js/dashboard.js` lendo o status do kill-switch de `system_config`
   (com degradação pra "desconhecido" se a consulta falhar). As 3 colunas
   antigas continuam em `settings`, intocadas e sem uso — **pendência**:
   Etapa 3b (remoção), só depois de alguns dias de produção estável.
   Detalhe/histórico da decisão em `AUDITORIA-MULTIUSUARIO.md`.
4. Tabela de decisão pessoal (`weekend_leg_user_state`: teto/status/notas/
   valor pago por usuário) + migrar dados atuais em 3 degraus (criar e
   copiar → frontend passa a usar → só depois remover colunas antigas de
   `weekend_legs`).
5. Frontend: Compras/Dashboard por usuário logado; `weekend_legs` vira
   somente-leitura no navegador; redesenho de RLS de update.
6. Telegram: cooldown/dedup de `alert_log` por (perna × usuário); composição
   de mensagem com nome+valor; mantém o mesmo `TELEGRAM_CHAT_ID` (grupo).
7. Criar conta do segundo usuário no Supabase Auth — **por último**, só
   depois de tudo testado. Regra dura: nenhuma conta nova antes disso.
