# STATE.md — FlyIop

> Atualizado em: 20/11/2026
> Última sessão: Claude Code (19/11/2026, investigação só-leitura +
> documentação) — **incidente de 06-18/11/2026: workflows agendados
> desativados pelo GitHub por 60 dias sem commit** (reativados manualmente
> pelo usuário em 18/11; cron confirmado de volta por run agendado em 19/11;
> 24 disparos perdidos; buraco em `weekend_radar_precision_log` em cima da
> faixa de 30-60 dias das pernas de fim de ano). Primeiro run agendado pós-
> reativação (19/11) pegou o `fli` bloqueado — em observação, sem ação.
> STATE/PLANO-ATIVO saneados (Fatia 2 do radar em produção desde 05/09, D3
> com SQL executado, D4 concluída) e seção 3 trocada pela fila nova de 7
> itens. Detalhe em `HISTORICO.md` item 28.
>
> **Sessões anteriores (01/08 a 05/09/2026):** o diário completo que ficava
> aqui foi movido, sem edição, para o `HISTORICO.md`, seção "Anexo — Diário de
> sessões do STATE.md".

---

## 1. Status atual

FlyIop está em produção, monitorando 66 fins de semana (132 "pernas" ida/volta independentes) na rota RIO↔BSB entre set/2026 e dez/2027. A fila real de rotação do lote `fli` é bem menor que 132, e **depende do estado do radar e varia dia a dia** — não existe um número fixo (o "43 pernas elegíveis" medido em 31/07/2026 desatualizou por dois motivos independentes: a janela desliza com a data, e o radar mudou a própria regra de elegibilidade). Sobre as 132 pernas do seed: com `radar_enabled=false`, elegível = dentro de `LIVE_CHECK_WINDOW_DAYS` (183 dias) = **52 pernas** (número geométrico, estável enquanto o seed não muda). Com `radar_enabled=true`, **87 pernas** têm data dentro do teto da fonte (305 dias) — mas quantas dessas efetivamente entram no lote como refresh de metadado num dia específico depende de `last_live_check_at` (só entra a que não foi checada nos últimos `RADAR_METADATA_REFRESH_DAYS` = 7 dias) e por isso oscila; produção real em 01/09/2026 mostrou 69 elegíveis naquele dia, não 87. O número estável é o das **45** pernas além dos 305 dias, que não entram em consulta ao vivo nenhuma, ponto (`HISTORICO.md` item 25) — não um tempo de volta completa da fila, que também passou a depender do estágio de frequência automática (1x/2x/3x por dia) e não tem mais um valor único fixo como o "~3 dias" antigo. Fonte primária de preço é a `fli` (endpoint interno do Google Flights, migrada de `fast-flights` por bug de parsing), com Travelpayouts como cache secundário — desde a Parte 9 (28/07/2026), a `fli` também grava companhia aérea e horário de partida. Cada perna expira da rotação de forma independente pela própria data (D+1 de margem), não mais pela data de ida do weekend inteiro — corrigido bug que cortava a perna de volta 2-3 dias antes da hora. A margem D+1 só mantém a perna na lista: desde 19/11/2026 nenhuma data anterior a hoje (BRT) vira consulta `fli` nem avaliação de cache (`HISTORICO.md` item 31). Desde a Parte 10 (28/07/2026), a frequência do lote `fli` escalona automaticamente em 3 estágios (1x/2x/3x por dia) conforme dias consecutivos sem bloqueio, com reversão imediata pro Estágio 0 em qualquer bloqueio detectado e teto automático no Estágio 2 — só a **primeira execução do dia** (não mais uma hora fixa — corrigido em 30/07/2026, ver item 15 do `HISTORICO.md`) roda rotas flexíveis/cache Travelpayouts/notificações, as execuções extras do mesmo dia só rodam o lote `fli`. Robô via GitHub Actions grava no Supabase (**cron restaurado para 2x/dia (08h/20h BRT) em 03/08/2026** — havia sido reduzido pra 1x/dia em 29/07/2026 enquanto se confirmava a correção do bug de agendamento; ver a fila arquivada em `HISTORICO.md` item 28, item 1; **pausado de 06/11 a 18/11/2026** pela desativação automática dos workflows por inatividade — `HISTORICO.md` item 28; decisão de rodar em Python); alertas via bot Telegram (FlyIopBot); site em GitHub Pages com 3 páginas (Dashboard, Compras, Configurações), login via Supabase Auth. Painel de Compras já tem: cards por fim de semana, teto editável por perna, campo de notas (localizador/horário), campo de valor pago, filtros (chips), selos de feriado/alta temporada, estado visual salvo/não-salvo/em-edição (âmbar), hierarquia visual por preço/status (perna comprada com identidade forte, card 2/2 colapsando por padrão com total pago). Dashboard redesenhado (ação do dia, urgência, progresso, oportunidades, orçamento, saúde do sistema); progresso/orçamento contam só a partir do fim de semana de 29/01/2027, oportunidades separadas em "abaixo do teto" (ação) e "mais baratas no momento" (informação). Alerta de bloqueio do scraping agora é rico e escalona por dias consecutivos. As 3 rotas flexíveis antigas (BSB→GIG, GIG→BSB, RIA→BSB) continuam rodando em paralelo, tratadas como legado.

## 2. Decisões vivas

- **Grade de calendário (`fli.search.dates.SearchDates`) validada com sucesso
  em produção — Etapa 0, 24/08/2026.** Devolve o mesmo preço que a consulta
  pontual atual (`SearchFlights`), 0,0% de diferença. **Propriedade conhecida
  do sistema, não bug:** a lib não busca além de hoje+305 dias — degrada pra
  lista vazia, sem erro; datas além disso ainda não foram abertas pra venda
  por nenhuma companhia, em nenhuma fonte. Detalhe completo em `HISTORICO.md`,
  item 24.
- **Radar de calendário (Fatia 1) — EM PRODUÇÃO, `radar_enabled=true`.**
  Correção anterior desta seção: dizia "NÃO ATIVADO EM PRODUÇÃO" e SQL "NÃO
  RODADO" — desatualizado, contradizia a seção 1 (acima) e `HISTORICO.md`
  item 25, que já registrava o radar ligado e 6 execuções reais em produção
  desde ~29/08/2026. A arquitetura de dois níveis decidida a partir do
  achado da Etapa 0 (RADAR — `SearchDates`, varre ~305 dias, fatiado
  manualmente em blocos <=61 dias, sequencial e espaçado; PRECISÃO —
  `SearchFlights`, só nas datas que o radar apontar perto do MAIOR teto entre
  usuários, e sempre ela quem vira alerta) está rodando: `src/radar_check.py`,
  filtro de regime em `src/live_check.py:select_batch` (`batch_regime`),
  `suppress_alert` em `src/weekends.py:evaluate_and_record_leg_price`
  (refresh de metadado nunca avalia teto), step em `daily.yml` antes de
  `main.py`. Schema (`sql/radar_calendario.sql`, 3 colunas em
  `system_config` + tabela `weekend_radar_grid`) rodado em produção. Detalhe
  completo em `HISTORICO.md`, itens 24 e 25.
- **Radar de calendário (Fatia 2) — preço na tela + persistência da
  comparação — ✅ EM PRODUÇÃO desde 05/09/2026 (commit `e0c45a6`,
  04/09/2026 22:05 BRT; SQL executado antes do código).** Correção de
  19/11/2026: esta entrada dizia "implementado localmente, pendente de
  commit/push e de SQL" — desatualizado; o primeiro run após o commit (05/09
  13:35 UTC) já gravou `radar_price` em 87 pernas sem erro 400 (`HISTORICO.md`
  item 28). Fecha o gargalo que a Fatia 1 deixou registrado
  (`HISTORICO.md` item 25): o radar descobria preço em ~88 pernas por
  varredura, mas só as 7-10 candidatas de precisão chegavam a
  `weekend_legs.current_price` — a maioria das pernas na aba Compras mostrava
  preço de 2-3+ dias. Agora `weekend_legs.radar_price`/`radar_price_at`/
  `radar_airport` são gravados pra TODA perna dentro do alcance, em
  `main.py`, ANTES do laço de precisão, reusando a mesma leitura de grade —
  zero consulta nova ao Google. `current_price_at` (coluna nova) corrige o
  rótulo "atualizado há Xh" da aba Compras, que até aqui lia
  `last_live_check_at` (idade da última TENTATIVA, não do preço).
  `weekend_radar_precision_log` (tabela nova) persiste a comparação
  radar×precisão pro checkpoint de reavaliação de 01/12/2026 (ver
  `PLANO-ATIVO.md`). **Disparo de alerta não muda**: `current_price`/
  `current_price_at`/`lowest_seen`/`weekend_leg_price_history` continuam
  exclusivos do caminho confirmado — verificado por teste dedicado. Aba
  Compras (só ela, não o Dashboard) mostra o preço mais recente entre radar
  e confirmado, sempre com rótulo "não confirmado" quando for do radar, e o
  confirmado mais antigo nunca some da tela. 348 testes locais passando (319
  antes desta fatia). **Lacuna de dado:** `weekend_radar_precision_log` não
  recebeu linhas de 06/11 a 17/11/2026 (workflows desativados por
  inatividade — `HISTORICO.md` item 28). Detalhe completo em `HISTORICO.md`, item 26, e
  `PLANO-ATIVO.md`, seção "Radar de calendário — Fatia 2".
- **Limitação conhecida e não corrigida: `Airport.RIA` não é utilizável com a
  versão pinada da `fli`.** `Airport.RIA` é alias silencioso de `Airport.AJU`
  (Aracaju, cidade diferente) na tabela de aeroportos da lib — qualquer
  consulta por "RIA" na prática busca Aracaju, sem erro. Achado na Etapa 0
  (24/08/2026); não afeta produção hoje (RIA→BSB já não tinha cobertura desde
  18/07/2026, por motivo então não diagnosticado — ver `HISTORICO.md`, item 1).
  Corrigir exige patch local ou reportar upstream; sem decisão de fazer isso.
- **Fonte de preço primária: `fli`, não `fast-flights`.**
  Motivo: `fast-flights` lia um payload SSR do Google que divergia do preço real (confirmado com bug de quase 2x); `fli` acessa o endpoint interno diretamente e bate com o navegador real.
- **Modelo de dados: pernas desacopladas (ida e volta compradas/monitoradas independentemente), não pacote casado.**
  Motivo: mercado doméstico não dá desconto por casar ida+volta; cache/scraping tem mais cobertura em busca one-way; usuário quer comprar cada perna assim que ficar boa, sem esperar a outra.
- **Comparação de preço em pacote (avulso vs. round-trip) está SUSPENSA.**
  Motivo: não existe hoje fonte que faça round-trip de forma sequencial (fli só faz via paralelismo, o que fere a regra de scraping). Reativar só se surgir fonte compatível.
- **Scraping: sempre sequencial, sem paralelismo, sem evasão/proxy/spoofing.** Se bloquear, a resposta é recuar e avisar — nunca contornar. Kill-switch manual + detector de bloqueio automático sempre presentes em qualquer fonte de scraping.
- **Nenhum arquivo do repositório tem autoridade para revisar regra de escopo sozinho** — só decisão explícita no chat de planejamento. (Origem: incidente com um arquivo de plano de autoria não esclarecida que tentou se autoatribuir precedência; resolvido e revogado.)
- **Documentação do projeto tem três arquivos com papéis exclusivos, sem sobreposição** (regra completa registrada no `PROTOCOLO-DE-TRABALHO.md`, 27/07/2026): `STATE.md` (orientação de alto nível — este arquivo), `PLANO-ATIVO.md` (plano técnico detalhado só da Parte em execução agora, vazio quando nada está ativo) e `HISTORICO.md` (arquivo morto de tudo já entregue, cronológico). Mais `CLAUDE.md` (escopo geral) e `PROTOCOLO-DE-TRABALHO.md` (como trabalhamos). Ao apresentar plano/atualização no chat, mostrar só a seção nova/alterada ou um resumo curto pedindo aprovação — nunca o arquivo inteiro.
- **Compra de passagem nunca é automatizada.** Sem dados de cartão armazenados, sem emissão via API.
- **Janela deslizante de monitoramento ao vivo: ~6 meses**, ~20 pernas/dia no lote de scraping, rotação por `last_live_check_at`.
- **Janela de compra real começa em 29/01/2027** (decisão de 28/07/2026, chat de planejamento). Fins de semana antes disso (set/2026–jan/2027) são monitorados intencionalmente e nunca serão comprados — são a fonte de dado mais valiosa do projeto hoje (histórico de preço, teste de ferramentas, curva completa até ~180 dias de antecedência) e não devem ser removidos da rotação por economia de chamadas. Progresso e orçamento do Dashboard devem contar só a partir de 29/01/2027. Antecedência máxima de interesse para compra: 180 dias — a janela deslizante de ~6 meses está correta em princípio, desde que ande de fato com o tempo.
- **Escalonamento automático de frequência do lote `fli`, Estágio 0→1→2** (decisão de 28/07/2026). Sobe 1 estágio após 5 dias consecutivos sem bloqueio; qualquer bloqueio derruba pro Estágio 0 na hora e reseta a contagem; teto automático é o Estágio 2 (3x/dia) — não sobe sozinho além disso sem aprovação explícita no chat. Toda mudança de estágio avisa no Telegram. Só a **primeira execução do dia** roda rotas flexíveis/cache Travelpayouts/notificações de rotas/resumo semanal — execuções extras do mesmo dia só rodam o lote `fli`, pra não triplicar consumo da Travelpayouts sem necessidade.
- **Decisão de "primeira execução do dia" é por estado gravado (`last_primary_run_date`/`last_batch_run_date`/`batches_run_today` em `bot_state`), não por hora BRT exata** (correção de 30/07/2026, ver item 15 do `HISTORICO.md`). Motivo: o cron do GitHub Actions não garante disparo na hora exata — um atraso bastava pra cair fora de todos os horários esperados e zerar a execução inteira (rotas, cache, lote `fli`, gravação de estado), silenciosamente, com exit 0. Confirmado em produção (run #43, 30/07/2026): `weekend_scrape_last_primary_run_date`/`weekend_scrape_last_batch_run_date` gravados pela primeira vez desde que essas chaves existem.
- **Config de sistema (`suspicious_below_avg_pct`, `fast_flights_enabled`, `fast_flights_daily_batch_size`) vive em `system_config`, linha única sem dono — não em `settings`** (Etapa 3 multi-usuário, concluída e **confirmada em produção 30/07/2026** — a implementação foi commitada/pushada em 29/07/2026, mas só rodou de fato depois da correção do bug de agendamento acima, que afetava a mesma execução). Motivo: essas 3 colunas já eram tratadas como globais pelo backend mesmo `settings` sendo per-user — risco real de um segundo usuário sobrescrever o kill-switch ou o limiar de suspeita de todo mundo sem perceber. Edição é 100% manual via SQL Editor do Supabase agora (sem UI, sem policy de update liberada) — procedimento em `RUNBOOK.md`. As 3 colunas antigas continuam em `settings`, intocadas e sem uso (Etapa 3b de remoção fica para depois de alguns dias de produção estável).
- **Teto padrão (`settings.weekend_default_ceiling`) recalibrado de R$250 para R$300 em 04/08/2026** — decisão do usuário via painel (botão "Salvar meu teto padrão"), confirmada no chat de planejamento na mesma data. Motivo: dado real recente mostrava pernas a R$242–248, ou seja, o R$250 antigo estava colado demais no preço real, sem margem. **A gravação de 04/08 não persistiu** (auditoria de `weekend_leg_ceiling_audit` mostra sequência de saves na mesma sessão, 250→300→310→250, terminando em 250 — não um bug de gravação/RLS, o próprio usuário regravou por cima). **Corrigido manualmente em 05/08/2026** (novo save de 300, auditoria com linha única 250→300). **Verificado em produção em 06/08/2026**: execução real do robô (20/20 pernas checadas) registrou todas as 22 ocorrências de teto no log em R$300, nenhuma em R$250 — fecha o ciclo aberto pelo incidente de gravação.
  - **A gravação de 04/08/2026 não persistiu como 300 na primeira tentativa.** `weekend_leg_ceiling_audit` mostra sequência de saves na mesma sessão (250→300→310→250), terminando em 250 — não um bug de gravação/RLS, e sim a última ação da sessão ter sido um valor diferente do pretendido. Só descoberto em 05/08/2026, durante a verificação de produção das pendências 6/7/8/9 (abaixo): o robô comparava corretamente com o teto efetivo, mas o teto efetivo em si era 250, não 300 — a fila de pernas na faixa R$250–300 continuou sem alertar por mais um dia. **Corrigido manualmente em 05/08/2026** (novo save de 300 no painel, confirmado via `weekend_leg_ceiling_audit` com linha única `250→300`).
  - **✅ RESOLVIDO (24/08/2026) — o DEFAULT continua R$300; o que varia são
    overrides por perna, uso legítimo do painel.** Leitura direta de
    `weekend_leg_ceiling_audit` (histórico completo, `scope`/`origin`
    presentes) confirmou: a última linha `scope='default'` do Elton segue
    sendo `250→300` em 05/08/2026 (nunca mais tocada); a única linha
    `scope='default'` do Gustavo é `null→300` em 16/08/2026 via `sql_editor`
    (a própria E7-2, FECHADA-1) — **os dois defaults batem exatamente com o
    documentado, sem mudança silenciosa.** O que mudou foi **por perna**, via
    painel (`origin='app'`, `changed_by` = o próprio usuário): Elton elevou 8
    pernas específicas para R$500 em 15-16/08 — todas próximas do início da
    janela de compra (29/01-14/02/2027), consistente com priorização manual
    do que pretende comprar em breve, já que o preço real (~R$316-350) estava
    perto demais do teto de R$300; Gustavo fez o mesmo em 18/08 e 24/08 (3
    pernas em R$500, 1 em R$400). **Não é bug, não é pendência** — é o
    mecanismo de override por perna (Etapa 4.2) funcionando como projetado,
    só não tinha sido observado em uso real até esta leitura. Detalhe
    completo (todas as linhas, com data e valor) na "PERGUNTA" correspondente
    na seção 4 (Bloqueios), agora fechada.
- **DECIDIDO (chat de planejamento, 11/08/2026): o Telegram passa a respeitar a janela de compra (fins de semana ≥ 29/01/2027) nos dois caminhos onde hoje não respeita.**
  - **(a) Alerta de oportunidade** (`weekend_opportunity_pct`) — hoje dispara por queda percentual contra a média histórica, independentemente do teto e da janela de compra. Passa a disparar só para pernas de fins de semana ≥ 29/01/2027.
  - **(b) Resumo semanal** ("Resumo semanal — pernas RIO↔BSB") — as duas listas ("Mais baratas agora" e "Mais próximas") passam a considerar só pernas ≥ 29/01/2027, e o denominador do contador ("X de N pernas compradas") deixa de ser 132 fixo e passa a contar só as pernas dentro da janela de compra — mesma regra que o Dashboard já usa pra progresso/orçamento desde 28/07/2026 (não hardcodar um número novo; confirmar o valor real na implementação, não estimar agora).
  - **Motivo:** fins de semana anteriores a 29/01/2027 são monitorados intencionalmente como fonte de histórico de preço (decisão de 28/07/2026) e nunca serão comprados; alertar/contabilizar sobre eles só polui o canal.
  - **Evidência observada (10-11/08/2026, resumo semanal e alerta reais):** "Mais baratas agora" listou 9 de 10 pernas anteriores a 29/01/2027 (só a de 29/01/2027 ida estava dentro da janela); "Mais próximas" listou as 10 pernas fora da janela (09/10/2026 a 04/12/2026, 100% fora); alerta de oportunidade recebido pro fim de semana de 25/12/2026, 19,6% abaixo da média (R$425,00 contra teto R$300) — fora da janela.
  - **Inconsistência que esta decisão corrige:** o Dashboard já conta progresso/orçamento só a partir de 29/01/2027; o Telegram contava as 132 pernas inteiras — os dois respondiam a mesma pergunta com números diferentes.
  - **✅ IMPLEMENTADA E PUBLICADA (Fatia D1, 12/08/2026, commit `757ab3e`).** Passou a fazer parte da Etapa 6, fatiada em D1-D4 (`PLANO-ATIVO.md`, seção "Etapa 6") — esta decisão (a+b) é a fatia D1, já em produção. SQL rodado e verificado pelo usuário em 12/08/2026 (todos os blocos batendo com o esperado). **Verificação de produção segue em andamento até 17/08/2026** (segunda-feira, resumo semanal real) — detalhe completo, incluindo o que falta confirmar, em `PLANO-ATIVO.md`, "Etapa 6" → "Fatia D1".
- **INVESTIGAÇÃO (chat de planejamento, 12/08/2026) — silêncio recente do
  Telegram, causa identificada: preço acima do teto, não perda de alerta.**
  Motivada pelo usuário notar poucas mensagens recentes. Diagnóstico read-only
  sobre 14 dias de produção (30/07–12/08/2026), 435 checagens com preço:
  - **Teto de R$300 nunca foi tocado — zero hits em 14 dias**, confirmado
    por duas medições independentes (contagem diária e busca direta por
    preço ≤ teto no histórico). Preço mínimo observado: R$304 em 04/08;
    desde 05/08 travado em R$334. Não há alerta de teto perdido porque não
    houve alerta de teto possível.
  - **32 alertas reconstruídos como devidos (pré-cooldown) contra 30
    enviados** no período — método validado por bater exatamente com o
    "6 de 13 orgânicos" já registrado para 01/08. Diferença residual (~8,
    de 02/08 em diante) é supressão por cooldown funcionando por desenho
    (`realert_days=1`, mais permissivo que o valor default documentado),
    não confirmada linha a linha.
  - **Zero casos de cooldown sem tipo colidindo** (alerta de oportunidade
    segurando alerta de teto ou vice-versa) — porque nunca houve hit de
    teto para colidir. O bug em si (alert_log sem coluna de tipo de
    alerta) segue real no código e é escopo da Fatia D2, mas não produziu
    perda observável neste período — só se manifestaria no momento de um
    primeiro hit de teto.
  - **Taxa de no_data de 85% (registrada em 02/08/2026) veio inteiramente
    do cache Travelpayouts** (que erra ~98% por desenho, conferidor
    secundário desde a Parte 2) — não do lote `fli` (fonte primária),
    que ficou em ~0% de falha em 13 dos 14 dias. Corrige a leitura anterior
    que tratava a taxa agregada como possível sinal de problema.
  - **Achado lateral confirmado, não solicitado:** bloqueio isolado
    detectado em 09/08/2026 às 23:27 UTC (`weekend_batch_blocked_at`)
    derrubou o estágio de escalonamento de 1 para 0 (`weekend_scrape_stage`
    em bot_state), reduzindo checagens de ~40/dia para 20/dia por alguns
    dias. Confirmado em 12/08/2026 que a recuperação está progredindo
    normalmente e sem intervenção: `weekend_block_streak_days = 0` (sem
    recorrência desde 09/08), `weekend_scrape_clean_days = 3` (subindo dia
    a dia), execuções primária e de lote rodando normalmente em 12/08. Não
    travado, não é pendência.

  MOTIVO REGISTRADO: fins de semana dentro da janela deslizante monitorada
  hoje ainda estão, em sua maioria, fora da janela de compra (< 29/01/2027) —
  o mercado real da rota, no período observado, não chegou perto do teto de
  R$300. Sem ação corretiva necessária; registrado como linha de base.
- **Fatia D2 — `alert_log` ganha tipo de alerta: ✅ CONCLUÍDA (14/08/2026).**
  Implementada e SQL executado em 13/08/2026; **verificação pós-deploy
  fechada em 14/08/2026 com dado real de produção** (itens 1-5 da lista —
  detalhe e tabela de evidência em `PLANO-ATIVO.md`, "Etapa 6" → "Fatia
  D2"). Corrige o bug estrutural descrito acima (cooldown de
  perna não distinguia teto de oportunidade). Duas colunas booleanas
  (`is_ceiling_alert`, `is_opportunity_alert`), cooldown por tipo com
  `all()` + guarda de lista vazia, índice `(leg_id, sent_at desc)`. 220
  testes passando (209 preexistentes + 11 novos). SQL validado ponta a ponta
  contra Postgres local descartável antes da execução real, e depois **rodado
  manualmente em produção e verificado em 13/08/2026** — todos os blocos
  (G0, backfill, índice, RLS/grants, prova sintética V6) bateram com o
  esperado; backfill real de perna veio 10/41/2 (53 total, 0 órfã) contra o
  previsto 10/40/2 (52 total) — 1 linha de oportunidade a mais, crescimento
  orgânico entre a medição de 12/08 e a execução de 13/08, já previsto no
  cabeçalho do script, não erro; rota bateu exatamente (17/0/5, 22 total).
  Detalhe completo, incluindo a evidência de produção que fechou a
  verificação, em `PLANO-ATIVO.md`, "Etapa 6" → "Fatia D2".
  - **Prova de produção (14/08/2026, execução das 08:37 BRT):** as três
    linhas gravadas pelo código novo nasceram classificadas corretamente,
    sem depender de backfill — 2 de rota (`abaixo da meta fixa`,
    `is_ceiling_alert=true`) e 1 de perna (`15.3% abaixo da média
    histórica`, `is_opportunity_alert=true`); zero órfã, zero flag errada.
    Confirmado por SQL direto em `alert_log`, não só pelo log do Actions.
  - **Lacuna de longo prazo, registrada — não é pendência ativa e não
    bloqueia nada:** a prova mais forte (colisão real teto × oportunidade
    na mesma perna, com dado escrito pelo próprio robô) depende de um
    primeiro hit de teto, que não ocorre desde 30/07/2026. A prova
    sintética (V6, transação com rollback, confirmada em produção) cobre a
    semântica da consulta. Se/quando um hit de teto acontecer, o item pode
    ser fechado só observando o comportamento em `alert_log` — nenhuma
    ação necessária agora.
  - **Débito técnico de nomenclatura, registrado — não é bug:** report de
    rota usa `is_ceiling_alert`/`is_opportunity_alert` (mesmo nome das
    colunas do banco); report de perna usa `is_ceiling_hit`/
    `is_opportunity_hit` (nome preexistente, já lido por
    `telegram_notifier.py`). Mesmo conceito, nomes diferentes por domínio —
    unificar tocaria código fora do escopo mínimo da fatia.
- **Fatia D3 — `alert_log` ganha `user_id` (14/08/2026): IMPLEMENTADA,
  SQL EXECUTADO E VERIFICADO EM PRODUÇÃO EM 14/08/2026 (commit `5352e3f`);
  itens 4-6 da verificação pós-deploy seguem como registrados no
  `PLANO-ATIVO.md`.** Correção de 19/11/2026: esta entrada dizia "SQL ainda
  não executado", contradizendo o `PLANO-ATIVO.md` (título e item 1 da
  Fatia D3). Prepara a D4 (avaliação por usuário) e a Etapa 7; não
  individualiza nada ainda, não muda o que é alertado nem o que é coletado.
  - **Preenchimento assimétrico, e é a decisão central:** linha de
    `alert_log` com `route_id` recebe dono trivial (`routes.user_id`, backfill
    cobre as 22 existentes); linha com `leg_id` fica **NULL de propósito** —
    não há dono derivável hoje. `weekend_legs` não tem `user_id`, e
    `weekend_leg_effective` resolve "quem monitora a perna" por cross join com
    `settings` (N usuários, não um), com o robô colapsando os N via MIN de
    teto. `weekend_leg_user_state` também não resolve (modelo preguiçoso):
    **medido em 14/08/2026 — 31 pernas já alertadas, só 4 com linha de
    estado**. Com uma conta só, gravar o `user_id` existente pareceria certo e
    seria dado inventado.
  - **Coluna nullable, com FK `on delete set null`, sem CHECK/NOT NULL/UNIQUE
    — restrição vinda de produção:** os dois inserts em `alert_log` rodam
    depois de a mensagem do Telegram já ter saído (e o de perna dentro de um
    laço), então nenhuma constraint nova pode ser capaz de rejeitar um insert
    que hoje passa. Os dois inserts passaram a ter `try/except` com
    `had_error` e log procurável `[alert_log] FALHA AO GRAVAR`.
  - **Ressalva registrada:** `on delete set null` é declaração de intenção,
    **não** garantia de preservação de histórico — as FKs de `alert_log` são
    `on delete cascade`, então apagar a conta cascateia as linhas de rota
    antes de o `set null` ter efeito.
  - **Índice e RLS não foram tocados** — a forma final do índice e o
    predicado de RLS por usuário são decisão da D4 (a expectativa registrada
    pela D2, de recriar o índice como `(leg_id, user_id, sent_at desc)`, foi
    revista e está corrigida na subseção "Fatia D2" do `PLANO-ATIVO.md`).
  - **Marca d'água do deploy** registrada no script (total de linhas +
    `max(sent_at)`): depois da D4, `user_id` NULL em linha de perna passaria a
    ter dois significados indistinguíveis (anterior à individualização vs.
    gravação de dono que falhou).
  - Detalhe completo, incluindo o G0 medido e a lista de verificação
    pendente, em `PLANO-ATIVO.md`, "Etapa 6" → "Fatia D3".
- **DECIDIDO E IMPLEMENTADO (Fatia D4, 15/08/2026): a decisão de alertar passa
  a ser tomada POR USUÁRIO — teto próprio, limiares próprios, cooldown próprio
  — e a mensagem do Telegram identifica quem disparou.** Última fatia da Etapa
  6; fecha a "JANELA ABERTA 2" (`PLANO-ATIVO.md`).
  - **O que morreu:** o MIN de teto entre usuários (regra provisória da Etapa
    4.2, marcada como tal no próprio código) e a escolha de UM usuário — o
    menor `user_id` — para ditar os limiares gerais, com os dois avisos de
    Telegram que anunciavam as duas coisas.
  - **Garantia central preservada:** nenhuma consulta de preço cresce com o
    número de usuários. Gravar preço, ler histórico, classificar suspeita e
    resolver a janela de compra continuam acontecendo **uma vez por perna**; o
    leque abre só na decisão e no envio. A Travelpayouts e o lote `fli` não
    multiplicam.
  - **Schema:** só uma coluna de rótulo, `settings.display_name` (nullable).
    Sem `display_name`, a mensagem cai nos 8 primeiros caracteres do uuid — por
    desenho, não por defeito. **Sem REVOKE/GRANT**, porque privilégio de coluna
    é herdado da tabela em Postgres e um revoke de coluna não restringe nada; a
    barreira real é a RLS per-user de `settings`, medida por personificação
    antes e depois (blocos G0-Q6 e V2-B do script).
  - **Transição prevista, uma vez só:** o cooldown de perna passa a filtrar por
    usuário, e as 54 linhas históricas com `user_id` NULL ficam invisíveis a
    esse filtro (predicado simples e permanente, **sem** `or user_id is null`,
    que casaria com dado de outra era). Consequência aceita: alguns alertas
    podem repetir **uma vez** na primeira execução após o deploy. Tamanho exato
    medido antes de rodar, no bloco G0-Q4 do script.
  - **Diferença real no modo degradado** (zero linha em `settings` — nunca
    ocorreu em produção): o alerta de oportunidade continua saindo, mas **não é
    mais gravado** em `alert_log`, então o cooldown não é alimentado e o alerta
    pode repetir a cada execução. Antes da D4 funcionava. Registrado como
    diferença, não como equivalência.
  - **Fora de escopo, e explicitamente não corrigido:** a semântica invertida
    de `notification_mode` em `rules.py:80-81` — `daily_summary` **desliga** o
    cooldown de perna e faz o usuário receber **mais** alertas. Bug
    pré-existente e independente; a D4 individualiza a leitura da coluna, não a
    semântica.
  - **Status:** código e testes prontos (267 testes passando, eram 227).
    **SQL executado e verificado em produção** (10/10 blocos, zero gate;
    `display_name` criada e populada com `'Elton'`). Previsão do re-alerta de
    transição já medida em G0-Q4: 1 perna de teto, 0 de oportunidade.
  - **✅ ITENS 5 E 6 DA VERIFICAÇÃO PÓS-DEPLOY CONFIRMADOS (17/08/2026), por
    evidências de naturezas diferentes.** **Item 5 (BANCO)** — a linha de perna
    em `alert_log` nasce com `user_id` preenchido: provado por `select` direto
    (`sql/etapa7_item5_verificacao_alerta_2908_2027.sql`) contra o alerta real
    de ~08h16 BRT de 17/08 (29/01/2027, volta, R$ 334); 3 linhas na janela
    08h–09h BRT, todas com `leg_id` e `user_id` preenchidos (`c72bf50e-…`),
    zero NULL. **É a primeira observação real do mecanismo** — pesava sobre
    este item o fato de a D3 nunca ter observado a gravação de `user_id` no
    caminho de rota, que **não serviu de ensaio** para o de perna; agora o
    caminho de perna foi medido direto. **Item 6 (MENSAGEM)** — nome do usuário
    na mensagem: print de tela do mesmo alerta exibindo "👤 Elton", não
    `uuid[:8]`. **Numeração:** item 5 = banco, item 6 = mensagem — um prompt de
    outro chat inverteu isso na mesma data; correção registrada em
    `PLANO-ATIVO.md` → "Fatia D4" → "Nota de numeração".
  - **✅ FATIA D4 CONCLUÍDA (fechamento registrado em 19/11/2026).** Itens
    restantes da verificação pós-deploy, fechados com a evidência disponível
    (`HISTORICO.md` item 28):
    - **Item 4 (publicar o código): ✅** commit `8a54529`, 15/08/2026.
    - **Item 7 (`had_error` não disparou): ✅** varredura dos 169 logs do
      `daily.yml` de 15/08 a 06/11/2026 — zero `[alert_log] FALHA AO GRAVAR`.
    - **Item 8 (avisos provisórios pararam): ✅ por log e código** — zero
      linha "provisório" nos mesmos 169 logs, bloco renomeado para "avisos de
      DEGRADAÇÃO" (`telegram_notifier.py:413`); canal do Telegram não
      conferido.
    - **Itens 9 (re-alerta de transição) e 10 (regressão estrutural): não
      verificados, aceitos.** Três meses de produção com dois usuários sem
      sinal de regressão; reconstruir a observação de 15-16/08 não vale o
      custo.

## 3. Próximos passos (ordem sugerida)

_Fila substituída em 19/11/2026, depois do incidente de 06-18/11
(`HISTORICO.md` item 28). A fila anterior (itens 1-9, quase todos concluídos)
foi arquivada na íntegra em `HISTORICO.md`, item 28, subseção "Fila de
próximos passos substituída". Destino de cada item antigo: 1, 2, 3, 5, 7 e 8
concluídos; 6 (resumo com denominador 90, prazo 17/08) fechado pelo resumo
semanal de 07/09/2026 (E7-7); 9 (ativar o radar) superado — radar ligado
desde ~29/08 e Fatia 2 em produção desde 05/09; 4 (observar o escalonamento)
segue como acompanhamento contínuo pelo Dashboard, sem item próprio._

1. **Reativação automática dos workflows dentro do `daily.yml` + atualizar
   `actions/checkout` e `actions/setup-python` para as versões Node 24 — ✅
   VERIFICADO (20/11/2026).** Run agendado do `daily` de 20/11 com
   `[keepalive] ok` nos dois arquivos e zero anotações (sem aviso de Node 20);
   run agendado do bot também sem anotações. Que `enable` zera o contador de
   60 dias continua não documentado pelo GitHub — a garantia real é o item 6.
   `HISTORICO.md` item 29.
   **Em paralelo, sem ação:** o `fli` segue bloqueado em 20/11, agora parcial
   (lote parou após 8 consultas, 2 com preço; radar 24/24 blocos, 13/20 em
   anomalia) — em observação. E o agendamento do GitHub está atrasando muito:
   o run das 08h de 19/11 saiu às 16h12 BRT, o das 20h às 00h54, e o das 08h
   de 20/11 não tinha saído às 14h13 — mais um motivo para o item 6.
2. **Aba Compras mostrar só fins de semana futuros — ✅ IMPLEMENTADO
   (19/11/2026), verificado no painel local, ainda não publicado.** Some no
   dia seguinte à última perna (fuso de SP, data real da volta), botão
   "Mostrar passados", só visual. Regra única em `docs/js/weekend-dates.js`,
   para o resumo do Dashboard (item 4) reaproveitar. `HISTORICO.md` item 30.
   **Pendência D+1 — ✅ CORRIGIDA (19/11/2026), verificação em produção
   parcial:** lote `fli` e varredura de cache não consultam nem avaliam
   perna com data anterior a hoje (BRT); a de hoje continua; margem D+1 da
   lista ativa mantida; cortes com data de Brasília. Primeiro run (20/11)
   coerente, mas sem perna de ontem na lista para cortar; caso positivo
   esperado nos runs de 21/11 e 23/11. `HISTORICO.md` item 31.
3. **Checkpoint do radar em 01/12/2026** (`PLANO-ATIVO.md`, "Checkpoint —
   radar como gatilho de alerta"). **Atenção:** o buraco de dados de 06-18/11
   caiu justamente na faixa de 30-60 dias antes das pernas de fim de ano
   (25/12/2026 e 01/01/2027) — a condição que motivou a data do checkpoint.
   Medir a série real em `weekend_radar_precision_log` (consulta em
   `HISTORICO.md` item 28) antes de concluir qualquer coisa.
4. **Resumo das pernas compradas no Dashboard — ✅ IMPLEMENTADO
   (20/11/2026), verificado no painel local com dados reais.** Bloco "Minhas
   compras" (próximos voos; "Voos anteriores" fechado com total gasto já
   viajado / a viajar); localizador vem de `notes` (não há coluna própria).
   Consultas ao snapshot de compra filtram `user_id` além da RLS.
   Complemento (20/11): só as 4 próximas à vista (`UPCOMING_VISIBLE` em
   `dashboard.js`), demais em "Mais N voos comprados" fechado.
   `HISTORICO.md` item 32.
5. **Gustavo deixa de participar:** sem alertas, fora do resumo semanal e das
   mensagens, mas com o login mantido.
6. **Alarme de "robô parado" fora do GitHub, antes de 29/01/2027** (início da
   janela de compra) — o incidente de 06-18/11 passou 12 dias sem ninguém
   perceber, porque o próprio GitHub era o que tinha parado.
7. **Consulta de passagens sob demanda entre quaisquer cidades.** Substitui o
   item "inserção manual de rotas/datas-alvo" declarado em 05/09/2026
   (`PLANO-ATIVO.md`).
8. **Compras: título da volta usa a variante do robô, não a data do voo
   comprado (cosmético).** Ex.: volta comprada para quarta 10/02/2027 num
   card que diz domingo/segunda. Só o rótulo; a regra de "já passou" já usa
   a data certa. `HISTORICO.md` item 32.

## 4. Bloqueios / perguntas em aberto

- **Multi-usuário (amigo que também vai comprar RIO↔BSB em 2027) — ✅ ENCERRADO COMO BLOQUEIO (05/09/2026).**
  As 7 etapas estão concluídas, e a Etapa 7 (conta do segundo usuário) foi
  executada inteira (E7-0 a E7-7) e verificada em produção **com as duas
  contas reais**: isolamento provado por SQL (E7-4), fan-out de alerta com dois
  `user_id` distintos na mesma execução confirmado por consulta sistemática
  (E7-5 — 12 pares, 6 pernas, janela 20/08–05/09/2026), e visibilidade cruzada
  de compra + rótulo "Você" conferidos por login nas duas direções (E7-6).
  Não é mais bloqueio nem pergunta em aberto. **Histórico completo por etapa no
  `HISTORICO.md`** (itens 17-23 para as etapas 4.x e as Fatias A/B/C; item 27
  para a Etapa 7 inteira, movida do `PLANO-ATIVO.md` em 05/09/2026); diagnóstico
  de RLS e escopo em `AUDITORIA-MULTIUSUARIO.md`.
  - **Em observação, não em bloqueio:** item 10 da lista nomeada dos 11
    (`notification_mode` por dono no caminho de rota, D-4b) é o único que segue
    sem observação em produção — depende de o Gustavo cadastrar uma rota
    flexível, e ele não cadastrou.
  - **Regra dura, cumprida e agora histórica:** a criação da conta foi de fato
    a última etapa, e a credencial só foi entregue depois da prova de
    isolamento (E7-4).
- **✅ ENCERRADO (04/08/2026) — regra de janela aberta (4.1 → 4.2): não editar teto no painel.** Entre a 4.1 e a 4.2 o estado vivia em dois lugares. O painel e o robô continuavam lendo e escrevendo o mundo antigo (`weekend_legs`); o mundo novo (`weekend_leg_user_state`) existia mas ficava parado na fotografia do dia da cópia. Teto editado no painel nesse intervalo iria para a coluna velha, fora do alcance da auditoria nova, e o re-sync da 4.2 teria que transformá-lo em **override explícito**. **Fechado por execução real do re-sync** (pendências 1 e 2 da Etapa 4.2, `sql/etapa4_2_resync.sql`, 04/08/2026): zero teto preso na coluna velha, zero divergência de estado. Já estava tecnicamente encerrado desde 03/08/2026 (pendências 3/4 — painel parou de escrever em `weekend_legs.price_ceiling`); a execução do re-sync fecha o registro formal do intervalo. Texto histórico mantido para contexto. Detalhe no `PLANO-ATIVO.md`, seção "Etapa 4.2".
- **Pedido de antecipar a criação da conta do segundo usuário: avaliado e recusado (31/07/2026).** Motivo: `price_ceiling`/`status`/`notes`/`paid_price` ainda são globais e a RLS de `weekend_legs` é genérica hoje — qualquer autenticado podia sobrescrever o dado do outro, sem auditoria de teto pra reconstruir depois, corrigido pela Etapa 4.4 (07/08/2026) (ver `AUDITORIA-MULTIUSUARIO.md` e pendência (d) do diagnóstico de alerta em `PLANO-ATIVO.md` — **a parte da auditoria foi resolvida pela Etapa 4.1 em 01/08/2026**; as colunas globais e a RLS genérica de `weekend_legs` continuam como estavam, então a recusa segue de pé). A regra dura (conta nova só na Etapa 7) permanece. Alternativa considerada e descartada: travar `weekend_legs` como somente-leitura via RLS temporária — descartada por mexer em política de segurança em produção, risco de falha silenciosa ao salvar no frontend, e por ser trabalho descartável. Enquanto isso, a necessidade real do segundo usuário ("ver preço e saber quando comprar") é atendida manualmente pelo usuário principal. **Lado de leitura fechado (08/08/2026):** decisão de produto tomada no chat de planejamento — dado objetivo de voo (preço atual, companhia, horário, menor preço visto, calendário dos fins de semana) é compartilhado entre usuários, decisão consciente. Confirmado por diagnóstico só-leitura em duas partes (catálogo de RLS + personificação de usuário fictício via `set local role authenticated` em transação com rollback, mesma técnica do bloco F da 4.1): zero divergência do esperado em todas as 16 tabelas/views verificadas — nenhuma tabela de decisão pessoal (`weekend_leg_user_state`, `weekend_leg_ceiling_audit`, `weekend_legs_legacy_columns_backup`) é legível por outro usuário; `weekend_legs`/`weekends`/histórico de preço/run log de perna são, como esperado, visíveis a qualquer autenticado. Achado de higiene sem ação necessária: `grant_select_anon = true` aparece em todas as tabelas (padrão de fábrica do Supabase, role grant — não RLS); a policy de linha continua sendo a barreira real, confirmada pela própria personificação. **Isso fecha só o lado de leitura.** O lado de escrita já tinha sido fechado pela Etapa 4.4 (07/08/2026). A pendência da RLS "genérica" está encerrada nos dois lados. Não bloqueia mais a Etapa 7 por este motivo — a Etapa 5 foi concluída por composição (ver acima). **Atualização de 15/08/2026:** a Etapa 6 foi fatiada em D1-D4 e todas as quatro estão implementadas; a Etapa 7 está planejada e totalmente decidida, e **o único bloqueio que resta é a verificação pós-deploy da Fatia D4** — ver o item próprio abaixo.

  **Resumo para colar em novo chat de planejamento:** iniciativa multi-usuário em andamento (7 etapas, ver `PLANO-ATIVO.md`). Etapas 1-3 concluídas: `routes`/`settings` já são per-user (RLS confirmada); policy de `alert_log` corrigida em produção (cobre `leg_id`); config de sistema (`suspicious_below_avg_pct`, `fast_flights_enabled`, `fast_flights_daily_batch_size`) migrada para `system_config` (linha única, sem dono, edição só via SQL Editor — ver `RUNBOOK.md`), colunas antigas em `settings` intocadas por ora (Etapa 3b de remoção pendente). **Etapa 4.1 concluída e verificada (01/08/2026):** existem no banco de produção `weekend_leg_user_state` (teto/status/notas/valor pago por perna × usuário, modelo preguiçoso — a linha só nasce quando o usuário decide algo), `settings.weekend_default_ceiling` = 250, `weekend_leg_ceiling_audit` (append-only, alimentada por trigger, pega até edição no SQL Editor) e a view `weekend_leg_effective` (`security_invoker`); verificada com os blocos A–G (mundo antigo intacto, isolamento entre usuários OK, carimbo de origem por `request.jwt.claims` — **a capacidade de prova de E e F foi revisada em 02/08/2026**, comportamento confirmado por reprodução num Postgres descartável, mas os blocos como escritos discriminam menos do que a redação original afirmava); os arquivos `sql/` estão no repositório desde o push de 02/08/2026. **A Etapa 4.2 (virada de leitura) está em execução, com 12 pendências nomeadas no `PLANO-ATIVO.md`.** Pendências 3 e 4 concluídas, commitadas e enviadas em 03/08/2026 (`531f34f`, `9436bc0`) — o painel (`docs/js/compras.js`) já lê `weekend_leg_effective` e escreve em `weekend_leg_user_state`, com verificação manual completa no site publicado. Pendências 1 e 2 (re-sync do estado) concluídas e executadas em produção em 04/08/2026 (`sql/etapa4_2_resync.sql`, mantido no repo, re-rodável) — **resultado: zero divergência**, nada precisou ser copiado do mundo antigo. Pendência 5 (`docs/js/dashboard.js`) concluída, commitada e enviada em 04/08/2026 (`05c6f97`, `c19329f`) — o Dashboard também passou a ler `weekend_leg_effective`, verificado no site publicado com um override de teto concordando entre Compras e Dashboard. Restam as pendências 6–12; a 4.3 remove as colunas antigas de `weekend_legs` depois. **Regra de janela aberta ENCERRADA (04/08/2026)** — confirmada pela execução do re-sync sem divergência, já estava tecnicamente fechada desde as pendências 3/4. O teste do caminho de alerta de perna já foi concluído em 01/08/2026, então a Etapa 6/Telegram não depende mais de teste nenhum, só da revisão explícita de praxe. RLS de `weekend_legs`/`weekends`: lado de escrita fechado pela Etapa 4.4 (07/08/2026), lado de leitura fechado por decisão de produto + diagnóstico em 08/08/2026 (dado de mercado compartilhado, decisão consciente) — ambos deixaram de ser motivo de bloqueio da Etapa 7; a Etapa 5 foi concluída por composição em 08/08/2026, ela segue bloqueada só pela Etapa 6; Telegram é hardcoded a 1 chat_id, resolvido pela decisão de grupo único; robô sempre usa service_role (nunca passa por RLS). Detalhe completo em `AUDITORIA-MULTIUSUARIO.md`. Regra dura: criar a conta do segundo usuário é sempre a última etapa. Teto padrão recalibrado de R$250 para R$300 em 04/08/2026 (decisão do usuário via painel — ver seção "Decisões vivas").
- **HIPÓTESE NÃO CONFIRMADA:** `alert_log` ter ficado com 0 registros de `leg_id` entre 23/07 e 31/07/2026 é provavelmente consequência do bug de agendamento corrigido em 30/07/2026 (item 15 do `HISTORICO.md`) — sem execução primária, nenhum alerta de perna chega a ser avaliado, silenciosamente e com exit 0. Reforça a hipótese o fato de 6 dos 13 alertas de 01/08/2026 serem orgânicos (`weekend_opportunity_pct`, teto normal), sem relação com o teste com tetos elevados artificialmente.
- **Ponto de atenção aberto:** o cooldown/dedup de perna nunca operou com dado real (`alert_log` estava vazia até 01/08). A execução de 02/08/2026 é a primeira observação real desse mecanismo — verificar se os 6 alertas de oportunidade de 01/08 se repetem indevidamente. Restaurar o cron pra 3x/dia (seção 3, item 1) só depois dessa observação.
- **OBSERVAÇÃO DO ROBÔ 02/08/2026, PARCIAL.** A execução das 08:54 BRT rodou e alertou (2 alertas de rota legado + 2 de oportunidade de perna). **A conclusão sobre cooldown/dedup NÃO foi tirada** — depende de consulta à `alert_log` comparando 01/08 e 02/08, ainda não feita. Continua valendo: não restaurar o cron para mais de 1x/dia antes dessa conclusão (seção 3, item 1).
- **✅ DECIDIDO em 11/08/2026 (era "ACHADO NOVO A DECIDIR", 02/08/2026):** os 2 alertas de oportunidade da execução das 08:54 de 02/08 dispararam para o fim de semana de 18/09/2026 (ida R$424, volta R$423, teto R$250) — fim de semana **anterior** a 29/01/2027, ou seja, fora da janela de compra, que por decisão de escopo nunca será comprado. O caminho de oportunidade (`weekend_opportunity_pct`) alerta por queda percentual contra a média histórica, **independentemente do teto e da janela de compra**. O Dashboard já separa ação de informação para esse mesmo caso; o Telegram não. **Decidido em 11/08/2026** (ver seção 2, "Decisões vivas"): o alerta de oportunidade passa a respeitar a janela de compra — **implementada e publicada (Fatia D1, 12/08/2026, commit `757ab3e`)**, verificação de produção em andamento até 17/08/2026 (`PLANO-ATIVO.md`, "Etapa 6" → "Fatia D1").
- **EXPOSIÇÃO CONHECIDA E ACEITA:** o `user_id` do Supabase do usuário (`c72bf50e-…`) aparece por extenso na documentação de um repositório **público**. Risco avaliado como baixo — UUID não é credencial, e a RLS exige JWT assinado, que não se forja conhecendo o identificador. Registrado como decisão consciente, não como descuido.
- **TAXA DE `no_data` DE 85% EM 02/08/2026 — ✅ ESCLARECIDO (12/08/2026).** 152 checagens no dia, 23 `ok`, 129 `no_data`. Detector de bloqueio **não disparou** (`bloqueio_detectado = false`, 4 dias limpos). Usuário avaliou que o scraping está funcionando bem e **decidiu não acionar o kill-switch**. Registrado como observação, não como incidente. **Esclarecido pela investigação de 12/08/2026** (ver seção 2, "Decisões vivas"): os 85% vinham inteiramente do cache Travelpayouts (que erra ~98% por desenho), não do lote `fli` (fonte primária, ~0% de falha em 13 dos 14 dias observados) — não indicava problema real. Não é mais dúvida em aberto.
- **DETECTOR DE BLOQUEIO POSSIVELMENTE MAL CALIBRADO — ✅ ESCLARECIDO (12/08/2026).** O limiar documentado (sucesso <50% com amostra ≥8) não disparou apesar de 85% de falha no dia. O detector (`live_check.py:218-220`) calcula `success_rate` só sobre o lote `fli` do dia, nunca sobre o total (o lote cache, que historicamente erra ~98% das pernas, não entra nessa conta). **Confirmado pela investigação de 12/08/2026** (ver seção 2, "Decisões vivas"): essa leitura estava correta — não é miscalibração de limiar, é escopo pretendido (o detector nunca teve a intenção de olhar o dia inteiro, só o lote que ele mesmo executa). Não é mais dúvida em aberto.
- **VOLUME DE CHECAGENS ACIMA DO PREVISTO — investigado e explicado (02/08/2026).** 152 checagens/dia contra `batch_size` 20 e ~43 pernas elegíveis pareciam divergentes. Leitura de código (`weekends.py`, `live_check.py`, `scrape_schedule.py`) explica o número: são dois lotes com escopos diferentes somados, cada um gravando 1 linha por perna, sem retentativa gerando linha extra — **cache** (`process_all_weekend_legs`/`get_active_legs`) roda TODA perna `monitoring` não expirada, **sem limite de janela de meses à frente** (~132 pernas), e **lote ao vivo** (`run_daily_batch`/`select_batch`) é o único limitado por `batch_size` (20) e pela janela de 183 dias. 132 + 20 = 152, bate exato. **IMPEDITIVO ATUAL para aumentar a frequência do cron:** enquanto não se souber se o volume do cache (sem limite de janela, ~132/dia, roda 1x/dia independente do estágio) muda com o aumento de frequência do lote `fli`, multiplicar a frequência viola a regra de scraping discreto. Achado registrado, decisão não tomada nesta tarefa.
- **ACHADOS DA INVESTIGAÇÃO READ-ONLY DE 14/08/2026 (frequência/cobertura do
  scraping) — registrados, sem ação proposta.** Leitura de código apenas
  (`src/scrape_schedule.py`, `src/main.py`, `src/live_check.py`,
  `.github/workflows/daily.yml`), nenhuma alteração feita:
  - **(a) O Estágio 2 do escalonamento é inalcançável pelo cron atual.**
    `STAGE_BATCHES_PER_DAY = {0: 1, 1: 2, 2: 3}`
    (`src/scrape_schedule.py:35`) define a cota de lotes `fli` por DIA, e o
    lote roda enquanto a cota não é atingida — mas quem entrega execução é o
    cron, hoje fixo em 2x/dia (`daily.yml:9-10`, 08h/20h BRT). Logo o teto
    real hoje é o Estágio 1 (2 lotes/dia): o terceiro lote do Estágio 2 só
    sairia por `workflow_dispatch` manual. Nenhum trecho de código ajusta o
    cron ao estágio.
  - **(b) A cobertura por perna degrada sozinha com o tempo.** A janela do
    lote ao vivo é constante (`LIVE_CHECK_WINDOW_DAYS = 183`,
    `src/live_check.py:54`) e desliza com a data, então a fila elegível
    cresce sozinha conforme os dias passam; a cota diária (estágio) e o
    tamanho do lote (`fast_flights_daily_batch_size`) são constantes. Nada em
    `scrape_schedule.py` lê tamanho de fila, tempo restante ou cobertura — a
    mesma cota passa a cobrir uma fração menor da fila por volta completa,
    sem aviso. Só muda por bloqueio (cai para Estágio 0), 5 dias limpos
    (sobe um estágio, até o teto) ou edição manual.
  - **Ler junto com o impeditivo já registrado no item acima** (volume do
    cache, ~132 pernas/dia sem limite de janela): **não** há aqui decisão
    pendente de mexer no cron — os dois achados são registro de estado, não
    proposta.
- **✅ DECIDIDO em 11/08/2026 — ALERTA DE OPORTUNIDADE (E RESUMO SEMANAL) FORA DA JANELA DE COMPRA** — ver item acima ("DECIDIDO em 11/08/2026") e seção 2, "Decisões vivas", para o texto completo da decisão (que passou a cobrir também o resumo semanal, não só o alerta de oportunidade). **Implementada e publicada (Fatia D1, 12/08/2026, commit `757ab3e`)**, verificação de produção em andamento até 17/08/2026 (`PLANO-ATIVO.md`, "Etapa 6" → "Fatia D1").
- **PERGUNTA ABERTA, REGISTRADA 11/08/2026 — "execução extra do dia" parece pular Travelpayouts, não só rotas flexíveis.** O item 1 da seção 1 já documenta que só a primeira execução do dia roda "rotas flexíveis/cache Travelpayouts/notificações", com as execuções extras rodando só o lote `fli`. Em observação recente, o usuário notou que a execução extra também não roda Travelpayouts — ainda não está claro se isso é exatamente esse comportamento já documentado (e portanto intencional) ou um achado novo/divergente. **Travelpayouts deve continuar rodando normalmente** — não é decisão de reduzir seu uso. **Sem ação agora** — só registrado para não esquecer; investigar em sessão futura antes de tirar conclusão.

- **✅ FECHADO (17/08/2026) — BLOQUEIO DO SCRAPING DE 16/08 ~23h16 BRT ERA
  TRANSITÓRIO E AUTORRECUPERADO.** A execução extra fora de padrão de 16/08
  ~23h16 BRT bateu o detector de bloqueio (falhas seguidas após 6 consultas,
  lote interrompido em 6/20 pernas) — primeira ocorrência de bloqueio real
  naquela sequência de logs, registrada com causa não investigada.
  **Encerrado pela mensagem do próprio bot em 17/08/2026 08h16 BRT:**
  *"✅ Consulta ao vivo normalizada — voltou a funcionar depois de 1 dia sem
  sucesso"* — a fonte voltou **sozinha, sem intervenção nenhuma**. Registrado
  como ocorrência **transitória e autorrecuperada**, **não** como problema
  persistente da fonte, e **não** como sinal estrutural ligado à lacuna do
  `LIVE_CHECK_WINDOW_DAYS` (achado (b) de 14/08, acima). **Deixa de ser
  pendência — não deve reaparecer como "em aberto".** Resta só a pergunta
  lateral **(a)**: o que disparou a execução extra tão perto do horário
  agendado (suspeita não confirmada: `workflow_dispatch` acionado por push de
  sessão de trabalho) — leia junto com a pergunta aberta de 11/08/2026 sobre a
  "execução extra do dia", logo acima, que é do mesmo tema.
- **✅ RESOLVIDA (24/08/2026) — divergência R$500/R$300 explicada por
  overrides legítimos por perna, não por bug ou recalibração perdida.**
  Origem (17/08/2026): o `reason` do primeiro alerta real citava
  `'abaixo da meta fixa (R$ 500.0)'`, divergindo do teto documentado (R$300).
  Ampliado em 24/08/2026 por uma primeira consulta (`alert_log` +
  `weekend_leg_effective`) que só confirmava a divergência sem explicar a
  causa. **Fechada pela leitura direta de `weekend_leg_ceiling_audit`**
  (histórico completo com `scope`, `origin`, `changed_by`):
  - **Os defaults (`scope='default'`) NUNCA divergiram do documentado.** Elton:
    última linha `250→300` em 05/08/2026, nunca mais tocada. Gustavo: única
    linha `null→300` em 16/08/2026 via `sql_editor` (a própria E7-2,
    FECHADA-1). Batem exatamente com `STATE.md`/`PLANO-ATIVO.md`.
  - **O que mudou foi por perna (`scope='leg'`), via painel (`origin='app'`,
    `changed_by` = o próprio dono).** Elton elevou 8 pernas para R$500 em
    15-16/08/2026 (`fd14836b`, `57834f25`, `c3c514ac`, `b4f28800`, `d7bf81ee`,
    `308f98e9`, `95b0bcab`, `16bff1f8`) — todas próximas do início da janela
    de compra (29/01-14/02/2027), consistente com priorizar manualmente o que
    pretende comprar em breve, já que o preço real (~R$316-350) estava perto
    demais do teto de R$300. Gustavo fez o mesmo em 18/08 e 24/08 (3 pernas em
    R$500, 1 — `b4f28800` — em R$400).
  - **Conclusão: não é bug, não é pendência.** É o mecanismo de override por
    perna (Etapa 4.2, em produção desde 04/08) sendo usado ativamente pelos
    dois usuários, exatamente como projetado — só não tinha sido observado em
    uso real antes desta leitura.
  - **Consequência para o radar de calendário:** confirma que a decisão do
    plano em revisão (gatilho da precisão deve usar o MAIOR teto entre
    usuários, lido ao vivo por perna — não `queue_ceiling`, que é MIN, nem um
    valor único assumido) está certa. Os tetos reais variam bastante por
    perna (R$229 a R$555 no histórico do Elton) e mudam com frequência — a
    calibração da margem pode prosseguir sem depender de mais nenhuma leitura.

## 5. Fora de escopo (lembrete de disciplina)

- Comparação de pacote (ida+volta casado) — suspensa, sem fonte segura.
- Regras de tarifa/bagagem no alerta — sem fonte gratuita disponível.
- Comparador de milhas automatizado — sem fonte de dados gratuita (existe campo/lógica no código, mas nunca é alimentado; decisão consciente de não fingir funcionalidade).
- Qualquer tática de evasão de bloqueio (proxy, rotação de IP, VPN, spoofing, resolução de CAPTCHA).
- Emissão/compra automatizada de passagem.
- Sazonalidade histórica via ANAC, câmbio, previsão por ML — ideias registradas, sem desenho ativo, só retomar em ciclo de planejamento próprio se fizer sentido no futuro.

## 6. Referências

- Repo: github.com/Eltoneap/flyiop (público)
- `STATE.md` — este arquivo: orientação de alto nível, lido no início de qualquer sessão nova
- `PLANO-ATIVO.md` — plano técnico detalhado só da Parte em execução agora. **Conteúdo em 19/11/2026:** ainda carrega seções já concluídas que não foram migradas para o `HISTORICO.md` (diagnóstico de alerta de perna com as perguntas abertas do item (e); iniciativa multi-usuário — Etapa 4.2 com a pendência 12 de UI em backlog, Etapas 4.3/4.4 concluídas; Etapa 6, Fatias D1-D4, todas concluídas, D3 com itens 4-6 da verificação ainda sem marca; Etapa 0 e radar Fatias 1 e 2, em produção). O que segue **vivo** ali: o **checkpoint do radar de 01/12/2026** (com nota sobre o buraco de 06-18/11, `HISTORICO.md` item 28) e as pendências nomeadas do falso bloqueio de 01/09. O próximo item de roadmap de 05/09 foi substituído pela fila da seção 3 deste arquivo.
- `HISTORICO.md` — tudo já decidido/implementado, cronológico
- `CLAUDE.md` — escopo geral do projeto (lido automaticamente pelo Claude Code)
- `PROTOCOLO-DE-TRABALHO.md` — como usuário e Claude Code trabalham juntos (Plan Mode, gatilhos de revisão, regra de manutenção dos três arquivos de documentação)
- `RUNBOOK.md` — operações manuais sem UI própria (kill-switch e outros ajustes de `system_config` via SQL Editor)
