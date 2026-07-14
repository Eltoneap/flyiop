from datetime import date

from booking_link import google_flights_link
from miles import compare_cash_vs_miles
from rules import detect_trend, is_good_price
from supabase_client import DEFAULT_SETTINGS, get_price_history, get_routes, get_settings, insert_price
from telegram_notifier import build_alert_message, send_message
from travelpayouts_client import get_month_matrix

MONTHS_AHEAD = 6  # varre em cima da hora até ~6 meses à frente; o histórico aprende sozinho qual faixa é mais barata


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


def process_route(route: dict, settings: dict) -> None:
    origin, destination, currency = route["origin"], route["destination"], route["currency"]
    route_label = f"{origin} → {destination}"

    # Duração da estadia é opcional: pedir uma duração exata reduz muito a cobertura
    # de dados de ida-e-volta em cache (confirmado em teste real: com duração fixa
    # vieram 0 resultados pra BSB-GIG, sem duração veio 1). Só restringe se o
    # usuário configurou explicitamente.
    trip_duration_raw = route.get("trip_duration_weeks")
    trip_duration_weeks = int(trip_duration_raw) if trip_duration_raw is not None else None

    matrix = []
    for month in _target_months():
        month_entries = get_month_matrix(
            origin, destination, currency, month=month, trip_duration_weeks=trip_duration_weeks, one_way=False
        )
        print(f"[{route_label}] mês {month[:7]}: {len(month_entries)} entradas")
        matrix.extend(month_entries)

    cheapest = cheapest_entry(matrix)
    if cheapest is None:
        print(f"[{route_label}] sem dados de ida e volta retornados em nenhum dos {MONTHS_AHEAD} meses varridos")
        return

    price = entry_price(cheapest)
    flight_date = cheapest.get("depart_date", "")

    insert_price(route["id"], flight_date, price, currency)

    history_30d = get_price_history(route["id"], days=30)
    history_prices = [float(h["price"]) for h in history_30d]

    target_price = _to_float(route.get("target_price"))
    target_percent = _to_float(route.get("target_percent_below_avg"))
    good, good_reason = is_good_price(price, history_prices, target_price, target_percent)

    history_7d = get_price_history(route["id"], days=7)
    recent = [(h["checked_at"], float(h["price"])) for h in history_7d]
    trending, trend_reason = detect_trend(
        recent, float(settings["window_3d_pct"]), float(settings["window_7d_pct"])
    )

    miles_note = compare_cash_vs_miles(
        price, cheapest.get("miles_required"), float(settings["cost_per_thousand_brl"])
    )
    print(f"[{route_label}] R$ {price:.2f} em {flight_date} — {miles_note}")

    should_alert = good or trending
    if should_alert or settings["notification_mode"] == "daily_summary":
        reason = good_reason if good else (trend_reason or "resumo diário")
        link = google_flights_link(origin, destination, flight_date)
        message = build_alert_message(route_label, price, currency, flight_date, reason, link)
        send_message(message)


def main() -> None:
    routes = get_routes()
    if not routes:
        print("Nenhuma rota cadastrada no Supabase.")
        return

    settings_cache: dict[str, dict] = {}
    for route in routes:
        user_id = route["user_id"]
        if user_id not in settings_cache:
            settings_cache[user_id] = get_settings(user_id) or DEFAULT_SETTINGS
        process_route(route, settings_cache[user_id])


if __name__ == "__main__":
    main()
