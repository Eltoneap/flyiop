"""Alvo Fins de Semana RIO↔BSB — pernas desacopladas (revisão de 23/07/2026).

Ida e volta são alvos independentes ("pernas"): cada weekend gera uma perna
'outbound' (sexta, GIG/SDU→BSB) e uma perna 'return' (domingo OU segunda,
BSB→GIG/SDU, a mais barata das duas vence), cada uma com seu próprio preço,
histórico, teto e status de compra. Motivo da mudança: exigir ida+volta como
um evento único (o modelo anterior) multiplicava a raridade do cache — nem
o código de cidade RIO (que agrega GIG+SDU) trazia cobertura suficiente.

Busca por MÊS, one-way, GIG e SDU separados (não mais o código de cidade
RIO): cada perna consulta os dois aeroportos individualmente, na direção
certa (ida: aeroporto→BSB; volta: BSB→aeroporto), com departure_at em
granularidade de mês — a mesma lição da rodada anterior (data exata vem
sistematicamente vazia). O match com a data exata da perna é filtrado
localmente, sem tolerância de ±1 dia — bate exato ou fica "sem dado ainda"
(estado normal, não erro).

Agrupamento por (mês, aeroporto, direção): várias pernas compartilham a
mesma chave (todas as pernas 'outbound' de setembro, por exemplo), então
cada chave é buscada uma única vez e reusada — não uma chamada por perna.

Reusa direto as funções de decisão já testadas em produção (rules.py):
evaluate_good_price (teto = meta fixa, oportunidade = % abaixo da média
própria), is_suspicious_price (autocheck anti-preço-fantasma) e
cooldown_blocks_alert (Etapa 3, aqui aplicado por perna × tipo de alerta ×
usuário via alert_log.leg_id + is_ceiling_alert/is_opportunity_alert +
user_id — Fatia D2, 13/08/2026, e Fatia D4, 15/08/2026).

Checkpoint da Parte 2 (23/07/2026): resultado real de produção conferido —
só 2 de 132 pernas bateram (cache insuficiente, mesmo padrão do RIO
round-trip). Por isso, desde a Parte 3 (live_check.py), esta busca cache
deixou de ser a fonte primária: o `fast_flights` (Google Flights) passou a
decidir `current_price`/alerta; esta busca continua rodando como conferidor
secundário (barata, ~64 consultas/dia), gravando com `source='cache'` via
a mesma `evaluate_and_record_leg_price` que o live-check usa.
"""
import time
import traceback
from datetime import date, datetime, timedelta, timezone

from rules import cooldown_blocks_alert, evaluate_good_price, is_suspicious_price
from supabase_client import (
    DEFAULT_SETTINGS,
    DEFAULT_SYSTEM_CONFIG,
    get_all_weekend_legs,
    get_effective_leg_state,
    get_last_weekend_leg_alert,
    get_monitoring_weekends,
    get_weekend_leg_price_history,
    insert_weekend_leg_price,
    insert_weekend_leg_run_log,
    update_weekend_leg,
)
from travelpayouts_client import get_prices_for_dates

GIG = "GIG"
SDU = "SDU"
AIRPORTS = (GIG, SDU)
BSB = "BSB"
CURRENCY = "BRL"
REQUEST_DELAY_SECONDS = 0.3
MONTH_QUERY_LIMIT = 200  # a API ordena por preço, não por data — limite alto
# aumenta a chance da data exata da perna aparecer entre os resultados do mês.

# Fallback do corte da janela de compra — só usado se a chave não vier de
# settings (que já é o merge de system_config feito em main.py). Mesmo valor
# de DEFAULT_SYSTEM_CONFIG (supabase_client.py); duplicado aqui só para o
# caso degradado ficar legível sem seguir o import. Fonte de verdade:
# system_config.weekend_buying_cutoff_date (sql/fatia_d1_janela_compra_telegram.sql).
BUYING_CUTOFF_FALLBACK = DEFAULT_SYSTEM_CONFIG["weekend_buying_cutoff_date"]


def resolve_buying_cutoff(settings: dict) -> tuple[str, bool]:
    """(corte efetivo, degradado?). `settings` aqui já é o dict mesclado com
    system_config que main.py monta — não outra leitura do banco.

    Degradado = a chave não veio como string não vazia (ausente, None, "").
    Direção da falha (Fatia D1, decisão 4): SEMPRE mantém o filtro, nunca o
    remove — um filtro restritivo demais só deixa o Telegram mais quieto
    (recuperável, preço continua no painel); um filtro que some é
    indistinguível do bug que esta fatia existe para corrigir. Quem chama
    decide se avisa no Telegram (main.py, 1x por execução, mesmo padrão dos
    avisos da Etapa 4.2)."""
    value = settings.get("weekend_buying_cutoff_date")
    if isinstance(value, str) and value:
        return value, False
    return BUYING_CUTOFF_FALLBACK, True


def cheapest_entry(entries: list[dict]) -> dict | None:
    if not entries:
        return None
    return min(entries, key=lambda e: float(e["price"]))


def relevant_months(leg: dict) -> list[str]:
    """Meses (YYYY-MM) que precisam ser consultados pra essa perna.
    'outbound' tem 1 data só; 'return' pode ter domingo e segunda em meses
    diferentes se o fim de semana cair na virada do mês."""
    if leg["direction"] == "outbound":
        return [leg["outbound_date"][:7]]
    return sorted({leg["return_sunday"][:7], leg["return_monday"][:7]})


def date_candidates(leg: dict) -> list[tuple[str | None, str]]:
    """[(variante, data)] a checar pra essa perna. 'outbound' não tem
    variante (só existe 1 data possível); 'return' tem domingo e segunda."""
    if leg["direction"] == "outbound":
        return [(None, leg["outbound_date"])]
    return [("sunday", leg["return_sunday"]), ("monday", leg["return_monday"])]


def fetch_leg_month_entries(month: str, airport: str, direction: str) -> list[dict]:
    """Uma chamada por (mês, aeroporto, direção) — reusada por todas as
    pernas que compartilham essa combinação."""
    if direction == "outbound":
        origin, destination = airport, BSB
    else:
        origin, destination = BSB, airport
    return get_prices_for_dates(origin, destination, CURRENCY, departure_at=month, one_way=True, limit=MONTH_QUERY_LIMIT)


def match_leg_entries(entries: list[dict], target_date: str) -> dict | None:
    """Entre as entradas do mês, a mais barata cuja data de partida bate
    EXATAMENTE com a perna. Sem tolerância de data — match exato ou nada.
    One-way: a data relevante é sempre departure_at (não há return_at)."""
    matches = [e for e in entries if (e.get("departure_at") or "")[:10] == target_date]
    return cheapest_entry(matches)


def leg_expiry_date(leg: dict) -> str:
    """Última data em que essa perna, especificamente, ainda faz sentido
    monitorar: a própria data de ida, ou (pra volta) `return_monday` — o
    candidato mais tardio entre domingo/segunda, cobrindo os dois mesmo sem
    `current_variant` decidido ainda. Ida e volta expiram de forma
    independente (Parte 9, 28/07/2026) — antes, as duas expiravam junto pela
    data de ida do weekend, cortando a perna de volta 2-3 dias cedo demais."""
    if leg["direction"] == "outbound":
        return leg["outbound_date"]
    return leg["return_monday"]


# Diagnóstico da última carga de pernas, para o aviso único por execução em
# main.py. get_active_legs roda 2x por execução (varredura cache + lote fli) e
# recalcula os mesmos números nas duas — por isso o dict é sobrescrito, nunca
# acumulado: quem lê manda no máximo uma mensagem por condição.
LEG_LOAD_DIAGNOSTICS = {"degraded_no_settings": False}


def resolve_effective_leg_state(state_rows: list[dict]) -> dict[str, dict[str, float | None]]:
    """Colapsa as linhas perna × usuário de `weekend_leg_effective` em
    {leg_id: {user_id: teto_efetivo_ou_None}} — uma chave por usuário que ainda
    monitora a perna, TENHA ELE TETO OU NÃO.

    Duas regras:

    - FILA (pendência 9 da Etapa 4.2): a perna fica na fila se PELO MENOS UM
      usuário ainda tem status efetivo 'monitoring'. Sai só quando TODOS
      decidiram outra coisa. Ausência de linha em `weekend_leg_user_state` já
      chega aqui como 'monitoring' (a view faz o coalesce) — silêncio segue o
      padrão, e o padrão é continuar monitorando.
    - TETO (Fatia D4, 15/08/2026): cada usuário carrega o SEU teto até o ponto
      de avaliação. O MIN entre usuários — regra provisória da Etapa 4.2, que
      existia só porque o Telegram era canal único sem fan-out — está
      aposentado: `evaluate_and_record_leg_price` itera por usuário e cada um
      recebe o alerta dele. Esta função passa a ser definitiva.

    CHAVEAMENTO PELA PRESENÇA, NÃO PELA EXISTÊNCIA DE TETO: usuário monitorando
    sem teto entra como {user_id: None} — chave presente, valor nulo — e nunca
    é omitido. Com isso, dict vazio significa exatamente uma coisa: NENHUM
    usuário monitora aquela perna. É o que torna inequívoco o marcador do modo
    degradado lido em `evaluate_and_record_leg_price` (`ceilings_by_user == {}`).
    Filtrar aqui quem não tem teto faria uma perna com um único usuário sem teto
    virar `{}` e ser lida como "perna sem dono" — alerta enviado sem registro em
    `alert_log`, e o estado "usuário presente, sem teto" desapareceria.

    Usuário que já marcou a perna como comprada não entra no dict: o teto dele
    não deve mais governar um alerta que só interessa a quem ainda monitora."""
    rows_by_leg: dict[str, list[dict]] = {}
    for row in state_rows:
        rows_by_leg.setdefault(row["leg_id"], []).append(row)

    effective: dict[str, dict[str, float | None]] = {}
    for leg_id, rows in rows_by_leg.items():
        monitoring = [r for r in rows if r.get("status") == "monitoring"]
        if not monitoring:
            continue  # todos os usuários já decidiram outra coisa — sai da fila
        effective[leg_id] = {
            r["user_id"]: (float(r["price_ceiling"]) if r.get("price_ceiling") is not None else None)
            for r in monitoring
        }
    return effective


def get_active_legs() -> list[dict]:
    """Pernas ainda monitoradas por pelo menos um usuário, cuja própria data
    (não a do weekend) ainda não passou de D+1 — expiração independente por
    perna (Parte 9). D+1 é folga de segurança: o robô roda 1x/dia, D0 puro
    arriscaria perder a checagem do próprio dia do voo por atraso de execução
    ou horário do voo já ter passado de manhã. Cada perna volta com as datas
    do weekend anexadas (prontas pro matching local), com `ceilings_by_user`
    (o teto de CADA usuário que ainda monitora — fonte única do alerta desde a
    Fatia D4) e com `queue_ceiling` (o menor teto entre eles, HEURÍSTICA DE
    PRIORIDADE da fila do lote fli, nunca decisão de alerta).

    Modo degradado: se `weekend_leg_effective` vier vazia (nenhum usuário em
    `settings`), a fila não filtra por status nenhum — devolve todas as pernas
    não expiradas com `ceilings_by_user = {}` e `queue_ceiling = None`, ou seja,
    grava preço e avalia oportunidade, mas sem comparação de teto e sem
    cooldown por usuário. Nunca esvazia a fila em silêncio, e nunca inventa um
    teto: main.py avisa no Telegram. (Até a Etapa 4.3 esse ramo caía no
    `weekend_legs.status` antigo; a coluna está congelada desde 03/08/2026 —
    não reflete decisão viva de usuário — e é removida na 4.3.)

    A ORDEM DOS DOIS TESTES É A GARANTIA, e não pode ser fundida num só:
    `degraded` é fato da CARGA INTEIRA (a consulta voltou vazia — erro de dado,
    o robô degrada e avisa) e curto-circuita o teste POR PERNA de "ninguém
    monitora" (estado normal, a perna terminou). Aplicar o segundo
    incondicionalmente esvaziaria a fila em silêncio no modo degradado —
    transformaria um erro de dado em "acabou o trabalho"."""
    cutoff = (date.today() - timedelta(days=1)).isoformat()
    weekends_by_id = {w["id"]: w for w in get_monitoring_weekends()}

    state_rows = get_effective_leg_state()
    effective = resolve_effective_leg_state(state_rows)
    degraded = not state_rows
    LEG_LOAD_DIAGNOSTICS["degraded_no_settings"] = degraded

    legs = []
    for leg in get_all_weekend_legs():
        weekend = weekends_by_id.get(leg["weekend_id"])
        if weekend is None:
            continue  # weekend já passou (nem a volta é mais válida) ou não existe mais
        if degraded:
            # Sem filtro de status (Etapa 4.3): `weekend_legs.status` está
            # congelado desde 03/08/2026 (o painel escreve em
            # weekend_leg_user_state) e some no DROP — ler daqui esvaziaria a
            # fila em silêncio (chave ausente vira None, e None != 'monitoring').
            ceilings_by_user: dict[str, float | None] = {}
            queue_ceiling = None
        else:
            if leg["id"] not in effective:
                continue  # nenhum usuário monitorando essa perna
            ceilings_by_user = effective[leg["id"]]
            known_ceilings = [c for c in ceilings_by_user.values() if c is not None]
            queue_ceiling = min(known_ceilings) if known_ceilings else None
        merged = {
            **leg,
            "outbound_date": weekend["outbound_date"],
            "return_sunday": weekend["return_sunday"],
            "return_monday": weekend["return_monday"],
            "ceilings_by_user": ceilings_by_user,
            "queue_ceiling": queue_ceiling,
        }
        if leg_expiry_date(merged) < cutoff:
            continue  # essa perna específica já passou do D+1 dela
        legs.append(merged)
    return legs


def evaluate_and_record_leg_price(leg: dict, system_settings: dict, settings_by_user: dict[str, dict],
                                  price: float, airport: str | None,
                                  variant: str | None, transfers: int | None, source: str,
                                  airline: str | None = None, departure_time: str | None = None,
                                  suppress_alert: bool = False) -> dict:
    """Núcleo compartilhado entre a varredura cache (process_weekend_leg, abaixo)
    e o lote fast-flights (live_check.py, Parte 3): grava o preço, avalia
    teto/oportunidade/suspeita/cooldown, e atualiza a perna. `source` é
    'cache' ou 'live' — desde a Parte 3, 'live' é a fonte primária (decide
    o current_price/alerta); 'cache' virou conferidor secundário, mas grava
    exatamente do mesmo jeito (histórico registra as duas fontes).
    `airline`/`departure_time` (Parte 9, 28/07/2026): só a fonte 'live' (fli)
    devolve esses campos — a Travelpayouts ('cache') não, ficam None ali.

    Fatia D4 (15/08/2026) — LINHA DE CORTE ENTRE O QUE É DO MERCADO E O QUE É
    DE QUEM OLHA, e ela é visível na ordem do corpo abaixo:

    - UMA VEZ POR PERNA (antes do laço): gravar o preço, ler o histórico,
      classificar suspeita e resolver a janela de compra. São fatos de mercado
      e regras de sistema, idênticos para qualquer usuário — nenhuma consulta
      cresce com o número de usuários, que é a garantia central desta fatia.
    - POR USUÁRIO (o laço): teto próprio, `weekend_opportunity_pct` próprio,
      cooldown próprio por tipo. Uma entrada em `per_user` por usuário que
      monitora a perna, alertando ou não — o filtro `should_alert` só é
      aplicado no laço de envio (main.py), que é onde o leque abre.
    - UMA VEZ POR PERNA (depois do laço): `update_weekend_leg` e
      `insert_weekend_leg_run_log`. Nenhum campo de decisão pessoal (teto,
      alerta, cooldown) entra em `weekend_legs` nem em `weekend_leg_run_log` —
      decisão pessoal vive em `weekend_leg_user_state` e em `alert_log`.

    `suppress_alert` (radar de calendário, decisão 1): usado só pelo refresh
    de metadado do regime 'metadata' em live_check.py — a perna já está
    coberta pelo radar, esta chamada existe só pra atualizar
    companhia/horário. Grava o preço e atualiza a perna normalmente, mas
    RETORNA ANTES de qualquer avaliação de teto/oportunidade (nem histórico
    de 90d, nem suspeita, nem janela de compra, nem laço por usuário) — nunca
    decide alertar. Default `False` = comportamento idêntico ao de antes
    desta fatia em toda chamada existente.

    `system_settings` é o `system_config` que main.py monta (não um dicionário
    novo): fornece `suspicious_below_avg_pct` e `weekend_buying_cutoff_date`.
    `settings_by_user` é o `settings_cache` de main.py, {user_id: settings}."""
    leg_id = leg["id"]
    direction = leg["direction"]
    if direction == "outbound":
        leg_date = leg["outbound_date"]
    else:
        leg_date = leg["return_sunday"] if variant == "sunday" else leg["return_monday"]

    insert_weekend_leg_price(leg_id, price, airport, variant, source, transfers, airline, departure_time)

    if suppress_alert:
        lowest_seen = leg.get("lowest_seen")
        is_new_low = lowest_seen is None or price < float(lowest_seen)
        update_fields = {
            "current_price": price,
            "current_price_at": datetime.now(timezone.utc).isoformat(),
            "current_airport": airport,
            "current_variant": variant,
            "current_source": source,
            "current_airline": airline,
            "current_departure_time": departure_time,
        }
        if is_new_low:
            update_fields["lowest_seen"] = price
            update_fields["lowest_seen_at"] = datetime.now(timezone.utc).isoformat()
        update_weekend_leg(leg_id, **update_fields)
        insert_weekend_leg_run_log(leg_id, "ok", price=price, source=source)

        variant_label = f", {variant}" if variant else ""
        print(
            f"[perna {direction} {leg['outbound_date']}] R$ {price:.2f} ({airport}{variant_label}, {source}) "
            "refresh de metadado (radar) — sem avaliação de teto"
        )
        return {
            "leg": leg,
            "status": "ok",
            "direction": direction,
            "weekend_id": leg["weekend_id"],
            "outbound_date": leg["outbound_date"],
            "price": price,
            "date": leg_date,
            "airport": airport,
            "variant": variant,
            "transfers": transfers,
            "source": source,
            "suspicious": None,
            "per_user": [],
            "degraded_alert": None,
            "should_alert": False,
            "alert_suppressed": True,
        }

    history = get_weekend_leg_price_history(leg_id, days=90)
    history_prices = [float(h["price"]) for h in history]

    suspicious_threshold = float(
        system_settings.get("suspicious_below_avg_pct") or DEFAULT_SETTINGS["suspicious_below_avg_pct"]
    )
    suspicious = is_suspicious_price(price, history_prices, suspicious_threshold)

    # Janela de compra (Fatia D1, 12/08/2026, ajuste do mesmo dia): filtro vale
    # para os DOIS tipos de alerta de perna — teto e oportunidade — não só
    # oportunidade. Um alerta de teto para um fim de semana anterior ao corte
    # mandaria "compre" algo que por decisão de escopo nunca será comprado
    # (STATE.md, seção 2). NÃO afeta a COLETA: o preço já foi gravado acima
    # (insert_weekend_leg_price) e current_price/lowest_seen são atualizados
    # normalmente mais abaixo, fora da janela ou não.
    buying_cutoff, _cutoff_degraded = resolve_buying_cutoff(system_settings)
    in_buying_window = leg["outbound_date"] >= buying_cutoff

    # `perna sem dono` — a condição do modo degradado, avaliada UMA VEZ, aqui.
    # Só é possível pelo ramo degradado de get_active_legs: no ramo normal, uma
    # perna sem nenhum usuário monitorando nem entra na lista.
    ceilings_by_user: dict[str, float | None] = leg.get("ceilings_by_user") or {}

    def suppressed_outside_window(owner: str | None = None) -> None:
        # Nomeia o usuário: com mais de um, esta linha sai uma vez por usuário
        # afetado, e duas linhas idênticas no log não diriam de quem são.
        who = f", {owner}" if owner else ""
        print(f"[{direction} {leg['outbound_date']}{who}] alerta suprimido — fim de semana fora da janela de compra (< {buying_cutoff})")

    per_user: list[dict] = []
    degraded_alert = None

    if ceilings_by_user:
        # Ordem determinística por user_id: nem get_effective_leg_state nem
        # get_all_weekend_legs pedem `order`, então a ordem do banco não é
        # garantida e a da mensagem não pode depender dela.
        for user_id, user_ceiling in sorted(ceilings_by_user.items()):
            user_settings = settings_by_user.get(user_id) or DEFAULT_SETTINGS
            ceiling = float(user_ceiling) if user_ceiling is not None else None
            opportunity_pct = float(
                user_settings.get("weekend_opportunity_pct") or DEFAULT_SETTINGS["weekend_opportunity_pct"]
            )
            # Teto None (usuário monitorando sem teto): a regra de teto sai de
            # cena para ESTE usuário (target_price=None => ceiling_hit sempre
            # False) e só a de oportunidade decide. Nada é inventado no lugar.
            good, reason, ceiling_hit, opportunity_hit = evaluate_good_price(
                price, history_prices, ceiling, opportunity_pct
            )
            would_alert = good and not suspicious and in_buying_window
            if good and not suspicious and not in_buying_window:
                suppressed_outside_window(user_id)
            cooldown_suppressed = False
            if would_alert:
                # Fatia D2 (13/08/2026): cooldown avaliado POR TIPO — um alerta
                # de oportunidade em cooldown não segura mais um de teto
                # liberado, e vice-versa (bug estrutural documentado em
                # STATE.md, seção 2). Fatia D4: e agora também POR USUÁRIO —
                # o cooldown de um não silencia o alerta do outro.
                # Segura só se TODOS os tipos que dispararam nesta avaliação
                # estão em cooldown; `active_types` nunca fica vazia aqui
                # (would_alert=True implica good=True, que implica ceiling_hit
                # ou opportunity_hit), mas o `bool(...)` guarda contra
                # all([]) == True mesmo assim — não confiar em invariante
                # implícito num ponto que decide silêncio.
                active_types = []
                if ceiling_hit:
                    active_types.append("ceiling")
                if opportunity_hit:
                    active_types.append("opportunity")
                blocks = [
                    cooldown_blocks_alert(get_last_weekend_leg_alert(leg_id, t, user_id), price, user_settings)
                    for t in active_types
                ]
                cooldown_suppressed = bool(blocks) and all(blocks)
            per_user.append({
                "user_id": user_id,
                "ceiling": ceiling,
                "reason": reason,
                "is_ceiling_hit": ceiling_hit,
                "is_opportunity_hit": opportunity_hit,
                "should_alert": would_alert and not cooldown_suppressed,
            })
    else:
        # RAMO DEGRADADO — `perna sem dono`. Um laço por usuário sobre dict
        # vazio não alertaria nada, e isso seria regressão silenciosa contra o
        # contrato de build_no_effective_ceiling_message ("o alerta de
        # oportunidade segue valendo"). Então o caso tem caminho próprio.
        #
        # SEM SENTINELA em `per_user`, de propósito: uma entrada com
        # user_id=None gravaria linha de perna em alert_log com user_id NULL, e
        # isso (a) contradiz a verificação desta fatia, que declara "linha nova
        # com NULL é defeito", e (b) cria um TERCEIRO significado de NULL do
        # mesmo lado da marca d'água da D3, que existe justamente para separar
        # "linha anterior à individualização" de "gravação de dono que falhou".
        # Por isso `per_user` fica [] e a decisão vai num campo próprio, e o
        # laço de envio manda a mensagem SEM gravar em alert_log.
        #
        # LIMIAR: DEFAULT_SETTINGS, e isso PRESERVA o comportamento de hoje em
        # vez de inventar um novo — sem linha em `settings` não há de quem ler,
        # e nos dois sub-casos (settings vazia com rotas, settings vazia sem
        # rotas) o valor efetivo que main.py montaria já era o do default.
        #
        # OS FILTROS COMUNS CONTINUAM VALENDO: `suspicious` e `in_buying_window`
        # foram calculados acima, fora da bifurcação, e são a MESMA porta de
        # saída do ramo normal. A janela de compra em especial não é negociável
        # — reabrir alerta para fim de semana anterior ao corte seria regressão
        # direta da Fatia D1, em produção desde 12/08/2026.
        opportunity_pct = float(DEFAULT_SETTINGS["weekend_opportunity_pct"])
        good, reason, ceiling_hit, opportunity_hit = evaluate_good_price(
            price, history_prices, None, opportunity_pct
        )
        if good and not suspicious and in_buying_window:
            degraded_alert = {
                "ceiling": None,
                "reason": reason,
                "is_ceiling_hit": ceiling_hit,      # sempre False: sem teto, a regra não roda
                "is_opportunity_hit": opportunity_hit,
            }
        elif good and not suspicious:
            suppressed_outside_window()

    lowest_seen = leg.get("lowest_seen")
    is_new_low = lowest_seen is None or price < float(lowest_seen)
    update_fields = {
        "current_price": price,
        "current_price_at": datetime.now(timezone.utc).isoformat(),
        "current_airport": airport,
        "current_variant": variant,
        "current_source": source,
        "current_airline": airline,
        "current_departure_time": departure_time,
    }
    if is_new_low:
        update_fields["lowest_seen"] = price
        update_fields["lowest_seen_at"] = datetime.now(timezone.utc).isoformat()
    update_weekend_leg(leg_id, **update_fields)

    insert_weekend_leg_run_log(leg_id, "ok", price=price, source=source)

    variant_label = f", {variant}" if variant else ""
    if not ceilings_by_user:
        decision_label = "sem usuário monitorando — só oportunidade (modo degradado)"
    elif len(per_user) == 1:
        only_ceiling = per_user[0]["ceiling"]
        decision_label = f"teto R$ {only_ceiling:.0f}" if only_ceiling is not None else "teto indisponível"
    else:
        queue_ceiling = leg.get("queue_ceiling")
        lowest = f"R$ {float(queue_ceiling):.0f}" if queue_ceiling is not None else "indisponível"
        decision_label = f"{len(per_user)} usuários, menor teto {lowest}"
    print(f"[perna {direction} {leg['outbound_date']}] R$ {price:.2f} ({airport}{variant_label}, {source}) {decision_label}")

    return {
        "leg": leg,
        "status": "ok",
        "direction": direction,
        "weekend_id": leg["weekend_id"],
        "outbound_date": leg["outbound_date"],
        "price": price,
        "date": leg_date,
        "airport": airport,
        "variant": variant,
        "transfers": transfers,
        "source": source,
        "suspicious": suspicious,
        # Uma decisão POR USUÁRIO (Fatia D4): `reason`/`is_ceiling_hit`/
        # `is_opportunity_hit` desceram do topo do report para dentro de
        # `per_user`, porque agora dependem de quem está olhando.
        "per_user": per_user,
        "degraded_alert": degraded_alert,
        # Agregado, e é o que mantém dedupe_weekend_reports e o resumo semanal
        # funcionando sem saber nada sobre usuários. Só existe em memória —
        # não chega a tabela nenhuma.
        "should_alert": any(u["should_alert"] for u in per_user) or degraded_alert is not None,
        # False aqui, True no ramo suppress_alert acima — main.py usa isso pra
        # nunca deixar um report suprimido (radar, regime 'metadata') vencer um
        # report alertável de verdade no dedupe da mesma perna no mesmo run.
        "alert_suppressed": False,
    }


def process_weekend_leg(leg: dict, system_settings: dict, settings_by_user: dict[str, dict],
                        month_cache: dict) -> dict:
    """Filtra localmente as entradas já buscadas pra essa perna (1 ou 2 datas
    candidatas × 2 aeroportos) e delega a gravação/avaliação pra
    evaluate_and_record_leg_price (fonte 'cache')."""
    leg_id = leg["id"]
    direction = leg["direction"]
    label = f"perna {direction} {leg['outbound_date']}"

    found = []  # (airport, variant, date, entry)
    for airport in AIRPORTS:
        for month in relevant_months(leg):
            entries = month_cache.get((month, airport, direction))
            if not entries:
                continue
            for variant, target_date in date_candidates(leg):
                if target_date[:7] != month:
                    continue
                best = match_leg_entries(entries, target_date)
                if best is not None:
                    found.append((airport, variant, target_date, best))

    if not found:
        print(f"[{label}] sem dado ainda (nenhum match exato) — estado normal, não é erro")
        insert_weekend_leg_run_log(leg_id, "no_data")
        return {"leg": leg, "status": "no_data"}

    airport, variant, _matched_date, best = min(found, key=lambda f: float(f[3]["price"]))
    price = float(best["price"])
    transfers = best.get("transfers")

    return evaluate_and_record_leg_price(
        leg, system_settings, settings_by_user, price, airport, variant, transfers, "cache"
    )


def process_all_weekend_legs(system_settings: dict, settings_by_user: dict[str, dict]) -> list[dict]:
    """Varre todas as pernas ativas, agrupando as buscas por (mês, aeroporto,
    direção) — cada chave é buscada 1 vez e reusada pelas pernas que a
    compartilham. Falha ao buscar uma chave só afeta as pernas que dependem
    dela; falha ao processar uma perna não derruba as outras."""
    legs = get_active_legs()
    if not legs:
        return []

    # O conjunto de chaves é derivado só de (mês, aeroporto, direção) — NUNCA
    # de usuário. É a garantia de que a Travelpayouts não multiplica com o
    # número de usuários (Fatia D4): o fan-out acontece na decisão, não na
    # consulta.
    fetch_keys = set()
    for leg in legs:
        for month in relevant_months(leg):
            for airport in AIRPORTS:
                fetch_keys.add((month, airport, leg["direction"]))

    month_cache: dict[tuple[str, str, str], list[dict] | None] = {}
    for i, key in enumerate(sorted(fetch_keys)):
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        month, airport, direction = key
        try:
            entries = fetch_leg_month_entries(month, airport, direction)
            month_cache[key] = entries
            print(f"[pernas {direction} {airport} {month}] {len(entries)} entradas")
        except Exception:
            print(f"[pernas {direction} {airport} {month}] ERRO ao buscar:\n{traceback.format_exc()}")
            month_cache[key] = None

    reports = []
    for leg in legs:
        label = f"perna {leg['direction']} {leg['outbound_date']}"
        needed_keys = [(month, airport, leg["direction"]) for month in relevant_months(leg) for airport in AIRPORTS]
        try:
            if all(month_cache.get(k) is None for k in needed_keys):
                raise RuntimeError("todas as buscas necessárias falharam")
            reports.append(process_weekend_leg(leg, system_settings, settings_by_user, month_cache))
        except Exception:
            detail = traceback.format_exc()[-500:]
            print(f"[{label}] ERRO:\n{detail}")
            try:
                insert_weekend_leg_run_log(leg["id"], "error", detail=detail)
            except Exception:
                print(f"[{label}] falha também ao gravar weekend_leg_run_log")
            reports.append({"leg": leg, "status": "error"})
    return reports
