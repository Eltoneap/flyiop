"""Teste local da Etapa 2 (PLAN-FASE-A.md): portão de frescor nos alertas.

Roda 100% com mocks — nenhuma chamada à API da Travelpayouts nem ao Supabase.
Uso: python -m unittest tests/test_etapa2_frescor.py -v  (a partir da raiz)
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main  # noqa: E402
from telegram_notifier import build_alert_message, hours_since_found  # noqa: E402


def iso_hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


class HoursSinceFoundTest(unittest.TestCase):
    def test_recent_timestamp(self):
        age = hours_since_found(iso_hours_ago(2))
        self.assertAlmostEqual(age, 2, delta=0.1)

    def test_naive_timestamp_treated_as_utc(self):
        naive = (datetime.now(timezone.utc) - timedelta(hours=5)).replace(tzinfo=None).isoformat()
        self.assertAlmostEqual(hours_since_found(naive), 5, delta=0.1)

    def test_missing_and_invalid(self):
        self.assertIsNone(hours_since_found(None))
        self.assertIsNone(hours_since_found(""))
        self.assertIsNone(hours_since_found("não-é-data"))


class StalenessTest(unittest.TestCase):
    def test_fresh(self):
        is_stale, age = main.staleness(iso_hours_ago(2), freshness_hours_limit=24)
        self.assertFalse(is_stale)
        self.assertAlmostEqual(age, 2, delta=0.1)

    def test_old(self):
        is_stale, age = main.staleness(iso_hours_ago(30), freshness_hours_limit=24)
        self.assertTrue(is_stale)
        self.assertAlmostEqual(age, 30, delta=0.1)

    def test_missing_found_at_is_stale_never_fresh(self):
        is_stale, age = main.staleness(None, freshness_hours_limit=24)
        self.assertTrue(is_stale)
        self.assertIsNone(age)


class ShouldSuppressAlertTest(unittest.TestCase):
    def test_stale_with_suppress_policy(self):
        settings = {"stale_alert_policy": "suppress", "notification_mode": "alert_only"}
        self.assertTrue(main.should_suppress_alert(True, settings))

    def test_stale_with_warn_policy_sends(self):
        settings = {"stale_alert_policy": "warn", "notification_mode": "alert_only"}
        self.assertFalse(main.should_suppress_alert(True, settings))

    def test_fresh_never_suppressed(self):
        settings = {"stale_alert_policy": "suppress", "notification_mode": "alert_only"}
        self.assertFalse(main.should_suppress_alert(False, settings))

    def test_daily_summary_never_suppressed(self):
        settings = {"stale_alert_policy": "suppress", "notification_mode": "daily_summary"}
        self.assertFalse(main.should_suppress_alert(True, settings))


class AlertMessageTest(unittest.TestCase):
    BASE_REPORT = {
        "origin": "BSB",
        "destination": "GIG",
        "currency": "BRL",
        "price": 520.0,
        "depart_date": "2026-11-27",
        "return_date": "2026-11-30",
        "stops": 1,
        "days_ahead": 132,
        "target_price": 600.0,
        "avg_30d": 700.0,
        "reason": "abaixo da meta fixa (R$ 600.0)",
    }

    def test_stale_alert_opens_with_strong_warning(self):
        report = {**self.BASE_REPORT, "is_stale": True, "age_hours": 30.0}
        message = build_alert_message(report)
        self.assertTrue(message.startswith("⚠️ <b>Dado antigo (visto há 30h)</b>"))
        self.assertIn("🔔 <b>Alerta de preço</b>", message)

    def test_unknown_age_warning(self):
        report = {**self.BASE_REPORT, "is_stale": True, "age_hours": None}
        message = build_alert_message(report)
        self.assertIn("Dado antigo (idade desconhecida)", message)

    def test_fresh_alert_has_no_warning(self):
        report = {**self.BASE_REPORT, "is_stale": False, "age_hours": 2.0}
        message = build_alert_message(report)
        self.assertTrue(message.startswith("🔔 <b>Alerta de preço</b>"))
        self.assertNotIn("Dado antigo", message)


class ProcessRouteIntegrationTest(unittest.TestCase):
    """process_route com tudo mockado: decisão de envio e detail do run_log."""

    ROUTE = {
        "id": "rota-1",
        "user_id": "user-1",
        "origin": "BSB",
        "destination": "GIG",
        "currency": "BRL",
        "target_price": 600,
        "target_percent_below_avg": None,
        "trip_duration_weeks": None,
    }

    def run_process_route(self, found_at: str | None, settings_extra: dict) -> tuple[dict, list]:
        settings = {"window_3d_pct": 10, "window_7d_pct": 15, "notification_mode": "alert_only",
                    "freshness_hours": 24, **settings_extra}
        v2_entry = {
            "value": 520.0, "depart_date": "2026-11-27", "return_date": "2026-11-30",
            "number_of_changes": 1, "found_at": found_at,
        }
        run_log_calls: list = []
        with patch("main.get_month_matrix", side_effect=[[v2_entry], [], [], [], [], []]), \
             patch("main.insert_price"), \
             patch("main.insert_run_log", side_effect=lambda *a, **k: run_log_calls.append((a, k))), \
             patch("main.get_price_history", return_value=[]), \
             patch("main.safe_v3_comparison", return_value="v3: 520.00 | v2: 520.00"), \
             patch("main.time.sleep", return_value=None):
            report = main.process_route(self.ROUTE, settings)
        return report, run_log_calls

    def test_stale_plus_suppress_holds_alert_and_logs_it(self):
        report, run_log_calls = self.run_process_route(
            iso_hours_ago(30), {"stale_alert_policy": "suppress"}
        )
        self.assertTrue(report["is_stale"])
        self.assertFalse(report["should_alert"])
        detail = run_log_calls[0][1]["detail"]
        self.assertIn("frescor: 30h (velho)", detail)
        self.assertIn("alerta segurado", detail)

    def test_stale_plus_warn_still_alerts(self):
        report, run_log_calls = self.run_process_route(
            iso_hours_ago(30), {"stale_alert_policy": "warn"}
        )
        self.assertTrue(report["is_stale"])
        self.assertTrue(report["should_alert"])
        self.assertNotIn("alerta segurado", run_log_calls[0][1]["detail"])

    def test_fresh_price_alerts_normally(self):
        report, run_log_calls = self.run_process_route(
            iso_hours_ago(2), {"stale_alert_policy": "suppress"}
        )
        self.assertFalse(report["is_stale"])
        self.assertTrue(report["should_alert"])
        self.assertIn("frescor: 2h", run_log_calls[0][1]["detail"])

    def test_missing_found_at_is_stale(self):
        report, run_log_calls = self.run_process_route(None, {"stale_alert_policy": "warn"})
        self.assertTrue(report["is_stale"])
        self.assertTrue(report["should_alert"])
        self.assertIn("frescor: desconhecido (velho)", run_log_calls[0][1]["detail"])


if __name__ == "__main__":
    unittest.main()
