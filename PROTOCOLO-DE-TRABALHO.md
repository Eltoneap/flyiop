# Protocolo de Trabalho — FlyIop

## Status Atual

_Verificado em 14/07/2026 direto no código e na infraestrutura real — não no que o `escopo-projeto-passagens.md` previa. Atualizado após a rodada "produto completo" (alerta rico, run_log, robustez)._

### Arquitetura em produção

- **Fonte de dados**: Travelpayouts Data API (`v2/prices/month-matrix`), ida e volta (`one_way=false`), varrendo os próximos 6 meses de calendário por rota a cada execução (até 18 chamadas/dia com as 3 rotas atuais).
- **Banco de dados**: Supabase (Postgres na nuvem), não SQLite/CSV. Tabelas: `routes`, `price_history`, `settings`, `bot_state`. Todas com Row Level Security.
- **Site**: estático em `docs/`, hospedado no GitHub Pages, login via Supabase Auth. Duas telas: Dashboard (histórico, gráfico, badge de status, aviso de janela de compra) e Configurações (CRUD de rotas com busca de aeroportos por nome/cidade, abas de rotas ativas/arquivadas, preferências de tendência e milhas).
- **Automação**: dois workflows do GitHub Actions —
  - `daily.yml`: roda 1x/dia (08:00 BRT), busca preços e grava no Supabase, dispara alerta no Telegram quando aplicável
  - `bot_commands.yml`: roda a cada 5 min, escuta comandos recebidos no Telegram (`/status`, `/precos`, `/rotas`) e responde sob demanda com o estado atual das rotas ativas
- **Repositório**: público (`github.com/Eltoneap/flyiop`) — necessário para GitHub Pages gratuito.

### Funciona e foi testado ponta a ponta

- Busca de preço real (ida e volta) → gravação no Supabase → avaliação de meta/tendência → alerta no Telegram
- Login no site, cadastro/edição/arquivamento de rotas, gráfico de histórico no Dashboard
- Detecção de tendência de alta **e** queda (mesmo limiar configurado, nas duas direções)
- Aviso de janela de compra: regra geral (pesquisa de mercado) até haver histórico suficiente; depois disso, cálculo dinâmico com o histórico real da própria rota

### Alerta e /status ricos (14/07/2026)

A notificação agora traz: datas de ida **e volta**, escalas, dias de antecedência, frescor do preço (`found_at` do cache Aviasales, com aviso "confirme no site"), meta + média 30d, posição na janela de compra recomendada, e dois links reais verificados no navegador — deep-link Aviasales (`aviasales.com/search/BSB3107GIG07081`) e Google Flights com ida e volta. Histórico grava `return_date`, `found_at`, `stops`, `days_ahead`. Tabela `run_log` registra o resultado por rota a cada execução ('ok'/'no_data'/'error'); dashboard mostra "última verificação do robô", distingue "sem cobertura na fonte" de "aguardando primeira execução", tem export CSV client-side e link Aviasales por rota. Robô: try/except por rota (uma falha não derruba as outras), retry com backoff em 429/5xx, resumo diário consolidado em 1 mensagem, sugestão de arquivar rota após 7 dias seguidos sem cobertura. Workflow `daily.yml` também roda em push de `src/**` (testes reais a cada mudança; conclusão acompanhável pela API pública do GitHub, repo é público).

### Limitações e funcionalidades "mortas" conhecidas

- **Comparador de milhas (`miles.py`)**: não existe fonte gratuita de preços em milhas por API. O módulo fica no repo aguardando fonte futura; a linha morta "sem opção em milhas" foi removida das mensagens e logs.
- **Cobertura de dados por rota é desigual**: RIA→BSB segue sem nenhum preço (nem ida e volta, nem só ida) — limitação de cache da Travelpayouts, não é bug. O produto agora expõe isso no dashboard e sugere arquivamento após 7 dias.

### Divergências do escopo original

Ver comparação detalhada entregue em 14/07/2026 (arquitetura de dados, frequência de chamadas, interface web inteira, comando sob demanda no Telegram, e mais — nenhuma dessas mudanças está refletida no texto do `escopo-projeto-passagens.md`, que continua descrevendo o plano original de 12/07/2026).

### Não implementado (backlog original, segue válido)

- Aeroportos alternativos na mesma cidade
- Painel de sazonalidade histórica com dados ANAC
- Alerta de câmbio combinado com preço
- Regras da tarifa (bagagem, remarcação) no alerta
- Reavaliação pós-compra
