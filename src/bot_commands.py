import os

from rules import detect_trend, is_good_price
from supabase_client import (
    DEFAULT_SETTINGS,
    get_last_update_id,
    get_price_history,
    get_routes,
    get_settings,
    set_last_update_id,
)
from telegram_notifier import get_updates, send_message

COMMANDS = {"/status", "/precos", "/rotas"}


def _to_float(value) -> float | None:
    return float(value) if value is not None else None


def build_status_message() -> str:
    routes = get_routes()
    if not routes:
        return "Nenhuma rota ativa cadastrada no momento."

    settings_cache: dict[str, dict] = {}
    lines = ["📊 <b>Rotas ativas</b>"]

    for route in routes:
        route_label = f"{route['origin']} → {route['destination']}"
        history = get_price_history(route["id"], days=30)

        if not history:
            lines.append(f"{route_label}: ainda sem histórico")
            continue

        prices = [float(h["price"]) for h in history]
        latest = prices[-1]

        good, good_reason = is_good_price(
            latest, prices, _to_float(route.get("target_price")), _to_float(route.get("target_percent_below_avg"))
        )

        user_id = route["user_id"]
        if user_id not in settings_cache:
            settings_cache[user_id] = get_settings(user_id) or DEFAULT_SETTINGS
        settings = settings_cache[user_id]

        history_7d = get_price_history(route["id"], days=7)
        recent = [(h["checked_at"], float(h["price"])) for h in history_7d]
        trending, trend_reason = detect_trend(
            recent, float(settings["window_3d_pct"]), float(settings["window_7d_pct"])
        )

        status = good_reason if good else (trend_reason if trending else "sem alerta no momento")
        lines.append(f"{route_label}: {route['currency']} {latest:.2f} — {status}")

    return "\n".join(lines)


def main() -> None:
    chat_id = str(os.environ["TELEGRAM_CHAT_ID"])
    last_update_id = get_last_update_id()
    updates = get_updates(last_update_id + 1)

    max_update_id = last_update_id
    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])
        message = update.get("message") or {}
        text = (message.get("text") or "").strip().lower()
        sender_chat_id = str(message.get("chat", {}).get("id", ""))

        if sender_chat_id != chat_id:
            continue  # ignora qualquer chat que não seja o do dono do bot
        if text in COMMANDS:
            send_message(build_status_message())

    if max_update_id != last_update_id:
        set_last_update_id(max_update_id)


if __name__ == "__main__":
    main()
