import os
import requests


def send_message(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False},
        timeout=15,
    )
    resp.raise_for_status()


def build_alert_message(route_label: str, price: float, currency: str, flight_date: str,
                         reason: str, booking_link: str) -> str:
    return (
        f"✈️ <b>{route_label}</b>\n"
        f"Preço: {currency} {price:.2f} — {flight_date}\n"
        f"Motivo: {reason}\n"
        f"<a href=\"{booking_link}\">Ver e comprar</a>"
    )
