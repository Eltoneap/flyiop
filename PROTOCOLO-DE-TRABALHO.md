# Protocolo de Trabalho — FlyIop

## Documentação — três arquivos com papéis exclusivos (regra vigente desde 27/07/2026, substitui qualquer versão anterior)

Status do projeto vive só em `STATE.md` — este arquivo (`PROTOCOLO-DE-TRABALHO.md`) descreve só o processo de trabalho, não o estado atual, pra não duplicar/divergir. Três papéis, sem sobreposição:

- **`STATE.md`** — orientação de alto nível: status atual, decisões vivas, próximos passos, bloqueios/perguntas em aberto, fora de escopo. Curto, sempre atualizado. É o que se lê no início de qualquer sessão nova.
- **`PLANO-ATIVO.md`** — plano técnico detalhado só da implementação em andamento agora (SQL, código, testes, passo a passo). Fica **vazio** quando nada está em execução; populado só durante uma Parte ativa.
- **`HISTORICO.md`** — arquivo morto de tudo já entregue, cronológico (investigações, decisões tomadas, partes concluídas, com data).

Nada de arquivos de plano soltos na raiz com nomes ad-hoc (`PLAN-*.md`, `ALVO-*.md`, nomes aleatórios de Plan Mode).

### Regra de manutenção

- **Ao concluir qualquer Parte**: mover o conteúdo do `PLANO-ATIVO.md` pro `HISTORICO.md` (seção nova, datada); esvaziar o `PLANO-ATIVO.md`; atualizar o `STATE.md` (status atual, decisões vivas, remover da lista de próximos passos o que foi concluído).
- **Ao iniciar uma Parte nova**: escrever o plano técnico completo só no `PLANO-ATIVO.md`. No chat, mostrar um resumo curto pedindo aprovação — nunca o arquivo inteiro.
- **Apresentação no chat sempre mostra só o delta**: ao apresentar um plano ou atualização, mostrar apenas a seção nova/alterada ou um resumo, nunca um arquivo inteiro reproduzido. Para dar contexto, referenciar a seção pelo nome (ex.: "ver Parte 7 no HISTORICO.md") em vez de reproduzir o conteúdo. O arquivo completo fica no disco pra consulta a qualquer momento.
- **Uma coisa por vez.** O chat de planejamento entrega UM prompt ou UMA decisão por rodada, nunca uma lista empilhada. Achado que não vira prompt imediato deve ser registrado em arquivo (`PLANO-ATIVO.md` ou `STATE.md`) na mesma rodada em que aparece — análise sem registro se perde. Se surgirem vários achados de uma vez, todos vão pra documentação e só o mais urgente vira prompt. (Origem: sessão de diagnóstico de 31/07/2026, que acumulou várias perguntas/achados soltos ao longo da conversa antes de registrar qualquer coisa em arquivo.)
- **`STATE.md` só descreve uma feature como "em produção" se o commit correspondente já foi enviado (push) ao repositório remoto** — trabalho implementado localmente mas não commitado/enviado deve ser descrito como "implementado localmente, pendente de commit", nunca como em produção. (Motivação: incidente de 30/07/2026 — Parte 9, Parte 10 e a Etapa 3 multi-usuário ficaram descritas como "concluídas"/"em produção" no `STATE.md` enquanto um bug de agendamento silencioso, corrigido no mesmo dia, ver `HISTORICO.md` item 15, impedia essas mudanças de rodar de fato em produção. "Commitado e enviado" é a barra mínima pra usar "em produção" — não substitui checar se a execução real está funcionando, mas evita a versão mais grave do problema: descrever como ativo algo que nem chegou ao remoto.)

## Eficiência no chat de planejamento (regra vigente desde 03/08/2026)

- O chat de planejamento (Claude, fora desta sessão de código) deve revisar um plano/retorno inteiro de uma vez e levantar todos os problemas encontrados numa mensagem só — não fatiar a revisão em várias rodadas de ida e volta quando os problemas já eram visíveis na primeira leitura.
- Claude (chat de planejamento) não empilha decisões, checagens ou próximos passos sem confirmação explícita do usuário a cada um — mas isso não deve virar fatiamento artificial de uma única revisão em múltiplas mensagens.
- Sempre que o chat de planejamento precisar que o usuário suba/cole algo (resultado de query, schema, diff, output do Claude Code), isso deve ser pedido de forma explícita e isolada — nunca assumido ou buscado por atalho (ex.: não tentar buscar código direto de fontes externas como substituto de pedir ao usuário ou ao Claude Code).
- Todo prompt destinado ao Claude Code é entregue em bloco de código (formato prompt), nunca descrito em prosa solta ou como arquivo .md anexado.
