"""Lote fast-flights (Google Flights) — fonte primária das pernas de fim de
semana desde a Parte 3 (23/07/2026), depois do veredito da Parte 2: o cache
Travelpayouts é estruturalmente insuficiente pra esse caso de uso (2 de 132
pernas bateram). O Travelpayouts (weekends.py) continua rodando em paralelo
como conferidor secundário, barato e sem risco — nunca mais decide o preço
corrente de uma perna de fim de semana.

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
- Kill-switch manual (settings.fast_flights_enabled) sempre vale por cima.

Reusa o cliente já validado na Etapa 0 (scripts/validate_fastflights.py) e
a avaliação de teto/oportunidade/suspeita/cooldown de weekends.py — o
live-check só descobre o preço; quem decide o que fazer com ele é a mesma
função usada pelo caminho cache (evaluate_and_record_leg_price).
"""
import time
import traceback
from datetime import date, datetime, timedelta, timezone

from fast_flights import FlightQuery, create_query, get_flights

from supabase_client import (
    DEFAULT_SETTINGS,
    get_weekend,
    get_weekend_legs_by_weekend,
    insert_weekend_leg_run_log,
    update_weekend_leg,
)
from telegram_notifier import send_message
from weekends import BSB, GIG, SDU, evaluate_and_record_leg_price, get_active_legs

LIVE_CHECK_WINDOW_DAYS = 183  # ~6 meses — pernas mais distantes ficam dormentes
LIVE_CHECK_DELAY_SECONDS = 2.5
BLOCK_STREAK_THRESHOLD = 5
BLOCK_RATE_THRESHOLD = 0.5
MIN_SAMPLE_FOR_RATE_CHECK = 8
BLOCK_ALERT_MESSAGE = "⚠️ Google Flights não está respondendo — provável bloqueio, fonte suspensa"


def check_live_price(origin: str, destination: str, travel_date: str) -> dict | None:
    """1 consulta one-way ao fast-flights. Best-effort: qualquer falha (sem
    resultado, exceção, timeout) vira None — nunca propaga, nunca derruba
    o lote (Parte 1 do PLAN-VALIDACAO-CRUZADA.md)."""
    try:
        query = create_query(
            flights=[FlightQuery(date=travel_date, from_airport=origin, to_airport=destination)],
            trip="one-way", seat="economy", currency="BRL", language="pt-BR",
        )
        results = get_flights(query)
    except Exception:
        print(f"[live-check] EXCEÇÃO em {origin}→{destination} {travel_date}:\n{traceback.format_exc()}")
        return None

    best = None
    for entry in results:
        price = getattr(entry, "price", 0)
        if not price:
            continue
        if best is None or price < best["price"]:
            best = {"price": float(price), "transfers": max(len(getattr(entry, "flights", []) or []) - 1, 0)}
    return best


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
    """Checa 1 perna via fast-flights (GIG, com fallback SDU se GIG vier
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
        leg, settings, result["price"], used_airport, variant, result.get("transfers"), "live"
    )
    update_weekend_leg(leg["id"], last_live_check_at=now_iso)
    return report, True


def check_package_price(airport: str, outbound_date: str, return_date: str) -> dict | None:
    """1 consulta round-trip ao fast-flights pro pacote fechado (ida+volta
    juntas) — só no momento do alerta (regra 4), nunca na varredura diária.
    Best-effort: qualquer falha vira None, o alerta sai igual, sem selo."""
    try:
        query = create_query(
            flights=[
                FlightQuery(date=outbound_date, from_airport=airport, to_airport=BSB),
                FlightQuery(date=return_date, from_airport=BSB, to_airport=airport),
            ],
            trip="round-trip", seat="economy", currency="BRL", language="pt-BR",
        )
        results = get_flights(query)
    except Exception:
        print(f"[pacote] EXCEÇÃO {airport}↔BSB {outbound_date}/{return_date}:\n{traceback.format_exc()}")
        return None

    best = None
    for entry in results:
        price = getattr(entry, "price", 0)
        if not price:
            continue
        if best is None or price < best:
            best = float(price)
    return {"price": best} if best is not None else None


def build_package_comparison(leg_report: dict, settings: dict) -> dict | None:
    """Regra 4 (Parte 3 do plano, ajustada em 23/07): 'avulso' usa os
    current_price já gravados das 2 pernas (sem buscar de novo); só o
    'pacote' é uma cotação nova. Se a perna irmã não tem preço ainda, não
    há avulso pra comparar — sem linha na mensagem. Kill-switch e
    best-effort valem aqui também."""
    if not settings.get("fast_flights_enabled", True):
        return None

    weekend_id = leg_report["weekend_id"]
    own_leg_id = leg_report["leg"]["id"]
    sibling = next(
        (leg for leg in get_weekend_legs_by_weekend(weekend_id) if leg["id"] != own_leg_id), None
    )
    if sibling is None or sibling.get("current_price") is None:
        return None

    avulso = float(leg_report["price"]) + float(sibling["current_price"])

    weekend = get_weekend(weekend_id)
    if weekend is None:
        return {"avulso": avulso, "pacote": None}

    if leg_report["direction"] == "outbound":
        outbound_date = leg_report["date"]
        variant = sibling.get("current_variant") or "sunday"
        return_date = weekend["return_sunday"] if variant == "sunday" else weekend["return_monday"]
    else:
        outbound_date = weekend["outbound_date"]
        return_date = leg_report["date"]

    airport = leg_report.get("airport") or GIG
    package = check_package_price(airport, outbound_date, return_date)
    return {"avulso": avulso, "pacote": package["price"] if package else None}


def run_daily_batch(settings: dict) -> list[dict]:
    """Lote diário do fast-flights. Kill-switch primeiro; depois seleção
    (janela + rotação); depois laço sequencial e espaçado com detector de
    bloqueio — para o lote e avisa no Telegram se disparar."""
    if not settings.get("fast_flights_enabled", True):
        print("[live-check] kill-switch desligado (fast_flights_enabled=false) — lote não roda hoje")
        return []

    batch = select_batch(settings)
    if not batch:
        print("[live-check] nenhuma perna elegível hoje (janela de 6 meses vazia)")
        return []

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
        send_message(BLOCK_ALERT_MESSAGE)

    return reports
