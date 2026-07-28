# Plano Ativo — FlyIop

_Atualizado em 24/07/2026. Contém só o que está em execução ou pendente de aprovação/implementação. Tudo que já foi entregue (com data e decisões tomadas) está em `HISTORICO.md` — referencie por lá em vez de reproduzir aqui._

**Regra de apresentação (24/07/2026):** ao apresentar um plano ou atualização no chat, mostrar só a seção nova/alterada, nunca o arquivo inteiro. Para contexto, referenciar a seção pelo nome (ex.: "ver Parte 8 no HISTORICO.md") em vez de reproduzir. O arquivo completo fica no disco; o chat recebe só o delta. (Ver também `PROTOCOLO-DE-TRABALHO.md`.)

---

## Parte 9 — Redesign visual da aba Compras — Bloco B (pendente, não iniciar)

Bloco A concluído e registrado no `HISTORICO.md` (Parte 10). Bloco B só começa depois que o usuário validar o Bloco A no ar. Referência visual: `design/mockup-compras.html`. Tokens `--amber`/`--amber-bg`/`--amber-line` já existem em `style.css` (adicionados no Bloco A), reservados pra este bloco.

- **B1** Botão "Salvar": salvo → apagado; não salvo → âmbar sólido (`--amber`); campo alterado ganha `field-dirty` (`--amber-bg`). Reaproveita o mecanismo `markFieldState` já existente em `compras.js`.
- **B2** Card 2/2 colapsa por padrão (faixa verde com datas + total pago), expande no clique. Total só soma se **ambas** as pernas tiverem `paid_price`; senão "total parcial" ou omite o número — nunca somar ignorando campo vazio.

Arquivos: `docs/css/style.css`, `docs/js/compras.js` — mesmos do Bloco A, sem novos arquivos.
