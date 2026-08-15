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


def user_label(user_id: str, settings_cache: dict) -> str:
    """Rótulo de exibição do usuário na mensagem (Fatia D4, 15/08/2026):
    `settings.display_name` quando houver, senão os 8 primeiros caracteres do
    uuid. Chave ausente e valor NULL caem no mesmo fallback — a mensagem nunca
    quebra por falta de nome, e nunca inventa um.

    Sempre devolve string e nunca recebe `None`: o ramo degradado (perna sem
    dono) não passa por aqui, ele chama build_weekend_alert_message com
    `who=None` direto."""
    row = settings_cache.get(user_id) or {}
    name = row.get("display_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return user_id[:8]


def build_weekend_alert_message(report: dict, decision: dict, who: str | None,
                                comparison: dict | None = None) -> str:
    """Alerta de teto (compra imediata) ou de oportunidade (relativo ao
    próprio histórico da perna) — ida e volta avaliadas independentemente
    desde a revisão de 23/07/2026. Sempre imediato — não espera o resumo
    semanal, é esse o ponto do alerta de teto.

    `decision` (Fatia D4, 15/08/2026): a decisão de UM usuário — uma entrada de
    `report["per_user"]` (com `ceiling`, `reason`, `is_ceiling_hit`), ou o
    `report["degraded_alert"]` do modo degradado. O que a mensagem diz depende
    de quem está olhando, então esses campos vêm daqui e não mais do topo do
    report.

    `who`: o rótulo de quem disparou, vindo do helper `user_label` acima
    (parâmetro com nome diferente do helper de propósito, para não sombreá-lo
    dentro desta função). `None` no modo degradado (perna sem dono) — a
    mensagem sai sem linha de nome, exatamente como antes da D4.

    `comparison` (Parte 4, regra 4): {'avulso': R$, 'pacote': R$|None} —
    avulso vem dos current_price já gravados das 2 pernas (sem busca nova);
    pacote é 1 cotação round-trip nova, best-effort. None = sem perna irmã
    com preço ainda, comparação não aparece na mensagem."""
    direction = report["direction"]
    direction_label = "Ida (sexta)" if direction == "outbound" else "Volta (domingo/segunda)"
    outbound = report["outbound_date"]
    leg_date = report["date"]
    price = report["price"]
    # Teto DE QUEM DISPAROU (Fatia D4) — None quando o usuário monitora sem
    # teto, ou no modo degradado (nenhum usuário em `settings`); nos dois casos
    # is_ceiling_hit é False (a regra de teto não roda) e a mensagem diz
    # "indisponível" em vez de exibir um número inventado.
    ceiling = decision.get("ceiling")
    ceiling = float(ceiling) if ceiling is not None else None
    ceiling_label = f"R$ {ceiling:.0f}" if ceiling is not None else "indisponível"

    if decision.get("is_ceiling_hit"):
        header = (
            f"🎯 <b>{direction_label} — fim de semana {format_date_br(outbound)}: "
            f"R$ {price:.2f} ≤ teto {ceiling_label}</b>\n"
            f"Compre e marque como comprada no painel — continua sendo monitorada até você marcar."
        )
    else:
        header = (
            f"📉 <b>Oportunidade — {direction_label.lower()} do fim de semana "
            f"{format_date_br(outbound)} caiu bastante</b>"
        )

    lines = [header]

    if who:
        lines.append(f"👤 {who}")

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

    if decision.get("reason"):
        lines.append(f"📌 {decision['reason']}")

    lines.append(f"📊 R$ {price:.2f} · teto {ceiling_label} · fonte: {report.get('source', 'cache')}")

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


def build_weekly_weekend_summary(weekend_reports: list[dict], total: int, purchased: int, cutoff: str) -> str:
    """Resumo semanal curado (segundas-feiras): 10 pernas mais baratas + 10
    mais próximas, sem listar as ~132 inteiras (a mensagem cresceria demais).

    `cutoff` (Fatia D1, 12/08/2026): as duas listas passam a considerar só
    pernas de fim de semana >= cutoff — mesma regra que já corta `total`/
    `purchased` (get_weekend_leg_counts, chamado por main.py) e que o
    Dashboard já aplica desde 28/07/2026 (docs/js/dashboard.js). Recortado
    pela `outbound_date` do FIM DE SEMANA (âncora), tanto para a perna de ida
    quanto para a de volta.

    Nota: `weekend_reports` é só o que esta EXECUÇÃO checou hoje (lote fli +
    cache), não um acúmulo da semana — "resumo semanal" é o nome da rotina
    (roda só às segundas), não do dado. Com o filtro de janela, a lista de
    elegíveis nas próximas semanas costuma ser pequena (a janela deslizante do
    lote fli tem 183 dias — cruza com a janela de compra em poucas dezenas de
    pernas por vez) — daí o estado vazio abaixo passar a ser comum, não sinal
    de falha."""
    ok_reports = [r for r in weekend_reports if r["status"] == "ok" and r["outbound_date"] >= cutoff]

    lines = [
        "📅 <b>Resumo semanal — pernas RIO↔BSB</b>",
        f"{purchased} de {total} pernas compradas · janela de compra a partir de {format_date_br(cutoff)}",
    ]

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
        lines.append(
            f"\nNenhuma perna dentro da janela de compra (a partir de {format_date_br(cutoff)}) "
            "foi checada na execução de hoje — normal enquanto a janela deslizante do lote de "
            "consulta ao vivo (~6 meses) ainda cobre poucas pernas dentro da janela de compra; "
            "cresce com o tempo."
        )

    return "\n".join(lines)


def build_summary_message(blocks: list[str], extra_notes: list[str] | None = None) -> str:
    parts = ["📊 <b>Resumo das rotas</b>"]
    parts.extend(blocks)
    if extra_notes:
        parts.append("\n".join(extra_notes))
    return "\n\n".join(parts)


def _format_elapsed_seconds(seconds: float) -> str:
    hours = seconds / 3600
    if hours < 1:
        return "menos de 1h"
    if hours < 24:
        return f"{round(hours)}h"
    days = round(hours / 24)
    return f"{days} dia{'s' if days != 1 else ''}"


def build_block_alert_message(diag: dict) -> str:
    """Alerta de bloqueio do lote de consulta ao vivo, com diagnóstico e
    escalonamento por dias consecutivos (nunca sugere proxy/IP/evasão — a
    resposta a bloqueio é sempre recuar, nunca contornar).

    diag: checked, failures, reason, seconds_since_last_success (float|None),
    streak_days (int, já contando o dia de hoje), streak_started_at
    (str ISO|None), config_url (str)."""
    lines = [
        "🚫 <b>Consulta ao vivo bloqueada</b>",
        f"{diag['checked']} consultas feitas hoje, {diag['failures']} falharam · gatilho: {diag['reason']}",
    ]
    if diag.get("seconds_since_last_success") is not None:
        lines.append(f"Última consulta bem-sucedida: há {_format_elapsed_seconds(diag['seconds_since_last_success'])}")
    lines.append("")
    lines.append("✅ Lote de hoje interrompido · Travelpayouts segue como fonte secundária · nenhuma nova tentativa hoje")
    lines.append("")

    streak = diag["streak_days"]
    if streak <= 1:
        lines.append("Isso costuma ser temporário — a execução de amanhã tenta do zero. Nenhuma ação necessária por enquanto.")
    elif streak <= 3:
        lines.append(
            f"Já é o {streak}º dia seguido bloqueado. Se persistir, considere reduzir "
            f'"Pernas checadas por dia no lote de consulta ao vivo" em Configurações.'
        )
    else:
        started = diag.get("streak_started_at")
        frozen = f" desde {started}" if started else ""
        lines.append(
            f"Já são {streak} dias seguidos bloqueado. Considere desligar \"Consulta de preço ao vivo\" em "
            f"Configurações — os preços no painel de Compras estão parados{frozen} (a Travelpayouts continua "
            f"rodando por baixo, com cobertura bem mais baixa)."
        )

    lines.append(f'⚙️ <a href="{diag["config_url"]}">Abrir Configurações</a>')
    return "\n".join(lines)


def build_block_recovered_message(streak_days: int) -> str:
    dias = f"{streak_days} dia{'s' if streak_days != 1 else ''}"
    return f"✅ <b>Consulta ao vivo normalizada</b> — voltou a funcionar depois de {dias} sem sucesso."


# ----------------------------------------------------------------------------
# Avisos de DEGRADAÇÃO — não são mais estado provisório (Fatia D4, 15/08/2026).
# Os dois avisos que existiam por causa do multiusuário parcial da Etapa 4.2
# (MIN de teto entre usuários e limiares gerais vindos de um usuário só) foram
# REMOVIDOS junto com as regras que descreviam: a avaliação agora é por
# usuário. Os dois que sobram descrevem degradação legítima — falta de dado que
# o robô contorna sem inventar número, e que não pode seguir em silêncio.
# Saem no máximo 1x por execução.
# ----------------------------------------------------------------------------

def build_no_effective_ceiling_message() -> str:
    """Nenhum usuário em `settings` — a view `weekend_leg_effective` volta
    vazia e não existe teto efetivo pra comparar. É erro de dado, não caso pra
    inventar um número: o robô segue gravando preço (o histórico é o ativo que
    não dá pra recuperar depois) e avaliando oportunidade, mas o alerta de teto
    fica desligado até a linha de settings existir.

    Fatia D4 (15/08/2026) — DIFERENÇA REAL EM RELAÇÃO A ANTES, registrada de
    propósito: neste modo o alerta enviado NÃO é gravado em `alert_log` (não há
    dono para gravar, e gravar NULL colidiria com a marca d'água da D3), então
    o cooldown não é alimentado e o mesmo alerta de oportunidade pode repetir a
    cada execução até a linha de `settings` voltar a existir. Antes da D4 o
    cooldown funcionava neste cenário. A troca é aceita porque o cenário exige
    zero linha em `settings` e nunca ocorreu em produção, o modo já é anunciado
    aqui a cada execução, e a alternativa (consultar `user_id is null`)
    corromperia permanentemente a separação de significados da coluna."""
    return (
        "⚠️ <b>Teto indisponível — alerta de teto desligado hoje</b>\n"
        "Nenhum usuário registrado em <code>settings</code>, então não há teto efetivo "
        "pra comparar. Os preços continuam sendo gravados normalmente e o alerta de "
        "oportunidade (% abaixo da média) segue valendo — só a comparação com o teto "
        "não roda. Verifique o cadastro de configurações no painel."
    )


def build_buying_cutoff_fallback_message(fallback_cutoff: str) -> str:
    """Fatia D1 (12/08/2026): a data de corte da janela de compra não veio de
    `system_config` (tabela sem a linha, ou chave ausente/ilegível na
    resposta) — o robô caiu no fallback embutido em vez de inventar um valor
    diferente ou desligar o filtro. O filtro CONTINUA valendo (com o valor de
    fallback); é isso que este aviso deixa explícito, no mesmo padrão dos
    outros avisos de estado provisório desta seção."""
    return (
        "⚠️ <b>Data de corte da janela de compra indisponível — usando padrão</b>\n"
        f"Não foi possível ler <code>system_config.weekend_buying_cutoff_date</code>. "
        f"O filtro de janela de compra do Telegram continua ativo, usando o valor padrão "
        f"<b>{format_date_br(fallback_cutoff)}</b>. Verifique a tabela <code>system_config</code> "
        "no Supabase (RUNBOOK.md)."
    )


STAGE_EXECUTIONS_PER_DAY = {0: 1, 1: 2, 2: 3}


def build_stage_change_message(new_stage: int, reason: str) -> str:
    """Parte 10 (28/07/2026): toda mudança de estágio do escalonamento
    automático de frequência avisa no Telegram — subida ou queda, com o
    motivo, pra nunca ser uma mudança silenciosa."""
    execucoes = STAGE_EXECUTIONS_PER_DAY[new_stage]
    direction = "🔺 Frequência subiu" if new_stage > 0 else "🔻 Frequência caiu"
    return (
        f"{direction} <b>pro Estágio {new_stage}</b> ({execucoes}x/dia) — motivo: {reason}."
    )
