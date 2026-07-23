"""Alvo Fins de Semana (22/07/2026): monitora fins de semana RIO↔BSB como
alvos de compra independentes com data fixa, até serem marcados como
comprados no painel. Cada alvo tem sua própria série de preços — meta
(teto), tendência de queda (oportunidade) e autocheck sempre comparam a
mesma viagem consigo mesma, sem misturar datas de viagem diferentes (é
exatamente o problema que a Etapa 5 (janela dupla) tentava contornar nas
rotas flexíveis; aqui não existe, por desenho).

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
    update_weekend_target,
)
from travelpayouts_client import get_prices_for_dates

ORIGIN = "RIO"  # código de cidade — agrega GIG+SDU, confirmado na Parte 0 (22/07/2026)
DESTINATION = "BSB"
CURRENCY = "BRL"
REQUEST_DELAY_SECONDS = 0.3


def cheapest_entry(entries: list[dict]) -> dict | None:
    if not entries:
        return None
    return min(entries, key=lambda e: float(e["price"]))


def process_weekend_target(target: dict, settings: dict) -> dict:
    """Busca as 2 variantes de volta (domingo/segunda), grava a mais barata
    no histórico do alvo, e avalia teto/oportunidade/suspeita/cooldown."""
    target_id = target["id"]
    outbound = target["outbound_date"]
    label = f"fim de semana {outbound}"

    variant_dates = [("sunday", target["return_sunday"]), ("monday", target["return_monday"])]
    found = []
    for i, (variant_name, return_date) in enumerate(variant_dates):
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        entries = get_prices_for_dates(ORIGIN, DESTINATION, CURRENCY, departure_at=outbound, one_way=False)
        same_return = [e for e in entries if (e.get("return_at") or "")[:10] == return_date]
        best = cheapest_entry(same_return)
        if best is not None:
            found.append((variant_name, return_date, best))

    if not found:
        print(f"[{label}] sem dados de nenhuma variante (domingo/segunda)")
        return {"target": target, "status": "no_data"}

    variant_name, return_date, best = min(found, key=lambda f: float(f[2]["price"]))
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
    Uma falha num alvo não derruba os outros, mesmo padrão de process_route."""
    targets = get_weekend_targets()
    reports = []
    for target in targets:
        try:
            reports.append(process_weekend_target(target, settings))
        except Exception:
            label = f"fim de semana {target.get('outbound_date')}"
            print(f"[{label}] ERRO:\n{traceback.format_exc()}")
            reports.append({"target": target, "status": "error"})
    return reports
