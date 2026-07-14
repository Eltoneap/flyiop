import sys
import time
import traceback
from datetime import date

from rules import detect_trend, is_good_price
from supabase_client import (
    DEFAULT_SETTINGS,
    get_price_history,
    get_recent_run_outcomes,
    get_routes,
    get_settings,
    insert_price,
    insert_run_log,
)
from telegram_notifier import build_alert_message, build_route_block, build_summary_message, send_message
from travelpayouts_client import get_month_matrix

MONTHS_AHEAD = 6  # varre em cima da hora até ~6 meses à frente; o histórico aprende sozinho qual faixa é mais barata
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
    """Busca, grava e avalia uma rota. Retorna um report para a camada de notificação."""
    origin, destination, currency = route["origin"], route["destination"], route["currency"]
    route_label = f"{origin} → {destination}"

    # Duração da estadia é opcional: pedir uma duração exata reduz muito a cobertura
    # de dados de ida-e-volta em cache (confirmado em teste real: com duração fixa
    # vieram 0 resultados pra BSB-GIG, sem duração veio 1). Só restringe se o
    # usuário configurou explicitamente.
    trip_duration_raw = route.get("trip_duration_weeks")
    trip_duration_weeks = int(trip_duration_raw) if trip_duration_raw is not None else None

    matrix = []
    for i, month in enumerate(_target_months()):
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        month_entries = get_month_matrix(
            origin, destination, currency, month=month, trip_duration_weeks=trip_duration_weeks, one_way=False
        )
        print(f"[{route_label}] mês {month[:7]}: {len(month_entries)} entradas")
        matrix.extend(month_entries)

    cheapest = cheapest_entry(matrix)
    if cheapest is None:
        print(f"[{route_label}] sem dados de ida e volta retornados em nenhum dos {MONTHS_AHEAD} meses varridos")
        insert_run_log(route["id"], "no_data")
        return {"route": route, "status": "no_data", "streak": _no_coverage_streak(route["id"])}

    price = entry_price(cheapest)
    depart_date = cheapest.get("depart_date") or None
    return_date = cheapest.get("return_date") or None
    stops = cheapest.get("number_of_changes")
    found_at = cheapest.get("found_at") or None
    days_ahead = _days_ahead(depart_date)

    insert_price(
        route["id"], depart_date or "", price, currency,
        return_date=return_date, found_at=found_at, stops=stops, days_ahead=days_ahead,
    )
    insert_run_log(route["id"], "ok", price=price)

    history_30d = get_price_history(route["id"], days=30)
    history_prices = [float(h["price"]) for h in history_30d]
    avg_30d = sum(history_prices) / len(history_prices) if history_prices else None

    target_price = _to_float(route.get("target_price"))
    target_percent = _to_float(route.get("target_percent_below_avg"))
    good, good_reason = is_good_price(price, history_prices, target_price, target_percent)

    history_7d = get_price_history(route["id"], days=7)
    recent = [(h["checked_at"], float(h["price"])) for h in history_7d]
    trending, trend_reason = detect_trend(
        recent, float(settings["window_3d_pct"]), float(settings["window_7d_pct"])
    )

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
        "should_alert": good or trending,
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
    return notes


def main() -> None:
    routes = get_routes()
    if not routes:
        print("Nenhuma rota cadastrada no Supabase.")
        return

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

    notes = build_notes(reports)
    # settings do primeiro usuário definem o modo (app é single-user por design)
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
        if notes:
            send_message("\n".join(notes))

    if had_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
