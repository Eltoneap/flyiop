# Histórico — FlyIop

_Consolidado em 24/07/2026 a partir de `PLAN-FASE-A.md`, `PLAN-VALIDACAO-CRUZADA.md`, `ALVO-FINS-DE-SEMANA-2027.md` e do plano de trabalho de fins de semana (antes espalhado num arquivo de nome aleatório do Plan Mode). Registro cronológico de investigações, decisões e partes entregues. Trabalho em execução ou pendente: ver `PLANO-ATIVO.md`. Estado atual do produto: `CLAUDE.md`. Decisões de escopo/scraping ainda vigentes: `ROADMAP-AUDITORIA.md`._

---

## 1. Fase A — Qualidade do dado (rotas flexíveis), 16–22/07/2026

_Fonte: `PLAN-FASE-A.md`. Plano original de 7 etapas derivado do `ROADMAP-AUDITORIA.md` (15/07)._

**Etapa 1 (A1) — cliente v3 + comparação paralela.** Pré-passo de rate limit confirmado em 16/07 (v3: 600 req/min, folga enorme pro uso real). `get_prices_for_dates` novo em `travelpayouts_client.py`, chamando `v3/prices_for_dates`. Rodou em paralelo ao v2 por comparação (sem gravar no `price_history`) de 17 a 21/07. `found_at` confirmado ausente na resposta v3 (17/07) — decisão registrada: tratar ausência como esperada da fonte, não como anômala (ver Etapa 6 abaixo).

**Etapa 2 (A2) — portão de frescor.** `freshness_hours`/`stale_alert_policy` em `settings`; alerta com dado velho sai com aviso destacado (`warn`) ou é segurado (`suppress`), nunca silencioso. `found_at` ausente = tratado como velho.

**Etapa 3 (A3) — cooldown/deduplicação de alertas — ✅ executada 22/07/2026.** Tabela `alert_log` nova (RLS); `realert_drop_pct`/`realert_days` em `settings`; só reenvia se caiu o suficiente ou passou tempo suficiente desde o último alerta da rota.

**Etapa 4 (A5 parte 1) — autocheck estatístico anti-preço-fantasma — ✅ executada 22/07/2026.** `is_suspicious_price` em `rules.py`: preço >50% abaixo da média 30d (com histórico mínimo) vira suspeito — grava normalmente no histórico, mas não dispara alerta, com nota explicando.

**Etapa 5 (A4) — janela dupla de monitoramento (curta/longa).** Motivada por preços "pulando de mês" nos dados reais de 17–21/07 (ex.: BSB→GIG mudou de 27/11→21/11→18/09 em poucos dias). Desenho completo (colunas `monitor_short`/`monitor_long`, `window` no histórico, limiares próprios por janela) ficou registrado no plano, mas a decisão do usuário em 22/07 foi pivotar pro modelo de **datas fixas por fim de semana** (ver seção 3 abaixo) — a motivação original da janela dupla (histórico misturando datas de viagem diferentes) deixa de existir com datas fixas, então esta etapa não foi implementada.

**Etapa 6 (A1 parte 2) — corte pro v3 — ✅ executada 21/07/2026.** 5 dias de comparação paralela: preço idêntico em 100% das observações nas rotas com cobertura (BSB→GIG, GIG→BSB). v3 virou fonte oficial do `price_history`; `get_month_matrix` (v2) mantido no cliente por 1 versão como rollback. Mensagem de frescor ajustada: ausência de `found_at` na v3 vira `ℹ️ Fonte com cache de até 48h` em vez de `⚠️ Dado antigo`. Salvaguarda: idade desconhecida nunca suprime alerta. 27 testes locais verdes.

**Etapa 7 (A5 parte 2) — confirmação pontual (2ª consulta, mesma fonte Travelpayouts).** Desenhada (consulta extra com data exata no momento do alerta, selo `✅ confirmado`), mas superada pela decisão de 18/07 de usar uma fonte **independente** (Google Flights) em vez de uma segunda consulta na mesma fonte — ver Etapa 8 e o pivô da seção 4.

**Fora desta fase:** heatmap, percentil, calculadora de milhas, melhor antecedência de compra, ANAC, câmbio, ML — só começariam com novo Plan Mode.

---

## 2. Validação cruzada + revisão da regra de scraping, 18/07/2026

_Fonte: `PLAN-VALIDACAO-CRUZADA.md`, complemento ao PLAN-FASE-A.md._

**Regra de scraping revisada (18/07/2026):** consulta a fonte não-oficial (scraping) passa a ser permitida quando **todas** as condições valerem: (1) volume mínimo — só no evento de alerta, nunca na varredura diária, no máximo 1 consulta extra por alerta; (2) best-effort — falha nunca bloqueia nem atrasa o alerta; (3) sem evasão ativa — nada de proxy, spoofing, CAPTCHA, burla de login; (4) fonte degradável — sistema funciona idêntico se a fonte sumir; (5) validação prévia obrigatória (Etapa 0). Racional: a Etapa 7 valida contra a mesma fonte (Travelpayouts); uma fonte independente (Google Flights) adiciona sinal genuinamente novo, com risco aceitável só sob essas 5 condições.

> Nota de autoridade entre documentos (21/07/2026): a cláusula original "em caso de conflito, o VALIDACAO-CRUZADA prevalece" foi revogada — nenhum arquivo tem mais autoridade automática de escopo; decisões de escopo exigem aprovação explícita no chat de planejamento.

**Etapa 0 — validação do fast-flights (18/07/2026).** Script `scripts/validate_fastflights.py` (fora de `src/`, não dispara `daily.yml`). Local: 2/3 rotas com preço (BSB→GIG R$638, GIG→BSB R$757; RIA→BSB sem cobertura, erro de parser consistente com "sem resultado", não bloqueio). GitHub Actions (`validate_fastflights.yml`, `workflow_dispatch` only): 2/3 rotas também, mais rápido que local (0,5s) — runner **não bloqueado**. Critério de aprovação (≥2/3 rotas em ≥3/4 execuções) batido já nas 2 primeiras execuções. Versão validada: `fast-flights==3.0.2` (API mudou da 2.x: sem `fetch_mode`, usa `create_query`+`get_flights`; aceita `currency`/`language` nativamente; packaging não declara `typing_extensions`, corrigido no requirements). **Decisão: aprovado.**

**Etapa 8 — selo de fonte independente no alerta.** Desenhada (`src/independent_check.py`, `check_google_flights`, comparação ±30%, selo `🔎 Google Flights` ou `divergente`) mas nunca implementada como etapa própria — superada pelo pivô de 22–23/07 (fim de semana como alvo, fast-flights virando fonte primária das pernas em vez de confirmação pontual de rotas flexíveis; ver seção 4).

**Roadmap consolidado B/C/D (datas-alvo, planejado 18/07/2026) — nunca executado, superado pelo pivô.** Fase B (gráfico Plotly, heatmap, melhor antecedência, percentil), Fase C (datas fixas + bot em linguagem natural via Claude Haiku), Fase D (sazonalidade ANAC, experimento VPN, previsão simples) — todo esse roadmap foi escrito ainda no modelo de "rotas flexíveis" como produto principal. A decisão de 22/07 (pivô pro alvo de fins de semana) tornou esse roadmap obsoleto antes de qualquer item começar. O backlog atual e realista vive em `CLAUDE.md`.

---

## 3. Pivô: alvo de fins de semana RIO→BSB 2027, 22/07/2026

_Fonte: `ALVO-FINS-DE-SEMANA-2027.md`. Primeira versão do pivô — depois redesenhada (seção 4) para 66 fins de semana 2026-2027 com pernas desacopladas._

Redefinição do objetivo prático: comprar passagem para (quase) todos os fins de semana de 2027, ida RIO→BSB sexta, volta domingo ou segunda, monitorando cada fim de semana individualmente. Desenho original: ~45 fins de semana (29/01 a 03/12/2027), tabela `weekend_targets` com `outbound_date`/`return_date` únicos por alvo, teto default R$400, varredura diária de todos os alvos `monitoring`, alerta de teto + alerta de oportunidade relativa + resumo semanal, painel de compras com tabela e botão "marcar comprado". Esse desenho (RIO como código de cidade agregando GIG+SDU, alvo único ida+volta por fim de semana) foi **substituído** em 23/07/2026 depois que a Parte 2 do redesenho (seção 4) mostrou cobertura de cache insuficiente com esse modelo — motivou o desacoplamento em pernas independentes.

---

## 4. Redesenho: pernas desacopladas + fast-flights em lote, 23–24/07/2026

_Fonte: plano de trabalho de fins de semana (Plan Mode), consolidado aqui._

### Contexto e decisão

Com RIO agregado (GIG+SDU) e ida+volta como evento único, a cobertura real ficou quase zerada (2 entradas de 66 alvos no run de 23/07). Diagnóstico: cache de buscas com código de cidade genérico é mais raro que aeroportos específicos, e exigir os dois trechos baterem juntos multiplica a raridade. Decisão: desacoplar ida e volta em 132 "pernas" independentes, consultar GIG e SDU separadamente por busca one-way, complementar com lotes rotativos de `fast-flights` (Google Flights).

### Modelo de dados

`weekends` (66 linhas, sexta 04/09/2026 a sexta 03/12/2027) + `weekend_legs` (132 linhas, 2 por weekend: `direction`, `price_ceiling` default 200, `status`, `current_price`/`airport`/`variant`/`source`, `lowest_seen`, `last_live_check_at`, `purchased_at`, `notes`, depois `paid_price` — ver `PLANO-ATIVO.md`) + `weekend_leg_price_history` + `weekend_leg_run_log` + `alert_log.leg_id`. Tabelas antigas (`weekend_targets` etc.) dropadas — zero dado real perdido.

### Partes entregues

- **Parte 1 (23/07) — ✅** SQL do schema novo completo (tabelas + seed + settings).
- **Parte 2 (23/07) — ✅** `weekends.py` reescrito pra busca one-way GIG+SDU por perna. **Veredito real de produção: cache Travelpayouts insuficiente, 2 de 132 pernas** — motivou a Parte 3 redesenhada.
- **Parte 3 redesenhada (23/07) — ✅** fast-flights vira fonte primária das pernas (não mais só confirmação pontual). Janela deslizante de 6 meses (~42-52 pernas elegíveis por vez, platô calculado); lote de 20/dia cobre em 2-3 dias. Rotação por `last_live_check_at` (nunca checada primeiro), desempate por proximidade de data e distância ao teto. GIG primeiro, SDU só se GIG vazio (limitação aceita: SDU mais barato pode passar despercebido). Detector de bloqueio: ≥5 falhas seguidas OU taxa de sucesso <50% (amostra ≥8) — para o lote e avisa no Telegram, nunca contorna. Kill-switch `settings.fast_flights_enabled`. Espaçamento ~2,5s, sequencial, sem paralelismo. Arquivos: `src/live_check.py` (novo), `evaluate_and_record_leg_price` extraída em `weekends.py` pra reuso entre cache e live. Revisão de escopo registrada no `ROADMAP-AUDITORIA.md` (regra do A5 revisada: lote diário limitado autorizado, além da confirmação pontual).
- **Parte 4 — confirmação de pacote no alerta — desenhada, depois suspensa.** Ver seção 6 (Parte 7) — suspensa em 24/07 por falta de fonte round-trip sequencial confiável.
- **Parte 5 (24/07) — ✅** Painel `docs/compras.html` + `docs/js/compras.js`. Cards por fim de semana (não tabela), ordenação puramente temporal por `outbound_date` (nunca por preço — sinal de alerta não deve ser escondido). Badge de status por perna (Monitorando/Comprada), teto editável por perna + aplicar a todos com confirmação específica (não `confirm()` genérico), botão Comprei/Desfazer, abas Ativos (≥1 perna não comprada) / Comprados (as 2 compradas) — nenhum card some de Ativos por falta de preço. Indicador de progresso (X/132 pernas, Y/66 weekends).
- **Parte 5b (24/07) — ✅** Configurações reorganizada em duas seções ("Rotas flexíveis (legado)" vs "Fins de semana RIO↔BSB"), expondo o kill-switch `fast_flights_enabled` e `fast_flights_daily_batch_size` na UI pela primeira vez (antes só via SQL direto).
- **Parte 6 (24/07) — ✅** Nota de revisão de escopo no `ROADMAP-AUDITORIA.md` (item A5) documentando o lote diário como uso adicional autorizado do fast-flights.

### Ajustes de UX no painel de Compras (24/07)

Campo de notas por perna (localizador, horário) — mesmo padrão blur+salvar do teto. Favicon/apple-touch-icon novos (avião de papel) substituindo o ícone genérico "F" do iOS; emoji ✈️ do cabeçalho trocado por SVG minimalista. Correção de dois bugs visuais mobile: `.leg-row-main` sem `flex-wrap` causava overflow horizontal com título/preço longos (corrigido); `nav` sem `flex-wrap` cortava "Sair" em telas estreitas (corrigido, com breakpoint em 480px). Renomeação de `escopo-projeto-passagens.md` para `CLAUDE.md` (lido automaticamente pelo Claude Code) com conteúdo atualizado pro estado real do projeto.

Depois: horário da última checagem por perna ("atualizado há Xh"/"nunca verificado", de `last_live_check_at`) e link "Ver/comprar" por perna, abrindo o Google Flights pré-filtrado pra aquela busca exata.

---

## 5. Bug de preço do fast-flights + migração pra fli, 24/07/2026

### Descoberta

Perna "Ida (sex) 22/01, GIG→BSB" mostrou R$561 no painel (fonte live); o Google Flights mostrava R$286-346 pra mesma busca one-way. Investigação em duas frentes.

**Frente 1 — link "Ver/comprar" abria em ida-e-volta por padrão (bug real, corrigido).** `google_flights_link` (`src/links.py`, reusado em `docs/js/compras.js`) montava a URL sem instrução explícita de one-way; testado ao vivo, o Google assume ida-e-volta por padrão nesse caso. Fix: acrescentar `"one way"` no texto da query quando não há `return_date`.

**Frente 2 — preço gravado pelo `check_live_price` também estava errado (achado mais sério).** Parâmetros da consulta confirmados corretos (`trip="one-way"`, protobuf `Trip.ONE_WAY`, sem `return_date` nenhum). Três hipóteses baratas testadas e descartadas: `fetch_mode` (não existe nem em `fast-flights==3.0.2` nem em `faster-flights==3.7.0`), `language`/`currency` (já explícitos), upgrade de versão (mesmo R$561, cookie de consentimento novo não mudou nada). Causa raiz encontrada capturando o HTTP cru: a lib lê um bloco JSON (`AF_initDataCallback` `ds:1`) embutido no HTML que o Google Flights serve — payload que diverge do que a interface real renderiza (confirmado: R$286 aparece como HTML visível real, `aria-label="286 Reais brasileiros"`, fora de qualquer `<script>` — não é questão de JavaScript não ter rodado, é que `ds:1` é um payload diferente do que popula os cards reais). Bug estrutural de parsing, não de configuração.

### Migração pra `fli`

`fli` (github.com/punitarani/fli) acessa o endpoint interno `GetShoppingResults` do Google diretamente (o mesmo RPC que o JS da página chama), sem parsing de HTML. Testado com `fli` real: lista completa e corretamente ordenada, R$286 em primeiro, R$561 aparecendo corretamente mais abaixo como opção mais cara — bate com o navegador.

**Migração aprovada e implementada em 24/07/2026:**
- `src/live_check.py`: `check_live_price` migrado pra `fli`, assinatura e formato de retorno preservados (`check_and_evaluate_leg`, `select_batch`, `run_daily_batch` — kill-switch e detector de bloqueio — intocados).
- `build_package_comparison` **suspensa** (retorna `None` sempre): `fli` só faz round-trip via expansão em threads paralelas, o que viola a regra de sempre do projeto (sequencial, sem paralelismo). Comparar "avulso" correto (fli) contra "pacote" sabidamente impreciso (fast_flights) seria pior que não comparar. Reativar exige uma fonte round-trip sequencial compatível — não existe hoje. Mitigação: o link "Ver/comprar" por perna permite alternar pra ida-e-volta manualmente.
- `requirements.txt`: `fli` pinado num commit específico do GitHub (`121d34fea056dc513258958c4262cb5a4cc033c1`, não `@main` — projeto não publica no PyPI sob esse nome; requirement usa o nome real do metadata, `flights`, senão o pip rejeita por nome divergente). `fast-flights==3.0.2` mantido por 1 ciclo de release só pra rollback rápido (mesmo padrão do corte v2→v3).
- `docs/config.html`: rótulos da UI atualizados no mesmo commit ("Consulta de preço ao vivo (Google Flights)" em vez de "Fast-flights ativo"), sem mencionar a comparação de pacote suspensa. Nomes de coluna no banco inalterados.
- 120 testes locais passando (mock). Smoke test real confirmou `check_live_price('GIG','BSB','2027-01-22')` retornando R$286.
- **Confirmado em produção 24/07/2026:** `daily.yml` run #33 (commit `4db8f38`) passou com sucesso. Run diário seguinte: **20/20 pernas checadas, 20 com preço**, incluindo `[perna outbound 2027-01-22] R$ 286.00 (GIG, live)` — a mesma perna que motivou a investigação, agora com o preço correto.

### Higiene de dado

**Preços `source='live'` gravados antes de 24/07/2026 são suspeitos** (não usar pra calibrar teto nem pra análise futura de melhor antecedência de compra) — não apagar, é histórico real do que o robô viu. A partir de 24/07/2026, `source='live'` é confiável. Preços `source='cache'` (Travelpayouts) nunca foram afetados por esse bug. A rotação natural do lote diário (ordenada por `last_live_check_at`) re-checa e substitui os valores suspeitos nos primeiros 2-3 dias após a migração.
