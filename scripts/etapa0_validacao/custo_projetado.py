"""Etapa 0 de validação (23/08/2026) — SOMENTE DIAGNÓSTICO, fora de `src/`.

Cálculo puro (sem rede, sem Supabase) do custo projetado de chamadas se a
grade de calendário (`fli.search.dates.SearchDates`) virasse fonte de
cobertura das 132 pernas, 4x/dia, comparado com o volume atual do lote
`fli` em produção (`src/live_check.py`).

Depende do RESULTADO do item (b) de `grade_calendario.py` (quantas
requisições HTTP reais o intervalo completo dispara) — os números abaixo são
parametrizados, não fixos, porque a Etapa 0 ainda não tinha essa medição
real quando este script foi escrito. Rode `grade_calendario.py` primeiro e
ajuste `REQUESTS_PER_FULL_WINDOW_SCAN` com o valor medido (ou projetado) que
ele imprimir, se quiser um número mais preciso do que o default abaixo.
"""

import sys

TOTAL_LEGS = 132
CHECKS_PER_DAY_CALENDAR_MODEL = 4

# Volume atual em produção (src/live_check.py + .github/workflows/daily.yml):
# lote de 20 pernas/dia (Estágio 0, default de
# system_config.fast_flights_daily_batch_size, ver CLAUDE.md), 1 consulta
# HTTP por perna (GIG, com fallback SDU só se GIG vier vazio — tratado aqui
# como 1 pro caso comum), dentro de uma janela deslizante de 183 dias.
CURRENT_DAILY_BATCH_SIZE = 20
CURRENT_WINDOW_DAYS = 183
CURRENT_REQUESTS_PER_LEG_CHECK = 1  # GIG na maioria; SDU só é 2ª tentativa se GIG vier vazio

# Default conservador pro que 1 varredura completa da grade de calendário
# custaria em requisições HTTP reais. CORREÇÃO: a janela útil real da
# SearchDates não é o intervalo do projeto inteiro (~16 meses) — a própria
# lib documenta que não busca mais que 305 dias no futuro a partir de hoje
# (ver grade_calendario.py, item b, parte 2). Blocos = ceil(305 / 61) = 5,
# não os 8 usados antes (baseados nos ~487 dias do intervalo do projeto).
# Ajuste este número com o resultado real impresso por grade_calendario.py
# (item b) antes de usar esta projeção pra decidir qualquer coisa.
USEFUL_WINDOW_DAYS = 305
MAX_DAYS_PER_SEARCH = 61
REQUESTS_PER_FULL_WINDOW_SCAN_PER_DIRECTION = -(-USEFUL_WINDOW_DAYS // MAX_DAYS_PER_SEARCH)  # ceil(305/61) = 5

# CORREÇÃO: produção usa GIG com fallback SDU (src/live_check.py) — as
# direções reais de calendário são GIG->BSB, SDU->BSB (idas) e BSB->GIG,
# BSB->SDU (voltas), não só GIG<->BSB. 4 direções, não 2.
DIRECTIONS = 4

SEP = "=" * 78


def section(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")


def main() -> int:
    print(SEP)
    print("Etapa 0 de validação — custo_projetado.py")
    print("SOMENTE DIAGNÓSTICO: cálculo puro, sem rede, sem Supabase.")
    print(SEP)

    section("Modelo proposto: grade de calendário, 4x/dia, cobrindo as 132 pernas")
    requests_per_scan = REQUESTS_PER_FULL_WINDOW_SCAN_PER_DIRECTION * DIRECTIONS
    print(
        f"1 varredura completa da janela útil ({USEFUL_WINDOW_DAYS} dias, não os "
        "~16 meses do projeto inteiro — ver correção no item b de "
        f"grade_calendario.py) via SearchDates custa ~{requests_per_scan} "
        f"requisições HTTP reais ({REQUESTS_PER_FULL_WINDOW_SCAN_PER_DIRECTION} "
        f"blocos por direção x {DIRECTIONS} direções — número estimado; ajuste "
        "com o real de grade_calendario.py)."
    )
    print(
        "\nNota de desenho: a grade de calendário devolve preço para TODAS as "
        "datas do range numa passada só (não 1 requisição por perna como o "
        "lote atual) — então o custo NÃO escala com TOTAL_LEGS diretamente. "
        "O paralelo justo é 'quantas passadas completas de calendário por dia' "
        "x 'quantas direções distintas existem entre as 132 pernas' (GIG->BSB, "
        "SDU->BSB, BSB->GIG, BSB->SDU — produção usa GIG com fallback SDU, "
        "src/live_check.py — cobrem, em tese, todas as pernas de uma vez; "
        "estrutura bem diferente do modelo atual de 1 consulta por perna)."
    )

    total_requests_per_day_calendar = (
        requests_per_scan * CHECKS_PER_DAY_CALENDAR_MODEL
    )
    print(
        f"\nSe cada uma das {CHECKS_PER_DAY_CALENDAR_MODEL}x/dia repetir a varredura completa "
        f"das {DIRECTIONS} direções do zero: ~{total_requests_per_day_calendar} requisições "
        "HTTP reais/dia (GIG->BSB, SDU->BSB, BSB->GIG, BSB->SDU, cada uma cobrindo "
        f"os {USEFUL_WINDOW_DAYS} dias úteis)."
    )

    section("Volume atual (produção, Estágio 0 — ver CLAUDE.md/HISTORICO.md item 14)")
    current_daily = CURRENT_DAILY_BATCH_SIZE * CURRENT_REQUESTS_PER_LEG_CHECK
    print(
        f"Lote atual: {CURRENT_DAILY_BATCH_SIZE} pernas/dia x "
        f"{CURRENT_REQUESTS_PER_LEG_CHECK} requisição/perna (GIG, caso comum) "
        f"= ~{current_daily} requisições HTTP reais/dia, dentro de uma janela "
        f"deslizante de {CURRENT_WINDOW_DAYS} dias (~6 meses)."
    )
    print(
        "Cobertura: rotativa — cada perna elegível é checada a cada "
        f"~{TOTAL_LEGS // CURRENT_DAILY_BATCH_SIZE if CURRENT_DAILY_BATCH_SIZE else 'N/A'} dias "
        "em média, não todo dia (ver src/live_check.py:select_batch)."
    )

    section("Comparação direta")
    if current_daily:
        ratio = total_requests_per_day_calendar / current_daily
        print(
            f"Modelo de calendário 4x/dia: ~{total_requests_per_day_calendar} req/dia "
            f"vs. lote atual: ~{current_daily} req/dia "
            f"-> {ratio:.1f}x o volume atual de requisições HTTP reais."
        )
    print(
        "\nRessalva importante: isso NÃO é comparação de qualidade de cobertura, "
        "só de volume de requisições. A grade de calendário cobre a janela "
        "inteira por direção a cada passada (todas as pernas de uma rota de "
        "uma vez); o lote atual cobre pernas específicas de forma rotativa. "
        "O item (b) de grade_calendario.py confirma que dá pra rodar isso de "
        "forma compatível com a regra de 'sequencial, sem paralelismo' do "
        "projeto, DESDE QUE o chamador fatie manualmente em blocos "
        f"<={MAX_DAYS_PER_SEARCH} dias — o paralelismo interno da SearchDates só "
        f"aciona se alguém pedir mais que {MAX_DAYS_PER_SEARCH} dias numa chamada "
        "só, o que este modelo evita por desenho."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
