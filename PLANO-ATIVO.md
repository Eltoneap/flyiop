# Plano Ativo — FlyIop

_Atualizado em 02/08/2026. Contém só o que está em execução ou pendente de aprovação/implementação. Tudo que já foi entregue (com data e decisões tomadas) está em `HISTORICO.md` — referencie por lá em vez de reproduzir aqui._

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

### (a) e (b) ✅ CONCLUÍDOS (01/08/2026) — movidos para o `HISTORICO.md`

Caminho de alerta de perna confirmado em produção (13 alertas gravados em
`alert_log`) e gatilho `push` removido do `daily.yml`. Detalhe completo no
`HISTORICO.md`, item 16.

### (c) ✅ DECIDIDA (chat de planejamento, 02/08/2026) — reavaliação fora da coleta

`should_alert` só é calculado no momento em que a perna é checada. O robô
nunca reavalia um `current_price` já salvo contra um teto novo. Consequência:
editar o teto no site não tem efeito nenhum no Telegram até a perna voltar
na rotação (hoje ~3 dias, ver item 1 do `STATE.md`). Isso afeta diretamente
a recalibração do teto padrão (`STATE.md`, seção 3): baixar o teto não muda
comportamento de alerta até cada perna dar a volta, sem sinal disso em lugar
nenhum. Nunca foi decisão explícita — é herança do código.

**Decisão: opção (a), e vai para a Etapa 4.2.** A reavaliação roda **ao fim de
cada execução primária**, **sem nenhuma chamada extra de scraping** (reavalia
o `current_price` já salvo, não busca preço novo), com **trava de frescor**
(preço velho demais não vira alerta). Descartadas: (b) empurrar a perna pro
topo da fila e (c) documentar o atraso como esperado.

**Nasce DESLIGADA**, por chave em `system_config` — só é ligada depois que a
observação do cooldown com dado real (`STATE.md`, seção 3, item 1b) confirmar
o comportamento. Motivo: reavaliar todas as pernas a cada execução multiplica
o número de oportunidades de alerta, e o cooldown/dedup ainda nunca operou com
`alert_log` populada.

### (d) ✅ RESOLVIDA na Etapa 4.1 (01/08/2026) — `price_ceiling` agora tem auditoria

`weekend_legs.price_ceiling` era sobrescrito a cada edição, sem registro do
valor anterior nem de quando mudou — o sistema não conseguia responder "perdi
alguma oportunidade?", e foi exatamente o que travou parte do diagnóstico de
31/07.

**Resolvido:** a Etapa 4.1 criou `weekend_leg_ceiling_audit` (perna, usuário,
teto anterior, teto novo, origem, timestamp), append-only e **alimentada por
trigger no banco** — por ser trigger e não código de aplicação, captura
inclusive edição feita direto no SQL Editor. Ver `HISTORICO.md`, item 17.

Limite que permanece: a auditoria nasce com um marco inicial (`origin =
'migracao'`), não com histórico retroativo — continua impossível responder
"que teto valia em 20/07/2026?". Registrado em "Limites conhecidos da 4.1",
abaixo.

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

### Nota (08/08/2026) — motivo adicional para visibilidade cruzada de compra

Registrado no chat de planejamento: uma proposta de design (não aprovada,
fora do repositório) sugeriu uma camada de visibilidade cruzada entre
usuários — o outro vê que você comprou uma perna e em qual voo. Além de
sincronia geral, essa funcionalidade serve também para otimizar logística —
saber que o outro já tem voo comprado ajuda a decidir se vale dividir táxi.

**Escopo, se e quando essa funcionalidade for desenhada: visibilidade só
depois que `status` vira `purchased`.** A alternativa de expor a
intenção/voo *antes* da compra (mais útil ainda para coordenar táxi com
antecedência, mas vaza mais informação pessoal do outro) foi levantada e
**descartada por ora** — revisar só se a limitação de "só depois de
comprado" virar dor real na prática.

**Desenhada em 09/08/2026 — ver seção "Fatia C — visibilidade de compra
entre usuários" abaixo.**

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
   valor pago por usuário) + migrar dados atuais em 3 degraus:
   - **4.1** — ✅ **Concluída e verificada (01/08/2026).** Estrutura nova criada
     e dados copiados, sem que nada passe a lê-la. Rodada à mão no SQL Editor e
     verificada com os blocos A–G. Detalhe no `HISTORICO.md`, item 17;
     tabelas da verificação em `AUDITORIA-MULTIUSUARIO.md`.
   - **4.2** — frontend e robô passam a ler/escrever a estrutura nova.
     **Em revisão no chat de planejamento, ainda não aprovada** — pendências
     nomeadas abaixo, na seção "Etapa 4.2".
   - **4.3** — só depois, remover as colunas antigas de `weekend_legs`.
5. ✅ **Concluída por composição (08/08/2026).** Frontend: Compras/Dashboard
   por usuário logado; `weekend_legs` vira somente-leitura no navegador;
   redesenho de RLS de update. Coberta por trabalho feito sob outros nomes:
   "`weekend_legs` somente-leitura no navegador" = Etapa 4.4 (07/08/2026);
   "redesenho de RLS de update" = Etapa 4.1, RLS de
   `weekend_leg_user_state`, provada nos blocos F/F2; "Compras/Dashboard por
   usuário logado" = funcionalmente pela Etapa 4.2 (pendências 3/5, leitura
   via `weekend_leg_effective`), visualmente pela Fatia A/B (UI,
   `HISTORICO.md` itens 21/22).
6. Telegram: cooldown/dedup de `alert_log` por (perna × usuário); composição
   de mensagem com nome+valor; mantém o mesmo `TELEGRAM_CHAT_ID` (grupo).
   **Depende do teste do caminho de alerta de perna** (ver "Diagnóstico:
   caminho de alerta de perna de fim de semana" abaixo) — sem confirmação de
   que o alerta dispara em produção, não faz sentido construir
   cooldown/dedup por usuário em cima dele.
7. Criar conta do segundo usuário no Supabase Auth — **por último**, só
   depois de tudo testado. Regra dura: nenhuma conta nova antes disso.
   **Segunda regra dura (01/08/2026, Etapa 4.1):** criar a linha de
   `settings` do usuário é parte obrigatória de criar a conta, no mesmo
   ato. A view `weekend_leg_effective` usa `settings` como registro de
   usuários; conta sem linha em `settings` não aparece na view — nenhuma
   perna, nenhum alerta, painel vazio, e **sem erro em lugar nenhum**.
   O teste real de isolamento entre as duas contas (o que os blocos E e F
   da verificação da 4.1 só conseguem simular) é a primeira coisa a fazer
   depois de criar a conta, antes de ela receber qualquer dado.

**Correção de sequenciamento (31/07/2026):** as Etapas 4 e 5 são modelo de
dados e interface — valem independente de o alerta de perna funcionar (é o
que o segundo usuário precisa; ele não usa Telegram) — e podem começar em
paralelo ao teste do caminho de alerta. Só a Etapa 6 depende desse teste.
Formulação anterior (que tratava o teste como pré-requisito das Etapas 4/5)
foi revisada e está incorreta.

**Pedido de antecipar a Etapa 7 (criação da conta do segundo usuário):
avaliado e recusado em 31/07/2026.** Motivo: `price_ceiling`/`status`/
`notes`/`paid_price` ainda são globais e a RLS de `weekend_legs` é genérica
hoje — qualquer autenticado sobrescreve o dado do outro, sem auditoria de
teto pra reconstruir depois (pendência (d) do diagnóstico — **a parte da
auditoria foi resolvida pela Etapa 4.1 em 01/08/2026**; as colunas globais e
a RLS genérica de `weekend_legs` continuam como estavam, e a recusa segue de
pé). A regra dura (conta nova só na Etapa 7, por último) permanece. Alternativa
considerada e descartada: travar `weekend_legs` como somente-leitura via
RLS temporária até a Etapa 4/5 ficarem prontas — descartada por mexer em
política de segurança em produção, risco de falha silenciosa ao salvar no
frontend, e por ser trabalho descartável (a RLS temporária seria jogada
fora assim que a Etapa 5 entregasse a versão definitiva). Enquanto isso, a
necessidade real do segundo usuário ("ver preço e saber quando comprar") é
atendida manualmente pelo usuário principal.

---

## Etapa 4.2 — virada de leitura (pendências 1–11 e 13 concluídas; 12 em aberto)

**Etapa 4.1 concluída e verificada em 01/08/2026.** A estrutura nova
(`weekend_leg_user_state`, `settings.weekend_default_ceiling` como teto padrão
por usuário, `weekend_leg_ceiling_audit`, view `weekend_leg_effective`) existe
no banco de produção e passou pelos blocos A–G. Detalhe no `HISTORICO.md`,
item 17; tabelas da verificação em `AUDITORIA-MULTIUSUARIO.md`. Nada lê a
estrutura nova ainda — é o que esta etapa faz.

> **O teto padrão é um valor vivo.** A fonte de verdade é
> `settings.weekend_default_ceiling`, editável no painel (Compras → "Salvar meu
> teto padrão"). Já mudou uma vez (250 → 300, em 04/08/2026) e deve mudar de
> novo conforme a calibração com preços reais de ida vs. volta avança. Nenhum
> texto de plano, código ou documentação deve fixar o número — sempre apontar
> para a coluna. Números datados em registros históricos abaixo ficam como
> estão: são fotografia do que valia naquele dia, não afirmação sobre hoje.

> ### ⚠️ REGRA DE JANELA ABERTA — vigente agora, entre a 4.1 e a 4.2
>
> Entre a 4.1 e a 4.2 **o estado vive em dois lugares**: o mundo antigo
> (`weekend_legs`) continua sendo o que o painel e o robô leem e escrevem, e o
> mundo novo (`weekend_leg_user_state`) existe mas está parado na fotografia do
> dia da cópia.
>
> Consequência prática: **teto editado no painel nesse intervalo vai para a
> coluna velha** (`weekend_legs.price_ceiling`), **a auditoria nova não
> enxerga** (a trigger está na tabela nova), e o re-sync da 4.2 vai ter que
> transformar aquele valor em **override explícito** em
> `weekend_leg_user_state.price_ceiling`, com registro próprio na auditoria.
> Se passar batido, o ajuste manual some na virada.
>
> **Enquanto a 4.2 não fechar: não editar teto no painel.**
>
> **✅ ENCERRADA (04/08/2026).** Confirmada por execução real do re-sync
> (pendências 1 e 2, `sql/etapa4_2_resync.sql`) — zero teto preso na coluna
> velha, zero campo de estado pendente de cópia. Já estava tecnicamente
> fechada desde as pendências 3/4 (03/08/2026), quando o painel parou de
> escrever em `weekend_legs.price_ceiling`; a execução do re-sync fecha
> formalmente o registro histórico do intervalo. Texto acima mantido para
> contexto de por que a regra existiu. **Não confundir com a "JANELA ABERTA 2"
> abaixo, que segue em aberto até a Etapa 6.**

> ### ⚠️ JANELA ABERTA 2 — painel novo × Telegram velho (decisão 03/08/2026)
>
> A pendência 3/4 vira só o **painel**: passa a ler/escrever
> `weekend_leg_effective` / `weekend_leg_user_state`. O robô e o Telegram
> (`src/weekends.py`, `live_check.py`, `telegram_notifier.py` — pendência 6,
> ainda não implementada) continuam lendo `weekend_legs.price_ceiling`
> diretamente. Consequência: **teto editado no painel deixa de ter qualquer
> efeito nos alertas do Telegram** até a Etapa 6 entrar.
>
> **Decisão: sem shadow-write.** Não gravar o teto nos dois lugares ao mesmo
> tempo para remendar esse intervalo — isso reintroduziria o problema que a
> Etapa 4 existe para resolver (`weekend_legs.price_ceiling` é 1 valor global,
> não comporta dois usuários com tetos diferentes). O painel mostra um aviso
> de UI simples perto do campo de teto (sem lógica nova) enquanto durar.
>
> **Fecha sozinha quando a Etapa 6 entrar** (o robô passar a ler o teto
> efetivo por usuário) — não antes.
>
> **✅ PARTE DO TETO ENCERRADA (05/08/2026, com prova de produção em
> 06/08/2026).** As pendências 6/7(leve)/8/9 fecharam a divergência de
> leitura: o robô e o Telegram passaram a ler `weekend_leg_effective`. **Teto
> editado no painel volta a valer no Telegram**, e perna marcada como comprada
> volta a sair da fila do robô. A previsão acima ("fecha só na Etapa 6") estava
> certa sobre o fan-out e errada sobre o teto — dava para separar as duas
> coisas, e foi o que se fez.
>
> A leitura funcionava desde 05/08, mas o valor lido ainda era R$250 — a
> recalibração para R$300 (04/08) não tinha persistido no banco. Corrigido
> manualmente em 05/08 (novo save, confirmado por `weekend_leg_ceiling_audit`).
> **Prova final em 06/08/2026:** execução real do robô, não pulada por cota
> diária ("20/20 pernas checadas, 20 com preço"), registrou as 22 ocorrências
> de teto no log todas em R$300, nenhuma em R$250. Fecha de vez esta parte —
> não só o caminho de leitura, mas o valor que ele lê em produção.
>
> **SEGUE ABERTO até a Etapa 6** (nada disso mudou nesta rodada):
> - **Fan-out de alerta por usuário.** O Telegram é um canal único. Com dois
>   usuários, quem receber o alerta recebe o do teto mais apertado, sem saber
>   de quem é.
> - **Cooldown/dedup por perna × usuário.** Hoje é por perna, global.
> - **Mensagem com nome e valor de cada usuário.**
> - **Limiares gerais de um usuário só** (% oportunidade, cooldown/re-alerta,
>   modo de notificação) — escolhidos de forma determinística (menor `user_id`)
>   e com aviso no Telegram quando há mais de um usuário, mas ainda não
>   individualizados.
>
> Enquanto isso, duas regras **provisórias** governam o caso multiusuário, as
> duas marcadas como tal no código (`weekends.resolve_effective_leg_state`):
> vale o **menor teto** entre os usuários que ainda monitoram a perna, e a
> perna **fica na fila enquanto pelo menos um** usuário a monitorar. Com uma
> conta só — cenário de hoje — as duas são invisíveis.

**Medição da janela aberta (03/08/2026, chat de planejamento).** Consulta
somente leitura em produção, comparando `weekend_legs` (mundo antigo) com a
fotografia da 4.1 em `weekend_leg_user_state`:

```
tetos_divergentes_janela_aberta:    0
compras_novas_sem_linha_de_estado:  0
linhas_existentes_ja_divergentes:   0
total_linhas_de_estado_hoje:        5
total_compradas_mundo_antigo:       0
total_com_valor_pago_mundo_antigo:  5
```

Confirma que a regra de janela aberta segurou 100% até agora — zero teto
editado no painel desde a 4.1 — e que zero compras/edições novas aconteceram
no intervalo (as 5 linhas de estado continuam idênticas à fotografia).
**Ressalva: isso não elimina o risco em princípio, só descreve o estado
observado nesta data** — o re-sync continua necessário, porque o intervalo
entre agora e a execução real da 4.2 pode gerar divergência nova.

### Pendências nomeadas (12 no total — 1 a 11 concluídas; resta a 12, que é backlog)

1. ✅ **Concluída e executada em produção (04/08/2026).** Re-sync do estado
   antes de virar a leitura — desenhada (03/08/2026), corrigida para a regra
   de não-sobrescrita por campo depois que as pendências 3/4 entraram antes
   do previsto, e executada via `sql/etapa4_2_resync.sql` (mantido no
   repositório, re-rodável). **Resultado: zero divergência** entre 01/08 e
   04/08/2026 — pré-voo (Bloco 0) com `p1_linhas_a_inserir` e todos os
   `p1_*_a_escrever` em 0; execução (Bloco 1) com `parte_a_linhas = 0`. Não
   havia nada a copiar: confirma e estende a medição de 03/08/2026 registrada
   abaixo. Desenho original mantido nesta seção como registro:

   A cópia da 4.1 é uma fotografia. A partir dela,
   todo `paid_price`/nota/compra novo continua indo para `weekend_legs` (mundo
   antigo) e não para `weekend_leg_user_state`. Quanto maior o intervalo 4.1 →
   4.2, mais desatualizada a cópia. O Bloco 7b é re-rodável, mas
   `on conflict do nothing` **não atualiza** linha já criada — o re-sync da 4.2
   precisa de lógica própria. Desenho decidido:
   - Trocar `on conflict do nothing` por
     `on conflict (leg_id, user_id) do update`, escrevendo
     `status`/`notes`/`paid_price`/`purchased_at` de `weekend_legs`, só quando
     o valor mudou (evitar linha de auditoria falsa em campo que não é teto).
   - Idempotência obrigatória: rodar duas vezes seguidas não pode gerar
     segunda linha de auditoria se nada mudou entre as rodadas (mesmo padrão
     já verificado na 4.1).
   - Decisão de timing: o script é genérico e re-rodável, mas só deve ser
     executado de fato imediatamente antes do deploy que vira a leitura — não
     antes.
2. ✅ **Concluída e executada em produção (04/08/2026).** Teto editado no
   painel entre a 4.1 e a 4.2 vira caso especial do re-sync — desenhada
   (03/08/2026) e executada junto com a pendência 1, via
   `sql/etapa4_2_resync.sql`. **Resultado: `p2_tetos_a_escrever = 0` e
   `parte_b_linhas = 0`** — nenhum teto ficou preso na coluna velha no
   intervalo 01/08 → 04/08/2026; confirma a medição de 03/08/2026 (zero
   divergências) e a estende até a data de execução. Desenho original mantido
   nesta seção como registro:

   O guarda 1c do script exige todas as pernas em 250 no momento de rodar, e a
   4.1 por isso não copia teto. Se um teto for editado no painel depois disso,
   ele vai para a coluna velha (`weekend_legs.price_ceiling`), a auditoria nova
   não enxerga (a trigger é na tabela nova), e o re-sync da 4.2 tem que saber
   transformar aquele valor em **override explícito** em
   `weekend_leg_user_state.price_ceiling` — e registrar isso na auditoria com
   origem própria. Se passar batido, o ajuste manual some na virada. Desenho
   decidido:
   - Toda perna onde `weekend_legs.price_ceiling <> 250` no momento em que o
     re-sync rodar de fato (calculado na hora da execução, não hardcoded a
     partir da medição de 03/08/2026, que deu zero divergências) recebe esse
     valor em `weekend_leg_user_state.price_ceiling`, com origem própria na
     auditoria: `origin = 'resync_override'` (distinta de `'migracao'` e de
     `'app'`).
3. ✅ **Concluída, commitada e enviada (03/08/2026).** **`docs/js/compras.js`**
   — ler de `weekend_leg_effective`, escrever em `weekend_leg_user_state`
   (upsert por `leg_id`, sem mandar `user_id`, que tem `default auth.uid()`),
   remover `DEFAULT_CEILING = 200`. Commits `531f34f` (implementação) e
   `9436bc0` (correção de um `return` ilegal fora de escopo de função,
   achado na verificação manual no site publicado). `origin/main == HEAD`
   confirmado após o push. Verificação manual completa (5 passos) realizada
   no site publicado, com login real.

   **Decisão 1 (chat de planejamento, 03/08/2026) — regra de "Salvar" do teto
   por perna:** ao clicar Salvar, o valor do campo naquele momento sempre vira
   override explícito em `weekend_leg_user_state.price_ceiling` — mesmo que
   numericamente coincida com o teto padrão atual do usuário. Não detectar
   "é igual ao padrão, então não é override de verdade": comportamento
   escondido, difícil de prever/debugar, e quebraria no dia em que o padrão
   mudasse (override deixaria de ser fixo, passaria a seguir o padrão novo
   por coincidência de número). Reverter um override e voltar a seguir o
   padrão é ação separada, fora do escopo desta rodada — ver item 12 abaixo.
   A view já expõe `ceiling_is_explicit` (`st.price_ceiling IS NOT NULL`),
   pronta para alimentar essa ação futura sem consulta extra.
4. ✅ **Concluída, commitada e enviada (03/08/2026).** **Botão "aplicar teto a
   todos" muda de significado** (decisão do chat de planejamento, 01/08/2026):
   virou "Salvar meu teto padrão", editando `settings.weekend_default_ceiling`,
   e **não sobrescreve** teto ajustado à mão perna a perna — o `update` em
   massa antigo em `weekend_legs` (`docs/js/compras.js:517`) foi substituído,
   sem filtro por status, e o texto do `confirm()` mudou junto. Mesmos commits
   da pendência 3 (`531f34f`, `9436bc0`).
5. ✅ **Concluída, commitada e enviada (04/08/2026).** **`docs/js/dashboard.js`**
   — mesma troca de fonte de `compras.js` (pendências 3/4): embed
   `weekends.select('*, weekend_legs(*)')` substituído por duas queries
   (`weekends` + `weekend_leg_effective`), agrupadas por `weekend_id` em JS,
   com `error` checado nas duas (antes só `weekends` era desestruturado sem
   checar) — em caso de erro, `alert()` e interrompe, sem renderizar dado
   parcial. Sem `normalizeLegRow` (`leg_id` → `id`): nenhuma função do arquivo
   referencia `leg.id`. Bootstrap virou `async function initPage(session)`
   pelo mesmo motivo do commit `9436bc0` (`return` de tratamento de erro é
   ilegal solto no escopo do módulo). Nenhuma função de render alterada.
   Commit `05c6f97`. `origin/main == HEAD` confirmado após o push.
   Verificação manual no site publicado, logado: teto individual salvo em
   Compras (perna Ida 04/09, override R$ 555) refletido no Dashboard —
   "Ação do dia" contou a perna como abaixo do teto e "Melhores
   oportunidades → Abaixo do teto" mostrou "R$ 536,00 (3% abaixo do teto)",
   consistente com o teto de R$ 555 salvo em Compras; console sem erros.
6. ✅ **Concluída (05/08/2026).** **Teto efetivo no robô e no Telegram.**
   `src/weekends.py`, `live_check.py` e `telegram_notifier.py` liam
   `weekend_legs.price_ceiling` com fallback `or 200`; passaram a ler
   `effective_ceiling`, resolvido de `weekend_leg_effective`.
   - **Ponto de origem único, confirmado antes de codar:** `select_batch`
     (live_check) e `process_all_weekend_legs` (weekends) chamam ambos
     `get_active_legs()`, que era o único chamador de `get_monitoring_legs`.
     Anexar o teto lá alimenta os três sites — não há caminho paralelo.
   - **`or 200` era inofensivo por acidente**, não a causa do bug em produção:
     `weekend_legs.price_ceiling` é `not null`, então o fallback nunca
     disparava. O bug real era ler a **coluna errada** (250 congelado desde a
     pendência 3/4) em vez do teto efetivo. O `or 200` saiu como dívida.
   - Eram **três** `or 200` no Python, não quatro. O quarto provavelmente era o
     `default 200` da coluna em `sql/pernas_desacopladas.sql:36` (DDL, não
     código de aplicação) — ou a contagem original errou.
   - **Sem fallback numérico.** Teto ausente (nenhum usuário em `settings`) é
     erro de dado: a regra de teto sai de cena (`target_price=None`), o preço
     continua sendo gravado, a regra de oportunidade continua valendo, e sai um
     aviso único no Telegram. Nunca um número inventado.
   - MIN entre usuários **restrito a quem ainda monitora** a perna: o teto de
     quem já comprou não deve governar o alerta de quem não comprou. Com um
     usuário só as duas leituras coincidem.
   - **Verificada em produção em 06/08/2026** (execução real, não pulada por
     cota diária): 22 ocorrências de teto no log da execução, todas em R$300 —
     ver "Janela Aberta 2" acima para o incidente de gravação que atrasou essa
     prova (04→05/08) e o detalhe completo.
7. ✅ **Concluída na versão leve (05/08/2026).** **`src/main.py`** — a escolha
   de quem dita os limiares gerais deixou de ser `next(iter(...))` (ordem de
   dicionário) e virou determinística (menor `user_id`) e barulhenta (aviso no
   Telegram quando há mais de um usuário, nomeando o escolhido). Vale para os
   dois sites do mesmo padrão — o de `weekend_settings` e o de
   `notification_mode`, que a pendência original não nomeava.
   - **Correção de desenho feita antes de codar:** `settings_cache` era montado
     a partir de `routes`, então a guarda "mais de um usuário" **nunca
     dispararia** no caso real (segundo usuário não terá rota flexível). Passou
     a ser montado de `get_all_settings()` — a mesma tabela que a view usa no
     cross join. `routes` só complementa usuário sem linha em `settings`.
   - **Não é o loop por usuário** — isso é a Etapa 6. Aqui só se trocou escolha
     implícita por escolha explícita e visível.
8. ✅ **Concluída (05/08/2026).** **Documentação do teto.** `CLAUDE.md` dizia
   "default R$ 200" e o cabeçalho desta seção dizia "= 250"; ambos passaram a
   apontar para `settings.weekend_default_ceiling` como fonte de verdade, **sem
   fixar número** — o valor é vivo (250 → 300 em 04/08/2026, e deve mudar de
   novo). Registros históricos datados ficaram como estão.
9. ✅ **Concluída no caso atual (05/08/2026).** **Fila de scraping por status
   efetivo.** `get_monitoring_legs` filtrava `weekend_legs.status = 'monitoring'`
   na consulta — coluna que o painel parou de escrever nas pendências 3/4.
   Consequência ativa em produção: **marcar perna como comprada no painel não a
   tirava da fila do robô**, e ela seguia gerando alerta de teto. Virou
   `get_all_weekend_legs()` (sem filtro de status) + filtro por status efetivo
   em `get_active_legs`.
   - Regra implementada (decisão do chat — **não reabrir**): a perna fica na
     fila enquanto **pelo menos um** usuário tiver status efetivo
     `'monitoring'`; sai só quando **todos** decidirem outra coisa. Ausência de
     linha em `weekend_leg_user_state` conta como `'monitoring'` — a view já faz
     `coalesce(st.status, 'monitoring')`, então nenhum coalesce foi preciso na
     aplicação.
   - **Modo degradado:** view vazia (nenhum usuário em `settings`) faz a fila
     cair no `weekend_legs.status` antigo, com aviso. Nunca esvazia a fila em
     silêncio.
10. ✅ **Concluída junto com a 6 (05/08/2026).** **Ordenação da fila:
    `price_ceiling` também ordena** (`price_gap` em `src/live_check.py`). Com
    dois tetos para a mesma perna, a ordenação usa o **MENOR teto entre os
    usuários** — quem tem o teto mais apertado puxa a perna pra cima na fila.
    (Decisão do chat de planejamento — **não reabrir**.) Implementada no mesmo
    ponto da pendência 6: `resolve_effective_leg_state` já entrega o MIN, e o
    `sort_key` só consome. Perna sem teto efetivo desempata por último
    (`inf`), como perna sem preço.
11. ✅ **Concluída (05/08/2026).** **Corrigir `sql/etapa4_1_verificacao.sql`** —
    a pendência tinha crescido além de só consolidar E e F numa linha cada,
    depois da investigação de 02/08/2026 (`AUDITORIA-MULTIUSUARIO.md`,
    "Verificação das estruturas novas" e "Lacuna de evidência no artefato de
    verificação"). Entregue: **blocos E e F substituídos e um bloco F2 novo
    inserido entre o F e o G** (desenho aprovado no chat de planejamento).
    Blocos A, B, C, D, G e H não foram tocados. **O arquivo não foi executado
    nesta rodada** — a execução no SQL Editor é manual, como sempre.
    - **Bloco E** — uma única linha de resultado, com `auth.uid()` e
      `current_user` como **colunas-guarda** ao lado das três contagens
      (`view_esp_0`, `estado_esp_0`, `auditoria_esp_0`). Resolve o defeito
      original: o SQL Editor só exibe o último `select` de cada bloco, então
      guarda em `select` separado era descartada em silêncio.
    - **Bloco F** — mesma consolidação, mais o **discriminador que faltava**:
      semeia dentro da própria transação uma linha de
      `weekend_leg_ceiling_audit` com `user_id` sintético alheio
      (`…-0002`, `new_value = 999`), antes de trocar de papel, e depois conta
      quantas o usuário legítimo enxerga (`alienigena_esp_0`, esperado 0). Isso
      só é possível porque `weekend_leg_ceiling_audit.user_id` **não tem FK**
      (decisão do Bloco 4 da 4.1). As outras colunas do bloco continuam sendo
      regressão do caminho legítimo, não prova de isolamento.
    - **Bloco F2 (novo)** — prova em produção a RLS de **escrita** de
      `weekend_leg_user_state`, que até aqui só tinha sido testada num Postgres
      descartável. Par de tentativas: insert com `user_id` alheio (deve ser
      rejeitado) e insert com `user_id` próprio (deve ser aceito), cada uma com
      o `sqlstate` capturado. O par junto é o que separa "o `with check` compara
      o uuid" de "está bloqueando tudo por outro motivo" — o que faria o teste
      passar por engano. Esperado: `bloqueado 42501` (RLS) e `aceito`; um
      `23503` no primeiro significaria que quem barrou foi a FK de
      `weekend_leg_user_state.user_id`, não a RLS.
    - Sub-item "limpar do `.sql` os resultados colados como tabelas markdown":
      **já estava resolvido ANTES desta sessão** — o arquivo já estava limpo em
      disco (restaurado ao último commit no housekeeping de 05/08, ver
      `STATE.md`). Não é entrega desta rodada; registrado só para fechar a
      lista.
    - **Limite que permanece, agora com motivo técnico documentado:** o
      isolamento de `weekend_leg_effective` e de `weekend_leg_user_state` entre
      **duas contas reais** continua **não demonstrável até a Etapa 7**. Não é
      lacuna vaga: a view depende de duas linhas em `settings`, e `settings.user_id`
      tem FK para `auth.users` (`settings_user_id_fkey`, confirmado em produção
      em 05/08/2026 — ver `AUDITORIA-MULTIUSUARIO.md`, seção 2), então não há
      como semear um segundo dono ali sem criar conta de verdade. O bloco F2
      cobre o que dava para cobrir com uma conta só (a RLS de escrita); o resto
      é o primeiro ato depois de criar a segunda conta.
    - **✅ Prova de produção (05/08/2026):** os três blocos (E, F, F2) rodaram
      no SQL Editor em produção e bateram exatamente com o esperado — ver
      `STATE.md`, entrada de sessão de 05/08/2026, para os números completos.
12. **Backlog — "limpar override" por perna** (registrado 03/08/2026, fora do
    escopo da pendência 3/4). Ação para remover a linha específica de
    `weekend_leg_user_state` (ou zerar `price_ceiling` para NULL) e a perna
    voltar a seguir o teto padrão do usuário automaticamente. A coluna
    `ceiling_is_explicit` da view já existe e está pronta para indicar quando
    esse controle deve aparecer — só falta desenhar a UI (ex.: botão
    "voltar ao padrão" ao lado do teto quando `ceiling_is_explicit = true`).
13. ✅ **Concluída (06/08/2026).** **`get_weekend_leg_counts` lendo coluna
    congelada.** `src/supabase_client.py` contava pernas compradas do resumo
    de segunda-feira lendo `weekend_legs.status` — a mesma coluna que as
    pendências 3/4 (03/08) tiraram de uso quando o painel passou a escrever
    status em `weekend_leg_user_state`. Consequência: o resumo semanal sempre
    relatava **0 compradas**, em silêncio, desde 03/08.
    - **Achada no diagnóstico da Etapa 4.3** (chat de planejamento paralelo,
      que audita o que ainda lê colunas antigas de `weekend_legs` antes do
      `DROP`), mas tratada como **bug vivo da 4.2**, não item da 4.3 — e com
      prioridade sobre a 4.3: essa mesma query quebraria de vez (erro, não
      silêncio) assim que as colunas antigas fossem derrubadas, então corrigir
      antes do `DROP` era condição para a 4.3 poder prosseguir.
    - **Correção:** passou a ler `weekend_leg_effective`. Perna conta como
      comprada só quando **todos** os usuários que a monitoram têm
      `status = 'purchased'` (`bool_and` por `leg_id`) — mesma regra de "sai da
      fila" da pendência 9, aplicada aqui ao complemento. Só existem dois
      estados possíveis hoje (`check` no schema,
      `sql/etapa4_1_estado_por_usuario.sql:91`), então comparar `==
      'purchased'` direto é seguro, sem inferir por ausência de monitoramento.
    - **Verificação:** consulta equivalente rodada no SQL Editor —
      132 pernas, 0 compradas, idêntico ao valor de hoje, sem regressão. O
      caminho de código só roda às segundas-feiras (`primary_run and
      date.today().weekday() == 0`), então não havia cron real disponível
      para observar a mensagem de verdade nesta rodada — **conferir a
      mensagem real do Telegram na próxima segunda-feira** para fechar o
      ciclo com prova de produção (mesmo padrão da pendência 6, que também
      levou dois dias entre "leitura corrigida" e "prova de produção do
      valor").
    - Commit `b22a569`, `origin/main == HEAD` confirmado. 189 testes
      passando (5 novos: contagem single-user e a regra de "todos precisam
      concordar" com múltiplos usuários).

### Limites conhecidos da 4.1 (registrados, não são pendência)

- A auditoria nasce com um marco inicial (`origin = 'migracao'`), não com
  histórico: continua impossível responder "que teto valia em 20/07/2026?".
- Append-only vale para a API (RLS sem policy de escrita), não para quem entra
  no SQL Editor como `postgres`, que é dono da tabela. Fechar isso exigiria
  `force row level security`, que bloquearia a própria trigger.
- A segurança da view é emprestada da RLS das tabelas de baixo — ela não tem
  filtro próprio, de propósito (com `user_id = auth.uid()` embutido, o robô, que
  roda como `service_role` com `auth.uid()` nulo, veria zero linhas). Qualquer
  policy nova em `settings` ou `weekend_leg_user_state` exige re-rodar os blocos
  E e F da verificação.
- As 5 pernas com `paid_price` preenchido e `status = 'monitoring'` são anomalia
  conhecida: copiadas como estão, sem normalizar (decisão do chat de
  planejamento).

---

## Etapa 4.3 — remoção das colunas antigas de `weekend_legs` (aberta 06/08/2026)

Remover de `weekend_legs` as 5 colunas do mundo pré-multi-usuário:
`price_ceiling`, `status`, `notes`, `paid_price`, `purchased_at`. A decisão
por perna × usuário vive em `weekend_leg_user_state` desde a 4.1, e desde a
4.2 painel e robô leem tudo por `weekend_leg_effective` — as colunas antigas
só continuam de pé como fotografia congelada.

**O que o diagnóstico (chat de planejamento, 06/08/2026) já estabeleceu:**

- Mapa de leitura/escrita de código levantado: depois da pendência 13, o
  último ponto vivo lendo essas colunas era o ramo degradado de
  `get_active_legs()` (passo 1 abaixo).
- **Nenhuma view** depende das 5 colunas.
- **Nenhuma policy de RLS** as referencia.
- **Zero divergência** entre `weekend_legs` e `weekend_leg_user_state` nas 132
  pernas.
- A pendência 13 da 4.2 (`get_weekend_leg_counts`) nasceu deste diagnóstico e
  foi tratada lá, por ser bug vivo e bloqueadora do `DROP`.

**Desenho aprovado, em 5 passos.** Regra: cada passo volta ao chat de
planejamento antes de rodar — nenhum passo encadeia sozinho. O detalhe fino de
cada passo futuro é discutido quando chegar a vez dele.

1. ✅ **Concluído (06/08/2026).** **Código do ramo degradado.** O filtro
   `if leg.get("status") != "monitoring": continue` saiu do ramo degradado de
   `get_active_legs()` (`src/weekends.py`). Precisava sair **antes** do `DROP`:
   sem colunas, `leg.get("status")` vira `None`, `None != "monitoring"` é
   sempre verdadeiro e toda perna cairia da fila em silêncio. Agora o modo
   degradado devolve todas as pernas não expiradas com
   `effective_ceiling = None` — não inventa teto, e `main.py` segue avisando no
   Telegram. Testes: `test_no_settings_still_respects_the_old_purchased_status`
   virou `test_no_settings_ignores_the_old_purchased_status` (asserção
   espelhada, guarda de regressão contra reintroduzir o filtro); a fixture
   `LEG_ROW` perdeu a chave `status`, que só existia por causa desse filtro.
   189 testes passando.
2. ⏸️ **DESACOPLADO do `DROP` (06/08/2026, chat de planejamento).** Era descrito
   aqui como pré-requisito técnico: esperar a segunda-feira para ver o
   `get_weekend_leg_counts` corrigido (pendência 13 da 4.2, commit `b22a569`)
   rodar de verdade, mantendo as 5 colunas antigas como rede de segurança até
   lá. **Não é mais pré-requisito.** Motivo: o código corrigido lê
   `weekend_leg_effective` e não toca mais nas colunas antigas — mantê-las de
   pé não sustenta rollback nenhum do caminho corrigido. A rota de volta real
   é o backup da Parte A do Passo 3. Segue como **pendência de fechamento de
   registro, não bloqueante**, e a Etapa 4.3 corre em paralelo a ela.
   **Ação combinada: a partir de segunda-feira 10/08/2026 o usuário traz o
   resultado real da mensagem de resumo semanal do Telegram** (contagem de
   pernas compradas — esperado: 0, sem erro) **e o resultado é registrado
   neste item.**
   - Resultado de 10/08/2026: _(aguardando)_
3. ✅ **CONCLUÍDO (06/08/2026).** Backup + `DROP` das 5 colunas legadas
   executados em produção pelo usuário, no SQL Editor. Script:
   `sql/etapa4_3_drop_colunas_legadas.sql` — Bloco 0 (inventário de definição,
   só leitura) / Parte A (backup) / Parte B (guardas G0–G4 + `DROP`) / receita
   de restauração em comentário.
   - **Resultado real da PARTE B**, rodada no SQL Editor de produção:

     | colunas_legadas_restantes | linhas_no_backup |
     |---|---|
     | 0 | 132 |

     Nenhum erro nas guardas G0–G4 — todas passaram. **As 5 colunas
     `price_ceiling`, `status`, `notes`, `paid_price` e `purchased_at` NÃO
     EXISTEM MAIS em `weekend_legs`.** O backup
     `weekend_legs_legacy_columns_backup` é **PERMANENTE** e contém as 132
     linhas originais. A receita de restauração (mesmo arquivo SQL) já está
     com os tipos e defaults reais (`price_ceiling numeric not null default
     200`, `status text not null default 'monitoring'::text`), não mais com
     marcadores `<TIPO_DO_BLOCO_0>`.
   - **Achado no desenho:** `weekend_legs.price_ceiling` (teto legado) e
     `settings.weekend_default_ceiling` (teto padrão vivo do usuário) são dois
     números diferentes por desenho, não por defeito — o legado está congelado
     em R$250 desde que o painel parou de escrever nele (pendências 3/4,
     03/08/2026), e o padrão vivo já foi recalibrado para R$300 (04/08/2026).
     A guarda G3 exige **uniformidade** do teto legado (`min = max`, sem NULL),
     mas **não exige igualdade** com o teto padrão de hoje — que aparece na
     mensagem só como contexto.
   - **Backup de dados não preserva definição de coluna.** `DROP COLUMN` leva
     junto tipo, default, not-null, checks e índices — por isso o script
     começa com um Bloco 0 de inventário (`information_schema.columns` +
     `pg_constraint` + `pg_indexes`), cujo resultado deve ser colado abaixo
     quando o usuário rodar.
     - **Inventário de definição das 5 colunas (BLOCO 0), rodado no SQL
       Editor de produção em 06/08/2026:**

       ```
       | tipo_de_linha | nome          | detalhe_1                | detalhe_2   | detalhe_3 | detalhe_4 | detalhe_5          |
       | coluna        | notes         | text                     | text        | /         | YES       |                    |
       | coluna        | paid_price    | numeric                  | numeric     | /         | YES       |                    |
       | coluna        | price_ceiling | numeric                  | numeric     | /         | NO        | 200                |
       | coluna        | purchased_at  | timestamp with time zone | timestamptz | /         | YES       |                    |
       | coluna        | status        | text                     | text        | /         | NO        | 'monitoring'::text |
       ```

       Nenhuma linha de tipo `constraint` e nenhuma de tipo `indice` — zero
       check/FK/unique/exclusion e zero índices citando as 5 colunas.
       Os 5 tipos conferidos batem exatamente com o `create table` da Parte A
       (nenhuma divergência; a instrução de parada do cabeçalho da Parte A não
       se aplicou). Os únicos elementos de definição a reaplicar numa eventual
       restauração são o `not null` + `default` de `price_ceiling` (`200`) e
       de `status` (`'monitoring'::text`) — o resto (`notes`, `paid_price`,
       `purchased_at`) é coluna simples, nullable, sem default.
   - **`weekend_legs_legacy_columns_backup` é PERMANENTE** — não deve ser
     apagada ao fim da Etapa 4.3 nem em limpeza de rotina; só sai por decisão
     explícita no chat de planejamento.
4. ✅ **CONCLUÍDO (07/08/2026).** Notas de cabeçalho nos scripts `sql/`
   afetados + **aposentadoria do Bloco A de `sql/etapa4_1_verificacao.sql`**.
   **Fechamento da lista fina:** o `grep` de 06/08/2026 tinha apontado 7
   arquivos; a lista final é **outra**:
   - `alvo_fins_de_semana.sql` **SAIU** da lista das 5 colunas — falso
     positivo do grep: as ocorrências de `status`/`price_ceiling`/
     `purchased_at` nele são de `weekend_targets`, tabela já dropada por
     `pernas_desacopladas.sql` (23/07/2026), não de `weekend_legs`. Recebeu
     nota própria por risco separado, fora do escopo da 4.3 — o arquivo, se
     rodado hoje, não dá erro e ressuscita em silêncio a tabela zumbi
     `weekend_targets` (66 linhas de seed) e a coluna `alert_log.target_id`.
   - `sql/etapa4_3_drop_colunas_legadas.sql` **ENTROU** — não constava na
     lista original; é o único script que já rodou contra produção (Passo 3,
     06/08/2026) sem carimbar isso, e agora tem nota de execução própria.
   - **Fecha em 7 arquivos em escopo**: 6 que tocam as colunas removidas de
     `weekend_legs` (`etapa4_1_estado_por_usuario.sql`,
     `etapa4_1_verificacao.sql`, `etapa4_2_resync.sql`, `notas_pernas.sql`,
     `parte8_preco_pago.sql`, `pernas_desacopladas.sql`) + o próprio script
     do `DROP` (`etapa4_3_drop_colunas_legadas.sql`).
   - **Armadilha ativa identificada:** `notas_pernas.sql` e
     `parte8_preco_pago.sql` fazem `alter table weekend_legs add column`
     sem `if not exists` e sem guarda — rodar hoje **não dá erro**, recria a
     coluna vazia e ressuscita em silêncio parte do mundo removido.
   - `pernas_desacopladas.sql` só falha se re-rodado por **acidente de
     ordem** (para no `create table weekends`, que já existe) — não por
     proteção desenhada; não conte com essa falha como guarda.
   - Em `etapa4_1_verificacao.sql`, só o **Bloco A** foi aposentado
     (comentado em bloco `/* */`, preservado como registro histórico).
     Blocos B, C, D, E, F, F2, G e H continuam válidos e rodáveis — E, F e
     F2 seguem sendo a prova de produção de isolamento entre usuários e de
     RLS de escrita (05/08/2026, commit `f50e55a`).
5. ✅ **CONCLUÍDO (07/08/2026).** Bloco de verificação pós-`DROP`. Script
   [sql/etapa4_3_verificacao_pos_drop.sql](sql/etapa4_3_verificacao_pos_drop.sql)
   — 6 blocos (A, B, C, D1, D2, E), todos `select`, desenhados como **colheita
   independente do Passo 3**: não reaproveitam nenhuma das guardas G0–G4 de
   `sql/etapa4_3_drop_colunas_legadas.sql`, é uma consulta escrita do zero.
   Rodado manualmente no SQL Editor de produção em 07/08/2026, um bloco por
   vez. **Zero divergência — todos os 6 blocos bateram exatamente com os
   valores esperados no rodapé do script:**
   - **Bloco A** (colunas ausentes, consulta independente): `controle_tabela
     = 1`, `controle_sobreviventes = 5`, `legadas_presentes = 0`,
     `legadas_quais = (nenhuma)`, `total_colunas_hoje = 13` — `id,
     weekend_id, direction, current_price, current_airport, current_variant,
     current_source, lowest_seen, lowest_seen_at, last_live_check_at,
     created_at, current_airline, current_departure_time`.
   - **Bloco B** (policies de `weekend_legs` vs. baseline de 01/08/2026): as
     2 policies esperadas, texto idêntico ao baseline, os 2 vereditos = `OK`.
   - **Bloco C** (triggers de `weekend_legs`): zero linhas (`Success. No rows
     returned`).
   - **Bloco D1** (estrutura nova, cardinalidade): `estado_linhas = 5`,
     `auditoria_linhas = 12`, `view_linhas = 132`, `view_esperado = 132`,
     `pernas = 132`, `usuarios = 1`.
   - **Bloco D2** (prova via `pg_depend` de que `weekend_leg_effective` não
     depende de nenhuma das 5 colunas removidas): 10 linhas
     (`current_airport`, `current_price`, `current_source`,
     `current_variant`, `direction`, `id`, `last_live_check_at`,
     `lowest_seen`, `lowest_seen_at`, `weekend_id`), `e_coluna_legada = false`
     em todas.
   - **Bloco E** (backup permanente íntegro): `linhas_backup = 132`,
     `linhas_weekend_legs = 132`, `colunas_backup = 7` (`id, price_ceiling,
     status, notes, paid_price, purchased_at, captured_at`),
     `capturas_distintas = 1`, `capturado_em = 2026-08-07 01:56:43.499924+00`
     (06/08/2026 22:56 BRT — ainda dentro do dia do Passo 3), `ids_orfaos =
     0`, `pernas_sem_backup = 0`, `rls_ligada = true`, `policies_no_backup =
     0`.

---

## Etapa 4.3 — CONCLUÍDA (07/08/2026)

Todos os 5 passos verificados: Passo 1 (código do ramo degradado, commit
`d5f97eb`), Passo 3 (backup + `DROP` em produção, commit `ce0d8b3`), Passo 4
(notas de cabeçalho + aposentadoria do Bloco A, commit `4b02093`) e Passo 5
(verificação pós-`DROP` independente, acima) concluídos. **Pendência
PARALELA e NÃO BLOQUEANTE segue em aberto**: o Passo 2 (resultado real do
resumo semanal do Telegram, a partir de segunda-feira 10/08/2026) ainda não
foi trazido — isso não impede marcar a etapa como concluída; é registro
separado, de fechamento de observação, não de correção estrutural.

---

## Etapa 4.4 — RLS de weekend_legs (CONCLUÍDA, 07/08/2026)

**Achado do diagnóstico:** `weekend_legs` tinha policy de `UPDATE` para
`authenticated` — vestígio do mundo pré-4.1/4.2, quando o painel escrevia
teto/status/notas direto nessa tabela. Desde as pendências 3/4/5 da Etapa 4.2
(verificadas em produção, 03-04/08/2026), o painel escreve em
`weekend_leg_user_state` e em `settings.weekend_default_ceiling` — nunca mais
em `weekend_legs`. Quem ainda escreve em `weekend_legs` é só o robô
(`service_role`, que sempre ignora RLS). A policy ficou sem uso real, mas
continuava sendo superfície de escrita: qualquer sessão autenticada no
navegador podia, tecnicamente, dar `update` direto em `weekend_legs` via API.
**`SELECT` continua aberto para qualquer autenticado — isso não mudou.**

**Achado do Passo 1** (checagem de segurança, `grep -rn "weekend_legs"
docs/js/`, antes de tocar no banco): 11 ocorrências, todas em `compras.js` e
`dashboard.js`, todas leitura — acesso à chave `weekend_legs` de um objeto JS
vindo de um select que embute `weekend_legs(*)` dentro de `weekends`, ou
leitura de `weekend_leg_effective`. Confirmação adicional (busca de todas as
chamadas `.from(...)` + `.update(`/`.upsert(`/`.insert(` nos dois arquivos):
as únicas escritas do frontend são `.from('weekend_leg_user_state').upsert(...)`
(`compras.js:51`) e `.from('settings').upsert(...)` (`compras.js:549`). **Zero
update/upsert/insert contra `weekend_legs` em `docs/js/`** — confirma que o
frontend não dependia da policy removida; nada divergia do que o `STATE.md`
já documentava sobre as pendências 3/4/5 da Etapa 4.2.

**Script:** [sql/etapa4_4_weekend_legs_readonly.sql](sql/etapa4_4_weekend_legs_readonly.sql)
— Guarda G0 (inventário do estado atual, para não em cima de suposição),
Parte A (`revoke update on weekend_legs from anon, authenticated`), Parte B
(`drop policy weekend_legs_update_authenticated`), verificação final.

**Resultado real, rodado manualmente no SQL Editor de produção em
07/08/2026:**

| bloco | resultado |
|---|---|
| Guarda G0 | `policies_update_hoje = 1`, `view_effective_e_updatable = NO` |
| Parte A (`revoke update`) | sucesso, sem erro |
| Parte B (`drop policy`) | sucesso, sem erro |
| Verificação final | `policies_update_depois = 0`, `authenticated_ainda_pode_update = false`, `anon_ainda_pode_update = false` |

**Achado lateral:** `view_effective_e_updatable` já vinha `NO` antes deste
script rodar. `weekend_leg_effective` é uma view com join de múltiplas
tabelas (`weekend_legs` + `weekends` + `settings` + `weekend_leg_user_state`),
sem trigger `INSTEAD OF` — o Postgres nunca a considerou automaticamente
atualizável, independente de qualquer RLS ou grant em `weekend_legs`. Ou seja:
o caminho de escrita pela view nunca foi real — este script fechou o único
caminho de escrita que de fato existia (direto na tabela).

**Correção (09/08/2026):** o parágrafo acima afirmava que o grant sobre
`weekend_leg_effective` "sempre foi só de `SELECT`"
(`sql/etapa4_1_estado_por_usuario.sql`, Bloco 6). É **falso** — verificado em
produção em 08/08/2026, no diagnóstico da Fatia C: a view tem os 7
privilégios (`select`/`insert`/`update`/`delete`/`truncate`/`references`/
`trigger`) para `anon` e `authenticated`, porque o Supabase aplica
`alter default privileges grant all` no schema `public` — todo objeto novo
nasce assim, independente do `grant select` explícito escrito no script (que
só *adiciona* select, nunca restringe o que o default já concedeu). A
**conclusão do achado lateral segue válida por outro motivo**, preservado
acima: a view não é atualizável por não ter trigger `INSTEAD OF`, qualquer
que seja o grant. Ver `sql/fatia_c_visibilidade_compra.sql` para o mesmo
achado aplicado à tabela de projeção nova (revoke explícito antes de
qualquer grant).

**Escopo confirmado como respeitado:** nenhuma outra tabela foi tocada —
`weekend_leg_user_state`, `weekend_leg_effective`, `weekends` e todas as
demais ficaram intocadas. Esta etapa foi só RLS/grants de `weekend_legs`.

**Relação com a pendência de RLS "genérica" registrada em `STATE.md` (seção
4, "Bloqueios/perguntas em aberto", 31/07/2026):** essa pendência tem dois
lados — `authenticated` conseguia **ler e escrever** qualquer linha de
`weekend_legs`, sem filtro por usuário. A Etapa 4.4 fecha só o lado de
**escrita**. O lado de **leitura** (qualquer autenticado ainda enxerga todas
as linhas de `weekend_legs`/`weekends`) segue sem alteração — continua
pendência separada, a resolver antes da Etapa 7. Nota também: a alternativa
descartada em 31/07/2026 ("travar `weekend_legs` como somente-leitura via RLS
**temporária**") era outra coisa — uma trava provisória para blindar a
migração 4.1→4.2 em andamento, descartada por risco de falha silenciosa no
frontend durante a própria migração. A Etapa 4.4 é diferente: **permanente**,
rodada só depois de a migração já estar concluída e verificada (Etapas
4.1-4.3), com checagem de segurança prévia no código real antes de tocar no
banco — não é a mesma decisão sendo revertida, é um passo posterior sobre uma
base já estável.

**Lado de leitura fechado (08/08/2026).** Pergunta de produto respondida no
chat de planejamento: dado objetivo de voo é compartilhado entre usuários —
decisão consciente, não um problema de RLS a corrigir. Confirmado por
diagnóstico só-leitura, duas partes, rodado manualmente no SQL Editor de
produção:

| bloco | resultado |
|---|---|
| Parte A (catálogo de RLS, 15 tabelas + 1 view) | todas as tabelas de decisão pessoal com policy `= auth.uid()`; todas as tabelas de mercado com policy `auth.uid() is not null`; `weekend_leg_effective` sem policy própria, `security_invoker=true` |
| Parte B (personificação de usuário fictício, `00000000-…-0001`, transação com rollback) | `weekend_leg_user_state=0`, `weekend_leg_ceiling_audit=0`, `weekend_legs_legacy_columns_backup=0`, `weekend_leg_effective=0` — zero leitura de dado pessoal alheio; `weekends=66`, `weekend_legs=132`, histórico/run log de perna > 0 — dado de mercado visível, como decidido; `price_history`/`run_log` (rotas legado) = 0, protegidas por `routes.user_id` |

Achado de higiene sem ação necessária: `grant_select_anon = true` em todas as
tabelas é grant de role padrão do Supabase, não RLS — a policy de linha é quem
efetivamente barra, confirmado pela Parte B. Fecha a pendência de RLS
"genérica" registrada em `STATE.md`, seção 4, nos dois lados (escrita pela
4.4, leitura por esta decisão). Não é mais bloqueio da Etapa 7.

---

## Fatia C — visibilidade de compra entre usuários (ATIVA, 09/08/2026)

Terceira fatia do handoff de UI multi-usuário (depois da Fatia A, item 21 do
`HISTORICO.md`, e da Fatia B, item 22) — a única das três que toca o banco,
não só a UI. Motivo adicional registrado em 08/08/2026: além de sincronia
geral entre os dois usuários, serve para logística de táxi (nota acima,
"Nota (08/08/2026)").

**Regra de produto (aprovada no chat de planejamento):** o outro usuário vê
QUE você comprou uma perna e EM QUAL VOO. Nunca quanto você pagou, qual seu
teto, nem seu localizador. Visibilidade só depois de `status = 'purchased'`
— nunca antes (a alternativa de expor antes da compra foi descartada em
08/08/2026, ver nota acima).

**Mecanismo escolhido: tabela de projeção mantida por trigger.**
`weekend_leg_purchase_shared`, alimentada por uma trigger `security definer`
em `weekend_leg_user_state`, contendo só os 3 campos de voo (companhia,
aeroporto, horário) + chave + timestamps — nenhum campo sensível (teto, valor
pago, notas) chega a existir nessa tabela. Princípio: a garantia é
**estrutural** (o dado sensível não está lá), não depende de um `WHERE`
correto numa view ou função.

**Duas alternativas avaliadas e descartadas**, e por quê:
- **View com `security_invoker = off`** — daria à view acesso irrestrito às
  tabelas de baixo, ignorando a RLS de `weekend_leg_user_state`; um `WHERE`
  errado (ou um `select *` futuro) vazaria teto/pago/notas do outro usuário.
  Bypass de RLS.
- **Função RPC `security definer`** — mesmo problema: a função rodaria com o
  privilégio de quem a criou, não de quem chama, e teria que reimplementar à
  mão exatamente o filtro que a RLS já faz de graça. Bypass de RLS.

Ambas descartadas pelo mesmo motivo de fundo, achado no diagnóstico desta
fatia (08/08/2026): **todo objeto novo em `public` neste projeto nasce com os
7 privilégios para `anon` e `authenticated`** — o Supabase aplica `alter
default privileges grant all` no schema `public`. Isso já tinha corrigido a
leitura do "Achado lateral" da Etapa 4.4 acima (grant da view nunca foi só
`SELECT` por padrão; era só `SELECT` funcional porque a view não é
atualizável, não porque o grant fosse restrito). Numa tabela de projeção, sem
esse achado, o `revoke all` explícito não seria óbvio — e sem ele, `anon`
teria os 7 privilégios sobre um objeto pensado para ser só-leitura de dado
compartilhado.

**Escopo, em duas partes:**
- **Parte 1 (banco) — script pronto, aguardando execução manual do
  usuário.** [sql/fatia_c_visibilidade_compra.sql](sql/fatia_c_visibilidade_compra.sql):
  3 colunas de snapshot em `weekend_leg_user_state` (`purchased_airline`,
  `purchased_airport`, `purchased_departure_time` — fotografia do voo
  comprado, independente das colunas `current_*` que o robô reescreve);
  tabela `weekend_leg_purchase_shared` (chave `leg_id`+`user_id`, FKs `on
  delete cascade`); trigger `flyiop_sync_purchase_shared` (grava/atualiza a
  projeção quando `status = 'purchased'`, remove em qualquer outro status ou
  `DELETE` — o botão "desfazer" do painel limpa a projeção sozinho); RLS
  ligada, `revoke all` explícito de `anon`/`authenticated` antes de qualquer
  grant, `grant select` só para `authenticated`, uma única policy de
  `SELECT` (`auth.uid() is not null`), nenhuma policy de escrita (só a
  trigger grava); backfill idempotente a partir do que já está `purchased`
  hoje (0 linhas). Guarda de inventário no início, 4 blocos de verificação no
  fim (estrutura, grants/policies, prova de comportamento com rollback, prova
  de isolamento com rollback).
- **Parte 2 (frontend)** — prompt separado, ainda não escrito.
- **Telegram** — fica para a Etapa 6, fora do escopo desta fatia.

**Nada tocado nesta fatia:** `weekend_leg_effective`, `weekend_legs`,
`settings`, as policies existentes de `weekend_leg_user_state`,
`flyiop_audit_leg_ceiling`, `flyiop_touch_updated_at`, `docs/`, `src/`.

**Resultado real da execução manual:** pendente — registrar aqui assim que
o usuário rodar o script e colar os 4 blocos de verificação (G0 + V1-V4), no
mesmo formato de tabela usado na Etapa 4.4.

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

`CLAUDE.md` referencia `ROADMAP-AUDITORIA.md` duas vezes como fonte das
regras de scraping (item A5) e do histórico de escopo. Verificado em
01/08/2026: o arquivo **existe** no repositório (`ROADMAP-AUDITORIA.md`,
raiz do repo). Sem risco — a regra dura de scraping não perdeu seu arquivo
de origem. Não corrigido agora — decisão de escopo, não desta iniciativa.

~~`CLAUDE.md` descreve o teto default por perna como R$ 200~~ — **corrigido em
05/08/2026** (pendência 8). Registro do que era: `CLAUDE.md` dizia "default
R$ 200, pendente de calibração" enquanto o valor real em produção era R$ 250
(confirmação de 01/08/2026 em `select count(*) from weekend_legs where
price_ceiling <> 250` retornando 0, registrada acima em "(a)"), e depois R$ 300
(04/08/2026). Fixar o número no texto foi a causa de ele desatualizar duas
vezes; agora aponta para `settings.weekend_default_ceiling`.

**Nota datada de 06/08/2026:** o inventário do Bloco 0 do script da Etapa 4.3,
Passo 3 (`sql/etapa4_3_drop_colunas_legadas.sql`) mostrou que o `default` da
coluna `weekend_legs.price_ceiling` no banco **sempre foi `200`**. O
`CLAUDE.md` não estava desatualizado no sentido de "valor antigo esquecido" —
ele descrevia corretamente o default do DDL da coluna, enquanto o resto da
documentação (`STATE.md`, `PLANO-ATIVO.md`) descrevia o valor efetivo das 132
linhas (`250`, depois `300`), que já divergia do default desde a criação da
tabela. Não eram duas versões conflitantes do mesmo fato — eram dois fatos
diferentes (default do DDL × valor efetivo dos dados). Registro histórico; a
coluna e o default somem com o `DROP` do Passo 3.

`README.md` tem duas descrições desatualizadas, verificadas em 01/08/2026
(linhas 3, 11 e 52 do arquivo):
- Descreve a busca de preço como "via Travelpayouts" (linhas 3 e 11). A
  fonte primária é a `fli` desde 24/07/2026; Travelpayouts é cache
  secundário — ver `CLAUDE.md` e `STATE.md`, "Decisões vivas".
- Descreve o gatilho `push` do `daily.yml` como funcionalidade proposital
  ("roda também a cada push em `src/` (teste real automático)", linha 52).
  **O gatilho não existe mais** — foi removido em 01/08/2026 (item (b) do
  diagnóstico, hoje no `HISTORICO.md`, item 16), justamente por rodar o
  caminho primário completo contra produção (consumia scraping do dia,
  gravava no Supabase, disparava Telegram) a cada commit em `src/**`. O
  `README.md` ficou descrevendo funcionalidade inexistente. Não corrigido
  agora — decisão de escopo, não desta iniciativa.
