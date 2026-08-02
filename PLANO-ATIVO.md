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
5. Frontend: Compras/Dashboard por usuário logado; `weekend_legs` vira
   somente-leitura no navegador; redesenho de RLS de update.
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

## Etapa 4.2 — virada de leitura (EM REVISÃO no chat de planejamento, ainda NÃO aprovada)

**Etapa 4.1 concluída e verificada em 01/08/2026.** A estrutura nova
(`weekend_leg_user_state`, `settings.weekend_default_ceiling` = 250,
`weekend_leg_ceiling_audit`, view `weekend_leg_effective`) existe no banco de
produção e passou pelos blocos A–G. Detalhe no `HISTORICO.md`, item 17;
tabelas da verificação em `AUDITORIA-MULTIUSUARIO.md`. Nada lê a estrutura nova
ainda — é o que esta etapa faz.

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

### Pendências nomeadas

1. **Re-sync do estado antes de virar a leitura.** A cópia da 4.1 é uma
   fotografia. A partir dela, todo `paid_price`/nota/compra novo continua indo
   para `weekend_legs` (mundo antigo) e não para `weekend_leg_user_state`.
   Quanto maior o intervalo 4.1 → 4.2, mais desatualizada a cópia. O Bloco 7b é
   re-rodável, mas `on conflict do nothing` **não atualiza** linha já criada — o
   re-sync da 4.2 precisa de lógica própria.
2. **Teto editado no painel entre a 4.1 e a 4.2 vira caso especial do re-sync.**
   O guarda 1c do script exige todas as pernas em 250 no momento de rodar, e a
   4.1 por isso não copia teto. Se um teto for editado no painel depois disso,
   ele vai para a coluna velha (`weekend_legs.price_ceiling`), a auditoria nova
   não enxerga (a trigger é na tabela nova), e o re-sync da 4.2 tem que saber
   transformar aquele valor em **override explícito** em
   `weekend_leg_user_state.price_ceiling` — e registrar isso na auditoria com
   origem própria. Se passar batido, o ajuste manual some na virada.
3. **`docs/js/compras.js`** — ler de `weekend_leg_effective`, escrever em
   `weekend_leg_user_state` (upsert por `leg_id`, sem mandar `user_id`, que tem
   `default auth.uid()`), remover `DEFAULT_CEILING = 200`.
4. **Botão "aplicar teto a todos" muda de significado** (decisão do chat de
   planejamento, 01/08/2026): vira "mudar meu teto padrão", editando
   `settings.weekend_default_ceiling`, e **não sobrescreve** teto ajustado à mão
   perna a perna. Hoje (`docs/js/compras.js:517`) ele faz `update` em massa em
   `weekend_legs` e sobrescreve tudo — o próprio `confirm()` avisa. É mudança de
   comportamento visível, e o texto do `confirm()` tem que mudar junto.
5. **`docs/js/dashboard.js:50,135,188`** — mesma troca de fonte.
6. **`src/weekends.py:164`, `src/live_check.py:123`, `src/telegram_notifier.py:169`**
   — trocar `leg.price_ceiling or 200` pelo teto efetivo por usuário. Encosta na
   Etapa 6 (alerta por perna × usuário); decidir na 4.2 até onde vai.
7. **`src/main.py:328`** — hoje o fluxo de fim de semana usa as settings do
   *primeiro* usuário que tiver rota cadastrada
   (`next(iter(settings_cache.values()))`). Precisa virar iteração explícita por
   usuário.
8. **`CLAUDE.md` e os `or 200`.** A 4.1 cria a fonte de verdade nova
   (`settings.weekend_default_ceiling` = 250) e ela convive com os quatro
   fallbacks `or 200` no código e com o texto desatualizado do `CLAUDE.md`. Sem
   efeito prático enquanto nada lê o novo — não pode passar batido na virada.
9. **Fila de scraping: `get_monitoring_legs` filtra `status = 'monitoring'` NA
   CONSULTA.** Com dois usuários, a perna só sai da fila quando **TODOS**
   pararem de monitorar — se um comprou e o outro não, a perna continua sendo
   checada (é o comportamento correto: o outro ainda precisa do preço).
   (Decisão do chat de planejamento — **não reabrir**.)
10. **Ordenação da fila: `price_ceiling` também ordena** (`price_gap` em
    `src/live_check.py`). Com dois tetos para a mesma perna, a ordenação usa o
    **MENOR teto entre os usuários** — quem tem o teto mais apertado puxa a
    perna pra cima na fila. (Decisão do chat de planejamento — **não
    reabrir**.)
11. **Corrigir `sql/etapa4_1_verificacao.sql`** — cresceu além de só
    consolidar E e F numa linha cada, depois da investigação de 02/08/2026
    (`AUDITORIA-MULTIUSUARIO.md`, "Verificação das estruturas novas" e
    "Lacuna de evidência no artefato de verificação"):
    - Blocos E e F devolvendo **uma única linha de resultado cada** (hoje têm
      vários `select`, e o SQL Editor do Supabase só exibe o resultado do
      último — os anteriores somem em silêncio).
    - **`auth.uid()` tem que virar COLUNA da mesma linha de resultado**, não um
      `select` à parte — senão a guarda do teste (saber se o contexto de papel
      foi de fato aplicado) continua sendo descartada pelo SQL Editor, mesmo
      depois de consolidar.
    - **O bloco F precisa de um discriminador** que separe "usuário legítimo"
      de "dono do banco" — hoje, com uma conta só, os dois casos devolvem
      resultado idêntico, e o bloco não prova isolamento positivo. Provavelmente
      exige simular um **segundo `user_id`** dentro da própria transação com
      `rollback`. Desenho a revisar no chat de planejamento — **não
      implementar agora**.
    - Limpar do `.sql` os resultados colados como tabelas markdown, que hoje
      quebram o arquivo como SQL executável.

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

`CLAUDE.md` descreve o teto default por perna como R$ 200 (seção "Fins de
semana RIO↔BSB", "default R$ 200, pendente de calibração"). O valor real em
uso em produção é **R$ 250** (ver `STATE.md`, seção 3 item 3, e a
confirmação de 01/08/2026 em `select count(*) from weekend_legs where
price_ceiling <> 250` retornando 0, registrada acima em "(a)"). `CLAUDE.md`
ficou desatualizado nesse número. Não corrigido agora — decisão de escopo,
não desta iniciativa.

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
