import yaml

from booking_link import google_flights_link
from miles import compare_cash_vs_miles
from rules import detect_trend, is_good_price
from storage import export_csv, get_all_prices, get_connection, get_recent_prices, insert_price
from telegram_notifier import build_alert_message, send_message
from travelpayouts_client import get_month_matrix


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def cheapest_entry(month_matrix: list[dict]) -> dict | None:
    if not month_matrix:
        return None
    return min(month_matrix, key=lambda entry: entry["price"])


def process_route(conn, route: dict, trend_cfg: dict, miles_cfg: dict, notify_mode: str) -> None:
    origin, destination, currency = route["origin"], route["destination"], route["currency"]
    route_label = f"{origin} → {destination}"

    matrix = get_month_matrix(origin, destination, currency)
    cheapest = cheapest_entry(matrix)
    if cheapest is None:
        print(f"[{route_label}] sem dados retornados")
        return

    price = cheapest["price"]
    flight_date = cheapest.get("depart_date", "")

    insert_price(conn, route["id"], flight_date, price, currency)

    history_30d = get_recent_prices(conn, route["id"], days=30)
    history_prices = [p for _, p in history_30d]

    good, good_reason = is_good_price(
        price, history_prices, route.get("target_price"), route.get("target_percent_below_avg")
    )
    history_7d = get_recent_prices(conn, route["id"], days=7)
    trending_up, trend_reason = detect_trend(history_7d, trend_cfg["window_3d_pct"], trend_cfg["window_7d_pct"])

    miles_note = compare_cash_vs_miles(price, cheapest.get("miles_required"), miles_cfg["cost_per_thousand_brl"])
    print(f"[{route_label}] R$ {price:.2f} em {flight_date} — {miles_note}")

    should_alert = good or trending_up
    if should_alert or notify_mode == "daily_summary":
        reason = good_reason if good else trend_reason if trend_reason else "resumo diário"
        link = google_flights_link(origin, destination, flight_date)
        message = build_alert_message(route_label, price, currency, flight_date, reason, link)
        send_message(message)


def main() -> None:
    config = load_config()
    conn = get_connection()

    for route in config["routes"]:
        process_route(conn, route, config["trend"], config["miles"], config["notification"]["mode"])

    export_csv(conn)
    conn.close()


if __name__ == "__main__":
    main()
