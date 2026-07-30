"""Lote de consulta ao vivo (Google Flights) — fonte primária das pernas de
fim de semana desde a Parte 3 (23/07/2026), depois do veredito da Parte 2: o
cache Travelpayouts é estruturalmente insuficiente pra esse caso de uso (2 de
132 pernas bateram). O Travelpayouts (weekends.py) continua rodando em
paralelo como conferidor secundário, barato e sem risco — nunca mais decide
o preço corrente de uma perna de fim de semana.

Migrado de `fast_flights` pra `fli` em 24/07/2026 (Parte 7): o `fast_flights`
lê um payload SSR do Google (`ds:1`) que provou divergir do preço real da UI
(caso real: perna gravou R$561, preço de verdade R$286) — bug estrutural de
parsing de HTML, não de configuração. `fli` chama o endpoint interno
`GetShoppingResults` do Google diretamente, sem parsing de HTML, e devolveu
o preço correto na mesma consulta que expôs o bug. Detalhe completo da
investigação e da migração: seção "Problema conhecido" e "Parte 7" do plano
de fins de semana.

Regras não-negociáveis (Parte 1 do PLAN-VALIDACAO-CRUZADA.md + decisões de
23/07/2026):
- Janela deslizante de 6 meses: só pernas com outbound_date dentro da janela
  entram no lote — as demais ficam dormentes (nenhuma consulta).
- 1 consulta por perna (GIG); só tenta SDU se GIG vier vazio (limitação
  conhecida e aceita: um SDU mais barato pode passar despercebido quando GIG
  já tem preço — troca deliberada de volume por cobertura, revisitar depois).
- Sequencial, espaçado (~2,5s), sem paralelismo, sem evasão de IP.
- Detector de bloqueio: ≥5 falhas seguidas OU taxa de sucesso <50% (com
  amostra mínima de 8) para o lote na hora e avisa no Telegram — nunca
  contorna tecnicamente, só recua.
- Kill-switch manual (system_config.fast_flights_enabled, via system_config,
  mesclado em settings_cache) sempre vale por cima.

Reusa a avaliação de teto/oportunidade/suspeita/cooldown de weekends.py — o
live-check só descobre o preço; quem decide o que fazer com ele é a mesma
função usada pelo caminho cache (evaluate_and_record_leg_price).
"""
import time
import traceback
from datetime import date, datetime, timedelta, timezone

from fli.models import Airport, FlightSearchFilters, FlightSegment, PassengerInfo, SeatType, TripType
from fli.search.flights import SearchFlights

from supabase_client import (
    DEFAULT_SETTINGS,
    get_last_successful_live_check,
    get_weekend_block_streak,
    insert_weekend_leg_run_log,
    set_weekend_batch_blocked_at,
    set_weekend_block_streak,
    update_weekend_leg,
)
from telegram_notifier import build_block_alert_message, build_block_recovered_message, send_message
from weekends import BSB, GIG, SDU, evaluate_and_record_leg_price, get_active_legs

LIVE_CHECK_WINDOW_DAYS = 183  # ~6 meses — pernas mais distantes ficam dormentes
LIVE_CHECK_DELAY_SECONDS = 2.5
BLOCK_STREAK_THRESHOLD = 5
BLOCK_RATE_THRESHOLD = 0.5
MIN_SAMPLE_FOR_RATE_CHECK = 8
WEEKEND_CONFIG_URL = "https://eltoneap.github.io/flyiop/config.html"


def check_live_price(origin: str, destination: str, travel_date: str) -> dict | None:
    """1 consulta one-way via fli (endpoint interno GetShoppingResults do
    Google, sem parsing de HTML). Best-effort: qualquer falha (sem resultado,
    exceção, timeout) vira None — nunca propaga, nunca derruba o lote
    (Parte 1 do PLAN-VALIDACAO-CRUZADA.md)."""
    try:
        segment = FlightSegment(
            departure_airport=[[getattr(Airport, origin), 0]],
            arrival_airport=[[getattr(Airport, destination), 0]],
            travel_date=travel_date,
        )
        filters = FlightSearchFilters(
            trip_type=TripType.ONE_WAY,
            passenger_info=PassengerInfo(adults=1),
            flight_segments=[segment],
            seat_type=SeatType.ECONOMY,
        )
        results = SearchFlights().search(filters, currency="BRL", language="pt-BR", country="BR")
    except Exception:
        print(f"[live-check] EXCEÇÃO em {origin}→{destination} {travel_date}:\n{traceback.format_exc()}")
        return None

    if not results:
        return None

    priced = [r for r in results if r.price is not None]
    if not priced:
        return None

    best = min(priced, key=lambda r: r.price)
    departure_time = best.legs[0].departure_datetime.isoformat() if best.legs else None
    return {
        "price": float(best.price),
        "transfers": best.stops,
        "airline": best.primary_airline_name,
        "departure_time": departure_time,
    }


def leg_travel_date(leg: dict) -> str:
    """Data usada tanto pro filtro de janela quanto pro desempate de
    prioridade — a data da perna em si (ida: sexta; volta: variante
    conhecida, ou domingo por default)."""
    if leg["direction"] == "outbound":
        return leg["outbound_date"]
    variant = leg.get("current_variant") or "sunday"
    return leg["return_sunday"] if variant == "sunday" else leg["return_monday"]


def select_batch(settings: dict) -> list[dict]:
    """Pernas elegíveis pro lote de hoje: dentro da janela de 6 meses,
    'monitoring'. Ordenadas por last_live_check_at (nunca checada primeiro)
    — garante rotação; desempate por (dias até a data, distância até o
    teto) — prioriza as mais urgentes e mais perto de bater meta."""
    cutoff = (date.today() + timedelta(days=LIVE_CHECK_WINDOW_DAYS)).isoformat()
    legs = [leg for leg in get_active_legs() if leg_travel_date(leg) <= cutoff]

    def sort_key(leg: dict) -> tuple:
        last_check = leg.get("last_live_check_at") or ""  # vazio ordena primeiro (nunca checada)
        days_until = (date.fromisoformat(leg_travel_date(leg)) - date.today()).days
        current_price = leg.get("current_price")
        ceiling = float(leg.get("price_ceiling") or 200)
        price_gap = abs(float(current_price) - ceiling) if current_price is not None else float("inf")
        return (last_check, days_until, price_gap)

    legs.sort(key=sort_key)
    batch_size = int(settings.get("fast_flights_daily_batch_size") or DEFAULT_SETTINGS["fast_flights_daily_batch_size"])
    return legs[:batch_size]


def check_and_evaluate_leg(leg: dict, settings: dict) -> tuple[dict, bool]:
    """Checa 1 perna via consulta ao vivo (GIG, com fallback SDU se GIG vier
    vazio). Retorna (report, teve_sucesso). last_live_check_at avança em
    toda tentativa — sucesso ou falha — pra rotação sempre andar."""
    direction = leg["direction"]
    travel_date = leg_travel_date(leg)
    variant = None if direction == "outbound" else (leg.get("current_variant") or "sunday")

    def query_params(airport: str) -> tuple[str, str]:
        return (airport, BSB) if direction == "outbound" else (BSB, airport)

    origin, destination = query_params(GIG)
    result = check_live_price(origin, destination, travel_date)
    used_airport = GIG

    if result is None:
        time.sleep(LIVE_CHECK_DELAY_SECONDS)
        origin, destination = query_params(SDU)
        result = check_live_price(origin, destination, travel_date)
        used_airport = SDU

    now_iso = datetime.now(timezone.utc).isoformat()

    if result is None:
        update_weekend_leg(leg["id"], last_live_check_at=now_iso)
        insert_weekend_leg_run_log(leg["id"], "no_data", source="live")
        return {"leg": leg, "status": "no_data"}, False

    report = evaluate_and_record_leg_price(
        leg, settings, result["price"], used_airport, variant, result.get("transfers"), "live",
        result.get("airline"), result.get("departure_time"),
    )
    update_weekend_leg(leg["id"], last_live_check_at=now_iso)
    return report, True


def build_package_comparison(leg_report: dict, settings: dict) -> dict | None:
    """Suspensa em 24/07/2026 (Parte 7): não há hoje nenhuma fonte que
    consulte round-trip de verdade de forma sequencial. O fast_flights (que
    fazia isso) provou ser estruturalmente não confiável — ver seção
    "Problema conhecido" do plano. O fli (a substituta) só faz round-trip
    via expansão em threads paralelas, o que viola a regra de sempre do
    projeto (sequencial, sem paralelismo). Comparar um "avulso" correto
    contra um "pacote" sabidamente impreciso seria pior que não comparar —
    a mensagem quase sempre diria "avulso mais barato" independente da
    realidade. Reativar só faz sentido se surgir uma fonte round-trip
    compatível com a regra de sequencial. Mitigação: o link "Ver/comprar"
    por perna no painel permite alternar pra ida-e-volta manualmente."""
    return None


def run_daily_batch(settings: dict) -> tuple[list[dict], bool]:
    """Lote diário de consulta ao vivo. Kill-switch primeiro; depois seleção
    (janela + rotação); depois laço sequencial e espaçado com detector de
    bloqueio — para o lote e avisa no Telegram se disparar. Devolve
    (reports, blocked) — Parte 10 (28/07/2026): o chamador (main.py) usa
    `blocked` pra derrubar o estágio de frequência automática na hora."""
    if not settings.get("fast_flights_enabled", True):
        print("[live-check] kill-switch desligado (fast_flights_enabled=false) — lote não roda hoje")
        return [], False

    batch = select_batch(settings)
    if not batch:
        print("[live-check] nenhuma perna elegível hoje (janela de 6 meses vazia)")
        return [], False

    reports: list[dict] = []
    consecutive_failures = 0
    checked = 0
    successes = 0
    blocked = False

    for i, leg in enumerate(batch):
        if i > 0:
            time.sleep(LIVE_CHECK_DELAY_SECONDS)

        report, ok = check_and_evaluate_leg(leg, settings)
        reports.append(report)
        checked += 1

        if ok:
            successes += 1
            consecutive_failures = 0
        else:
            consecutive_failures += 1

        success_rate = successes / checked
        streak_tripped = consecutive_failures >= BLOCK_STREAK_THRESHOLD
        rate_tripped = checked >= MIN_SAMPLE_FOR_RATE_CHECK and success_rate < BLOCK_RATE_THRESHOLD
        if streak_tripped or rate_tripped:
            blocked = True
            reason = "falhas seguidas" if streak_tripped else "taxa de sucesso"
            print(f"[live-check] bloqueio detectado ({reason}) após {checked} consultas — lote interrompido")
            break

    print(f"[live-check] {checked}/{len(batch)} pernas checadas, {successes} com preço" + (" — BLOQUEADO" if blocked else ""))

    if blocked:
        failures = checked - successes
        last_success = get_last_successful_live_check()
        seconds_since_last_success = None
        if last_success:
            last_success_dt = datetime.fromisoformat(last_success.replace("Z", "+00:00"))
            seconds_since_last_success = (datetime.now(timezone.utc) - last_success_dt).total_seconds()

        streak_days, streak_started_at = get_weekend_block_streak()
        streak_days += 1
        if streak_days == 1:
            streak_started_at = date.today().isoformat()
        set_weekend_block_streak(streak_days, streak_started_at)

        send_message(build_block_alert_message({
            "checked": checked, "failures": failures, "reason": reason,
            "seconds_since_last_success": seconds_since_last_success,
            "streak_days": streak_days, "streak_started_at": streak_started_at,
            "config_url": WEEKEND_CONFIG_URL,
        }))
        set_weekend_batch_blocked_at(datetime.now(timezone.utc).isoformat())
    else:
        streak_days, _ = get_weekend_block_streak()
        if streak_days > 0:
            send_message(build_block_recovered_message(streak_days))
            set_weekend_block_streak(0, None)

    return reports, blocked
