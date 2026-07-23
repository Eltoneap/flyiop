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


def hours_since_found(found_at: str | None) -> float | None:
    """Idade do preço em horas (found_at do cache Aviasales). None = desconhecida."""
    if not found_at:
        return None
    try:
        seen = datetime.fromisoformat(found_at)
    except ValueError:
        return None
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - seen).total_seconds() / 3600


def _freshness(found_at: str | None) -> str | None:
    """Há quanto tempo o preço foi visto no cache da Aviasales."""
    hours = hours_since_found(found_at)
    if hours is None:
        return None
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


def _time_hhmm(iso_datetime: str | None) -> str | None:
    """'2026-09-06T20:00:00-03:00' -> '20:00'. Não filtra por hora, só exibe —
    a API não tem filtro de hora, isso é informativo pro usuário julgar."""
    if not iso_datetime or len(iso_datetime) < 16:
        return None
    return iso_datetime[11:16]


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
    elif report.get("cache_48h"):
        lines.append("ℹ️ Fonte com cache de até 48h — confirme no site antes de comprar")

    if report.get("depart_date"):
        gf = google_flights_link(origin, destination, report["depart_date"], report.get("return_date"))
        av = aviasales_link(origin, destination, report["depart_date"], report.get("return_date"))
        lines.append(f'🔗 <a href="{gf}">Google Flights</a> · <a href="{av}">conferência de preço (em USD)</a>')

    return "\n".join(lines)


def build_alert_message(report: dict) -> str:
    header = "🔔 <b>Alerta de preço</b>"
    if report.get("is_stale"):
        age = report.get("age_hours")
        if age is None and report.get("cache_48h"):
            # Fonte v3 (Etapa 6): ausência de found_at é esperada, não anômala —
            # aviso informativo em vez do alarme de dado antigo.
            header = "ℹ️ <b>Fonte com cache de até 48h</b> — confirme no site antes de comprar.\n\n" + header
        else:
            age_label = f"visto há {age:.0f}h" if age is not None else "idade desconhecida"
            header = (
                f"⚠️ <b>Dado antigo ({age_label})</b> — o preço pode não existir mais; "
                f"confirme no site antes de se animar.\n\n" + header
            )
    return header + "\n\n" + build_route_block(report)


def build_weekend_alert_message(report: dict, comparison: dict | None = None) -> str:
    """Alerta de teto (compra imediata) ou de oportunidade (relativo ao
    próprio histórico da perna) — ida e volta avaliadas independentemente
    desde a revisão de 23/07/2026. Sempre imediato — não espera o resumo
    semanal, é esse o ponto do alerta de teto.

    `comparison` (Parte 4, regra 4): {'avulso': R$, 'pacote': R$|None} —
    avulso vem dos current_price já gravados das 2 pernas (sem busca nova);
    pacote é 1 cotação round-trip nova, best-effort. None = sem perna irmã
    com preço ainda, comparação não aparece na mensagem."""
    direction = report["direction"]
    direction_label = "Ida (sexta)" if direction == "outbound" else "Volta (domingo/segunda)"
    outbound = report["outbound_date"]
    leg_date = report["date"]
    price = report["price"]
    ceiling = float(report["leg"].get("price_ceiling") or 200)

    if report.get("is_ceiling_hit"):
        header = (
            f"🎯 <b>{direction_label} — fim de semana {format_date_br(outbound)}: "
            f"R$ {price:.2f} ≤ teto R$ {ceiling:.0f}</b>\n"
            f"Compre e marque como comprada no painel — continua sendo monitorada até você marcar."
        )
    else:
        header = (
            f"📉 <b>Oportunidade — {direction_label.lower()} do fim de semana "
            f"{format_date_br(outbound)} caiu bastante</b>"
        )

    lines = [header]

    date_part = f"🗓 {format_date_br(leg_date)}"
    if report.get("variant"):
        variant_label = "domingo" if report["variant"] == "sunday" else "segunda"
        date_part += f" ({variant_label})"
    stops_label = _stops_label(report.get("transfers"))
    if stops_label:
        date_part += f" · {stops_label}"
    lines.append(date_part)

    airport = report.get("airport")
    if airport:
        lines.append(f"📍 {'ida' if direction == 'outbound' else 'volta'} por {airport}")

    if report.get("reason"):
        lines.append(f"📌 {report['reason']}")

    lines.append(f"📊 R$ {price:.2f} · teto R$ {ceiling:.0f} · fonte: {report.get('source', 'cache')}")

    if comparison and comparison.get("avulso") is not None:
        avulso = comparison["avulso"]
        pacote = comparison.get("pacote")
        if pacote is not None:
            lines.append(f"💰 Avulso (2 pernas): R$ {avulso:.2f} · Pacote (ida+volta): R$ {pacote:.2f}")
        else:
            lines.append(f"💰 Avulso (2 pernas): R$ {avulso:.2f} — pacote indisponível agora")

    if airport:
        if direction == "outbound":
            gf, av = google_flights_link(airport, "BSB", leg_date), aviasales_link(airport, "BSB", leg_date)
        else:
            gf, av = google_flights_link("BSB", airport, leg_date), aviasales_link("BSB", airport, leg_date)
        lines.append(f'🔗 <a href="{gf}">Google Flights</a> · <a href="{av}">conferência de preço (em USD)</a>')

    return "\n".join(lines)


def build_weekly_weekend_summary(weekend_reports: list[dict], total: int, purchased: int) -> str:
    """Resumo semanal curado (segundas-feiras): 10 pernas mais baratas + 10
    mais próximas, sem listar as ~132 inteiras (a mensagem cresceria demais)."""
    ok_reports = [r for r in weekend_reports if r["status"] == "ok"]

    lines = ["📅 <b>Resumo semanal — pernas RIO↔BSB</b>", f"{purchased} de {total} pernas compradas"]

    if ok_reports:
        def leg_label(r: dict) -> str:
            direction_word = "ida" if r["direction"] == "outbound" else "volta"
            return f"{format_date_br(r['outbound_date'])} ({direction_word})"

        cheapest = sorted(ok_reports, key=lambda r: r["price"])[:10]
        lines.append("\n<b>Mais baratas agora:</b>")
        for r in cheapest:
            lines.append(f"· {leg_label(r)}: R$ {r['price']:.2f}")

        nearest = sorted(ok_reports, key=lambda r: r["outbound_date"])[:10]
        lines.append("\n<b>Mais próximas:</b>")
        for r in nearest:
            lines.append(f"· {leg_label(r)}: R$ {r['price']:.2f}")
    else:
        lines.append("\nSem preços coletados ainda esta semana.")

    return "\n".join(lines)


def build_summary_message(blocks: list[str], extra_notes: list[str] | None = None) -> str:
    parts = ["📊 <b>Resumo das rotas</b>"]
    parts.extend(blocks)
    if extra_notes:
        parts.append("\n".join(extra_notes))
    return "\n\n".join(parts)
