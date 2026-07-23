"""Teste local do módulo de alvos de fim de semana (weekends.py).

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


TARGET = {
    "id": "alvo-1",
    "outbound_date": "2026-09-04",
    "return_sunday": "2026-09-06",
    "return_monday": "2026-09-07",
    "price_ceiling": 400,
    "lowest_seen": None,
}


def other_target(target_id: str, outbound: str) -> dict:
    return {
        "id": target_id, "outbound_date": outbound,
        "return_sunday": outbound[:8] + str(int(outbound[8:]) + 2).zfill(2),
        "return_monday": outbound[:8] + str(int(outbound[8:]) + 3).zfill(2),
        "price_ceiling": 400, "lowest_seen": None,
    }


SETTINGS = {
    "notification_mode": "alert_only",
    "weekend_opportunity_pct": 15,
    "suspicious_below_avg_pct": 50,
    "realert_drop_pct": 5,
    "realert_days": 3,
}


def entry(price: float, departure_date: str, return_date: str,
         origin_airport="GIG", destination_airport="BSB", transfers=0) -> dict:
    return {
        "price": price, "departure_at": f"{departure_date}T07:00:00Z", "return_at": f"{return_date}T20:00:00Z",
        "origin_airport": origin_airport, "destination_airport": destination_airport, "transfers": transfers,
    }


class MatchVariantTest(unittest.TestCase):
    def test_exact_match_found(self):
        entries = [entry(450.0, "2026-09-04", "2026-09-06")]
        result = weekends.match_variant(entries, "2026-09-04", "2026-09-06")
        self.assertIsNotNone(result)
        self.assertEqual(result["price"], 450.0)

    def test_one_day_off_is_not_a_match(self):
        """Sem tolerância de ±1 dia — data exata ou nada, por decisão do usuário (23/07)."""
        entries = [entry(450.0, "2026-09-05", "2026-09-06")]  # ida 1 dia depois do pedido
        result = weekends.match_variant(entries, "2026-09-04", "2026-09-06")
        self.assertIsNone(result)

    def test_picks_cheapest_among_multiple_matches(self):
        entries = [entry(600.0, "2026-09-04", "2026-09-06"), entry(450.0, "2026-09-04", "2026-09-06")]
        result = weekends.match_variant(entries, "2026-09-04", "2026-09-06")
        self.assertEqual(result["price"], 450.0)


class ProcessWeekendTargetTest(unittest.TestCase):
    def run_process(self, month_entries, history_prices=None, target=None, settings=None, last_alert=None):
        history = [{"price": p, "checked_at": "2026-08-01T10:00:00Z"} for p in (history_prices or [])]
        with patch("weekends.insert_weekend_price") as mock_insert, \
             patch("weekends.get_weekend_price_history", return_value=history), \
             patch("weekends.get_last_weekend_alert", return_value=last_alert), \
             patch("weekends.update_weekend_target") as mock_update, \
             patch("weekends.insert_weekend_run_log") as mock_run_log:
            report = weekends.process_weekend_target(target or TARGET, settings or SETTINGS, month_entries)
        return report, mock_insert, mock_update, mock_run_log

    def test_cheaper_variant_wins_sunday(self):
        month_entries = [
            entry(450.0, "2026-09-04", "2026-09-06"),
            entry(500.0, "2026-09-04", "2026-09-07"),
        ]
        report, mock_insert, _, mock_run_log = self.run_process(month_entries)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["price"], 450.0)
        self.assertEqual(report["variant"], "sunday")
        mock_insert.assert_called_once_with("alvo-1", 450.0, "sunday", "GIG", "BSB", 0)
        mock_run_log.assert_called_once_with("alvo-1", "ok", price=450.0)

    def test_cheaper_variant_wins_monday(self):
        month_entries = [
            entry(500.0, "2026-09-04", "2026-09-06"),
            entry(380.0, "2026-09-04", "2026-09-07"),
        ]
        report, _, _, _ = self.run_process(month_entries)
        self.assertEqual(report["variant"], "monday")
        self.assertEqual(report["price"], 380.0)

    def test_no_exact_match_in_month_is_no_data_not_error(self):
        # entradas do mês existem, mas nenhuma bate a data exata do alvo
        month_entries = [entry(450.0, "2026-09-11", "2026-09-13")]
        report, mock_insert, mock_update, mock_run_log = self.run_process(month_entries)
        self.assertEqual(report["status"], "no_data")
        mock_insert.assert_not_called()
        mock_update.assert_not_called()
        mock_run_log.assert_called_once_with("alvo-1", "no_data")

    def test_empty_month_is_no_data(self):
        report, mock_insert, _, mock_run_log = self.run_process([])
        self.assertEqual(report["status"], "no_data")
        mock_insert.assert_not_called()
        mock_run_log.assert_called_once_with("alvo-1", "no_data")

    def test_price_below_ceiling_is_ceiling_hit_and_alerts(self):
        month_entries = [entry(350.0, "2026-09-04", "2026-09-06")]
        report, _, _, _ = self.run_process(month_entries, history_prices=[900.0, 950.0])
        self.assertTrue(report["is_ceiling_hit"])
        self.assertTrue(report["should_alert"])

    def test_opportunity_above_ceiling_still_alerts(self):
        month_entries = [entry(720.0, "2026-09-04", "2026-09-06")]
        report, _, _, _ = self.run_process(month_entries, history_prices=[900.0, 900.0, 900.0])
        self.assertFalse(report["is_ceiling_hit"])
        self.assertTrue(report["should_alert"])
        self.assertIn("abaixo da média", report["reason"])

    def test_price_above_ceiling_and_not_opportunity_does_not_alert(self):
        month_entries = [entry(890.0, "2026-09-04", "2026-09-06")]
        report, _, _, _ = self.run_process(month_entries, history_prices=[900.0, 900.0, 900.0])
        self.assertFalse(report["should_alert"])

    def test_suspicious_price_never_alerts_even_below_ceiling(self):
        month_entries = [entry(350.0, "2026-09-04", "2026-09-06")]
        report, _, _, _ = self.run_process(
            month_entries, history_prices=[1000.0, 1010.0, 990.0, 1005.0, 995.0]
        )
        self.assertTrue(report["suspicious"])
        self.assertFalse(report["should_alert"])

    def test_cooldown_blocks_repeat_alert(self):
        month_entries = [entry(350.0, "2026-09-04", "2026-09-06")]
        last_alert = {"price": 350.0, "sent_at": iso_days_ago(1)}
        report, _, _, _ = self.run_process(month_entries, history_prices=[900.0], last_alert=last_alert)
        self.assertFalse(report["should_alert"])

    def test_new_low_updates_lowest_seen(self):
        target = {**TARGET, "lowest_seen": 500.0}
        month_entries = [entry(350.0, "2026-09-04", "2026-09-06")]
        _, _, mock_update, _ = self.run_process(month_entries, target=target)
        fields = mock_update.call_args[1]
        self.assertEqual(fields["lowest_seen"], 350.0)
        self.assertIn("lowest_seen_at", fields)

    def test_not_a_new_low_does_not_touch_lowest_seen(self):
        target = {**TARGET, "lowest_seen": 300.0}
        month_entries = [entry(350.0, "2026-09-04", "2026-09-06")]
        _, _, mock_update, _ = self.run_process(month_entries, target=target)
        fields = mock_update.call_args[1]
        self.assertNotIn("lowest_seen", fields)


class ProcessAllWeekendTargetsTest(unittest.TestCase):
    def test_one_month_fetch_covers_all_targets_in_that_month(self):
        """2 alvos no mesmo mês -> 1 única chamada de busca, não 2."""
        targets = [TARGET, other_target("alvo-2", "2026-09-11")]
        month_entries = [entry(450.0, "2026-09-04", "2026-09-06")]

        with patch("weekends.get_weekend_targets", return_value=targets), \
             patch("weekends.fetch_month_entries", return_value=month_entries) as mock_fetch, \
             patch("weekends.insert_weekend_price"), \
             patch("weekends.get_weekend_price_history", return_value=[]), \
             patch("weekends.get_last_weekend_alert", return_value=None), \
             patch("weekends.update_weekend_target"), \
             patch("weekends.insert_weekend_run_log"), \
             patch("weekends.time.sleep", return_value=None):
            reports = weekends.process_all_weekend_targets(SETTINGS)

        mock_fetch.assert_called_once_with("2026-09")
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[0]["status"], "ok")  # alvo-1 bate a data exata
        self.assertEqual(reports[1]["status"], "no_data")  # alvo-2 não bate

    def test_different_months_trigger_separate_fetches(self):
        targets = [TARGET, other_target("alvo-2", "2026-10-02")]

        with patch("weekends.get_weekend_targets", return_value=targets), \
             patch("weekends.fetch_month_entries", return_value=[]) as mock_fetch, \
             patch("weekends.insert_weekend_run_log"), \
             patch("weekends.time.sleep", return_value=None):
            weekends.process_all_weekend_targets(SETTINGS)

        self.assertEqual(mock_fetch.call_count, 2)
        called_months = {c.args[0] for c in mock_fetch.call_args_list}
        self.assertEqual(called_months, {"2026-09", "2026-10"})

    def test_month_fetch_failure_only_affects_that_months_targets(self):
        targets = [TARGET, other_target("alvo-2", "2026-10-02")]

        def fake_fetch(month):
            if month == "2026-09":
                raise RuntimeError("falha simulada na busca do mês")
            return [entry(400.0, "2026-10-02", "2026-10-04")]

        with patch("weekends.get_weekend_targets", return_value=targets), \
             patch("weekends.fetch_month_entries", side_effect=fake_fetch), \
             patch("weekends.insert_weekend_price"), \
             patch("weekends.get_weekend_price_history", return_value=[]), \
             patch("weekends.get_last_weekend_alert", return_value=None), \
             patch("weekends.update_weekend_target"), \
             patch("weekends.insert_weekend_run_log"), \
             patch("weekends.time.sleep", return_value=None):
            reports = weekends.process_all_weekend_targets(SETTINGS)

        by_id = {r["target"]["id"]: r for r in reports}
        self.assertEqual(by_id["alvo-1"]["status"], "error")
        self.assertEqual(by_id["alvo-2"]["status"], "ok")

    def test_individual_target_failure_does_not_crash_others(self):
        targets = [TARGET, other_target("alvo-2", "2026-09-11")]
        month_entries = [entry(450.0, "2026-09-04", "2026-09-06"), entry(400.0, "2026-09-11", "2026-09-13")]

        def fake_process(target, settings, entries):
            if target["id"] == "alvo-2":
                raise RuntimeError("falha simulada")
            return {"target": target, "status": "ok", "price": 450.0}

        with patch("weekends.get_weekend_targets", return_value=targets), \
             patch("weekends.fetch_month_entries", return_value=month_entries), \
             patch("weekends.process_weekend_target", side_effect=fake_process), \
             patch("weekends.insert_weekend_run_log") as mock_run_log, \
             patch("weekends.time.sleep", return_value=None):
            reports = weekends.process_all_weekend_targets(SETTINGS)

        self.assertEqual(reports[0]["status"], "ok")
        self.assertEqual(reports[1]["status"], "error")
        mock_run_log.assert_called_once()  # só o erro grava aqui; o "ok" é mockado dentro do fake_process

    def test_no_targets_returns_empty_without_any_fetch(self):
        with patch("weekends.get_weekend_targets", return_value=[]), \
             patch("weekends.fetch_month_entries") as mock_fetch:
            reports = weekends.process_all_weekend_targets(SETTINGS)
        self.assertEqual(reports, [])
        mock_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
