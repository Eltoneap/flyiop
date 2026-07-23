"""Alvo Fins de Semana (22/07/2026): monitora fins de semana RIO↔BSB como
alvos de compra independentes com data fixa, até serem marcados como
comprados no painel. Cada alvo tem sua própria série de preços — meta
(teto), tendência de queda (oportunidade) e autocheck sempre comparam a
mesma viagem consigo mesma, sem misturar datas de viagem diferentes (é
exatamente o problema que a Etapa 5 (janela dupla) tentava contornar nas
rotas flexíveis; aqui não existe, por desenho).

Busca por MÊS (22/07/2026): a Parte 0 provou que consulta por data exata
(YYYY-MM-DD) vem sistematicamente vazia mesmo pra rotas com cobertura
conhecida (GIG/SDU) — o cache é populado por buscas reais de terceiros,
não por data isolada. A consulta por mês (YYYY-MM) tem cobertura real;
o match com a data exata do alvo é filtrado localmente, sem tolerância
de ±1 dia — bate exato ou o alvo fica "sem dado ainda" (estado normal,
não erro). Como vários alvos caem no mesmo mês (~4 por mês, cadência
semanal), 1 chamada por mês cobre todos eles — menos chamadas que antes.

Reusa direto as funções de decisão já testadas em produção (rules.py):
is_good_price (teto = meta fixa, oportunidade = % abaixo da média própria),
is_suspicious_price (autocheck anti-preço-fantasma) e cooldown_blocks_alert
(Etapa 3, aqui aplicado por alvo via alert_log.target_id).
"""
import time
import traceback
from datetime import datetime, timezone

from rules import cooldown_blocks_alert, is_good_price, is_suspicious_price
from supabase_client import (
    DEFAULT_SETTINGS,
    get_last_weekend_alert,
    get_weekend_price_history,
    get_weekend_targets,
    insert_weekend_price,
    insert_weekend_run_log,
    update_weekend_target,
)
from travelpayouts_client import get_prices_for_dates

ORIGIN = "RIO"  # código de cidade — agrega GIG+SDU, confirmado na Parte 0 (22/07/2026)
DESTINATION = "BSB"
CURRENCY = "BRL"
REQUEST_DELAY_SECONDS = 0.3
MONTH_QUERY_LIMIT = 200  # a API ordena por preço, não por data — limite alto
# aumenta a chance da data exata do alvo aparecer entre os resultados do mês.


def cheapest_entry(entries: list[dict]) -> dict | None:
    if not entries:
        return None
    return min(entries, key=lambda e: float(e["price"]))


def fetch_month_entries(month: str) -> list[dict]:
    """Uma chamada por mês (YYYY-MM) — reusada por todos os alvos daquele mês."""
    return get_prices_for_dates(
        ORIGIN, DESTINATION, CURRENCY, departure_at=month, one_way=False, limit=MONTH_QUERY_LIMIT
    )


def match_variant(entries: list[dict], outbound_date: str, return_date: str) -> dict | None:
    """Entre as entradas do mês, acha a mais barata cuja ida e volta batem
    EXATAMENTE com o alvo. Sem tolerância de data — só conta o match exato."""
    matches = [
        e for e in entries
        if (e.get("departure_at") or "")[:10] == outbound_date
        and (e.get("return_at") or "")[:10] == return_date
    ]
    return cheapest_entry(matches)


def process_weekend_target(target: dict, settings: dict, month_entries: list[dict]) -> dict:
    """Filtra localmente as entradas do mês (já buscadas pelo chamador) pras
    2 variantes de volta (domingo/segunda), grava a mais barata no histórico
    do alvo, e avalia teto/oportunidade/suspeita/cooldown."""
    target_id = target["id"]
    outbound = target["outbound_date"]
    label = f"fim de semana {outbound}"

    candidates = []
    for variant_name, return_date in (("sunday", target["return_sunday"]), ("monday", target["return_monday"])):
        best = match_variant(month_entries, outbound, return_date)
        if best is not None:
            candidates.append((variant_name, return_date, best))

    if not candidates:
        print(f"[{label}] sem dado ainda (nenhum match exato no mês) — estado normal, não é erro")
        insert_weekend_run_log(target_id, "no_data")
        return {"target": target, "status": "no_data"}

    variant_name, return_date, best = min(candidates, key=lambda c: float(c[2]["price"]))
    price = float(best["price"])
    outbound_airport = best.get("origin_airport")
    return_airport = best.get("destination_airport")
    transfers = best.get("transfers")

    insert_weekend_price(target_id, price, variant_name, outbound_airport, return_airport, transfers)

    history = get_weekend_price_history(target_id, days=90)
    history_prices = [float(h["price"]) for h in history]

    ceiling = float(target.get("price_ceiling") or 400)
    opportunity_pct = float(settings.get("weekend_opportunity_pct") or DEFAULT_SETTINGS["weekend_opportunity_pct"])
    good, reason = is_good_price(price, history_prices, ceiling, opportunity_pct)

    suspicious_threshold = float(
        settings.get("suspicious_below_avg_pct") or DEFAULT_SETTINGS["suspicious_below_avg_pct"]
    )
    suspicious = is_suspicious_price(price, history_prices, suspicious_threshold)

    would_alert = good and not suspicious
    cooldown_suppressed = False
    if would_alert:
        last_alert = get_last_weekend_alert(target_id)
        cooldown_suppressed = cooldown_blocks_alert(last_alert, price, settings)

    lowest_seen = target.get("lowest_seen")
    is_new_low = lowest_seen is None or price < float(lowest_seen)
    update_fields = {
        "current_price": price,
        "current_return_variant": variant_name,
        "current_outbound_airport": outbound_airport,
        "current_return_airport": return_airport,
    }
    if is_new_low:
        update_fields["lowest_seen"] = price
        update_fields["lowest_seen_at"] = datetime.now(timezone.utc).isoformat()
    update_weekend_target(target_id, **update_fields)

    insert_weekend_run_log(target_id, "ok", price=price)

    print(f"[{label}] R$ {price:.2f} ({variant_name}, {outbound_airport}→{return_airport}) teto R$ {ceiling:.0f}")

    return {
        "target": target,
        "status": "ok",
        "price": price,
        "outbound_date": outbound,
        "return_date": return_date,
        "variant": variant_name,
        "outbound_airport": outbound_airport,
        "return_airport": return_airport,
        "transfers": transfers,
        "return_at_raw": best.get("return_at"),
        "reason": reason,
        "is_ceiling_hit": price <= ceiling,
        "suspicious": suspicious,
        "should_alert": would_alert and not cooldown_suppressed,
    }


def process_all_weekend_targets(settings: dict) -> list[dict]:
    """Varre todos os alvos com status 'monitoring' e outbound_date futura
    (auto-expiração é o filtro da própria query em get_weekend_targets).

    Agrupa por mês antes de buscar: 1 chamada por mês distinto, reusada por
    todos os alvos daquele mês (~4 em média). Falha ao buscar o mês vira
    'error' só pros alvos daquele mês, não pros outros; falha ao processar
    um alvo individual (gravação, etc.) não derruba os demais."""
    targets = get_weekend_targets()
    if not targets:
        return []

    months = sorted({t["outbound_date"][:7] for t in targets})
    month_entries: dict[str, list[dict] | None] = {}
    for i, month in enumerate(months):
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        try:
            entries = fetch_month_entries(month)
            month_entries[month] = entries
            print(f"[alvos {month}] {len(entries)} entradas no mês")
        except Exception:
            print(f"[alvos {month}] ERRO ao buscar o mês:\n{traceback.format_exc()}")
            month_entries[month] = None

    reports = []
    for target in targets:
        month = target["outbound_date"][:7]
        entries = month_entries.get(month)
        label = f"fim de semana {target.get('outbound_date')}"
        try:
            if entries is None:
                raise RuntimeError(f"busca do mês {month} falhou")
            reports.append(process_weekend_target(target, settings, entries))
        except Exception:
            detail = traceback.format_exc()[-500:]
            print(f"[{label}] ERRO:\n{detail}")
            try:
                insert_weekend_run_log(target["id"], "error", detail=detail)
            except Exception:
                print(f"[{label}] falha também ao gravar weekend_run_log")
            reports.append({"target": target, "status": "error"})
    return reports
