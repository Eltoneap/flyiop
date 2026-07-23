"""Teste local do módulo de pernas de fim de semana (weekends.py) — revisão
de 23/07/2026 (ida/volta desacopladas, busca one-way GIG+SDU por mês).

Roda 100% com mocks — nenhuma chamada à API da Travelpayouts nem ao Supabase.
Uso: python -m unittest tests/test_weekends.py -v  (a partir da raiz do repo)
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import weekends  # noqa: E402


def iso_days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


WEEKEND = {"outbound_date": "2026-09-04", "return_sunday": "2026-09-06", "return_monday": "2026-09-07"}

OUTBOUND_LEG = {
    "id": "leg-out-1", "weekend_id": "wknd-1", "direction": "outbound",
    "price_ceiling": 200, "lowest_seen": None, **WEEKEND,
}

RETURN_LEG = {
    "id": "leg-ret-1", "weekend_id": "wknd-1", "direction": "return",
    "price_ceiling": 200, "lowest_seen": None, **WEEKEND,
}

SETTINGS = {
    "notification_mode": "alert_only",
    "weekend_opportunity_pct": 15,
    "suspicious_below_avg_pct": 50,
    "realert_drop_pct": 5,
    "realert_days": 3,
}


def entry(price: float, departure_date: str, transfers=0) -> dict:
    return {"price": price, "departure_at": f"{departure_date}T07:00:00Z", "transfers": transfers}


class RelevantMonthsAndCandidatesTest(unittest.TestCase):
    def test_outbound_single_month(self):
        self.assertEqual(weekends.relevant_months(OUTBOUND_LEG), ["2026-09"])

    def test_return_same_month(self):
        self.assertEqual(weekends.relevant_months(RETURN_LEG), ["2026-09"])

    def test_return_spanning_month_boundary(self):
        leg = {**RETURN_LEG, "outbound_date": "2026-07-30", "return_sunday": "2026-08-01", "return_monday": "2026-08-02"}
        self.assertEqual(weekends.relevant_months(leg), ["2026-08"])  # as duas datas caem em agosto

    def test_return_spanning_two_different_months(self):
        leg = {**RETURN_LEG, "return_sunday": "2026-08-30", "return_monday": "2026-09-01"}
        self.assertEqual(weekends.relevant_months(leg), ["2026-08", "2026-09"])

    def test_outbound_candidates_have_no_variant(self):
        self.assertEqual(weekends.date_candidates(OUTBOUND_LEG), [(None, "2026-09-04")])

    def test_return_candidates_are_sunday_and_monday(self):
        self.assertEqual(
            weekends.date_candidates(RETURN_LEG),
            [("sunday", "2026-09-06"), ("monday", "2026-09-07")],
        )


class MatchLegEntriesTest(unittest.TestCase):
    def test_exact_match_found(self):
        result = weekends.match_leg_entries([entry(300.0, "2026-09-04")], "2026-09-04")
        self.assertEqual(result["price"], 300.0)

    def test_one_day_off_is_not_a_match(self):
        result = weekends.match_leg_entries([entry(300.0, "2026-09-05")], "2026-09-04")
        self.assertIsNone(result)

    def test_picks_cheapest_among_multiple_matches(self):
        entries = [entry(450.0, "2026-09-04"), entry(300.0, "2026-09-04")]
        result = weekends.match_leg_entries(entries, "2026-09-04")
        self.assertEqual(result["price"], 300.0)


class GetActiveLegsTest(unittest.TestCase):
    def test_merges_weekend_dates_onto_legs(self):
        weekend_row = {"id": "wknd-1", "outbound_date": "2026-09-04", "return_sunday": "2026-09-06", "return_monday": "2026-09-07"}
        leg_row = {"id": "leg-out-1", "weekend_id": "wknd-1", "direction": "outbound", "price_ceiling": 200}
        with patch("weekends.get_monitoring_weekends", return_value=[weekend_row]), \
             patch("weekends.get_monitoring_legs", return_value=[leg_row]):
            legs = weekends.get_active_legs()
        self.assertEqual(len(legs), 1)
        self.assertEqual(legs[0]["outbound_date"], "2026-09-04")
        self.assertEqual(legs[0]["return_sunday"], "2026-09-06")

    def test_leg_of_expired_weekend_is_excluded(self):
        leg_row = {"id": "leg-out-1", "weekend_id": "wknd-passado", "direction": "outbound", "price_ceiling": 200}
        with patch("weekends.get_monitoring_weekends", return_value=[]), \
             patch("weekends.get_monitoring_legs", return_value=[leg_row]):
            legs = weekends.get_active_legs()
        self.assertEqual(legs, [])


class ProcessWeekendLegTest(unittest.TestCase):
    def run_process(self, month_cache, history_prices=None, leg=None, settings=None, last_alert=None):
        history = [{"price": p, "checked_at": "2026-08-01T10:00:00Z"} for p in (history_prices or [])]
        with patch("weekends.insert_weekend_leg_price") as mock_insert, \
             patch("weekends.get_weekend_leg_price_history", return_value=history), \
             patch("weekends.get_last_weekend_leg_alert", return_value=last_alert), \
             patch("weekends.update_weekend_leg") as mock_update, \
             patch("weekends.insert_weekend_leg_run_log") as mock_run_log:
            report = weekends.process_weekend_leg(leg or OUTBOUND_LEG, settings or SETTINGS, month_cache)
        return report, mock_insert, mock_update, mock_run_log

    def test_outbound_cheapest_airport_wins(self):
        month_cache = {
            ("2026-09", "GIG", "outbound"): [entry(350.0, "2026-09-04")],
            ("2026-09", "SDU", "outbound"): [entry(280.0, "2026-09-04")],
        }
        report, mock_insert, _, mock_run_log = self.run_process(month_cache)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["price"], 280.0)
        self.assertEqual(report["airport"], "SDU")
        self.assertIsNone(report["variant"])
        mock_insert.assert_called_once_with("leg-out-1", 280.0, "SDU", None, "cache", 0)
        mock_run_log.assert_called_once_with("leg-out-1", "ok", price=280.0, source="cache")

    def test_return_cheapest_variant_and_airport_wins(self):
        month_cache = {
            ("2026-09", "GIG", "return"): [entry(200.0, "2026-09-06"), entry(500.0, "2026-09-07")],
            ("2026-09", "SDU", "return"): [entry(180.0, "2026-09-07")],
        }
        report, _, _, _ = self.run_process(month_cache, leg=RETURN_LEG)
        self.assertEqual(report["price"], 180.0)
        self.assertEqual(report["airport"], "SDU")
        self.assertEqual(report["variant"], "monday")

    def test_no_match_in_any_key_is_no_data(self):
        month_cache = {
            ("2026-09", "GIG", "outbound"): [entry(350.0, "2026-09-11")],  # outro dia
            ("2026-09", "SDU", "outbound"): [],
        }
        report, mock_insert, mock_update, mock_run_log = self.run_process(month_cache)
        self.assertEqual(report["status"], "no_data")
        mock_insert.assert_not_called()
        mock_update.assert_not_called()
        mock_run_log.assert_called_once_with("leg-out-1", "no_data")

    def test_missing_cache_key_is_treated_as_no_data_not_crash(self):
        report, mock_insert, _, _ = self.run_process({})
        self.assertEqual(report["status"], "no_data")
        mock_insert.assert_not_called()

    def test_price_below_ceiling_is_ceiling_hit_and_alerts(self):
        month_cache = {("2026-09", "GIG", "outbound"): [entry(150.0, "2026-09-04")]}
        report, _, _, _ = self.run_process(month_cache, history_prices=[400.0, 420.0])
        self.assertTrue(report["is_ceiling_hit"])
        self.assertTrue(report["should_alert"])

    def test_suspicious_price_never_alerts_even_below_ceiling(self):
        month_cache = {("2026-09", "GIG", "outbound"): [entry(150.0, "2026-09-04")]}
        report, _, _, _ = self.run_process(
            month_cache, history_prices=[1000.0, 1010.0, 990.0, 1005.0, 995.0]
        )
        self.assertTrue(report["suspicious"])
        self.assertFalse(report["should_alert"])

    def test_cooldown_blocks_repeat_alert(self):
        month_cache = {("2026-09", "GIG", "outbound"): [entry(150.0, "2026-09-04")]}
        last_alert = {"price": 150.0, "sent_at": iso_days_ago(1)}
        report, _, _, _ = self.run_process(month_cache, history_prices=[400.0], last_alert=last_alert)
        self.assertFalse(report["should_alert"])

    def test_new_low_updates_lowest_seen(self):
        leg = {**OUTBOUND_LEG, "lowest_seen": 300.0}
        month_cache = {("2026-09", "GIG", "outbound"): [entry(200.0, "2026-09-04")]}
        _, _, mock_update, _ = self.run_process(month_cache, leg=leg)
        fields = mock_update.call_args[1]
        self.assertEqual(fields["lowest_seen"], 200.0)
        self.assertIn("lowest_seen_at", fields)

    def test_not_a_new_low_does_not_touch_lowest_seen(self):
        leg = {**OUTBOUND_LEG, "lowest_seen": 100.0}
        month_cache = {("2026-09", "GIG", "outbound"): [entry(200.0, "2026-09-04")]}
        _, _, mock_update, _ = self.run_process(month_cache, leg=leg)
        fields = mock_update.call_args[1]
        self.assertNotIn("lowest_seen", fields)


class ProcessAllWeekendLegsTest(unittest.TestCase):
    def test_shared_fetch_key_used_once_across_legs(self):
        """2 pernas outbound no mesmo mês -> a chave (mês, aeroporto, direção)
        é buscada 1 vez só, não 1 por perna."""
        leg2 = {**OUTBOUND_LEG, "id": "leg-out-2", "weekend_id": "wknd-2", "outbound_date": "2026-09-11"}

        with patch("weekends.get_active_legs", return_value=[OUTBOUND_LEG, leg2]), \
             patch("weekends.fetch_leg_month_entries", return_value=[entry(300.0, "2026-09-04")]) as mock_fetch, \
             patch("weekends.insert_weekend_leg_price"), \
             patch("weekends.get_weekend_leg_price_history", return_value=[]), \
             patch("weekends.get_last_weekend_leg_alert", return_value=None), \
             patch("weekends.update_weekend_leg"), \
             patch("weekends.insert_weekend_leg_run_log"), \
             patch("weekends.time.sleep", return_value=None):
            reports = weekends.process_all_weekend_legs(SETTINGS)

        # 1 mês x 2 aeroportos x 1 direção (as duas pernas outbound de set/2026
        # compartilham a mesma chave por aeroporto) -> 2 chamadas de fetch, não 4.
        self.assertEqual(mock_fetch.call_count, 2)
        self.assertEqual(len(reports), 2)

    def test_month_fetch_failure_only_affects_dependent_legs(self):
        def fake_fetch(month, airport, direction):
            if month == "2026-09":
                raise RuntimeError("falha simulada")
            return [entry(300.0, "2026-10-02")]

        other_leg = {**OUTBOUND_LEG, "id": "leg-out-2", "weekend_id": "wknd-2", "outbound_date": "2026-10-02"}

        with patch("weekends.get_active_legs", return_value=[OUTBOUND_LEG, other_leg]), \
             patch("weekends.fetch_leg_month_entries", side_effect=fake_fetch), \
             patch("weekends.insert_weekend_leg_price"), \
             patch("weekends.get_weekend_leg_price_history", return_value=[]), \
             patch("weekends.get_last_weekend_leg_alert", return_value=None), \
             patch("weekends.update_weekend_leg"), \
             patch("weekends.insert_weekend_leg_run_log"), \
             patch("weekends.time.sleep", return_value=None):
            reports = weekends.process_all_weekend_legs(SETTINGS)

        by_id = {r["leg"]["id"]: r for r in reports}
        self.assertEqual(by_id["leg-out-1"]["status"], "error")
        self.assertEqual(by_id["leg-out-2"]["status"], "ok")

    def test_individual_leg_failure_does_not_crash_others(self):
        leg2 = {**OUTBOUND_LEG, "id": "leg-out-2", "weekend_id": "wknd-2"}

        def fake_process(leg, settings, cache):
            if leg["id"] == "leg-out-2":
                raise RuntimeError("falha simulada")
            return {"leg": leg, "status": "ok", "price": 300.0}

        with patch("weekends.get_active_legs", return_value=[OUTBOUND_LEG, leg2]), \
             patch("weekends.fetch_leg_month_entries", return_value=[entry(300.0, "2026-09-04")]), \
             patch("weekends.process_weekend_leg", side_effect=fake_process), \
             patch("weekends.insert_weekend_leg_run_log") as mock_run_log, \
             patch("weekends.time.sleep", return_value=None):
            reports = weekends.process_all_weekend_legs(SETTINGS)

        self.assertEqual(reports[0]["status"], "ok")
        self.assertEqual(reports[1]["status"], "error")
        mock_run_log.assert_called_once()

    def test_no_legs_returns_empty_without_any_fetch(self):
        with patch("weekends.get_active_legs", return_value=[]), \
             patch("weekends.fetch_leg_month_entries") as mock_fetch:
            reports = weekends.process_all_weekend_legs(SETTINGS)
        self.assertEqual(reports, [])
        mock_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
