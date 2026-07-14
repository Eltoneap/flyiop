import os
from datetime import date, datetime, timezone

import requests

from buying_window import buying_window_days, is_domestic
from links import aviasales_link, google_flights_link


def send_message(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
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


def format_date_br(iso_date: str | None) -> str:
    if not iso_date:
        return "?"
    return f"{iso_date[8:10]}/{iso_date[5:7]}/{iso_date[0:4]}"


def _freshness(found_at: str | None) -> str | None:
    """Há quanto tempo o preço foi visto no cache da Aviasales."""
    if not found_at:
        return None
    try:
        seen = datetime.fromisoformat(found_at)
    except ValueError:
        return None
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - seen).total_seconds() / 3600
    if hours < 1:
        return "há menos de 1h"
    if hours < 48:
        return f"há {hours:.0f}h"
    return f"há {hours / 24:.0f} dias"


def _stops_label(stops: int | None) -> str | None:
    if stops is None:
        return None
    if stops == 0:
        return "voo direto"
    if stops == 1:
        return "1 escala"
    return f"{stops} escalas"


def build_route_block(report: dict) -> str:
    """Bloco completo de uma rota para o Telegram.

    report: origin, destination, currency, price, depart_date, return_date,
            stops, found_at, days_ahead, reason, target_price, avg_30d
    (campos ausentes são omitidos da mensagem, nunca inventados)
    """
    origin, destination = report["origin"], report["destination"]
    lines = []

    trip_kind = "ida e volta" if report.get("return_date") else "só ida encontrada"
    lines.append(f"✈️ <b>{origin} → {destination}</b> — {report['currency']} {report['price']:.2f} ({trip_kind})")

    date_part = f"🗓 Ida {format_date_br(report.get('depart_date'))}"
    if report.get("return_date"):
        date_part += f" → Volta {format_date_br(report['return_date'])}"
    stops_label = _stops_label(report.get("stops"))
    if stops_label:
        date_part += f" · {stops_label}"
    if report.get("days_ahead") is not None:
        date_part += f" · faltam {report['days_ahead']} dias"
    lines.append(date_part)

    if report.get("reason"):
        lines.append(f"📌 {report['reason']}")

    context_bits = []
    if report.get("target_price") is not None:
        context_bits.append(f"meta R$ {report['target_price']:.0f}")
    if report.get("avg_30d") is not None:
        context_bits.append(f"média 30d R$ {report['avg_30d']:.2f}")
    if context_bits:
        lines.append(f"📊 {' · '.join(context_bits)}")

    if report.get("days_ahead") is not None:
        lo, hi = buying_window_days(origin, destination)
        kind = "nacional" if is_domestic(origin, destination) else "internacional"
        inside = lo <= report["days_ahead"] <= hi
        position = "dentro" if inside else "fora"
        lines.append(f"🕐 Janela recomendada ({kind}: {lo}–{hi} dias antes): você está {position} ({report['days_ahead']} dias)")

    freshness = _freshness(report.get("found_at"))
    if freshness:
        lines.append(f"👁 Preço visto {freshness} (cache Aviasales — confirme no site antes de comprar)")

    if report.get("depart_date"):
        av = aviasales_link(origin, destination, report["depart_date"], report.get("return_date"))
        gf = google_flights_link(origin, destination, report["depart_date"], report.get("return_date"))
        lines.append(f'🔗 <a href="{av}">Aviasales</a> · <a href="{gf}">Google Flights</a>')

    return "\n".join(lines)


def build_alert_message(report: dict) -> str:
    return "🔔 <b>Alerta de preço</b>\n\n" + build_route_block(report)


def build_summary_message(blocks: list[str], extra_notes: list[str] | None = None) -> str:
    parts = ["📊 <b>Resumo das rotas</b>"]
    parts.extend(blocks)
    if extra_notes:
        parts.append("\n".join(extra_notes))
    return "\n\n".join(parts)
