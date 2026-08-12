# STATE.md — FlyIop

> Atualizado em: 11/08/2026
> Última sessão: Claude Code (11/08/2026, documentação apenas — chat de
> planejamento) — **Fatia C movida para o `HISTORICO.md` (item 23)**,
> conforme a regra de manutenção do `PROTOCOLO-DE-TRABALHO.md` (mover ao
> concluir uma Parte); `PLANO-ATIVO.md` mantém só um ponteiro de uma linha
> pra lá. **Prova de produção da pendência 13 da Etapa 4.2 detalhada**: o
> resumo semanal do Telegram de segunda-feira 10/08/2026, 08:42 BRT, foi
> recebido pelo usuário e exibiu "0 de 132 pernas compradas", sem erro na
> montagem da mensagem — registrado em `PLANO-ATIVO.md`, Etapa 4.3, Passo 2.
> **Corrigida informação desatualizada na seção 3**: dizia que a Etapa 5
> (frontend por usuário) "ainda não iniciada, exige revisão explícita no
> chat de planejamento antes de começar" — contradizia a própria seção 4 e
> o `PLANO-ATIVO.md`, que já registravam a Etapa 5 como concluída por
> composição em 08/08/2026. **Item de fechamento de registro do resumo
> semanal removido da seção 3** — resolvido pelo item acima. **Nova decisão
> registrada na seção 2**: o Telegram passa a respeitar a janela de compra
> (fins de semana ≥ 29/01/2027) nos dois caminhos onde hoje não respeita —
> alerta de oportunidade (`weekend_opportunity_pct`) e resumo semanal (as
> duas listas de pernas e o denominador do contador de compradas), motivada
> por evidência observada em 10-11/08/2026 (9 de 10 pernas de "mais baratas
> agora" e 100% das de "mais próximas" fora da janela; alerta de
> oportunidade recebido pro fim de semana de 25/12/2026, também fora).
> **Implementação fica pra Etapa 6 — nada de código mudou nesta rodada.**
> Sessão só de documentação: nenhum arquivo em `src/`, `docs/` ou `sql/`
> tocado, nenhum SQL executado, nenhum commit feito.
> Sessão anterior: Claude Code (11/08/2026) — **FATIA C CONCLUÍDA (Parte 1
> banco + Parte 2 frontend).** Roteiro de verificação manual em produção da
> Parte 2, rodado pelo usuário: todos os itens passaram, sem erro no
> console, sem regressão visível — painel de confirmação de compra abre
> pré-preenchido corretamente (hora batendo com o Google Flights, confirma
> o achado de fuso), confirmar em branco funciona, hora sem data avisa e
> não salva, edição pós-compra salva os 4 campos num clique só com
> round-trip de fuso correto, desfazer/recomprar preserva o snapshot
> salvo. A visibilidade da linha "outro usuário já comprou" segue sem
> verificação positiva possível — depende da Etapa 7 (segunda conta),
> registrado como limite estrutural, não como pendência da fatia. Fatia C
> inteira encerrada: `docs/js/compras.js`/`docs/css/style.css` publicados
> em produção desde `ca54dd8` (11/08/2026), banco publicado e verificado
> desde 10/08/2026. Restam fora do escopo desta fatia: Telegram (Etapa 6)
> e a segunda conta em si (Etapa 7). Detalhe completo em `HISTORICO.md`,
> item 23 (movido de `PLANO-ATIVO.md` em sessão posterior no mesmo dia).
> Sessão anterior: Claude Code (11/08/2026) — **Fatia C, Parte 2 (frontend)
> IMPLEMENTADA, aguardando verificação manual em produção.** Planejada em
> Plan Mode (diagnóstico read-only inicial, plano escrito e aprovado com 4
> ajustes do usuário antes da implementação) e implementada em
> `docs/js/compras.js` + `docs/css/style.css` (`docs/compras.html` não
> tocado — cards são montados 100% em JS). Entrega: painel de confirmação
> de compra (abre em vez de salvar direto, pré-preenchido por
> snapshot→voo monitorado→vazio), bloco de edição pós-compra (4 campos,
> 1 botão Salvar), linha "outro usuário já comprou" no card (consome a
> projeção `weekend_leg_purchase_shared` da Parte 1, filtrada no front pra
> excluir a própria linha), toggle GIG/SDU que desmarca no segundo clique,
> `USER_LABELS` hardcoded (uuid → "Você"). Achado registrado em comentário
> no código: `current_departure_time` (robô) é datetime naive rotulado
> como UTC — lido cru, sem conversão de fuso, de propósito; já
> `purchased_departure_time` (esta fatia) tem offset `-03:00` real e É
> convertido para `America/Sao_Paulo` na leitura — as duas funções fazem o
> oposto uma da outra, comportamento correto, não bug. Revisão em 2
> rodadas de diff completo com o usuário antes da aprovação (1ª rodada:
> reposicionamento do bloco CSS + auditoria de variáveis de tema; 2ª
> rodada: 4 correções — snapshot em memória não atualizava após salvar o
> bloco de edição, `hourCycle: 'h23'` em vez de `hour12: false` por
> precaução com Safari/iOS, `display: ''` em vez de `'block'` ao cancelar,
> check-mark do bloco de edição não devia aparecer com os 4 campos vazios).
> Sem `node` disponível no ambiente para `node --check`; verificação de
> sintaxe feita manualmente (balanço de parênteses/chaves/colchetes e
> contagem de crases). Detalhe completo, roteiro de verificação manual
> pendente e lista de arquivos, em `PLANO-ATIVO.md`, seção "Fatia C".
> Registradas também, sem ação: pergunta sobre a execução extra do dia
> aparentemente pular Travelpayouts (seção 4) e confirmação de que o
> resumo semanal do Telegram de 10/08/2026 bateu `0/132` sem erro,
> fechando a pendência 13 da Etapa 4.2 com prova de produção, mais o
> detector de bloqueio de scraping de 09/08 à noite tendo funcionado
> corretamente (parou, avisou, recuperou sozinho) — ambos em
> `PLANO-ATIVO.md`.
> Sessão anterior: Claude Code (10/08/2026, documentação apenas — nenhum
> comando executado contra o Supabase) — **Fatia C, Parte 1 (banco)
> CONCLUÍDA E VERIFICADA EM PRODUÇÃO.** O usuário rodou
> `sql/fatia_c_visibilidade_compra.sql` manualmente no SQL Editor; os 5
> blocos de verificação (G0 + V1-V4) bateram 100% com o esperado —
> destaque para V2, que prova que `anon` termina com zero privilégio sobre
> `weekend_leg_purchase_shared` (o achado de fundo desta fatia, objeto novo
> em `public` nascendo com os 7 privilégios para `anon`, foi neutralizado
> nesta tabela), e V3, que confirma os três ramos da trigger de
> sincronização (compra grava, desfazer remove, recomprar grava de novo).
> Resultado real completo, bloco a bloco, registrado em `PLANO-ATIVO.md`,
> seção "Fatia C". **Parte 2 (frontend) segue sem prompt escrito** —
> aguardando início no chat de planejamento; Telegram fica para a Etapa 6.
> Sessão anterior: Claude Code (09/08/2026) — **Fatia C, Parte 1/2 (banco)
> PLANEJADA E ESCRITA, aguardando execução manual no SQL Editor** —
> visibilidade de compra entre usuários (o outro vê QUE você comprou uma
> perna e EM QUAL VOO, nunca quanto pagou/teto/localizador; só depois de
> `status = 'purchased'`). Mecanismo: tabela de projeção
> (`weekend_leg_purchase_shared`) mantida por trigger `security definer`,
> contendo só os 3 campos de voo — nenhum campo sensível chega a existir na
> tabela compartilhada. View e função `security definer` foram avaliadas e
> descartadas por serem bypass de RLS; achado de fundo: todo objeto novo em
> `public` neste projeto nasce com os 7 privilégios para `anon`/
> `authenticated` (default do Supabase), então `revoke all` explícito antes
> de qualquer grant é requisito, não capricho. No caminho, corrigida uma
> afirmação falsa no "Achado lateral" da Etapa 4.4 (o grant da view
> `weekend_leg_effective` nunca foi "só SELECT" por padrão — a conclusão
> daquele achado segue válida por outro motivo, a view não ter trigger
> `INSTEAD OF`). Script:
> [sql/fatia_c_visibilidade_compra.sql](sql/fatia_c_visibilidade_compra.sql).
> Nenhum comando executado contra o Supabase por esta sessão — só o usuário
> roda, manualmente. Parte 2 (frontend) é prompt separado, ainda não
> escrito; Telegram fica para a Etapa 6. Detalhe completo em
> `PLANO-ATIVO.md`, seção "Fatia C".
> Sessão anterior: Claude Code (08/08/2026) — **Fatia B CONCLUÍDA e
> publicada:** separação pessoal × sistema na UI. Dashboard
> ganhou etiqueta de escopo por bloco (`SÓ SEU` em Ação do dia,
> Progresso, Melhores oportunidades, Orçamento e Rotas flexíveis;
> `DO SISTEMA` em Saúde do sistema e Feriados/alta temporada; Urgência
> sem etiqueta, de propósito), e em Configurações a tabela de rotas mais
> os 6 campos de alerta legado viraram uma seção única que só existe
> para quem tem rota própria — com o form "Adicionar rota" fora do gate,
> sempre visível. O gate tem regra deliberadamente diferente por tela:
> Configurações conta todas as rotas (ativas + arquivadas, para
> preservar a aba "Arquivadas" e o botão "Reativar"), Dashboard conta só
> as ativas (lá não há caminho de volta a preservar). Nenhum token de
> cor novo, nenhuma coluna/query/RLS nova, nenhuma mudança de Telegram.
> Consequência aceita e registrada: usuário com 0 rotas ativas e N
> arquivadas perde o export CSV na UI (reversível). Fatia C
> (visibilidade cruzada entre usuários) segue fora de escopo, não
> implementada. Publicado no commit `b44a353`. Detalhe completo em
> `HISTORICO.md`, item 22; RLS de `routes` confirmada em produção e
> registrada no `AUDITORIA-MULTIUSUARIO.md`.
> Sessão anterior: Claude Code (08/08/2026) — **Fatia A CONCLUÍDA e
> publicada:** tema escuro por padrão + paleta em variáveis CSS no site
> estático (`docs/`), recorte puramente visual de um handoff maior de UI
> multi-usuário que não está aprovado — só esta fatia entrou, o resto
> (rótulos SÓ SEU/DOS DOIS, visibilidade cruzada entre usuários,
> separação pessoal×global em Configurações) segue fora de escopo. As 25
> variáveis já existentes em `:root` de `docs/css/style.css` ganharam
> bloco `:root[data-theme="dark"]`, mais 6 variáveis novas para literais
> sem token e 3 de sombra; alternância por `data-theme` em `<html>`,
> persistida só em `localStorage` (`flyiop-theme`, escuro é o padrão),
> script inline anti-flash nas 4 páginas, botão só em
> index/compras/config (`login.html` só herda o tema salvo), novo módulo
> `docs/js/theme.js`. Única exceção de JS fora de CSS: cor do gráfico
> Chart.js em `docs/js/dashboard.js`, lida via CSS var e recolorida ao
> vivo sem re-consultar o Supabase — aprovada explicitamente. Corrigido
> durante a implementação: 2 literais `#fff` catalogados como texto eram
> na verdade fundos (`input`/`select`, `.btn-outline-full`) — trocados
> para `var(--card)` pra não ficarem brancos no escuro. Testado com dados
> reais + harness sintético para estados sem cobertura nos dados atuais;
> usuário confirmou teste manual completo no navegador local antes do
> push. Publicado no commit `809eb2d`. Detalhe completo em
> `HISTORICO.md`, item 21. Frente independente das etapas multi-usuário —
> não desbloqueia nem bloqueia nada listado nas seções 3/4 abaixo.
>
> Sessão anterior: Claude Code (07/08/2026) — **Etapa 4.4 CONCLUÍDA:**
> `weekend_legs` vira somente-leitura no navegador. A policy de `UPDATE`
> para `authenticated` era vestígio do mundo pré-4.1/4.2 — desde as
> pendências 3/4/5 da Etapa 4.2 (03-04/08/2026) o painel escreve em
> `weekend_leg_user_state`/`settings`, nunca mais em `weekend_legs`; só o
> robô (`service_role`, ignora RLS) continua escrevendo lá. `SELECT`
> continua aberto para qualquer autenticado — isso não mudou. **Checagem de
> segurança antes de rodar** (`grep -rn "weekend_legs" docs/js/`): 11
> ocorrências em `compras.js`/`dashboard.js`, todas leitura — nenhum
> update/upsert/insert contra `weekend_legs`; confirma que o frontend não
> dependia da policy removida. Script
> [sql/etapa4_4_weekend_legs_readonly.sql](sql/etapa4_4_weekend_legs_readonly.sql)
> rodado manualmente no SQL Editor de produção em 07/08/2026. **Resultado
> real:** Guarda G0 — `policies_update_hoje = 1`,
> `view_effective_e_updatable = NO`; Parte A (`revoke update`) e Parte B
> (`drop policy`) sem erro; verificação final — `policies_update_depois =
> 0`, `authenticated_ainda_pode_update = false`, `anon_ainda_pode_update =
> false`. **Achado lateral:** `weekend_leg_effective` já não era
> atualizável antes deste script (view com join de múltiplas tabelas, sem
> `INSTEAD OF` trigger, grant só de `SELECT`) — o caminho de escrita pela
> view nunca foi real; este script fechou o único caminho de escrita que de
> fato existia (direto na tabela). Detalhe completo em `PLANO-ATIVO.md`,
> "Etapa 4.4".
>
> Sessão anterior: Claude Code (07/08/2026) — Etapa 4.3, Passo 5 CONCLUÍDO —
> **Etapa 4.3 ENCERRADA.** Script
> [sql/etapa4_3_verificacao_pos_drop.sql](sql/etapa4_3_verificacao_pos_drop.sql),
> 6 blocos (A, B, C, D1, D2, E) desenhados como colheita **independente** do
> Passo 3 (não reaproveitam as guardas G0–G4 do script do `DROP`), rodado
> manualmente no SQL Editor de produção em 07/08/2026. **Zero divergência em
> todos os 6 blocos**: as 5 colunas legadas continuam ausentes de
> `weekend_legs` (Bloco A), as 2 policies batem com o baseline de 01/08/2026
> texto a texto (Bloco B), zero trigger (Bloco C), a estrutura nova
> (`weekend_leg_user_state`/`weekend_leg_ceiling_audit`/`weekend_leg_effective`)
> segue intacta com 132 linhas na view (Bloco D1), prova via `pg_depend` de
> que a view não depende de nenhuma das 5 colunas removidas (Bloco D2), e o
> backup permanente `weekend_legs_legacy_columns_backup` continua com 132
> linhas mapeando 1:1 com as pernas vivas, zero órfão dos dois lados (Bloco
> E). Detalhe completo dos 6 resultados em `HISTORICO.md`, item 19, e
> `PLANO-ATIVO.md`, Etapa 4.3. **Etapa 4.3 CONCLUÍDA (07/08/2026), todos os
> 5 passos verificados** — segue em aberto só o Passo 2, pendência paralela
> e não bloqueante (resultado do resumo semanal do Telegram, a partir de
> segunda 10/08/2026).
>
> Sessão anterior: Claude Code (07/08/2026) — Etapa 4.3, Passo 4 CONCLUÍDO:
> notas de cabeçalho carimbadas em 7 scripts `sql/` que descrevem estrutura
> removida das 5 colunas de `weekend_legs`, e aposentadoria do Bloco A de
> `sql/etapa4_1_verificacao.sql` (comentado em bloco `/* */`, preservado como
> registro histórico — blocos B, C, D, E, F, F2, G e H continuam válidos e
> rodáveis). Fechamento da lista fina do Passo 4: `alvo_fins_de_semana.sql`
> saiu (falso positivo do grep — as colunas citadas são de `weekend_targets`,
> já dropada, não de `weekend_legs`; ganhou nota própria de risco separado) e
> `sql/etapa4_3_drop_colunas_legadas.sql` entrou (único script que já rodou
> contra produção sem carimbar isso). Fecha em 7 arquivos em escopo. Achado
> reforçado: `notas_pernas.sql` e `parte8_preco_pago.sql` são armadilha
> ativa — `alter table ... add column` sem guarda, recriam a coluna vazia
> sem dar erro se re-rodados. Detalhe completo em `PLANO-ATIVO.md`, Etapa
> 4.3, item 4.
>
> Sessão anterior: Claude Code (06/08/2026) — Etapa 4.3, Passo 3 CONCLUÍDO:
> backup + `DROP` das 5 colunas legadas de `weekend_legs` (`price_ceiling`,
> `status`, `notes`, `paid_price`, `purchased_at`) executados em produção pelo
> usuário no SQL Editor, com o script `sql/etapa4_3_drop_colunas_legadas.sql`
> desenhado nas sessões anteriores. Guardas G0–G4 passaram sem erro; resultado
> real da Parte B: `colunas_legadas_restantes = 0`, `linhas_no_backup = 132`.
> As 5 colunas não existem mais em `weekend_legs` — o estado por perna vive só
> em `weekend_leg_user_state`/`weekend_leg_effective` desde a 4.1/4.2. Backup
> `weekend_legs_legacy_columns_backup` (132 linhas, permanente) é a rota de
> volta, com receita de restauração completa (tipos e defaults reais) em
> comentário no próprio script. Passos 4 (notas de cabeçalho + aposentadoria
> do Bloco A de `sql/etapa4_1_verificacao.sql`) e 5 (verificação pós-`DROP`)
> não iniciados — dependem de revisão explícita no chat de planejamento antes
> de começar. Detalhe completo em `PLANO-ATIVO.md`, Etapa 4.3, e `HISTORICO.md`
> item 18.
>
> Sessão anterior: Claude Code (06/08/2026) — Etapa 4.3, Passo 3 desenhado:
> script `sql/etapa4_3_drop_colunas_legadas.sql` criado (Bloco 0 — inventário
> de definição, só leitura; Parte A — backup em
> `weekend_legs_legacy_columns_backup`, permanente, RLS ligada sem policies;
> Parte B — guardas G1–G4 + `DROP` das 5 colunas; receita de restauração em
> comentário), revisado em 3 rodadas no chat de planejamento paralelo. Achado
> registrado: `weekend_legs.price_ceiling` (congelado em R$250 desde
> 03/08/2026) e `settings.weekend_default_ceiling` (teto vivo, R$300 desde
> 04/08/2026) são números diferentes por desenho — a guarda G3 exige
> uniformidade do teto legado, não igualdade com o padrão vivo. O Passo 2
> (janela de observação até segunda) foi desacoplado do `DROP` na mesma
> sessão — não é mais pré-requisito, vira pendência de fechamento de registro
> (trazer o resumo semanal do Telegram em 10/08/2026). Execução real do
> script segue manual, pelo usuário, no SQL Editor — nada rodou contra
> produção nesta sessão. Detalhe completo em `PLANO-ATIVO.md`, Etapa 4.3.
>
> Sessão anterior: Claude Code (06/08/2026) — Etapa 4.2, pendência 13 fechada:
> `get_weekend_leg_counts` (resumo de segunda-feira) lia `weekend_legs.status`,
> coluna congelada desde as pendências 3/4 — relatava 0 compradas em silêncio
> desde 03/08. Achada no diagnóstico da Etapa 4.3 (chat paralelo), tratada como
> bug vivo da 4.2 e priorizada por ser bloqueadora da 4.3 (a query quebraria de
> vez após o `DROP` das colunas antigas). Corrigida para ler
> `weekend_leg_effective` (`bool_and(status='purchased')` por `leg_id` — mesma
> regra de "sai da fila" da pendência 9, aplicada ao complemento). Verificado
> via SQL: 132 pernas, 0 compradas, sem regressão; caminho real só roda às
> segundas, prova de produção da mensagem em si fica para a próxima
> segunda-feira. Commit `b22a569`, `origin/main == HEAD` confirmado. Detalhe
> completo em `PLANO-ATIVO.md`, Etapa 4.2, pendência 13.
>
> Sessão anterior: Claude Code (06/08/2026) — Etapa 4.2, verificação final do teto R$300 em produção: execução real do robô (não pulada por cota diária, "20/20 pernas checadas, 20 com preço", ~09:49 BRT) confirma as 22 ocorrências de teto no log todas em R$ 300, nenhuma em R$ 250; escolha determinística da pendência 7 confirmada no log (`settings de c72bf50e-... (1 usuário(s))`); zero erros. Fecha a lacuna que ficara pendente da sessão anterior. Detalhe em "Decisões vivas" (seção 2). Pendências 6/7(leve)/8/9/10 da Etapa 4.2 agora totalmente verificadas em produção — restam só as pendências 11 (em desenho separado) e 12 (backlog de UI). "Janela aberta 2" fechada de vez na parte do teto, com prova de produção; segue aberta só para fan-out/cooldown/mensagem por usuário (Etapa 6).
>
> Sessão anterior: Claude Code (05/08/2026) — Etapa 4.2, pendência 11 fechada com prova de produção: os blocos E/F/F2 de `sql/etapa4_1_verificacao.sql` (reescritos no commit `f50e55a`) rodaram no SQL Editor em produção e bateram exatamente com o esperado — Bloco E: `uid_visto=00000000-...-0001`, `papel_efetivo=authenticated`, `view_esp_0=0`, `estado_esp_0=0`, `auditoria_esp_0=0`; Bloco F: `uid_visto=c72bf50e-...`, `papel_efetivo=authenticated`, `view_esp_132=132`, `estado_esp_5=5`, `alienigena_esp_0=0`; Bloco F2: `uid_visto=c72bf50e-...`, `papel_efetivo=authenticated`, `escrita_alheia_esp_bloqueada="bloqueado 42501"`, `escrita_propria_esp_aceita="aceito"`. É a primeira prova real (não só reprodução num Postgres descartável) de isolamento positivo (F) e de RLS de escrita (F2) do projeto. Cabeçalho de `sql/etapa4_1_verificacao.sql` corrigido junto (dizia "nenhum insert" quando F e F2 fazem insert transitório dentro de transação com rollback; "Como usar" passou a citar o F2). `AUDITORIA-MULTIUSUARIO.md` ganhou notas de fechamento datadas nas três seções que ainda descreviam os defeitos antigos dos blocos E/F como pendentes, sem apagar o histórico da investigação original.
>
> Sessão anterior: Claude Code (05/08/2026) — Etapa 4.2, pendências 6/7(leve)/8/9/10: robô e `main.py` passaram a ler teto e status efetivos de `weekend_leg_effective` em vez de `weekend_legs` direto (commit `029ea61`). Verificado em produção sem regressão na fila (132 pernas). No caminho, achado o incidente de gravação do teto padrão (250→300→310→250 na mesma sessão de 04/08, terminando em 250 em vez de 300) — corrigido manualmente, ver seção 2. Housekeeping: `sql/etapa4_1_verificacao.sql` restaurado ao último commit (tinha resultados colados quebrando o SQL); `sql/etapa4_2_resync.sql` aposentado (hardcoded pro teto 250).
>
> Sessão anterior: Claude Code (02/08/2026) — três frentes sobre a **Etapa 4.1 multi-usuário**: (1) sincronização de documentação (detalhe no `HISTORICO.md`, item 17; tabelas em `AUDITORIA-MULTIUSUARIO.md`); (2) push dos três commits pendentes (`be81384`, `6e195c4`, `51a55ce`) — a **estrutura** existe no banco de produção desde 01/08 (rodada à mão no SQL Editor), os **arquivos `sql/`** existem no repositório desde este push, e as duas coisas nunca foram a mesma; (3) investigação da capacidade de prova dos blocos E e F: reprodução fiel num Postgres 16.14 descartável confirmou que **a estrutura se comporta corretamente** (isolamento OK), mas os blocos como escritos **têm prova mais fraca do que a documentação afirmava** — bloco E sólido no que registrou, com uma ressalva sobre o que o SQL Editor descarta; bloco F não discrimina hoje "usuário legítimo" de "dono do banco" (detalhe em `AUDITORIA-MULTIUSUARIO.md`, "Verificação das estruturas novas" e "Lacuna de evidência"). Bloco H (drop da sonda `flyiop_audit_selftest`) executado e confirmado. Itens (c) e (d) do diagnóstico de alerta fechados: (c) decidida — reavaliação vai para a 4.2, nascendo desligada; (d) resolvida na 4.1. **Vigente: regra de janela aberta — não editar teto no painel até a 4.2 fechar** (seção 4).
>
> Sessão anterior: Claude Code (01/08/2026) — fechamento do teste do caminho de alerta de perna de fim de semana (13 alertas enviados no Telegram = 13 registros gravados em `alert_log` com `leg_id`; caminho de alerta de perna confirmado de ponta a ponta, envio e gravação, nos dois tipos de gatilho — teto fixo e oportunidade); gatilho `on: push` removido do `daily.yml` (pendência (b) do `PLANO-ATIVO.md` resolvida) — confirmado via log do Actions que a última execução via push foi no-op (1m03s, sem scraping, sem Telegram), como previsto pela análise de código; `realert_days` ajustado para 1 em `settings` (confirmado via SELECT, `user_id c72bf50e-16f7-48fd-9c86-7b49dea1551e`); estágio do escalonamento automático consultado: 0 (via `bot_state`, chave `weekend_scrape_stage`) — só ~4 dias desde 28/07/2026, abaixo dos 5 dias limpos necessários pra subir; `RUNBOOK.md` ganhou a consulta de stage.

---

## 1. Status atual

FlyIop está em produção, monitorando 66 fins de semana (132 "pernas" ida/volta independentes) na rota RIO↔BSB entre set/2026 e dez/2027. A fila real de rotação do lote `fli` hoje é de **43 pernas elegíveis** (dentro da janela deslizante de 183 dias) — não 132; com o lote de 20/dia, a fila dá uma volta completa a cada ~3 dias (medido em 31/07/2026, ver `PLANO-ATIVO.md`). Fonte primária de preço é a `fli` (endpoint interno do Google Flights, migrada de `fast-flights` por bug de parsing), com Travelpayouts como cache secundário — desde a Parte 9 (28/07/2026), a `fli` também grava companhia aérea e horário de partida. Cada perna expira da rotação de forma independente pela própria data (D+1 de margem), não mais pela data de ida do weekend inteiro — corrigido bug que cortava a perna de volta 2-3 dias antes da hora. Desde a Parte 10 (28/07/2026), a frequência do lote `fli` escalona automaticamente em 3 estágios (1x/2x/3x por dia) conforme dias consecutivos sem bloqueio, com reversão imediata pro Estágio 0 em qualquer bloqueio detectado e teto automático no Estágio 2 — só a **primeira execução do dia** (não mais uma hora fixa — corrigido em 30/07/2026, ver item 15 do `HISTORICO.md`) roda rotas flexíveis/cache Travelpayouts/notificações, as execuções extras do mesmo dia só rodam o lote `fli`. Robô via GitHub Actions grava no Supabase (**cron restaurado para 2x/dia (08h/20h BRT) em 03/08/2026** — havia sido reduzido pra 1x/dia em 29/07/2026 enquanto se confirmava a correção do bug de agendamento; ver seção 3, item 1; decisão de rodar em Python); alertas via bot Telegram (FlyIopBot); site em GitHub Pages com 3 páginas (Dashboard, Compras, Configurações), login via Supabase Auth. Painel de Compras já tem: cards por fim de semana, teto editável por perna, campo de notas (localizador/horário), campo de valor pago, filtros (chips), selos de feriado/alta temporada, estado visual salvo/não-salvo/em-edição (âmbar), hierarquia visual por preço/status (perna comprada com identidade forte, card 2/2 colapsando por padrão com total pago). Dashboard redesenhado (ação do dia, urgência, progresso, oportunidades, orçamento, saúde do sistema); progresso/orçamento contam só a partir do fim de semana de 29/01/2027, oportunidades separadas em "abaixo do teto" (ação) e "mais baratas no momento" (informação). Alerta de bloqueio do scraping agora é rico e escalona por dias consecutivos. As 3 rotas flexíveis antigas (BSB→GIG, GIG→BSB, RIA→BSB) continuam rodando em paralelo, tratadas como legado.

## 2. Decisões vivas

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
- **DECIDIDO (chat de planejamento, 11/08/2026): o Telegram passa a respeitar a janela de compra (fins de semana ≥ 29/01/2027) nos dois caminhos onde hoje não respeita.**
  - **(a) Alerta de oportunidade** (`weekend_opportunity_pct`) — hoje dispara por queda percentual contra a média histórica, independentemente do teto e da janela de compra. Passa a disparar só para pernas de fins de semana ≥ 29/01/2027.
  - **(b) Resumo semanal** ("Resumo semanal — pernas RIO↔BSB") — as duas listas ("Mais baratas agora" e "Mais próximas") passam a considerar só pernas ≥ 29/01/2027, e o denominador do contador ("X de N pernas compradas") deixa de ser 132 fixo e passa a contar só as pernas dentro da janela de compra — mesma regra que o Dashboard já usa pra progresso/orçamento desde 28/07/2026 (não hardcodar um número novo; confirmar o valor real na implementação, não estimar agora).
  - **Motivo:** fins de semana anteriores a 29/01/2027 são monitorados intencionalmente como fonte de histórico de preço (decisão de 28/07/2026) e nunca serão comprados; alertar/contabilizar sobre eles só polui o canal.
  - **Evidência observada (10-11/08/2026, resumo semanal e alerta reais):** "Mais baratas agora" listou 9 de 10 pernas anteriores a 29/01/2027 (só a de 29/01/2027 ida estava dentro da janela); "Mais próximas" listou as 10 pernas fora da janela (09/10/2026 a 04/12/2026, 100% fora); alerta de oportunidade recebido pro fim de semana de 25/12/2026, 19,6% abaixo da média (R$425,00 contra teto R$300) — fora da janela.
  - **Inconsistência que esta decisão corrige:** o Dashboard já conta progresso/orçamento só a partir de 29/01/2027; o Telegram contava as 132 pernas inteiras — os dois respondiam a mesma pergunta com números diferentes.
  - **IMPORTANTE: a implementação desta decisão pertence à Etapa 6 e ainda NÃO foi feita.** Nenhum código mudou nesta rodada, só o registro da decisão.

## 3. Próximos passos (ordem sugerida)

1. ✅ **Cron de `daily.yml` restaurado para 2x/dia (08h/20h BRT) em 03/08/2026.** Reduzido pra 1x/dia em 29/07/2026 enquanto se corrigia o bug de agendamento (item 15 do `HISTORICO.md`). Sequência:
   a) ✅ `realert_days` ajustado para 1 em `settings` (confirmado 01/08/2026 via SELECT — `user_id c72bf50e...`, `realert_days = 1`).
   b) ✅ Observação do cooldown/realert com `alert_log` de 01–02/08/2026 feita no chat de planejamento (03/08/2026).
   c) ✅ Decisão: 2x/dia, não 3x/dia — motivo: fila de ~43 pernas elegíveis, 40 slots em 2x/dia já cobre quase toda ela; 3x geraria recheque duplicado de parte da fila. Janela de 14h BRT avaliada e descartada. Cron restaurado nesta data (03/08/2026).
   d) Estágio do escalonamento automático confirmado em 0 (consulta feita no chat de planejamento em 03/08/2026: `select value from bot_state where key = 'weekend_scrape_stage'` retornou 0) — a rampa de 5 dias limpos por estágio começa do zero a partir de agora.
2. **Etapa 4 da iniciativa multi-usuário** (`weekend_leg_user_state` — teto/status/notas/valor pago por usuário, o núcleo do trabalho que falta), **quebrada em três degraus: 4.1 / 4.2 / 4.3**:
   - **4.1 — ✅ concluída e verificada (01/08/2026).** Estrutura nova criada no banco de produção (rodada à mão no SQL Editor) e verificada com os blocos A–G; nada em `src/` ou `docs/` lê a estrutura nova ainda, o sistema se comporta exatamente como antes. Ver `HISTORICO.md`, item 17.
   - **4.2 — pendências 1–11 e 13 concluídas e verificadas em produção; resta a 12.** É a virada de leitura: frontend e robô passam a ler/escrever a estrutura nova. 12 pendências nomeadas no `PLANO-ATIVO.md`; **pendências 3 e 4 (`docs/js/compras.js` e o botão "aplicar teto a todos") concluídas, commitadas e enviadas ao remoto em 03/08/2026** (commits `531f34f` e `9436bc0`, `origin/main == HEAD` confirmado), com verificação manual completa no site publicado. **Pendências 1 e 2 (re-sync do estado) concluídas e executadas em produção em 04/08/2026** (`sql/etapa4_2_resync.sql`, mantido no repo mas **aposentado em 05/08/2026** — hardcoded pro teto de 250, não reutilizável sem revisão) — resultado: zero divergência, nada precisou ser copiado. **Pendência 5 (`docs/js/dashboard.js` lendo `weekend_leg_effective`, mesma troca de fonte de `compras.js`) concluída, commitada e enviada em 04/08/2026** (commits `05c6f97` e `c19329f`, `origin/main == HEAD` confirmado), com verificação manual no site publicado — teto individual (override) salvo em Compras refletido de forma consistente no Dashboard. **Pendências 6/7(leve)/8/9/10 concluídas, commitadas e verificadas em produção em 05/08/2026** (commit `029ea61`, `origin/main == HEAD` confirmado): o robô (`weekends.py`, `live_check.py`, `telegram_notifier.py`) e `main.py` passaram a ler o teto e o status efetivos de `weekend_leg_effective`, em vez de `weekend_legs.price_ceiling`/`status` direto. Verificação de produção (execução manual, 05/08/2026): fila de pernas idêntica à de antes (132 pernas, nenhuma entrou ou saiu por causa da mudança); teto efetivo funcionando — override de R$555 da perna Ida 04/09 confirmado tanto via SQL (`weekend_leg_effective`) quanto no log da execução. **Pendência 10 (ordenação da fila pelo menor teto entre usuários) já estava resolvida como efeito colateral da pendência 6** — `live_check.py` lê o mesmo `effective_ceiling` que `get_active_legs()` já resolve com MIN, sem trabalho extra. **Verificação de produção do teto R$300 em si CONCLUÍDA em 06/08/2026**: execução real do robô (não pulada por cota diária — "20/20 pernas checadas, 20 com preço", ~09:49 BRT) registrou todas as 22 ocorrências de teto no log em R$300, nenhuma em R$250; zero erros. Fecha a lacuna aberta pelo incidente de gravação de 04/08 — ver "Decisões vivas". **Pendência 13 (`get_weekend_leg_counts` lendo `weekend_legs.status` congelado, resumo de segunda-feira sempre relatando 0 compradas) concluída em 06/08/2026** (commit `b22a569`) — achada no diagnóstico da Etapa 4.3 mas tratada como bug vivo da 4.2, bloqueadora do `DROP` das colunas antigas; passou a ler `weekend_leg_effective`; verificado via SQL (132 pernas, 0 compradas, sem regressão), prova de produção da mensagem real fica para a próxima segunda-feira. Detalhe em `PLANO-ATIVO.md`. Restam a reavaliação de teto fora da coleta (decidida em 02/08, nasce desligada por chave em `system_config`) e a pendência 12 (backlog de UI, não iniciada) — a 11 foi concluída em 05/08/2026, com prova de produção. **A regra de janela aberta (seção 4) está encerrada desde 04/08/2026; a "Janela aberta 2" (painel novo × Telegram velho) está encerrada de vez na parte do teto, agora com prova de produção (06/08/2026)** — segue aberta só para fan-out de alerta por usuário, cooldown/dedup por usuário e limiares gerais individualizados, que são a Etapa 6 (detalhe no `PLANO-ATIVO.md`).
   - **4.3 — CONCLUÍDA (07/08/2026), todos os 5 passos verificados.**
     Remoção das 5 colunas antigas de `weekend_legs`. Passo 1 (código do
     ramo degradado) concluído, commit `d5f97eb`. **Passo 2 desacoplado do
     `DROP`** (06/08/2026) — pendência PARALELA de fechamento de registro,
     não bloqueante, segue em aberto (ver item 5 abaixo). **Passo 3
     CONCLUÍDO (06/08/2026):** backup íntegro (132 linhas) e `DROP`
     executado em produção, zero colunas legadas restantes, confirmado por
     select. **Passo 4 CONCLUÍDO (07/08/2026):** notas de cabeçalho nos 7
     scripts `sql/` em escopo (a lista fina fechou diferente da contagem
     original — `alvo_fins_de_semana.sql` saiu, `etapa4_3_drop_colunas_legadas.sql`
     entrou) + aposentadoria do Bloco A de `sql/etapa4_1_verificacao.sql`.
     **Passo 5 CONCLUÍDO (07/08/2026):** verificação pós-`DROP`
     independente (`sql/etapa4_3_verificacao_pos_drop.sql`, 6 blocos, zero
     divergência) — detalhe completo em `HISTORICO.md`, item 19, e
     `PLANO-ATIVO.md`, Etapa 4.3.
   - **4.4 — CONCLUÍDA (07/08/2026).** `weekend_legs` vira somente-leitura
     no navegador — `revoke update` + `drop policy` dos papéis `anon`/
     `authenticated`, `SELECT` inalterado. Checagem de segurança prévia
     (`grep` em `docs/js/`) confirmou zero escrita contra `weekend_legs` no
     frontend. Script
     [sql/etapa4_4_weekend_legs_readonly.sql](sql/etapa4_4_weekend_legs_readonly.sql),
     zero divergência no resultado real. Detalhe em `PLANO-ATIVO.md`, Etapa
     4.4. **Fecha só o lado de escrita da RLS "genérica" de `weekend_legs`
     registrada na seção 4 (Bloqueios)** — o lado de leitura (qualquer
     autenticado ainda enxerga todas as linhas de `weekend_legs`/`weekends`)
     segue sem alteração, é pendência separada a resolver antes da Etapa 7.

   **Etapa 5** (frontend por usuário) — **CONCLUÍDA POR COMPOSIÇÃO em 08/08/2026.** Os três itens do escopo original foram cobertos por trabalho feito sob outros nomes: "`weekend_legs` somente-leitura no navegador" = Etapa 4.4 (07/08/2026); "redesenho de RLS de update" = Etapa 4.1, RLS de `weekend_leg_user_state`, provada nos blocos F/F2; "Compras/Dashboard por usuário logado" = funcionalmente pela Etapa 4.2 (pendências 3/5, leitura via `weekend_leg_effective`), visualmente pelas Fatias A/B (UI, `HISTORICO.md` itens 21/22). Ver seção 4 e item 5 do "Ordem de execução" em `PLANO-ATIVO.md`.

   **Fatia C — visibilidade de compra entre usuários — CONCLUÍDA (Parte 1 banco 10/08/2026, Parte 2 frontend 11/08/2026).** Terceira fatia do handoff de UI multi-usuário (depois das Fatias A e B, `HISTORICO.md` itens 21/22) — a única que toca o banco. Regra de produto: o outro usuário vê QUE você comprou uma perna e EM QUAL VOO, nunca quanto pagou/teto/localizador, só depois de `status = 'purchased'`. Mecanismo: tabela de projeção (`weekend_leg_purchase_shared`) mantida por trigger `security definer`, com só os 3 campos de voo — nenhum campo sensível chega a existir na tabela compartilhada; view/função `security definer` avaliadas e descartadas por serem bypass de RLS. Script [sql/fatia_c_visibilidade_compra.sql](sql/fatia_c_visibilidade_compra.sql) rodado manualmente no SQL Editor de produção em 10/08/2026, os 5 blocos de verificação (G0 + V1-V4) batendo 100% com o esperado. **Parte 2 (frontend)** (`docs/js/compras.js`, `docs/css/style.css`; `docs/compras.html` não tocado) — painel de confirmação de compra, bloco de edição pós-compra, linha "outro usuário já comprou" no card — commitada/enviada (`ca54dd8`, 11/08/2026) e com roteiro de verificação manual em produção **100% passado** (sem erro no console, sem regressão). O item mais sensível, a linha do outro usuário, segue sem verificação positiva possível (só na Etapa 7, quando a segunda conta existir) — limite estrutural, não pendência. **Detalhe completo, resultado real bloco a bloco e roteiro de verificação, em `HISTORICO.md`, item 23** (movido de `PLANO-ATIVO.md`, que mantém só um ponteiro de uma linha).

   **Desejo do usuário, registrado em 02/08/2026: criar a conta do segundo usuário — objetivo ativo, não recusado.** Bloqueado pela regra dura da Etapa 7 (`PLANO-ATIVO.md`), que exige 4.2/4.3/5/6 concluídas antes. **Os dois desejos registrados em 02/08/2026 (aumentar frequência do scraping, item 1 acima, e criar a conta do segundo usuário) são objetivos ativos, nenhum recusado — o caminho para os dois é concluir a Etapa 4.2.**
3. ✅ **Concluído (04/08/2026, corrigido em 05/08/2026, verificado em produção em 06/08/2026).** Teto padrão recalibrado de R$250 para R$300 — ver seção 2, "Decisões vivas", pelo incidente de gravação, a correção manual e a prova final de produção.
4. **Observar o escalonamento automático rodando em produção** — acompanhar via Dashboard (seção "Saúde do sistema") se o estágio sobe conforme esperado e se algum bloqueio real acontece nos volumes mais altos (40/60 pernas·dia); agora depende de o cron 2x/dia estar restaurado (item 1) pra ter mais de 1 execução/dia pra observar.
5. ✅ **Concluído (11/08/2026).** Resultado do resumo semanal do Telegram de
   segunda-feira 10/08/2026 trazido e registrado: recebido pelo usuário às
   08:42 BRT, "0 de 132 pernas compradas", sem erro — fecha a prova de
   produção da pendência 13 da Etapa 4.2 (`get_weekend_leg_counts`, commit
   `b22a569`). Resultado completo em `PLANO-ATIVO.md`, Etapa 4.3, Passo 2.

## 4. Bloqueios / perguntas em aberto

- **Multi-usuário (amigo que também vai comprar RIO↔BSB em 2027):** iniciativa ativa, em execução por etapas — ver `PLANO-ATIVO.md`. Escopo completo (alertas + painel + aba Compras próprios); Telegram em grupo único compartilhado, mensagem identifica nome+teto de quem disparou. Etapas 1-3 concluídas e confirmadas em produção (Etapa 3 só foi confirmada rodando de fato em 30/07/2026, depois da correção do bug de agendamento — ver item 15 do `HISTORICO.md`). **Etapa 4 quebrada em 4.1 / 4.2 / 4.3: a 4.1 está concluída e verificada (01/08/2026)** — estrutura de decisão pessoal por perna criada no banco de produção pelo SQL Editor e verificada com os blocos A–G (ver item 17 do `HISTORICO.md`); os arquivos `sql/` correspondentes estão no repositório desde o push de 02/08/2026 (`be81384`). **A capacidade de prova dos blocos E e F foi revisada em 02/08/2026** — o comportamento da estrutura está confirmado (isolamento OK), mas os blocos como escritos hoje têm prova mais fraca do que se pensava; detalhe e pendência de correção em `AUDITORIA-MULTIUSUARIO.md` e `PLANO-ATIVO.md` (item 11 da 4.2). **A 4.2 (virada de leitura) está em execução, com 13 pendências nomeadas no `PLANO-ATIVO.md`** (12 concluídas — 1–11 e 13; resta só a 12, backlog de UI — ver item 2 abaixo, seção 3); a 4.3 (remover colunas antigas) vem depois dela. **Etapa 5 (frontend por usuário) — concluída por composição (08/08/2026):** "`weekend_legs` somente-leitura no navegador" = Etapa 4.4 (07/08/2026); "redesenho de RLS de update" = Etapa 4.1, RLS de `weekend_leg_user_state`, provada nos blocos F/F2; "Compras/Dashboard por usuário logado" = funcionalmente pela Etapa 4.2 (pendências 3/5, leitura via `weekend_leg_effective`), visualmente pela Fatia A/B (UI, `HISTORICO.md` itens 21/22). **Atualização (01/08/2026):** o teste do caminho de alerta de perna (ver item 16 do `HISTORICO.md`) foi concluído e o caminho confirmado em produção — o gate que ele impunha sobre a Etapa 6 (Telegram por usuário) caiu. Etapa 6 segue exigindo, como todas as etapas, revisão explícita no chat de planejamento antes de rodar — não há mais nenhuma dependência de teste pendente.

- **✅ ENCERRADO (04/08/2026) — regra de janela aberta (4.1 → 4.2): não editar teto no painel.** Entre a 4.1 e a 4.2 o estado vivia em dois lugares. O painel e o robô continuavam lendo e escrevendo o mundo antigo (`weekend_legs`); o mundo novo (`weekend_leg_user_state`) existia mas ficava parado na fotografia do dia da cópia. Teto editado no painel nesse intervalo iria para a coluna velha, fora do alcance da auditoria nova, e o re-sync da 4.2 teria que transformá-lo em **override explícito**. **Fechado por execução real do re-sync** (pendências 1 e 2 da Etapa 4.2, `sql/etapa4_2_resync.sql`, 04/08/2026): zero teto preso na coluna velha, zero divergência de estado. Já estava tecnicamente encerrado desde 03/08/2026 (pendências 3/4 — painel parou de escrever em `weekend_legs.price_ceiling`); a execução do re-sync fecha o registro formal do intervalo. Texto histórico mantido para contexto. Detalhe no `PLANO-ATIVO.md`, seção "Etapa 4.2".
- **Pedido de antecipar a criação da conta do segundo usuário: avaliado e recusado (31/07/2026).** Motivo: `price_ceiling`/`status`/`notes`/`paid_price` ainda são globais e a RLS de `weekend_legs` é genérica hoje — qualquer autenticado podia sobrescrever o dado do outro, sem auditoria de teto pra reconstruir depois, corrigido pela Etapa 4.4 (07/08/2026) (ver `AUDITORIA-MULTIUSUARIO.md` e pendência (d) do diagnóstico de alerta em `PLANO-ATIVO.md` — **a parte da auditoria foi resolvida pela Etapa 4.1 em 01/08/2026**; as colunas globais e a RLS genérica de `weekend_legs` continuam como estavam, então a recusa segue de pé). A regra dura (conta nova só na Etapa 7) permanece. Alternativa considerada e descartada: travar `weekend_legs` como somente-leitura via RLS temporária — descartada por mexer em política de segurança em produção, risco de falha silenciosa ao salvar no frontend, e por ser trabalho descartável. Enquanto isso, a necessidade real do segundo usuário ("ver preço e saber quando comprar") é atendida manualmente pelo usuário principal. **Lado de leitura fechado (08/08/2026):** decisão de produto tomada no chat de planejamento — dado objetivo de voo (preço atual, companhia, horário, menor preço visto, calendário dos fins de semana) é compartilhado entre usuários, decisão consciente. Confirmado por diagnóstico só-leitura em duas partes (catálogo de RLS + personificação de usuário fictício via `set local role authenticated` em transação com rollback, mesma técnica do bloco F da 4.1): zero divergência do esperado em todas as 16 tabelas/views verificadas — nenhuma tabela de decisão pessoal (`weekend_leg_user_state`, `weekend_leg_ceiling_audit`, `weekend_legs_legacy_columns_backup`) é legível por outro usuário; `weekend_legs`/`weekends`/histórico de preço/run log de perna são, como esperado, visíveis a qualquer autenticado. Achado de higiene sem ação necessária: `grant_select_anon = true` aparece em todas as tabelas (padrão de fábrica do Supabase, role grant — não RLS); a policy de linha continua sendo a barreira real, confirmada pela própria personificação. **Isso fecha só o lado de leitura.** O lado de escrita já tinha sido fechado pela Etapa 4.4 (07/08/2026). A pendência da RLS "genérica" está encerrada nos dois lados. Não bloqueia mais a Etapa 7 por este motivo — a Etapa 7 segue bloqueada pela Etapa 6, ainda não iniciada — a Etapa 5 foi concluída por composição (ver acima).

  **Resumo para colar em novo chat de planejamento:** iniciativa multi-usuário em andamento (7 etapas, ver `PLANO-ATIVO.md`). Etapas 1-3 concluídas: `routes`/`settings` já são per-user (RLS confirmada); policy de `alert_log` corrigida em produção (cobre `leg_id`); config de sistema (`suspicious_below_avg_pct`, `fast_flights_enabled`, `fast_flights_daily_batch_size`) migrada para `system_config` (linha única, sem dono, edição só via SQL Editor — ver `RUNBOOK.md`), colunas antigas em `settings` intocadas por ora (Etapa 3b de remoção pendente). **Etapa 4.1 concluída e verificada (01/08/2026):** existem no banco de produção `weekend_leg_user_state` (teto/status/notas/valor pago por perna × usuário, modelo preguiçoso — a linha só nasce quando o usuário decide algo), `settings.weekend_default_ceiling` = 250, `weekend_leg_ceiling_audit` (append-only, alimentada por trigger, pega até edição no SQL Editor) e a view `weekend_leg_effective` (`security_invoker`); verificada com os blocos A–G (mundo antigo intacto, isolamento entre usuários OK, carimbo de origem por `request.jwt.claims` — **a capacidade de prova de E e F foi revisada em 02/08/2026**, comportamento confirmado por reprodução num Postgres descartável, mas os blocos como escritos discriminam menos do que a redação original afirmava); os arquivos `sql/` estão no repositório desde o push de 02/08/2026. **A Etapa 4.2 (virada de leitura) está em execução, com 12 pendências nomeadas no `PLANO-ATIVO.md`.** Pendências 3 e 4 concluídas, commitadas e enviadas em 03/08/2026 (`531f34f`, `9436bc0`) — o painel (`docs/js/compras.js`) já lê `weekend_leg_effective` e escreve em `weekend_leg_user_state`, com verificação manual completa no site publicado. Pendências 1 e 2 (re-sync do estado) concluídas e executadas em produção em 04/08/2026 (`sql/etapa4_2_resync.sql`, mantido no repo, re-rodável) — **resultado: zero divergência**, nada precisou ser copiado do mundo antigo. Pendência 5 (`docs/js/dashboard.js`) concluída, commitada e enviada em 04/08/2026 (`05c6f97`, `c19329f`) — o Dashboard também passou a ler `weekend_leg_effective`, verificado no site publicado com um override de teto concordando entre Compras e Dashboard. Restam as pendências 6–12; a 4.3 remove as colunas antigas de `weekend_legs` depois. **Regra de janela aberta ENCERRADA (04/08/2026)** — confirmada pela execução do re-sync sem divergência, já estava tecnicamente fechada desde as pendências 3/4. O teste do caminho de alerta de perna já foi concluído em 01/08/2026, então a Etapa 6/Telegram não depende mais de teste nenhum, só da revisão explícita de praxe. RLS de `weekend_legs`/`weekends`: lado de escrita fechado pela Etapa 4.4 (07/08/2026), lado de leitura fechado por decisão de produto + diagnóstico em 08/08/2026 (dado de mercado compartilhado, decisão consciente) — ambos deixaram de ser motivo de bloqueio da Etapa 7; a Etapa 5 foi concluída por composição em 08/08/2026, ela segue bloqueada só pela Etapa 6; Telegram é hardcoded a 1 chat_id, resolvido pela decisão de grupo único; robô sempre usa service_role (nunca passa por RLS). Detalhe completo em `AUDITORIA-MULTIUSUARIO.md`. Regra dura: criar a conta do segundo usuário é sempre a última etapa. Teto padrão recalibrado de R$250 para R$300 em 04/08/2026 (decisão do usuário via painel — ver seção "Decisões vivas").
- **HIPÓTESE NÃO CONFIRMADA:** `alert_log` ter ficado com 0 registros de `leg_id` entre 23/07 e 31/07/2026 é provavelmente consequência do bug de agendamento corrigido em 30/07/2026 (item 15 do `HISTORICO.md`) — sem execução primária, nenhum alerta de perna chega a ser avaliado, silenciosamente e com exit 0. Reforça a hipótese o fato de 6 dos 13 alertas de 01/08/2026 serem orgânicos (`weekend_opportunity_pct`, teto normal), sem relação com o teste com tetos elevados artificialmente.
- **Ponto de atenção aberto:** o cooldown/dedup de perna nunca operou com dado real (`alert_log` estava vazia até 01/08). A execução de 02/08/2026 é a primeira observação real desse mecanismo — verificar se os 6 alertas de oportunidade de 01/08 se repetem indevidamente. Restaurar o cron pra 3x/dia (seção 3, item 1) só depois dessa observação.
- **OBSERVAÇÃO DO ROBÔ 02/08/2026, PARCIAL.** A execução das 08:54 BRT rodou e alertou (2 alertas de rota legado + 2 de oportunidade de perna). **A conclusão sobre cooldown/dedup NÃO foi tirada** — depende de consulta à `alert_log` comparando 01/08 e 02/08, ainda não feita. Continua valendo: não restaurar o cron para mais de 1x/dia antes dessa conclusão (seção 3, item 1).
- **✅ DECIDIDO em 11/08/2026 (era "ACHADO NOVO A DECIDIR", 02/08/2026):** os 2 alertas de oportunidade da execução das 08:54 de 02/08 dispararam para o fim de semana de 18/09/2026 (ida R$424, volta R$423, teto R$250) — fim de semana **anterior** a 29/01/2027, ou seja, fora da janela de compra, que por decisão de escopo nunca será comprado. O caminho de oportunidade (`weekend_opportunity_pct`) alerta por queda percentual contra a média histórica, **independentemente do teto e da janela de compra**. O Dashboard já separa ação de informação para esse mesmo caso; o Telegram não. **Decidido em 11/08/2026** (ver seção 2, "Decisões vivas"): o alerta de oportunidade passa a respeitar a janela de compra — implementação pertence à Etapa 6, ainda não feita.
- **EXPOSIÇÃO CONHECIDA E ACEITA:** o `user_id` do Supabase do usuário (`c72bf50e-…`) aparece por extenso na documentação de um repositório **público**. Risco avaliado como baixo — UUID não é credencial, e a RLS exige JWT assinado, que não se forja conhecendo o identificador. Registrado como decisão consciente, não como descuido.
- **TAXA DE `no_data` DE 85% EM 02/08/2026:** 152 checagens no dia, 23 `ok`, 129 `no_data`. Detector de bloqueio **não disparou** (`bloqueio_detectado = false`, 4 dias limpos). Usuário avaliou que o scraping está funcionando bem e **decidiu não acionar o kill-switch**. Registrado como observação, não como incidente. Revisitar só se repetir.
- **DETECTOR DE BLOQUEIO POSSIVELMENTE MAL CALIBRADO:** o limiar documentado (sucesso <50% com amostra ≥8) não disparou apesar de 85% de falha no dia. **Não investigado a fundo** — mas a investigação do item de volume abaixo já apurou um dado relevante: o detector (`live_check.py:218-220`) calcula `success_rate` só sobre o lote `fli` do dia, nunca sobre o total (o lote cache, que historicamente erra ~98% das pernas, não entra nessa conta). Se essa leitura estiver certa, não é miscalibração de limiar — é escopo: o detector nunca teve a intenção de olhar o dia inteiro, só o lote que ele mesmo executa. Revisar essa leitura antes de mexer no limiar.
- **VOLUME DE CHECAGENS ACIMA DO PREVISTO — investigado e explicado (02/08/2026).** 152 checagens/dia contra `batch_size` 20 e ~43 pernas elegíveis pareciam divergentes. Leitura de código (`weekends.py`, `live_check.py`, `scrape_schedule.py`) explica o número: são dois lotes com escopos diferentes somados, cada um gravando 1 linha por perna, sem retentativa gerando linha extra — **cache** (`process_all_weekend_legs`/`get_active_legs`) roda TODA perna `monitoring` não expirada, **sem limite de janela de meses à frente** (~132 pernas), e **lote ao vivo** (`run_daily_batch`/`select_batch`) é o único limitado por `batch_size` (20) e pela janela de 183 dias. 132 + 20 = 152, bate exato. **IMPEDITIVO ATUAL para aumentar a frequência do cron:** enquanto não se souber se o volume do cache (sem limite de janela, ~132/dia, roda 1x/dia independente do estágio) muda com o aumento de frequência do lote `fli`, multiplicar a frequência viola a regra de scraping discreto. Achado registrado, decisão não tomada nesta tarefa.
- **✅ DECIDIDO em 11/08/2026 — ALERTA DE OPORTUNIDADE (E RESUMO SEMANAL) FORA DA JANELA DE COMPRA** — ver item acima ("DECIDIDO em 11/08/2026") e seção 2, "Decisões vivas", para o texto completo da decisão (que passou a cobrir também o resumo semanal, não só o alerta de oportunidade). Implementação pertence à Etapa 6, ainda não feita.
- **PERGUNTA ABERTA, REGISTRADA 11/08/2026 — "execução extra do dia" parece pular Travelpayouts, não só rotas flexíveis.** O item 1 da seção 1 já documenta que só a primeira execução do dia roda "rotas flexíveis/cache Travelpayouts/notificações", com as execuções extras rodando só o lote `fli`. Em observação recente, o usuário notou que a execução extra também não roda Travelpayouts — ainda não está claro se isso é exatamente esse comportamento já documentado (e portanto intencional) ou um achado novo/divergente. **Travelpayouts deve continuar rodando normalmente** — não é decisão de reduzir seu uso. **Sem ação agora** — só registrado para não esquecer; investigar em sessão futura antes de tirar conclusão.

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
- `PLANO-ATIVO.md` — plano técnico detalhado só da Parte em execução agora. **Não está vazio (11/08/2026):** contém a iniciativa multi-usuário (Etapa 4.2 com as 13 pendências nomeadas — 12 concluídas, 1–11 e 13, restando só a 12, backlog de UI — e o histórico da regra de janela aberta, encerrada; Etapas 4.3 e 4.4 concluídas e verificadas em produção), o que restou do diagnóstico de alerta de perna (item (e), perguntas abertas) e as pendências de escopo separado. A **Fatia C (visibilidade de compra entre usuários), CONCLUÍDA (Parte 1 banco + Parte 2 frontend), foi movida para o `HISTORICO.md` (item 23)** — `PLANO-ATIVO.md` mantém só um ponteiro de uma linha.
- `HISTORICO.md` — tudo já decidido/implementado, cronológico
- `CLAUDE.md` — escopo geral do projeto (lido automaticamente pelo Claude Code)
- `PROTOCOLO-DE-TRABALHO.md` — como usuário e Claude Code trabalham juntos (Plan Mode, gatilhos de revisão, regra de manutenção dos três arquivos de documentação)
- `RUNBOOK.md` — operações manuais sem UI própria (kill-switch e outros ajustes de `system_config` via SQL Editor)
