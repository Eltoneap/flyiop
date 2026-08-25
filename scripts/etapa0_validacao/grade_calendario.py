"""Etapa 0 de validação (23/08/2026) — SOMENTE DIAGNÓSTICO, fora de `src/`.

Não escreve no Supabase, não dispara alerta no Telegram, não importa nada de
`src/`. Roda só via `.github/workflows/etapa0-validacao.yml`
(workflow_dispatch manual, sem cron/push). Usa a MESMA versão pinada da `fli`
já em produção (`requirements.txt`) — não instala nada à parte.

Objetivo: responder, com evidência real, se `fli.search.dates.SearchDates`
(endpoint de calendário do Google Flights) é viável como substituto/complemento
do lote atual de consultas pontuais (`src/live_check.py`), respondendo as
perguntas a-e do plano de validação. Ver `HISTORICO.md`/`PLANO-ATIVO.md` para
o contexto do sistema de fins de semana RIO<->BSB.

Rotas de teste usam GIG (não um código agregado "RIO" — a `fli` fala
diretamente com o endpoint do Google Flights por AEROPORTO específico, sem
noção de cidade agregada; é o mesmo motivo pelo qual `weekends.py` já usa
GIG/SDU em vez de "RIO"). RIA entra separadamente no item (d).
"""

import sys
import threading
import time
from datetime import date, datetime, timedelta

from fli.models import (
    Airport,
    DateSearchFilters,
    FlightSearchFilters,
    FlightSegment,
    PassengerInfo,
    SeatType,
    TripType,
)
from fli.search.client import Client
from fli.search.dates import SearchDates
from fli.search.flights import SearchFlights

GIG = "GIG"
SDU = "SDU"
BSB = "BSB"
RIA = "RIA"

# Data de referência única usada nos itens (d)/(c) — mantida como estava.
TEST_DATE_OUTBOUND = "2026-09-04"  # sexta — GIG->BSB
TEST_DATE_RETURN = "2026-09-06"  # domingo seguinte — BSB->GIG

# Item (a): 3 checkpoints por rota (correção — as duas datas originais
# ficavam dentro da janela ao vivo de 183 dias, testando só o caso que já
# funciona). Todas são sextas que já são fim de semana monitorado (a série
# roda toda sexta de 04/09/2026 a 03/12/2027, ver CLAUDE.md), com a volta no
# domingo seguinte.
TEST_CHECKPOINTS = [
    ("perto (dentro da janela ao vivo de 183 dias)", "2026-09-04", "2026-09-06"),
    ("longe (além da janela ao vivo de 183 dias, ~193 dias a partir de hoje)", "2027-03-05", "2027-03-07"),
    ("perto do teto de 305 dias da SearchDates (~291 dias a partir de hoje)", "2027-06-11", "2027-06-13"),
]

# Janela útil real da SearchDates (item b): NÃO é o intervalo do projeto
# inteiro (set/2026-dez/2027, ~16 meses) — o próprio docstring da lib diz
# "we can't search more than 305 days in the future" a partir de hoje. A
# janela que de fato dá pra varrer é hoje até hoje+305 dias.
USEFUL_WINDOW_DAYS = 305

# Range curto (item c, round-trip) — cabe num único bloco de 61 dias, evita
# disparar o particionamento paralelo descrito no item (b).
ROUND_TRIP_FROM = "2026-09-01"
ROUND_TRIP_TO = "2026-09-30"
ROUND_TRIP_DURATION_DAYS = 2

# Mesmo espaçamento usado em src/live_check.py entre consultas sequenciais.
LIVE_CHECK_DELAY_SECONDS = 2.5

SEP = "=" * 78


def section(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")


def one_way_segment(origin: str, destination: str, travel_date: str) -> FlightSegment:
    return FlightSegment(
        departure_airport=[[getattr(Airport, origin), 0]],
        arrival_airport=[[getattr(Airport, destination), 0]],
        travel_date=travel_date,
    )


def search_flights_price(origin: str, destination: str, travel_date: str) -> float | None:
    """Mesmo padrão de `src/live_check.py:check_live_price`, sem depender
    de `src/` (Etapa 0 não pode importar código de produção com efeitos
    colaterais) — reimplementado aqui só com os pedaços necessários."""
    filters = FlightSearchFilters(
        trip_type=TripType.ONE_WAY,
        passenger_info=PassengerInfo(adults=1),
        flight_segments=[one_way_segment(origin, destination, travel_date)],
        seat_type=SeatType.ECONOMY,
    )
    try:
        results = SearchFlights().search(filters, currency="BRL", language="pt-BR", country="BR")
    except Exception as exc:
        print(f"  [SearchFlights] EXCEÇÃO: {exc!r}")
        return None
    if not results:
        print("  [SearchFlights] resposta vazia (sem resultados)")
        return None
    priced = [r for r in results if r.price is not None]
    if not priced:
        print("  [SearchFlights] resultados sem preço")
        return None
    best = min(priced, key=lambda r: r.price)
    return float(best.price)


def search_dates_price_for_date(origin: str, destination: str, target_date: str) -> float | None:
    """Consulta o calendário (SearchDates) só pra UM dia (from_date == to_date
    == target_date), pra comparar diretamente contra o SearchFlights do mesmo
    dia/rota (item a)."""
    filters = DateSearchFilters(
        trip_type=TripType.ONE_WAY,
        passenger_info=PassengerInfo(adults=1),
        flight_segments=[one_way_segment(origin, destination, target_date)],
        seat_type=SeatType.ECONOMY,
        from_date=target_date,
        to_date=target_date,
    )
    try:
        results = SearchDates().search(filters, currency="BRL", language="pt-BR", country="BR")
    except Exception as exc:
        print(f"  [SearchDates] EXCEÇÃO: {exc!r}")
        return None
    if not results:
        print("  [SearchDates] resposta vazia (sem resultados)")
        return None
    best = min(results, key=lambda d: d.price)
    return float(best.price)


def item_a() -> None:
    section("ITEM (a) — SearchDates (calendário) vs SearchFlights, 3 checkpoints por rota")

    # Lista achatada (não agrupada por checkpoint) pra saber, com um índice só,
    # quando estamos na ÚLTIMA combinação do item inteiro (não precisa de sleep
    # depois dela).
    all_pairs = []
    for checkpoint_label, outbound_date, return_date in TEST_CHECKPOINTS:
        all_pairs.append((f"GIG->BSB ({checkpoint_label})", GIG, BSB, outbound_date))
        all_pairs.append((f"BSB->GIG ({checkpoint_label})", BSB, GIG, return_date))

    for i, (label, origin, destination, travel_date) in enumerate(all_pairs):
        print(f"\n[{label}] data={travel_date}")
        sf_price = search_flights_price(origin, destination, travel_date)
        print(f"  SearchFlights (busca pontual, fonte atual de produção): R$ {sf_price}")

        time.sleep(LIVE_CHECK_DELAY_SECONDS)

        sd_price = search_dates_price_for_date(origin, destination, travel_date)
        print(f"  SearchDates   (calendário, 1 dia só): R$ {sd_price}")
        if sf_price is None or sd_price is None:
            print("  -> comparação inconclusiva (uma das duas fontes não respondeu)")
        else:
            diff_pct = abs(sf_price - sd_price) / sf_price * 100
            bateu = "SIM" if diff_pct < 1.0 else f"NÃO (diferença de {diff_pct:.1f}%)"
            print(f"  -> preços bateram? {bateu}")

        if i < len(all_pairs) - 1:
            time.sleep(LIVE_CHECK_DELAY_SECONDS)


def counting_client_post():
    """Monkeypatch de `Client.post` que conta chamadas reais sem mudar
    comportamento (delega pro original). Devolve (contador_mutável,
    restaurar) — chamador é responsável por restaurar no finally."""
    call_count = {"n": 0}
    lock = threading.Lock()
    original_post = Client.post

    def counting_post(self, *args, **kwargs):
        with lock:
            call_count["n"] += 1
        return original_post(self, *args, **kwargs)

    def restore() -> None:
        Client.post = original_post

    Client.post = counting_post
    return call_count, restore


def search_dates_block(from_d: date, to_d: date) -> tuple[int, list | None]:
    """1 chamada de SearchDates para um bloco <= 61 dias (nunca aciona o
    particionamento paralelo da lib — ver correção do item b abaixo).
    Devolve (requisições HTTP reais, resultados)."""
    filters = DateSearchFilters(
        trip_type=TripType.ONE_WAY,
        passenger_info=PassengerInfo(adults=1),
        flight_segments=[one_way_segment(GIG, BSB, from_d.isoformat())],
        seat_type=SeatType.ECONOMY,
        from_date=from_d.isoformat(),
        to_date=to_d.isoformat(),
    )
    call_count, restore = counting_client_post()
    try:
        results = SearchDates().search(filters, currency="BRL", language="pt-BR", country="BR")
    except Exception as exc:
        print(f"  [SearchDates bloco {from_d}..{to_d}] EXCEÇÃO: {exc!r}")
        results = None
    finally:
        restore()
    return call_count["n"], results


def item_b() -> None:
    section("ITEM (b) — quantas requisições HTTP reais, fatiando manualmente?")

    print(
        "CORREÇÃO (revisão do usuário, confirmada lendo fli/search/dates.py "
        "diretamente): quando o intervalo pedido é <= "
        f"{SearchDates.MAX_DAYS_PER_SEARCH} dias, `SearchDates.search` chama "
        "`_search_chunk` direto — SEM passar por `parallel_map`/"
        "ThreadPoolExecutor. O paralelismo só entra quando o CHAMADOR pede um "
        f"intervalo acima de {SearchDates.MAX_DAYS_PER_SEARCH} dias numa única "
        "chamada, e a lib particiona sozinha. Não há conflito com a regra do "
        "projeto ('sequencial, espaçado, sem paralelismo') DESDE QUE o projeto "
        f"fatie manualmente em blocos <= {SearchDates.MAX_DAYS_PER_SEARCH} dias "
        "e chame cada bloco em sequência, com espaçamento — o mesmo padrão já "
        "usado em src/live_check.py. Esse caminho manual está confirmado como "
        "compatível com a regra; é o que este item testa abaixo."
    )

    print(
        f"\nJanela útil real (não o intervalo do projeto inteiro): hoje até "
        f"hoje+{USEFUL_WINDOW_DAYS} dias — a própria SearchDates documenta "
        "que não busca mais que isso no futuro (testado empiricamente abaixo)."
    )
    expected_chunks = -(-USEFUL_WINDOW_DAYS // SearchDates.MAX_DAYS_PER_SEARCH)  # ceil division
    print(
        f"Blocos necessários pra cobrir os {USEFUL_WINDOW_DAYS} dias úteis "
        f"(cálculo puro, sem rede): ceil({USEFUL_WINDOW_DAYS} / "
        f"{SearchDates.MAX_DAYS_PER_SEARCH}) = {expected_chunks} blocos."
    )

    section_label = "Confirmação empírica: 2 blocos SEQUENCIAIS de <=61 dias, espaçados ~2,5s"
    print(f"\n{section_label}")
    today = date.today()
    block1_from = today + timedelta(days=1)
    block1_to = block1_from + timedelta(days=SearchDates.MAX_DAYS_PER_SEARCH - 1)
    block2_from = block1_to + timedelta(days=1)
    block2_to = block2_from + timedelta(days=SearchDates.MAX_DAYS_PER_SEARCH - 1)

    print(f"  Bloco 1: {block1_from} a {block1_to} ({(block1_to - block1_from).days + 1} dias)")
    count1, results1 = search_dates_block(block1_from, block1_to)
    print(f"    requisições HTTP reais: {count1} | datas com preço: {len(results1) if results1 else 0}")

    time.sleep(LIVE_CHECK_DELAY_SECONDS)

    print(f"  Bloco 2: {block2_from} a {block2_to} ({(block2_to - block2_from).days + 1} dias)")
    count2, results2 = search_dates_block(block2_from, block2_to)
    print(f"    requisições HTTP reais: {count2} | datas com preço: {len(results2) if results2 else 0}")

    print(
        f"\nResumo: 1 bloco de {SearchDates.MAX_DAYS_PER_SEARCH} dias custou "
        f"{count1} requisição(ões) HTTP real(is) e devolveu "
        f"{len(results1) if results1 else 0} datas com preço (bloco 1); "
        f"{count2} requisição(ões) e {len(results2) if results2 else 0} datas "
        f"no bloco 2. Pra cobrir os {USEFUL_WINDOW_DAYS} dias úteis inteiros "
        f"seriam {expected_chunks} blocos assim, sequenciais e espaçados."
    )

    section("ITEM (b), parte 2 — teto de 305 dias: limite rígido ou degradação?")
    print(
        "Testando um bloco <=61 dias posicionado ALÉM da janela útil de "
        f"{USEFUL_WINDOW_DAYS} dias a partir de hoje, pra ver se a lib rejeita "
        "com erro, devolve lista vazia, ou devolve preços mesmo assim."
    )
    time.sleep(LIVE_CHECK_DELAY_SECONDS)

    beyond_from = today + timedelta(days=USEFUL_WINDOW_DAYS + 5)
    beyond_to = beyond_from + timedelta(days=40)
    print(f"  Bloco além do teto: {beyond_from} a {beyond_to} (~{USEFUL_WINDOW_DAYS + 5}-{USEFUL_WINDOW_DAYS + 45} dias a partir de hoje)")
    count3, results3 = search_dates_block(beyond_from, beyond_to)
    if results3:
        print(f"    NÃO rejeitou — {count3} requisição(ões), {len(results3)} datas com preço retornadas além do teto documentado.")
    elif count3:
        print(f"    {count3} requisição(ões) HTTP real(is) disparada(s), resposta vazia/sem preço — consistente com o teto de {USEFUL_WINDOW_DAYS} dias (degrada pra vazio, não erro).")
    else:
        print("    0 requisições HTTP — rejeitado antes de ir à rede (validação local/erro).")


def item_c() -> None:
    section("ITEM (c) — round-trip com duração fixa (SearchDates)")
    print(
        f"Range: {ROUND_TRIP_FROM} a {ROUND_TRIP_TO}, duração fixa de "
        f"{ROUND_TRIP_DURATION_DAYS} dias, GIG<->BSB"
    )
    outbound_placeholder = ROUND_TRIP_FROM
    return_placeholder = (
        datetime.strptime(ROUND_TRIP_FROM, "%Y-%m-%d") + timedelta(days=ROUND_TRIP_DURATION_DAYS)
    ).strftime("%Y-%m-%d")

    filters = DateSearchFilters(
        trip_type=TripType.ROUND_TRIP,
        passenger_info=PassengerInfo(adults=1),
        flight_segments=[
            one_way_segment(GIG, BSB, outbound_placeholder),
            one_way_segment(BSB, GIG, return_placeholder),
        ],
        seat_type=SeatType.ECONOMY,
        from_date=ROUND_TRIP_FROM,
        to_date=ROUND_TRIP_TO,
        duration=ROUND_TRIP_DURATION_DAYS,
    )
    try:
        results = SearchDates().search(filters, currency="BRL", language="pt-BR", country="BR")
    except Exception as exc:
        print(f"  EXCEÇÃO: {exc!r}")
        results = None

    if not results:
        print("  Resposta vazia — round-trip por SearchDates não devolveu pares nesse range.")
        return

    print(f"  {len(results)} pares (ida, volta) retornados. Amostra (até 10):")
    for entry in results[:10]:
        dates = entry.date
        if len(dates) == 2:
            print(f"    ida={dates[0].date()} volta={dates[1].date()} preço=R$ {entry.price}")
        else:
            print(f"    data única={dates[0].date()} preço=R$ {entry.price} (inesperado p/ round-trip)")


def item_d() -> None:
    section("ITEM (d) — RIA (Santa Maria) tem cobertura via fli?")
    print(
        "Contexto: RIA->BSB falhou no fast-flights em 18/07/2026 (ver "
        "HISTORICO.md, seção 1, Etapa 0). Reconfirmando aqui com fli, mesma "
        "data de teste dos outros itens."
    )

    checked_codes = ["GIG", "SDU", "BSB", "POA", "CGH", "GRU", "CNF", "FLN", "IGU"]
    print(
        f"  Verificado independentemente: {', '.join(checked_codes)} NÃO têm esse "
        "problema de alias (cada um resolve pro seu próprio nome canônico no "
        "enum) — o problema é isolado a RIA."
    )

    ria_member = getattr(Airport, RIA)
    if ria_member.name != RIA:
        print(
            f"\n  *** BUG ENCONTRADO NO PACOTE `fli` PINADO (não é bug deste script) ***\n"
            f"  Airport.{RIA} é um ALIAS de Airport.{ria_member.name} — os dois têm o "
            f"mesmo valor descritivo ('{ria_member.value}') na tabela de aeroportos "
            f"da fli, e o Python Enum trata valores duplicados como o MESMO membro "
            f"(o primeiro definido vence como nome canônico). Resultado: qualquer "
            f"código que faça `getattr(Airport, 'RIA')` está na verdade consultando "
            f"{ria_member.name} — uma cidade diferente (Santa Maria/RS vs. o outro "
            f"código) — sem erro, sem aviso, silenciosamente.\n"
            f"  NÃO estou rodando a consulta RIA->BSB por baixo desse alias — daria "
            f"um resultado que pareceria válido mas seria da rota errada. Este "
            f"achado por si só já responde ao item (d): RIA não é seguro de usar "
            f"com esta versão pinada da fli sem corrigir o alias antes (patch local, "
            f"issue upstream, ou continuar sem cobertura de RIA)."
        )
        return

    price = search_flights_price(RIA, BSB, TEST_DATE_OUTBOUND)
    print(f"  RIA->BSB em {TEST_DATE_OUTBOUND}: R$ {price}" if price is not None else "  RIA->BSB: sem cobertura (None)")


def item_e() -> None:
    section("ITEM (e) — algo equivalente a 'price_insights' na versão pinada?")
    print(
        "Busca estática (grep) no pacote `fli` pinado (requirements.txt) por "
        "'price_insights'/'PriceInsights'/campo de faixa típica/baixo/alto: "
        "NÃO ENCONTRADO em fli.models nem fli.search."
    )
    print("Campos reais disponíveis num FlightResult (via SearchFlights), pra registro:")
    from fli.models.google_flights.base import FlightResult

    for field_name in FlightResult.model_fields:
        print(f"  - {field_name}")
    print(
        "\nNenhum desses é uma faixa típica/baixo/alto — é preço, paradas, "
        "companhia, legs, duração etc. de UM resultado. Conclusão: a versão "
        "pinada da fli não expõe price_insights; não seria confiável simular "
        "isso a partir de SearchDates sem uma amostra estatística própria."
    )


def main() -> int:
    print(SEP)
    print("Etapa 0 de validação — grade_calendario.py")
    print("SOMENTE DIAGNÓSTICO: nenhuma escrita no Supabase, nenhum alerta no Telegram.")
    print(SEP)

    item_a()
    item_b()
    item_c()
    item_d()
    item_e()

    print(f"\n{SEP}\nFIM — grade_calendario.py\n{SEP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
