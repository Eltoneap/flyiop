"""Radar de calendário — grade de preços via `fli.search.dates.SearchDates`
(endpoint interno `GetCalendarGraph` do Google Flights), validada em produção
real na Etapa 0 (24/08/2026, ver `HISTORICO.md` item 24): devolve o MESMO
preço que `SearchFlights` (0,0% de diferença em 6 comparações), e 1 bloco de
<=61 dias custa 1 requisição HTTP real. Descobre preço em lote, ~305 dias a
partir de "hoje" (teto real da lib, degrada pra vazio sem erro além disso —
não é buraco de cobertura corrigível), fatiado manualmente em blocos <=61
dias e chamado em SEQUÊNCIA, espaçado ~2,5s (mesmo padrão de
`live_check.py`) — `SearchDates.search` só aciona `ThreadPoolExecutor`
quando o INTERVALO PEDIDO numa única chamada passa do teto; fatiar na mão
nunca aciona esse caminho.

Nível RADAR, não PRECISÃO: este módulo só descobre e grava preço em
`weekend_radar_grid` — nunca decide alerta, nunca chama `SearchFlights`,
nunca manda mensagem de perna no Telegram (só o alerta de anomalia, que é
sobre o radar em si, não sobre preço de perna). A seleção de candidatas pra
precisão (`select_precision_candidates`/`load_radar_candidates`, abaixo) é
lógica pura de leitura — quem chama e processa é `main.py`, que segue sendo
o ÚNICO dono do laço de envio de alerta de perna (fan-out por usuário,
cooldown, `degraded_alert`, `insert_weekend_alert_log`). Duplicar esse laço
aqui recriaria exatamente o risco que a Fatia D4 já resolveu.

Kill-switch PRÓPRIO (`system_config.radar_enabled`), separado de
`fast_flights_enabled` — desligar um nunca desliga o outro. Nasce `false`.

Regras não-negociáveis, as mesmas de sempre (`CLAUDE.md`): sequencial,
espaçado, sem proxy, sem evasão. Se a fonte bloquear (ou o volume de dados
cair de forma suspeita em relação ao histórico), o radar recua e avisa —
nunca contorna.
"""
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone

from fli.models import Airport, DateSearchFilters, FlightSegment, PassengerInfo, SeatType, TripType
from fli.search.dates import SearchDates

from live_check import leg_travel_date
from scrape_schedule import current_brt_date
from supabase_client import (
    DEFAULT_SYSTEM_CONFIG,
    get_radar_sweep_state,
    get_system_config,
    get_weekend_radar_grid_for_dates,
    get_weekend_radar_grid_known_count,
    set_radar_sweep_state,
    upsert_weekend_radar_grid,
)
from telegram_notifier import build_radar_anomaly_message, send_message
from weekends import BSB, GIG, SDU

RADAR_WINDOW_DAYS = 305  # teto real da SearchDates (Etapa 0) — além disso degrada pra vazio, não é buraco corrigível
RADAR_BLOCK_DAYS = SearchDates.MAX_DAYS_PER_SEARCH  # 61 — nunca pedir intervalo maior que isso numa chamada só
RADAR_DELAY_SECONDS = 2.5  # mesmo espaçamento de live_check.py
RADAR_GRID_MAX_AGE_HOURS = 24  # grade mais velha que isso é tratada como morta pelo gatilho de precisão
PRECISION_DIVERGENCE_PCT = 5.0  # tolerância de log entre preço do radar e da precisão
ANOMALY_MIN_KNOWN = 5  # amostra mínima de DATAS já conhecidas NUM BLOCO pro detector por-bloco opinar
ANOMALY_DROP_RATIO = 0.5  # volume de hoje abaixo da metade do conhecido = suspeito
# Amostra mínima de BLOCOS com histórico suficiente antes do detector de
# varredura poder interromper por "100% anômalo até agora" — sem isso, o
# primeiríssimo bloco anômalo do run (podendo ser 1 em 20) já derrubaria a
# varredura inteira. Não veio explícito no prompt original; mesma cautela já
# aplicada em live_check.py (MIN_SAMPLE_FOR_RATE_CHECK), reaplicada aqui por
# analogia direta — registrar caso o usuário queira revisar o número.
ANOMALY_MIN_BLOCKS_WITH_HISTORY = 3
RADAR_DIRECTIONS = ((GIG, BSB), (SDU, BSB), (BSB, GIG), (BSB, SDU))
RADAR_CONFIG_URL = "https://eltoneap.github.io/flyiop/config.html"


def date_blocks(start: date, end: date) -> list[tuple[date, date]]:
    """Fatia [start, end] (inclusive dos dois lados) em blocos <=RADAR_BLOCK_DAYS
    dias — é o que garante que SearchDates.search NUNCA aciona o
    particionamento paralelo interno da lib (só entra em jogo quando o
    intervalo PEDIDO numa única chamada passa do teto). Bloco final pode
    ficar menor que o teto."""
    blocks = []
    current = start
    while current <= end:
        block_end = min(current + timedelta(days=RADAR_BLOCK_DAYS - 1), end)
        blocks.append((current, block_end))
        current = block_end + timedelta(days=1)
    return blocks


def search_dates_block(origin: str, destination: str, from_d: date, to_d: date) -> list | None:
    """1 chamada SearchDates pra um bloco <=61 dias. Best-effort: qualquer
    falha (sem resultado, exceção, timeout) vira None — mesmo contrato de
    check_live_price (live_check.py) — nunca derruba a varredura inteira."""
    try:
        segment = FlightSegment(
            departure_airport=[[getattr(Airport, origin), 0]],
            arrival_airport=[[getattr(Airport, destination), 0]],
            travel_date=from_d.isoformat(),
        )
        filters = DateSearchFilters(
            trip_type=TripType.ONE_WAY,
            passenger_info=PassengerInfo(adults=1),
            flight_segments=[segment],
            seat_type=SeatType.ECONOMY,
            from_date=from_d.isoformat(),
            to_date=to_d.isoformat(),
        )
        return SearchDates().search(filters, currency="BRL", language="pt-BR", country="BR")
    except Exception:
        print(f"[radar] EXCEÇÃO em {origin}→{destination} {from_d}..{to_d}:\n{traceback.format_exc()}")
        return None


def detect_block_anomaly(today_count: int, known_count: int) -> bool:
    """Separa 'sempre vazio é normal' (known_count baixo, sem histórico pra
    comparar) de 'ficou vazio de repente' (tinha histórico e sumiu, ou caiu
    pela metade) — só opina com amostra mínima de datas já conhecidas pro
    bloco. `known_count` DEVE ser medido ANTES do upsert da varredura de
    hoje (radar_check.py:run_sweep) — medido depois, compararia a varredura
    de hoje contra ela mesma e nunca dispararia."""
    if known_count < ANOMALY_MIN_KNOWN:
        return False
    return today_count == 0 or today_count < known_count * ANOMALY_DROP_RATIO


def _grid_rows(origin: str, destination: str, results: list | None, swept_at: str) -> list[dict]:
    rows = []
    for entry in results or []:
        flight_date = entry.date[0].date().isoformat()
        rows.append({
            "origin": origin, "destination": destination, "flight_date": flight_date,
            "price": float(entry.price), "currency": entry.currency or "BRL", "swept_at": swept_at,
        })
    return rows


def run_sweep(system_config: dict) -> dict:
    """Varredura diária do radar. Kill-switch primeiro; depois cota do dia
    (`radar_sweeps_per_day`, por-estado em bot_state, mesmo padrão de
    get_weekend_scrape_state — sobrevive a atraso de disparo do cron);
    depois 4 direções × ~5 blocos cada, sequencial e espaçado, com detector
    de anomalia por bloco e detector de bloqueio da varredura inteira
    (100% dos blocos com histórico vieram anômalos, com amostra mínima) —
    interrompe e avisa no Telegram, nunca contorna.

    Blocos gravados ANTES de uma interrupção continuam na grade (upsert é
    por bloco, não transação única) — varredura parcial é estado normal,
    tratado como qualquer outra ausência de dado por quem lê depois."""
    if not system_config.get("radar_enabled", False):
        print("[radar] kill-switch desligado (radar_enabled=false) — varredura não roda hoje")
        return {"ran": False, "reason": "kill_switch_off"}

    today_str = current_brt_date()
    today_date = date.fromisoformat(today_str)
    sweeps_per_day = int(system_config.get("radar_sweeps_per_day") or DEFAULT_SYSTEM_CONFIG["radar_sweeps_per_day"])

    state = get_radar_sweep_state()
    sweeps_today = state["sweeps_today"] if state["last_sweep_date"] == today_str else 0
    if sweeps_today >= sweeps_per_day:
        print(f"[radar] cota de {sweeps_per_day} varredura(s)/dia já cumprida hoje ({today_str}) — pulado")
        return {"ran": False, "reason": "quota_reached"}

    end_date = today_date + timedelta(days=RADAR_WINDOW_DAYS)
    blocks = date_blocks(today_date, end_date)
    swept_at = datetime.now(timezone.utc).isoformat()
    all_blocks = [(origin, destination, block) for origin, destination in RADAR_DIRECTIONS for block in blocks]

    blocks_checked = 0
    rows_written = 0
    blocks_with_history = 0
    anomalous_with_history = 0
    blocked = False

    for i, (origin, destination, (from_d, to_d)) in enumerate(all_blocks):
        if i > 0:
            time.sleep(RADAR_DELAY_SECONDS)

        known_count = get_weekend_radar_grid_known_count(origin, destination, from_d.isoformat(), to_d.isoformat())
        results = search_dates_block(origin, destination, from_d, to_d)
        blocks_checked += 1
        today_count = len(results) if results else 0

        has_history = known_count >= ANOMALY_MIN_KNOWN
        anomalous = has_history and detect_block_anomaly(today_count, known_count)
        if has_history:
            blocks_with_history += 1
            if anomalous:
                anomalous_with_history += 1

        if anomalous:
            # Bloco anômalo isolado: nunca sobrescreve dado bom que já
            # existia com um resultado suspeito — só linha de log.
            print(
                f"[radar] ANOMALIA {origin}→{destination} {from_d}..{to_d}: "
                f"hoje {today_count} datas, conhecido {known_count} — não gravado"
            )
        else:
            rows = _grid_rows(origin, destination, results, swept_at)
            if rows:
                upsert_weekend_radar_grid(rows)
                rows_written += len(rows)
            print(f"[radar] {origin}→{destination} {from_d}..{to_d}: {today_count} datas com preço")

        if (
            blocks_with_history >= ANOMALY_MIN_BLOCKS_WITH_HISTORY
            and anomalous_with_history == blocks_with_history
        ):
            blocked = True
            print(
                f"[radar] bloqueio detectado (100% dos {blocks_with_history} blocos com histórico "
                f"vieram anômalos) após {blocks_checked}/{len(all_blocks)} blocos — varredura interrompida"
            )
            break

    print(
        f"[radar] varredura concluída: {blocks_checked}/{len(all_blocks)} blocos consultados, "
        f"{rows_written} linhas gravadas, {anomalous_with_history}/{blocks_with_history} "
        "blocos com histórico deram anomalia" + (" — BLOQUEADO" if blocked else "")
    )

    if blocked:
        send_message(build_radar_anomaly_message({
            "blocks_checked": blocks_checked, "blocks_total": len(all_blocks),
            "anomalous_blocks": anomalous_with_history, "config_url": RADAR_CONFIG_URL,
        }))

    set_radar_sweep_state(last_sweep_date=today_str, sweeps_today=sweeps_today + 1)

    return {
        "ran": True, "blocked": blocked, "blocks_checked": blocks_checked,
        "rows_written": rows_written, "anomalous_blocks": anomalous_with_history,
    }


# ----------------------------------------------------------------------------
# Seleção de candidatas pra PRECISÃO — só leitura, sem efeito colateral.
# Chamada por main.py, que processa as candidatas pelo laço de alerta que já
# existe (check_and_evaluate_leg, o mesmo do lote fli).
# ----------------------------------------------------------------------------

def _radar_airports(direction: str) -> tuple[tuple[str, str], tuple[str, str]]:
    """(origin, destination) pros dois aeroportos do Rio, na direção certa —
    mesma troca consciente de GIG/SDU já usada em live_check.py."""
    if direction == "outbound":
        return (GIG, BSB), (SDU, BSB)
    return (BSB, GIG), (BSB, SDU)


def select_precision_candidates(legs: list[dict], grid: list[dict], today: date, max_per_run: int) -> list[dict]:
    """Pura, sem I/O. Regras (decisão 2 do prompt, fechadas na revisão desta
    sessão):

    - perna elegível se leg_travel_date(leg) cai em [hoje, hoje+305];
    - preço do radar = o MENOR entre GIG e SDU disponíveis na grade, na
      direção certa, naquela data exata;
    - `max_ceiling` = MAIOR teto entre os usuários que monitoram a perna
      (leg['ceilings_by_user'], resolvido de weekend_leg_effective) — NUNCA
      queue_ceiling (que é MIN e faria a precisão nunca disparar, em
      silêncio, pro usuário de teto mais alto);
    - candidata se radar <= max_ceiling OU radar < lowest_seen histórico da
      perna (sem margem percentual — decisão fechada, teto real já disparou
      quase sempre com margem);
    - ordem: (radar_price - max_ceiling) crescente — MAIOR FOLGA primeiro,
      não abs(). Sem teto (max_ceiling None, só gatilho por lowest_seen):
      gap = +inf, desempata por último — mesmo padrão de price_gap em
      live_check.py:select_batch;
    - corte em max_per_run.

    Perna de volta é avaliada só na data de leg_travel_date (variante
    corrente, ou domingo por default) — domingo E segunda não é escopo desta
    fatia, embora a grade já tenha os dois preços gravados (achado da Etapa
    0), disponíveis pra uso futuro sem trabalho extra de coleta."""
    window_end = today + timedelta(days=RADAR_WINDOW_DAYS)

    grid_by_key: dict[tuple[str, str, str], float] = {}
    for row in grid:
        key = (row["origin"], row["destination"], row["flight_date"])
        price = float(row["price"])
        if key not in grid_by_key or price < grid_by_key[key]:
            grid_by_key[key] = price

    candidates = []
    for leg in legs:
        travel_date_str = leg_travel_date(leg)
        try:
            travel_date = date.fromisoformat(travel_date_str)
        except ValueError:
            continue
        if not (today <= travel_date <= window_end):
            continue

        airport_pairs = _radar_airports(leg["direction"])
        priced_pairs = [
            (origin, destination, grid_by_key[(origin, destination, travel_date_str)])
            for origin, destination in airport_pairs
            if (origin, destination, travel_date_str) in grid_by_key
        ]
        if not priced_pairs:
            continue
        radar_origin, radar_destination, radar_price = min(priced_pairs, key=lambda p: p[2])

        ceilings = [c for c in (leg.get("ceilings_by_user") or {}).values() if c is not None]
        max_ceiling = max(float(c) for c in ceilings) if ceilings else None

        lowest_seen = leg.get("lowest_seen")
        lowest_seen = float(lowest_seen) if lowest_seen is not None else None

        under_ceiling = max_ceiling is not None and radar_price <= max_ceiling
        new_low = lowest_seen is not None and radar_price < lowest_seen
        if not (under_ceiling or new_low):
            continue

        gap = (radar_price - max_ceiling) if max_ceiling is not None else float("inf")
        candidates.append({
            "leg": leg,
            "travel_date": travel_date_str,
            "radar_price": radar_price,
            "radar_origin": radar_origin,
            "radar_destination": radar_destination,
            "max_ceiling": max_ceiling,
            "gap": gap,
        })

    candidates.sort(key=lambda c: c["gap"])
    return candidates[:max_per_run]


def load_radar_candidates(system_config: dict, legs: list[dict]) -> list[dict]:
    """Lê weekend_radar_grid (só linhas dentro de RADAR_GRID_MAX_AGE_HOURS —
    grade mais velha é tratada como morta, o gatilho de precisão não
    dispara sobre preço que já pode ter mudado) e delega à seleção pura."""
    max_per_run = int(
        system_config.get("radar_precision_max_per_run") or DEFAULT_SYSTEM_CONFIG["radar_precision_max_per_run"]
    )
    today = date.fromisoformat(current_brt_date())
    dates = [leg_travel_date(leg) for leg in legs]
    since_iso = (datetime.now(timezone.utc) - timedelta(hours=RADAR_GRID_MAX_AGE_HOURS)).isoformat()
    grid = get_weekend_radar_grid_for_dates(dates, since_iso)
    return select_precision_candidates(legs, grid, today, max_per_run)


def log_precision_divergence(candidate: dict, report: dict) -> None:
    """Compara o preço que a precisão (SearchFlights) realmente encontrou
    contra o preço que o radar tinha apontado — sinal de que o radar está
    desalinhado com a realidade. Sinal positivo = precisão mais cara."""
    label = f"{candidate['radar_origin']}→{candidate['radar_destination']} {candidate['travel_date']}"
    radar_price = candidate["radar_price"]

    if report.get("status") != "ok":
        print(f"[radar] DIVERGÊNCIA VAZIA  {label}  radar R$ {radar_price:.2f} → precisão sem resultado")
        return

    precision_price = float(report["price"])
    diff_pct = (precision_price - radar_price) / radar_price * 100
    via_sdu = f", via {SDU}" if report.get("airport") == SDU else ""
    if abs(diff_pct) <= PRECISION_DIVERGENCE_PCT:
        print(
            f"[radar] precisão ok        {label}  radar R$ {radar_price:.2f} → "
            f"precisão R$ {precision_price:.2f} ({diff_pct:+.1f}%{via_sdu})"
        )
    else:
        print(
            f"[radar] DIVERGÊNCIA        {label}  radar R$ {radar_price:.2f} → "
            f"precisão R$ {precision_price:.2f} ({diff_pct:+.1f}%, tolerância {PRECISION_DIVERGENCE_PCT:.1f}%{via_sdu})"
        )


def main() -> int:
    raw_system_config = get_system_config()
    system_config = {**DEFAULT_SYSTEM_CONFIG, **(raw_system_config or {})}
    run_sweep(system_config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
