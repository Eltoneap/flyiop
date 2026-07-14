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


def get_updates(offset: int) -> list[dict]:
    """Mensagens recebidas pelo bot desde `offset` (long polling, sem timeout de espera)."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    resp = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"offset": offset, "timeout": 0},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def build_alert_message(route_label: str, price: float, currency: str, flight_date: str,
                         reason: str, booking_link: str) -> str:
    return (
        f"✈️ <b>{route_label}</b>\n"
        f"Preço: {currency} {price:.2f} — {flight_date}\n"
        f"Motivo: {reason}\n"
        f"<a href=\"{booking_link}\">Ver e comprar</a>"
    )
