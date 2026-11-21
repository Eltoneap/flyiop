"""20/11/2026 — "quem ainda quer esta perna?": perna dispensada (status
'dismissed') e usuário fora do monitoramento (settings.monitoring_active =
false). Cenário simulado de ponta a ponta no robô, sem banco nem fli:

- Elton: comprou a volta do fim de semana 1 e dispensou a ida ("Não preciso").
- Gustavo: monitoring_active = false (login preservado, fora de tudo).
- "Sem linha": usuário cuja linha da view não traz monitoring_active (o que o
  robô veria antes da migração / sem valor) — conta como ativo.

Regra-alvo: fila do fli, fan-out de alerta de preço e resumo de segunda só
consideram pernas NÃO compradas e NÃO dispensadas por usuário ATIVO.

Uso: python -m unittest tests/test_quem_quer_a_perna.py -v (a partir da raiz)
"""
import os
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import live_check  # noqa: E402
import supabase_client  # noqa: E402
import weekends  # noqa: E402

ELTON = "user-elton"
GUSTAVO = "user-gustavo"
SEM_LINHA = "user-sem-linha"
CUTOFF = "2000-01-01"  # janela de compra aberta para tudo nos testes


def days_from_today(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


WEEKEND_1 = {"id": "w1", "outbound_date": days_from_today(10),
             "return_sunday": days_from_today(12), "return_monday": days_from_today(13)}
WEEKEND_2 = {"id": "w2", "outbound_date": days_from_today(17),
             "return_sunday": days_from_today(19), "return_monday": days_from_today(20)}
LEGS = [
    {"id": "w1-ida", "weekend_id": "w1", "direction": "outbound", "current_price": None,
     "lowest_seen": None, "last_live_check_at": None},
    {"id": "w1-volta", "weekend_id": "w1", "direction": "return", "current_price": None,
     "lowest_seen": None, "last_live_check_at": None},
    {"id": "w2-ida", "weekend_id": "w2", "direction": "outbound", "current_price": None,
     "lowest_seen": None, "last_live_check_at": None},
    {"id": "w2-volta", "weekend_id": "w2", "direction": "return", "current_price": None,
     "lowest_seen": None, "last_live_check_at": None},
]
OUTBOUND = {"w1": WEEKEND_1["outbound_date"], "w2": WEEKEND_2["outbound_date"]}


def view_row(leg_id, user_id, status="monitoring", active=True, ceiling=300):
    row = {"leg_id": leg_id, "user_id": user_id, "price_ceiling": ceiling,
           "status": status, "outbound_date": OUTBOUND[leg_id.split("-")[0]]}
    if active is not None:  # None = coluna ausente na linha
        row["monitoring_active"] = active
    return row


def elton_rows():
    return [
        view_row("w1-ida", ELTON, status="dismissed"),
        view_row("w1-volta", ELTON, status="purchased"),
        view_row("w2-ida", ELTON),
        view_row("w2-volta", ELTON),
    ]


def gustavo_rows(active=False):
    return [view_row(leg["id"], GUSTAVO, active=active, ceiling=250) for leg in LEGS]


def active_legs(state):
    with patch("weekends.get_monitoring_weekends", return_value=[WEEKEND_1, WEEKEND_2]), \
         patch("weekends.get_all_weekend_legs", return_value=LEGS), \
         patch("weekends.get_effective_leg_state", return_value=state):
        return weekends.get_active_legs()


SYSTEM = {"fast_flights_enabled": True, "fast_flights_daily_batch_size": 20,
          "suspicious_below_avg_pct": 50, "weekend_buying_cutoff_date": CUTOFF}


class ScenarioQueueTest(unittest.TestCase):
    """Fila do robô (varredura cache, radar de precisão e lote fli nascem de
    get_active_legs)."""

    def test_elton_purchase_and_dismiss_with_gustavo_inactive_leave_only_wanted_legs(self):
        legs = active_legs(elton_rows() + gustavo_rows(active=False))
        self.assertEqual([leg["id"] for leg in legs], ["w2-ida", "w2-volta"])
        for leg in legs:
            self.assertEqual(leg["ceilings_by_user"], {ELTON: 300})

    def test_fli_batch_does_not_query_unwanted_legs(self):
        legs = active_legs(elton_rows() + gustavo_rows(active=False))
        with patch("live_check.get_active_legs", return_value=legs):
            batch = live_check.select_batch(SYSTEM)
        self.assertEqual(sorted(leg["id"] for leg in batch), ["w2-ida", "w2-volta"])

    def test_active_gustavo_keeps_legs_elton_no_longer_wants(self):
        # Comportamento de hoje preservado: o Gustavo ativo ainda quer w1, então
        # w1 segue na fila — só com o teto DELE (o Elton não recebe alerta).
        legs = active_legs(elton_rows() + gustavo_rows(active=True))
        by_id = {leg["id"]: leg for leg in legs}
        self.assertEqual(sorted(by_id), ["w1-ida", "w1-volta", "w2-ida", "w2-volta"])
        self.assertEqual(by_id["w1-ida"]["ceilings_by_user"], {GUSTAVO: 250})
        self.assertEqual(by_id["w1-volta"]["ceilings_by_user"], {GUSTAVO: 250})
        self.assertEqual(by_id["w2-ida"]["ceilings_by_user"], {ELTON: 300, GUSTAVO: 250})

    def test_user_without_monitoring_active_value_counts_as_active(self):
        rows = [view_row(leg["id"], SEM_LINHA, active=None) for leg in LEGS]
        legs = active_legs(rows)
        self.assertEqual(len(legs), 4)
        self.assertEqual(legs[0]["ceilings_by_user"], {SEM_LINHA: 300})

    def test_null_monitoring_active_counts_as_active(self):
        rows = [{**view_row(leg["id"], SEM_LINHA), "monitoring_active": None} for leg in LEGS]
        self.assertEqual(len(active_legs(rows)), 4)

    def test_everyone_inactive_empties_queue_without_degraded_mode(self):
        # Ninguém quer nada é estado normal (fila vazia), não erro de dado:
        # o modo degradado é só para view vazia (nenhum usuário em settings).
        legs = active_legs(gustavo_rows(active=False))
        self.assertEqual(legs, [])
        self.assertFalse(weekends.LEG_LOAD_DIAGNOSTICS["degraded_no_settings"])

    def test_dismissed_is_reversible(self):
        rows = elton_rows()
        rows[0] = view_row("w1-ida", ELTON, status="monitoring")  # "Voltar a monitorar"
        legs = active_legs(rows)
        self.assertIn("w1-ida", [leg["id"] for leg in legs])


class ScenarioAlertFanOutTest(unittest.TestCase):
    """Fan-out de alerta de preço: só quem ainda quer a perna é avaliado."""

    def evaluate(self, leg, price):
        with patch("weekends.insert_weekend_leg_price"), \
             patch("weekends.update_weekend_leg"), \
             patch("weekends.insert_weekend_leg_run_log"), \
             patch("weekends.get_weekend_leg_price_history", return_value=[]), \
             patch("weekends.get_last_weekend_leg_alert", return_value=None):
            return weekends.evaluate_and_record_leg_price(
                leg, SYSTEM, {}, price, "GIG", None, 0, "live",
            )

    def test_price_below_every_ceiling_alerts_only_active_users_who_want_the_leg(self):
        legs = {leg["id"]: leg for leg in active_legs(elton_rows() + gustavo_rows(active=False))}
        report = self.evaluate(legs["w2-ida"], 100.0)
        alerted = [u["user_id"] for u in report["per_user"] if u["should_alert"]]
        self.assertEqual(alerted, [ELTON])

    def test_leg_wanted_only_by_inactive_or_dismissing_users_never_reaches_evaluation(self):
        legs = {leg["id"]: leg for leg in active_legs(elton_rows() + gustavo_rows(active=False))}
        self.assertNotIn("w1-ida", legs)   # dispensada pelo Elton, Gustavo inativo
        self.assertNotIn("w1-volta", legs)  # comprada pelo Elton, Gustavo inativo


class ScenarioWeeklySummaryTest(unittest.TestCase):
    """Resumo de segunda (get_weekend_leg_counts)."""

    def counts(self, rows):
        with patch("supabase_client.get_effective_leg_state", return_value=rows):
            return supabase_client.get_weekend_leg_counts(CUTOFF)

    def test_dismissed_leaves_denominator_and_inactive_user_leaves_summary(self):
        counts = self.counts(elton_rows() + gustavo_rows(active=False))
        self.assertEqual(counts, {ELTON: (3, 1)})

    def test_active_gustavo_still_counted_with_full_denominator(self):
        counts = self.counts(elton_rows() + gustavo_rows(active=True))
        self.assertEqual(counts, {GUSTAVO: (4, 0), ELTON: (3, 1)})

    def test_user_without_monitoring_active_value_is_in_summary(self):
        rows = [view_row(leg["id"], SEM_LINHA, active=None) for leg in LEGS]
        self.assertEqual(self.counts(rows), {SEM_LINHA: (4, 0)})


class FetchSelectsMonitoringActiveTest(unittest.TestCase):
    def test_view_query_asks_for_monitoring_active(self):
        with patch("supabase_client.requests.get") as mock_get, \
             patch("supabase_client._url", return_value="http://teste/weekend_leg_effective"), \
             patch("supabase_client._headers", return_value={}):
            mock_get.return_value.json.return_value = []
            supabase_client.get_effective_leg_state()
        select = mock_get.call_args.kwargs["params"]["select"]
        self.assertIn("monitoring_active", select.split(","))


if __name__ == "__main__":
    unittest.main()
