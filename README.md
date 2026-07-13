# FlyIop

Monitor automático de passagens aéreas. Busca preços diariamente via Travelpayouts, compara com metas configuradas e avisa por Telegram quando encontra um bom preço ou uma alta preocupante.

Escopo completo em [escopo-projeto-passagens.md](escopo-projeto-passagens.md).

## Setup local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # preencha com seus tokens
```

Edite `config.yaml` com suas rotas e metas reais.

Rodar manualmente:

```bash
export $(cat .env | xargs)
python src/main.py
```

## GitHub Actions

Cadastre os secrets do repositório (Settings → Secrets and variables → Actions):

- `TRAVELPAYOUTS_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

O workflow [`daily.yml`](.github/workflows/daily.yml) roda todo dia às 08:00 (horário de Brasília) e também pode ser disparado manualmente na aba Actions.
