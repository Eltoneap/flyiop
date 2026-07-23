import sys
import time
import traceback
from datetime import date

from rules import (
    cooldown_blocks_alert,
    detect_trend,
    is_good_price,
    is_suspicious_price,
    should_suppress_alert,
    staleness,
)
from supabase_client import (
    DEFAULT_SETTINGS,
    get_last_alert,
    get_price_history,
    get_recent_run_outcomes,
    get_routes,
    get_settings,
    get_weekend_leg_counts,
    insert_alert_log,
    insert_price,
    insert_run_log,
    insert_weekend_alert_log,
)
from telegram_notifier import (
    build_alert_message,
    build_route_block,
    build_summary_message,
    build_weekend_alert_message,
    build_weekly_weekend_summary,
    send_message,
)
from travelpayouts_client import get_prices_for_dates
from weekends import process_all_weekend_legs

MONTHS_AHEAD = 6  # varre de "em cima da hora" até ~6 meses à frente; o histórico aprende sozinho qual faixa é mais barata
REQUEST_DELAY_SECONDS = 0.3  # precaução contra possível limite de requisições da Travelpayouts
NO_COVERAGE_SUGGESTION_EVERY = 7  # sugere arquivar a cada N dias consecutivos sem cobertura


def _target_months(count: int = MONTHS_AHEAD) -> list[str]:
    today = date.today()
    months = []
    year, month = today.year, today.month
    for _ in range(count):
        months.append(date(year, month, 1).isoformat())
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _to_float(value) -> float | None:
    return float(value) if value is not None else None


def entry_price(entry: dict) -> float:
    # month-matrix (v2) devolve o preço em "value"; prices/cheap (v1) em "price"
    value = entry.get("value", entry.get("price"))
    if value is None:
        raise KeyError(f"entrada sem preço reconhecível: {entry}")
    return float(value)


def cheapest_entry(month_matrix: list[dict]) -> dict | None:
    if not month_matrix:
        return None
    return min(month_matrix, key=entry_price)


def _days_ahead(depart_date: str | None) -> int | None:
    if not depart_date:
        return None
    try:
        return (date.fromisoformat(depart_date) - date.today()).days
    except ValueError:
        return None


def _no_coverage_streak(route_id: str) -> int:
    """Dias consecutivos (mais recentes) em que a rota ficou sem dados na fonte."""
    outcomes = get_recent_run_outcomes(route_id)
    streak = 0
    for outcome in outcomes:
        if outcome != "no_data":
            break
        streak += 1
    return streak


def process_route(route: dict, settings: dict) -> dict:
    """Busca, grava e avalia uma rota. Retorna um report para a camada de notificação.

    Fonte: v3 prices_for_dates (corte da Etapa 6, 21/07/2026 — 5 dias de
    comparação paralela com 100% de paridade de preço com o v2).
    Nota: o v3 não tem filtro de duração da estadia; trip_duration_weeks da
    rota deixou de ter efeito na busca (a UI de Configurações avisa)."""
    origin, destination, currency = route["origin"], route["destination"], route["currency"]
    route_label = f"{origin} → {destination}"

    matrix = []
    for i, month in enumerate(_target_months()):
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        month_entries = get_prices_for_dates(origin, destination, currency, departure_at=month[:7], one_way=False)
        print(f"[{route_label}] mês {month[:7]}: {len(month_entries)} entradas")
        matrix.extend(month_entries)

    cheapest = cheapest_entry(matrix)
    if cheapest is None:
        print(f"[{route_label}] sem dados de ida e volta retornados em nenhum dos {MONTHS_AHEAD} meses varridos")
        insert_run_log(route["id"], "no_data", detail="fonte: v3")
        return {"route": route, "status": "no_data", "streak": _no_coverage_streak(route["id"])}

    price = entry_price(cheapest)
    depart_date = (cheapest.get("departure_at") or "")[:10] or None
    return_date = (cheapest.get("return_at") or "")[:10] or None
    stops = cheapest.get("transfers")
    found_at = cheapest.get("found_at") or None
    days_ahead = _days_ahead(depart_date)

    insert_price(
        route["id"], depart_date or "", price, currency,
        return_date=return_date, found_at=found_at, stops=stops, days_ahead=days_ahead,
    )

    freshness_limit = float(settings.get("freshness_hours") or DEFAULT_SETTINGS["freshness_hours"])
    is_stale, age_hours = staleness(found_at, freshness_limit)
    cache_48h = is_stale and age_hours is None  # ausência esperada na fonte v3
    if age_hours is None:
        freshness_note = "frescor: n/d (cache ≤48h)"
    else:
        freshness_note = f"frescor: {age_hours:.0f}h"
        if is_stale:
            freshness_note += " (velho)"

    history_30d = get_price_history(route["id"], days=30)
    history_prices = [float(h["price"]) for h in history_30d]
    avg_30d = sum(history_prices) / len(history_prices) if history_prices else None

    suspicious_threshold = float(
        settings.get("suspicious_below_avg_pct") or DEFAULT_SETTINGS["suspicious_below_avg_pct"]
    )
    suspicious = is_suspicious_price(price, history_prices, suspicious_threshold)
    if suspicious and avg_30d:
        pct_below_avg = (1 - price / avg_30d) * 100
        freshness_note += f" | suspeito: {pct_below_avg:.0f}% abaixo da média 30d"
        print(f"[{route_label}] preço suspeito: {pct_below_avg:.0f}% abaixo da média 30d — alerta não dispara hoje")

    target_price = _to_float(route.get("target_price"))
    target_percent = _to_float(route.get("target_percent_below_avg"))
    good, good_reason = is_good_price(price, history_prices, target_price, target_percent)

    history_7d = get_price_history(route["id"], days=7)
    recent = [(h["checked_at"], float(h["price"])) for h in history_7d]
    trending, trend_reason = detect_trend(
        recent, float(settings["window_3d_pct"]), float(settings["window_7d_pct"])
    )

    would_alert = (good or trending) and not suspicious
    stale_suppressed = would_alert and should_suppress_alert(is_stale, age_hours, settings)
    if stale_suppressed:
        freshness_note += " — alerta segurado"
        print(f"[{route_label}] alerta segurado: dado velho e política 'suppress'")
    elif would_alert and cache_48h and settings.get("stale_alert_policy") == "suppress":
        freshness_note += " — política suppress não aplicada (idade desconhecida, fonte v3)"

    cooldown_suppressed = False
    if would_alert and not stale_suppressed:
        last_alert = get_last_alert(route["id"])
        cooldown_suppressed = cooldown_blocks_alert(last_alert, price, settings)
        if cooldown_suppressed:
            freshness_note += " — alerta segurado (cooldown)"
            print(f"[{route_label}] alerta segurado: cooldown ativo (sem queda nem tempo suficiente)")

    insert_run_log(route["id"], "ok", price=price, detail=f"fonte: v3 | {freshness_note}")

    print(f"[{route_label}] R$ {price:.2f} ida {depart_date} volta {return_date} ({stops} escalas)")

    return {
        "route": route,
        "status": "ok",
        "origin": origin,
        "destination": destination,
        "currency": currency,
        "price": price,
        "depart_date": depart_date,
        "return_date": return_date,
        "stops": stops,
        "found_at": found_at,
        "days_ahead": days_ahead,
        "target_price": target_price,
        "avg_30d": avg_30d,
        "is_stale": is_stale,
        "age_hours": age_hours,
        "cache_48h": cache_48h,
        "suspicious": suspicious,
        "should_alert": would_alert and not stale_suppressed and not cooldown_suppressed,
        "reason": good_reason if good else (trend_reason if trending else None),
    }


def build_notes(reports: list[dict]) -> list[str]:
    """Notas extras: rotas sem cobertura persistente (sugestão de arquivar) e erros."""
    notes = []
    for r in reports:
        label = f"{r['route']['origin']} → {r['route']['destination']}"
        if r["status"] == "no_data":
            streak = r.get("streak", 0)
            if streak >= NO_COVERAGE_SUGGESTION_EVERY and streak % NO_COVERAGE_SUGGESTION_EVERY == 0:
                notes.append(
                    f"⚠️ {label}: {streak} dias seguidos sem cobertura de dados na fonte. "
                    f"Considere arquivar a rota nas Configurações (o histórico é preservado)."
                )
        elif r["status"] == "error":
            notes.append(f"❌ {label}: erro na busca de hoje — será tentada de novo amanhã.")
        elif r["status"] == "ok" and r.get("suspicious"):
            notes.append(
                f"🔍 {label}: preço de hoje (R$ {r['price']:.2f}) muito abaixo da média — marcado como "
                f"suspeito, alerta não disparado. Será reavaliado amanhã (se persistir 2 dias, deixa de ser suspeito)."
            )
    return notes


def main() -> None:
    routes = get_routes()

    settings_cache: dict[str, dict] = {}
    reports: list[dict] = []
    had_error = False

    for route in routes:
        user_id = route["user_id"]
        if user_id not in settings_cache:
            settings_cache[user_id] = get_settings(user_id) or DEFAULT_SETTINGS
        try:
            reports.append(process_route(route, settings_cache[user_id]))
        except Exception:
            had_error = True
            label = f"{route['origin']} → {route['destination']}"
            print(f"[{label}] ERRO:\n{traceback.format_exc()}")
            try:
                insert_run_log(route["id"], "error", detail=traceback.format_exc()[-500:])
            except Exception:
                print(f"[{label}] falha também ao gravar run_log")
            reports.append({"route": route, "status": "error"})

    # settings do primeiro usuário definem tudo (app é single-user por design).
    # Sem rotas flexíveis cadastradas, cai no default — as pernas de fim de
    # semana não podem ficar reféns de existir alguma rota flexível.
    weekend_settings = next(iter(settings_cache.values()), None) or DEFAULT_SETTINGS
    weekend_reports = process_all_weekend_legs(weekend_settings)
    if any(wr["status"] == "error" for wr in weekend_reports):
        had_error = True

    if not routes and not weekend_reports:
        print("Nenhuma rota nem perna de fim de semana cadastrada.")
        return

    notes = build_notes(reports)

    if routes:
        mode = next(iter(settings_cache.values()))["notification_mode"]
        if mode == "daily_summary":
            blocks = [build_route_block(r) for r in reports if r["status"] == "ok"]
            for r in reports:
                if r["status"] == "no_data":
                    blocks.append(
                        f"✈️ <b>{r['route']['origin']} → {r['route']['destination']}</b> — sem dados na fonte hoje"
                    )
            send_message(build_summary_message(blocks, notes))
        else:
            for r in reports:
                if r["status"] == "ok" and r["should_alert"]:
                    send_message(build_alert_message(r))
                    insert_alert_log(r["route"]["id"], r["price"], r.get("reason"))
            if notes:
                send_message("\n".join(notes))
    elif notes:
        send_message("\n".join(notes))

    # Pernas de fim de semana: notificação sempre imediata quando bate teto ou
    # oportunidade — independe do notification_mode das rotas flexíveis
    # (é o próprio ponto do alerta de teto: avisar na hora). Resumo semanal
    # curado só às segundas-feiras, cadência própria.
    for wr in weekend_reports:
        if wr["status"] == "ok" and wr["should_alert"]:
            send_message(build_weekend_alert_message(wr))
            insert_weekend_alert_log(wr["leg"]["id"], wr["price"], wr.get("reason"))

    if date.today().weekday() == 0:  # segunda-feira
        total, purchased = get_weekend_leg_counts()
        send_message(build_weekly_weekend_summary(weekend_reports, total, purchased))

    if had_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
