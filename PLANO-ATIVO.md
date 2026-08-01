# Plano Ativo — FlyIop

_Atualizado em 31/07/2026. Contém só o que está em execução ou pendente de aprovação/implementação. Tudo que já foi entregue (com data e decisões tomadas) está em `HISTORICO.md` — referencie por lá em vez de reproduzir aqui._

**Regra de apresentação (24/07/2026):** ao apresentar um plano ou atualização no chat, mostrar só a seção nova/alterada, nunca o arquivo inteiro. Para contexto, referenciar a seção pelo nome (ex.: "ver Parte 8 no HISTORICO.md") em vez de reproduzir. O arquivo completo fica no disco; o chat recebe só o delta. (Ver também `PROTOCOLO-DE-TRABALHO.md`.)

---

## Diagnóstico: caminho de alerta de perna de fim de semana (31/07/2026)

`alert_log` tem 0 registros com `leg_id` desde que a coluna existe
(23/07/2026): o caminho de alerta de PERNA de fim de semana nunca disparou em
produção. Sessão de diagnóstico somente-leitura de 31/07/2026 não encontrou
defeito estrutural — `should_alert` é calculado corretamente, `is_good_price`
funciona, cooldown não bloqueia o primeiro disparo, `insert_weekend_alert_log`
roda logo após o envio sem try/except engolindo erro, `weekend_leg_run_log`
não registra nenhum `outcome = 'error'` nos checks investigados. A aparência
inicial de "oportunidades perdidas" (preços históricos abaixo do teto atual)
era artefato de comparar preço histórico contra o teto de HOJE, não contra o
teto vigente na época do check — `weekend_legs.price_ceiling` não tem
histórico/auditoria (ver pendência (d) abaixo).

### (a) TESTE EM CURSO

Teto elevado manualmente a R$ 2000 em 5 pernas do topo da fila de rotação
(`b4f28800`, `f2bfcf96`, `4a15353d`, `5fd70bb7`, `9c455da7`) e a R$ 500 em
`c3c514ac` — todas com preço observado ~R$ 308-309, bem abaixo de qualquer um
dos dois tetos. Resultado esperado na execução de 01/08/2026: ou chega alerta
de perna no Telegram, ou o caminho está de fato quebrado, com o mapa de busca
já pronto (arquivo:linha de cada portão, ver histórico da sessão de
diagnóstico). **Depois do teste, devolver os tetos aos valores normais.**

### (b) PENDÊNCIA — gatilho `push` no workflow

`.github/workflows/daily.yml` tem `on: push` com filtro de paths (`src/**`,
`requirements.txt`, `daily.yml`). Qualquer commit nesses caminhos roda o
caminho primário completo contra PRODUÇÃO: consome as 20 chamadas de
scraping do dia, grava no Supabase, dispara Telegram, e grava
`last_primary_run_date` — podendo fazer a execução agendada do dia cair em
modo lote-só. Recomendação do chat de planejamento: remover `push`, manter
só `schedule` + `workflow_dispatch`. **Decisão adiada para depois do
resultado do teste de 01/08 (item a).**

### (c) PENDÊNCIA — desenho do alerta (reavaliação fora da coleta)

`should_alert` só é calculado no momento em que a perna é checada. O robô
nunca reavalia um `current_price` já salvo contra um teto novo. Consequência:
editar o teto no site não tem efeito nenhum no Telegram até a perna voltar
na rotação (hoje ~3 dias, ver item 1 do `STATE.md`). Isso afeta diretamente
a recalibração do teto padrão (`STATE.md`, seção 3): baixar o teto não muda
comportamento de alerta até cada perna dar a volta, sem sinal disso em lugar
nenhum. Nunca foi decisão explícita — é herança do código.

Opções levantadas:
- (a) reavaliar todas as pernas ao fim de cada execução primária, custo zero
  de chamadas extras, precisa de trava de frescor.
- (b) editar o teto empurra a perna pro topo da fila de rotação.
- (c) não mexer e documentar o atraso como comportamento esperado.

Inclinação do chat de planejamento: opção (a). **Decisão adiada para depois
de 01/08 (item a).**

### (d) PENDÊNCIA — `price_ceiling` não tem auditoria (entra na Etapa 4)

`weekend_legs.price_ceiling` é sobrescrito a cada edição, sem registro do
valor anterior nem de quando mudou. Consequência: o sistema não consegue
responder "perdi alguma oportunidade?" — foi exatamente o que travou parte
do diagnóstico de 31/07. Como a Etapa 4 da iniciativa multi-usuário
(abaixo) vai criar `weekend_leg_user_state` do zero, é o momento de
resolver; se passar batido, a cegueira é reconstruída e multiplicada por
dois usuários. Escopo sugerido: tabela simples de auditoria (perna, usuário,
teto anterior, teto novo, timestamp). **Revisar no chat de planejamento
antes da Etapa 4.**

### (e) PERGUNTAS ABERTAS do diagnóstico de 31/07 (ainda sem resposta)

- Por que a perna `b4f28800` (return, voo 31/01/2027, `last_live_check_at`
  null, status monitoring) não foi a primeira do lote de 31/07, se a
  ordenação é "nulos/mais antigos primeiro"? (Resposta parcial já obtida
  para o caso específico investigado nessa sessão — a perna citada em outro
  ponto da conversa ficou fora por cair fora da janela de 183 dias, não por
  ordenação — mas vale confirmar se `b4f28800` tem o mesmo padrão.)
- Cache × live: uma perna registrou preço estável por dias via cache e depois
  um valor bem diferente no mesmo dia. Divergência entre fontes ou movimento
  real de preço?
- O alerta de perna pode disparar em cima de preço de CACHE (até 48h de
  atraso)? A mensagem diferencia a fonte, como fazem as rotas flexíveis? Uma
  mesma perna pode ser avaliada duas vezes no mesmo dia (passada de cache +
  lote fli)? `weekend_leg_run_log` sugere que sim.

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

---

## Pendência fora do escopo desta iniciativa (registrada 30/07/2026)

`CLAUDE.md` linha 14 descreve a comparação de preço "avulso vs. pacote"
(ida+volta casado) como funcionalidade ativa, mas `STATE.md` (seção
"Decisões vivas") registra que essa comparação está **suspensa** — não
existe hoje fonte que faça round-trip de forma sequencial (`fli` só faz via
paralelismo, o que fere a regra de scraping). Achado durante a revisão de
consistência de 30/07/2026, ao corrigir a troca `fast-flights`→`fli` nessa
mesma linha (só a nomenclatura foi corrigida, não o conteúdo). Não
corrigido agora — decisão de escopo, não desta iniciativa. Retomar em
ciclo de planejamento próprio.
