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

SETTINGS = {
    "notification_mode": "alert_only",
    "weekend_opportunity_pct": 15,
    "suspicious_below_avg_pct": 50,
    "realert_drop_pct": 5,
    "realert_days": 3,
}


def entry(price: float, return_at: str, origin_airport="GIG", destination_airport="BSB", transfers=0) -> dict:
    return {
        "price": price, "departure_at": "2026-09-04T07:00:00Z", "return_at": return_at,
        "origin_airport": origin_airport, "destination_airport": destination_airport, "transfers": transfers,
    }


class ProcessWeekendTargetTest(unittest.TestCase):
    def run_process(self, v3_side_effect, history_prices=None, target=None, settings=None, last_alert=None):
        history = [{"price": p, "checked_at": "2026-08-01T10:00:00Z"} for p in (history_prices or [])]
        with patch("weekends.get_prices_for_dates", side_effect=v3_side_effect), \
             patch("weekends.insert_weekend_price") as mock_insert, \
             patch("weekends.get_weekend_price_history", return_value=history), \
             patch("weekends.get_last_weekend_alert", return_value=last_alert), \
             patch("weekends.update_weekend_target") as mock_update, \
             patch("weekends.time.sleep", return_value=None):
            report = weekends.process_weekend_target(target or TARGET, settings or SETTINGS)
        return report, mock_insert, mock_update

    def test_cheaper_variant_wins_sunday(self):
        report, mock_insert, _ = self.run_process([
            [entry(450.0, "2026-09-06T20:00:00Z")],
            [entry(500.0, "2026-09-07T06:00:00Z")],
        ])
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["price"], 450.0)
        self.assertEqual(report["variant"], "sunday")
        mock_insert.assert_called_once_with("alvo-1", 450.0, "sunday", "GIG", "BSB", 0)

    def test_cheaper_variant_wins_monday(self):
        report, _, _ = self.run_process([
            [entry(500.0, "2026-09-06T20:00:00Z")],
            [entry(380.0, "2026-09-07T06:00:00Z")],
        ])
        self.assertEqual(report["variant"], "monday")
        self.assertEqual(report["price"], 380.0)

    def test_no_matching_return_date_is_no_data(self):
        # entradas existem mas nenhuma bate a data de volta exata pedida
        report, mock_insert, _ = self.run_process([
            [entry(450.0, "2026-09-10T20:00:00Z")],
            [],
        ])
        self.assertEqual(report["status"], "no_data")
        mock_insert.assert_not_called()

    def test_price_below_ceiling_is_ceiling_hit_and_alerts(self):
        report, _, _ = self.run_process(
            [[entry(350.0, "2026-09-06T20:00:00Z")], []],
            history_prices=[900.0, 950.0],
        )
        self.assertTrue(report["is_ceiling_hit"])
        self.assertTrue(report["should_alert"])

    def test_opportunity_above_ceiling_still_alerts(self):
        # acima do teto (450 > 400), mas 20% abaixo da média 900 -> oportunidade
        report, _, _ = self.run_process(
            [[entry(720.0, "2026-09-06T20:00:00Z")], []],
            history_prices=[900.0, 900.0, 900.0],
        )
        self.assertFalse(report["is_ceiling_hit"])
        self.assertTrue(report["should_alert"])
        self.assertIn("abaixo da média", report["reason"])

    def test_price_above_ceiling_and_not_opportunity_does_not_alert(self):
        report, _, _ = self.run_process(
            [[entry(890.0, "2026-09-06T20:00:00Z")], []],
            history_prices=[900.0, 900.0, 900.0],
        )
        self.assertFalse(report["should_alert"])

    def test_suspicious_price_never_alerts_even_below_ceiling(self):
        # 350 é <= teto (400), mas também >60% abaixo da média de 5 registros -> suspeito
        report, _, _ = self.run_process(
            [[entry(350.0, "2026-09-06T20:00:00Z")], []],
            history_prices=[1000.0, 1010.0, 990.0, 1005.0, 995.0],
        )
        self.assertTrue(report["suspicious"])
        self.assertFalse(report["should_alert"])

    def test_cooldown_blocks_repeat_alert(self):
        last_alert = {"price": 350.0, "sent_at": iso_days_ago(1)}
        report, _, _ = self.run_process(
            [[entry(350.0, "2026-09-06T20:00:00Z")], []],
            history_prices=[900.0],
            last_alert=last_alert,
        )
        self.assertFalse(report["should_alert"])  # mesmo preço, recente -> cooldown ativo

    def test_new_low_updates_lowest_seen(self):
        target = {**TARGET, "lowest_seen": 500.0}
        _, _, mock_update = self.run_process(
            [[entry(350.0, "2026-09-06T20:00:00Z")], []],
            target=target,
        )
        fields = mock_update.call_args[1]
        self.assertEqual(fields["lowest_seen"], 350.0)
        self.assertIn("lowest_seen_at", fields)

    def test_not_a_new_low_does_not_touch_lowest_seen(self):
        target = {**TARGET, "lowest_seen": 300.0}
        _, _, mock_update = self.run_process(
            [[entry(350.0, "2026-09-06T20:00:00Z")], []],
            target=target,
        )
        fields = mock_update.call_args[1]
        self.assertNotIn("lowest_seen", fields)


class ProcessAllWeekendTargetsTest(unittest.TestCase):
    def test_one_failing_target_does_not_crash_the_others(self):
        targets = [{"id": "ok-1", "outbound_date": "2026-09-04"}, {"id": "boom", "outbound_date": "2026-09-11"}]

        def fake_process(target, settings):
            if target["id"] == "boom":
                raise RuntimeError("falha simulada")
            return {"target": target, "status": "ok", "price": 400.0}

        with patch("weekends.get_weekend_targets", return_value=targets), \
             patch("weekends.process_weekend_target", side_effect=fake_process):
            reports = weekends.process_all_weekend_targets(SETTINGS)

        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[0]["status"], "ok")
        self.assertEqual(reports[1]["status"], "error")


if __name__ == "__main__":
    unittest.main()
