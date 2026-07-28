# STATE.md — FlyIop

> Atualizado em: 27/07/2026
> Última sessão: Claude Code (documentação/manutenção)

---

## 1. Status atual

FlyIop está em produção, monitorando 66 fins de semana (132 "pernas" ida/volta independentes) na rota RIO↔BSB entre set/2026 e dez/2027. Fonte primária de preço é a `fli` (endpoint interno do Google Flights, migrada de `fast-flights` por bug de parsing), com Travelpayouts como cache secundário. Robô diário via GitHub Actions grava no Supabase; alertas via bot Telegram (FlyIopBot); site em GitHub Pages com 3 páginas (Dashboard, Compras, Configurações), login via Supabase Auth. Painel de Compras já tem: cards por fim de semana, teto editável por perna, campo de notas (localizador/horário), campo de valor pago, filtros (chips), selos de feriado/alta temporada, estado visual salvo/não-salvo/em-edição (âmbar), hierarquia visual por preço/status (perna comprada com identidade forte, card 2/2 colapsando por padrão com total pago). Dashboard redesenhado (ação do dia, urgência, progresso, oportunidades, orçamento, saúde do sistema). Alerta de bloqueio do scraping agora é rico e escalona por dias consecutivos. As 3 rotas flexíveis antigas (BSB→GIG, GIG→BSB, RIA→BSB) continuam rodando em paralelo, tratadas como legado.

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

## 3. Próximos passos (ordem sugerida)

1. **Recalibrar o teto padrão por perna** (hoje R$250) — dado real recente mostrou pernas a R$242-248, ou seja, o teto está quase colado no preço real; usuário decidiu esperar mais alguns dias de coleta antes de decidir o número novo.
2. **Investigar arquitetura multi-usuário** (ver seção 4 — decisão em aberto, não iniciada).
3. Migrar esta conversa pro Projeto dedicado "FlyIop" no Claude — organizacional, sem pressa, decisão do usuário.

## 4. Bloqueios / perguntas em aberto

- **Multi-usuário (amigo que também vai comprar RIO↔BSB em 2027):** decidido em linhas gerais — preço/histórico/robô continuam **compartilhados** (mesma rota, não faz sentido duplicar scraping); o que precisa ser separado é a "camada de decisão pessoal" por usuário (teto, status de compra, notas, valor pago). Login próprio dele via Supabase Auth; alertas em bot Telegram separado (canal simples, não integrado ao mesmo bot). **Falta**: investigação de como a RLS/schema atual está desenhada hoje (provavelmente assume usuário único) antes de qualquer plano de implementação — próxima etapa é um prompt de auditoria, não implementação direta.
- **Teto padrão**: aguardando mais dias de coleta de preço real antes de decidir o valor de recalibração.

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
- `PLANO-ATIVO.md` — plano técnico detalhado só da Parte em execução agora (vazio no momento desta versão — nada em andamento)
- `HISTORICO.md` — tudo já decidido/implementado, cronológico
- `CLAUDE.md` — escopo geral do projeto (lido automaticamente pelo Claude Code)
- `PROTOCOLO-DE-TRABALHO.md` — como usuário e Claude Code trabalham juntos (Plan Mode, gatilhos de revisão, regra de manutenção dos três arquivos de documentação)
