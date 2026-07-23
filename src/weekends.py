"""Alvo Fins de Semana RIO↔BSB — pernas desacopladas (revisão de 23/07/2026).

Ida e volta são alvos independentes ("pernas"): cada weekend gera uma perna
'outbound' (sexta, GIG/SDU→BSB) e uma perna 'return' (domingo OU segunda,
BSB→GIG/SDU, a mais barata das duas vence), cada uma com seu próprio preço,
histórico, teto e status de compra. Motivo da mudança: exigir ida+volta como
um evento único (o modelo anterior) multiplicava a raridade do cache — nem
o código de cidade RIO (que agrega GIG+SDU) trazia cobertura suficiente.

Busca por MÊS, one-way, GIG e SDU separados (não mais o código de cidade
RIO): cada perna consulta os dois aeroportos individualmente, na direção
certa (ida: aeroporto→BSB; volta: BSB→aeroporto), com departure_at em
granularidade de mês — a mesma lição da rodada anterior (data exata vem
sistematicamente vazia). O match com a data exata da perna é filtrado
localmente, sem tolerância de ±1 dia — bate exato ou fica "sem dado ainda"
(estado normal, não erro).

Agrupamento por (mês, aeroporto, direção): várias pernas compartilham a
mesma chave (todas as pernas 'outbound' de setembro, por exemplo), então
cada chave é buscada uma única vez e reusada — não uma chamada por perna.

Reusa direto as funções de decisão já testadas em produção (rules.py):
is_good_price (teto = meta fixa, oportunidade = % abaixo da média própria),
is_suspicious_price (autocheck anti-preço-fantasma) e cooldown_blocks_alert
(Etapa 3, aqui aplicado por perna via alert_log.leg_id).

Checkpoint da Parte 2 (23/07/2026): resultado real de produção conferido —
só 2 de 132 pernas bateram (cache insuficiente, mesmo padrão do RIO
round-trip). Por isso, desde a Parte 3 (live_check.py), esta busca cache
deixou de ser a fonte primária: o `fast_flights` (Google Flights) passou a
decidir `current_price`/alerta; esta busca continua rodando como conferidor
secundário (barata, ~64 consultas/dia), gravando com `source='cache'` via
a mesma `evaluate_and_record_leg_price` que o live-check usa.
"""
import time
import traceback
from datetime import datetime, timezone

from rules import cooldown_blocks_alert, is_good_price, is_suspicious_price
from supabase_client import (
    DEFAULT_SETTINGS,
    get_last_weekend_leg_alert,
    get_monitoring_legs,
    get_monitoring_weekends,
    get_weekend_leg_price_history,
    insert_weekend_leg_price,
    insert_weekend_leg_run_log,
    update_weekend_leg,
)
from travelpayouts_client import get_prices_for_dates

GIG = "GIG"
SDU = "SDU"
AIRPORTS = (GIG, SDU)
BSB = "BSB"
CURRENCY = "BRL"
REQUEST_DELAY_SECONDS = 0.3
MONTH_QUERY_LIMIT = 200  # a API ordena por preço, não por data — limite alto
# aumenta a chance da data exata da perna aparecer entre os resultados do mês.


def cheapest_entry(entries: list[dict]) -> dict | None:
    if not entries:
        return None
    return min(entries, key=lambda e: float(e["price"]))


def relevant_months(leg: dict) -> list[str]:
    """Meses (YYYY-MM) que precisam ser consultados pra essa perna.
    'outbound' tem 1 data só; 'return' pode ter domingo e segunda em meses
    diferentes se o fim de semana cair na virada do mês."""
    if leg["direction"] == "outbound":
        return [leg["outbound_date"][:7]]
    return sorted({leg["return_sunday"][:7], leg["return_monday"][:7]})


def date_candidates(leg: dict) -> list[tuple[str | None, str]]:
    """[(variante, data)] a checar pra essa perna. 'outbound' não tem
    variante (só existe 1 data possível); 'return' tem domingo e segunda."""
    if leg["direction"] == "outbound":
        return [(None, leg["outbound_date"])]
    return [("sunday", leg["return_sunday"]), ("monday", leg["return_monday"])]


def fetch_leg_month_entries(month: str, airport: str, direction: str) -> list[dict]:
    """Uma chamada por (mês, aeroporto, direção) — reusada por todas as
    pernas que compartilham essa combinação."""
    if direction == "outbound":
        origin, destination = airport, BSB
    else:
        origin, destination = BSB, airport
    return get_prices_for_dates(origin, destination, CURRENCY, departure_at=month, one_way=True, limit=MONTH_QUERY_LIMIT)


def match_leg_entries(entries: list[dict], target_date: str) -> dict | None:
    """Entre as entradas do mês, a mais barata cuja data de partida bate
    EXATAMENTE com a perna. Sem tolerância de data — match exato ou nada.
    One-way: a data relevante é sempre departure_at (não há return_at)."""
    matches = [e for e in entries if (e.get("departure_at") or "")[:10] == target_date]
    return cheapest_entry(matches)


def get_active_legs() -> list[dict]:
    """Pernas com status 'monitoring' cujo weekend ainda não passou
    (outbound_date >= hoje) — auto-expiração sem job separado. Cada perna
    volta com as datas do weekend anexadas, prontas pro matching local."""
    weekends_by_id = {w["id"]: w for w in get_monitoring_weekends()}
    legs = []
    for leg in get_monitoring_legs():
        weekend = weekends_by_id.get(leg["weekend_id"])
        if weekend is None:
            continue  # weekend já passou ou não existe mais
        legs.append({
            **leg,
            "outbound_date": weekend["outbound_date"],
            "return_sunday": weekend["return_sunday"],
            "return_monday": weekend["return_monday"],
        })
    return legs


def evaluate_and_record_leg_price(leg: dict, settings: dict, price: float, airport: str | None,
                                  variant: str | None, transfers: int | None, source: str) -> dict:
    """Núcleo compartilhado entre a varredura cache (process_weekend_leg, abaixo)
    e o lote fast-flights (live_check.py, Parte 3): grava o preço, avalia
    teto/oportunidade/suspeita/cooldown, e atualiza a perna. `source` é
    'cache' ou 'live' — desde a Parte 3, 'live' é a fonte primária (decide
    o current_price/alerta); 'cache' virou conferidor secundário, mas grava
    exatamente do mesmo jeito (histórico registra as duas fontes)."""
    leg_id = leg["id"]
    direction = leg["direction"]
    if direction == "outbound":
        leg_date = leg["outbound_date"]
    else:
        leg_date = leg["return_sunday"] if variant == "sunday" else leg["return_monday"]

    insert_weekend_leg_price(leg_id, price, airport, variant, source, transfers)

    history = get_weekend_leg_price_history(leg_id, days=90)
    history_prices = [float(h["price"]) for h in history]

    ceiling = float(leg.get("price_ceiling") or 200)
    opportunity_pct = float(settings.get("weekend_opportunity_pct") or DEFAULT_SETTINGS["weekend_opportunity_pct"])
    good, reason = is_good_price(price, history_prices, ceiling, opportunity_pct)

    suspicious_threshold = float(
        settings.get("suspicious_below_avg_pct") or DEFAULT_SETTINGS["suspicious_below_avg_pct"]
    )
    suspicious = is_suspicious_price(price, history_prices, suspicious_threshold)

    would_alert = good and not suspicious
    cooldown_suppressed = False
    if would_alert:
        last_alert = get_last_weekend_leg_alert(leg_id)
        cooldown_suppressed = cooldown_blocks_alert(last_alert, price, settings)

    lowest_seen = leg.get("lowest_seen")
    is_new_low = lowest_seen is None or price < float(lowest_seen)
    update_fields = {
        "current_price": price,
        "current_airport": airport,
        "current_variant": variant,
        "current_source": source,
    }
    if is_new_low:
        update_fields["lowest_seen"] = price
        update_fields["lowest_seen_at"] = datetime.now(timezone.utc).isoformat()
    update_weekend_leg(leg_id, **update_fields)

    insert_weekend_leg_run_log(leg_id, "ok", price=price, source=source)

    variant_label = f", {variant}" if variant else ""
    print(f"[perna {direction} {leg['outbound_date']}] R$ {price:.2f} ({airport}{variant_label}, {source}) teto R$ {ceiling:.0f}")

    return {
        "leg": leg,
        "status": "ok",
        "direction": direction,
        "weekend_id": leg["weekend_id"],
        "outbound_date": leg["outbound_date"],
        "price": price,
        "date": leg_date,
        "airport": airport,
        "variant": variant,
        "transfers": transfers,
        "source": source,
        "reason": reason,
        "is_ceiling_hit": price <= ceiling,
        "suspicious": suspicious,
        "should_alert": would_alert and not cooldown_suppressed,
    }


def process_weekend_leg(leg: dict, settings: dict, month_cache: dict) -> dict:
    """Filtra localmente as entradas já buscadas pra essa perna (1 ou 2 datas
    candidatas × 2 aeroportos) e delega a gravação/avaliação pra
    evaluate_and_record_leg_price (fonte 'cache')."""
    leg_id = leg["id"]
    direction = leg["direction"]
    label = f"perna {direction} {leg['outbound_date']}"

    found = []  # (airport, variant, date, entry)
    for airport in AIRPORTS:
        for month in relevant_months(leg):
            entries = month_cache.get((month, airport, direction))
            if not entries:
                continue
            for variant, target_date in date_candidates(leg):
                if target_date[:7] != month:
                    continue
                best = match_leg_entries(entries, target_date)
                if best is not None:
                    found.append((airport, variant, target_date, best))

    if not found:
        print(f"[{label}] sem dado ainda (nenhum match exato) — estado normal, não é erro")
        insert_weekend_leg_run_log(leg_id, "no_data")
        return {"leg": leg, "status": "no_data"}

    airport, variant, _matched_date, best = min(found, key=lambda f: float(f[3]["price"]))
    price = float(best["price"])
    transfers = best.get("transfers")

    return evaluate_and_record_leg_price(leg, settings, price, airport, variant, transfers, "cache")


def process_all_weekend_legs(settings: dict) -> list[dict]:
    """Varre todas as pernas ativas, agrupando as buscas por (mês, aeroporto,
    direção) — cada chave é buscada 1 vez e reusada pelas pernas que a
    compartilham. Falha ao buscar uma chave só afeta as pernas que dependem
    dela; falha ao processar uma perna não derruba as outras."""
    legs = get_active_legs()
    if not legs:
        return []

    fetch_keys = set()
    for leg in legs:
        for month in relevant_months(leg):
            for airport in AIRPORTS:
                fetch_keys.add((month, airport, leg["direction"]))

    month_cache: dict[tuple[str, str, str], list[dict] | None] = {}
    for i, key in enumerate(sorted(fetch_keys)):
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        month, airport, direction = key
        try:
            entries = fetch_leg_month_entries(month, airport, direction)
            month_cache[key] = entries
            print(f"[pernas {direction} {airport} {month}] {len(entries)} entradas")
        except Exception:
            print(f"[pernas {direction} {airport} {month}] ERRO ao buscar:\n{traceback.format_exc()}")
            month_cache[key] = None

    reports = []
    for leg in legs:
        label = f"perna {leg['direction']} {leg['outbound_date']}"
        needed_keys = [(month, airport, leg["direction"]) for month in relevant_months(leg) for airport in AIRPORTS]
        try:
            if all(month_cache.get(k) is None for k in needed_keys):
                raise RuntimeError("todas as buscas necessárias falharam")
            reports.append(process_weekend_leg(leg, settings, month_cache))
        except Exception:
            detail = traceback.format_exc()[-500:]
            print(f"[{label}] ERRO:\n{detail}")
            try:
                insert_weekend_leg_run_log(leg["id"], "error", detail=detail)
            except Exception:
                print(f"[{label}] falha também ao gravar weekend_leg_run_log")
            reports.append({"leg": leg, "status": "error"})
    return reports
