from booking_link import google_flights_link
from miles import compare_cash_vs_miles
from rules import detect_trend, is_good_price
from supabase_client import get_price_history, get_routes, get_settings, insert_price
from telegram_notifier import build_alert_message, send_message
from travelpayouts_client import get_month_matrix

DEFAULT_SETTINGS = {
    "window_3d_pct": 10,
    "window_7d_pct": 15,
    "notification_mode": "alert_only",
    "cost_per_thousand_brl": 25,
}


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

    matrix = get_month_matrix(origin, destination, currency)
    cheapest = cheapest_entry(matrix)
    if cheapest is None:
        print(f"[{route_label}] sem dados retornados")
        return

    price = entry_price(cheapest)
    flight_date = cheapest.get("depart_date", "")

    insert_price(route["id"], flight_date, price, currency)

    history_30d = get_price_history(route["id"], days=30)
    history_prices = [float(h["price"]) for h in history_30d]

    good, good_reason = is_good_price(
        price, history_prices, route.get("target_price"), route.get("target_percent_below_avg")
    )

    history_7d = get_price_history(route["id"], days=7)
    recent = [(h["checked_at"], float(h["price"])) for h in history_7d]
    trending_up, trend_reason = detect_trend(recent, settings["window_3d_pct"], settings["window_7d_pct"])

    miles_note = compare_cash_vs_miles(price, cheapest.get("miles_required"), settings["cost_per_thousand_brl"])
    print(f"[{route_label}] R$ {price:.2f} em {flight_date} — {miles_note}")

    should_alert = good or trending_up
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
