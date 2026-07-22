"""Teste local da Etapa 4 (PLAN-FASE-A.md): autocheck estatístico anti-preço-fantasma.

Roda 100% com mocks — nenhuma chamada à API da Travelpayouts nem ao Supabase.
Uso: python -m unittest tests/test_etapa4_suspeito.py -v  (a partir da raiz)
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main  # noqa: E402
from rules import is_suspicious_price  # noqa: E402


class IsSuspiciousPriceTest(unittest.TestCase):
    def test_far_below_average_is_suspicious(self):
        history = [1000.0, 1050.0, 980.0, 1020.0, 990.0]  # média = 1008
        self.assertTrue(is_suspicious_price(400.0, history, threshold_pct=50))  # ~60% abaixo

    def test_moderately_below_average_is_not_suspicious(self):
        history = [1000.0, 1050.0, 980.0, 1020.0, 990.0]
        self.assertFalse(is_suspicious_price(700.0, history, threshold_pct=50))  # ~30% abaixo

    def test_short_history_never_classifies(self):
        history = [1000.0, 900.0]  # menos de 5 registros
        self.assertFalse(is_suspicious_price(10.0, history, threshold_pct=50))

    def test_empty_history_never_classifies(self):
        self.assertFalse(is_suspicious_price(10.0, [], threshold_pct=50))

    def test_exactly_at_threshold_is_not_suspicious(self):
        history = [1000.0] * 5  # média = 1000
        self.assertFalse(is_suspicious_price(500.0, history, threshold_pct=50))  # exatamente 50%

    def test_just_above_threshold_is_suspicious(self):
        history = [1000.0] * 5
        self.assertTrue(is_suspicious_price(499.0, history, threshold_pct=50))


class ProcessRouteSuspiciousIntegrationTest(unittest.TestCase):
    ROUTE = {
        "id": "rota-1",
        "user_id": "user-1",
        "origin": "BSB",
        "destination": "GIG",
        "currency": "BRL",
        "target_price": None,
        "target_percent_below_avg": None,
        "trip_duration_weeks": None,
    }

    def run_process_route(self, price: float, history_prices: list[float]) -> tuple[dict, list]:
        settings = {
            "window_3d_pct": 10, "window_7d_pct": 15, "notification_mode": "alert_only",
            "freshness_hours": 24, "stale_alert_policy": "warn",
            "realert_drop_pct": 5, "realert_days": 3, "suspicious_below_avg_pct": 50,
        }
        v3_entry = {
            "price": price, "departure_at": "2026-11-27T00:00:00Z", "return_at": "2026-11-30T00:00:00Z",
            "transfers": 1,
        }
        history_rows = [{"price": p, "checked_at": f"2026-07-{i+1:02d}T10:00:00Z"} for i, p in enumerate(history_prices)]
        run_log_calls: list = []
        with patch("main.get_prices_for_dates", side_effect=[[v3_entry], [], [], [], [], []]), \
             patch("main.insert_price"), \
             patch("main.insert_run_log", side_effect=lambda *a, **k: run_log_calls.append((a, k))), \
             patch("main.get_price_history", return_value=history_rows), \
             patch("main.get_last_alert", return_value=None), \
             patch("main.time.sleep", return_value=None):
            report = main.process_route(self.ROUTE, settings)
        return report, run_log_calls

    def test_suspicious_price_never_alerts_even_if_good_or_trending(self):
        # preço 60% abaixo da média de 1000 -> suspeito, mesmo sem meta configurada
        history = [1000.0, 1010.0, 990.0, 1005.0, 995.0]
        report, run_log_calls = self.run_process_route(400.0, history)

        self.assertTrue(report["suspicious"])
        self.assertFalse(report["should_alert"])
        detail = run_log_calls[0][1]["detail"]
        self.assertIn("suspeito:", detail)
        self.assertIn("% abaixo da média 30d", detail)

    def test_normal_price_is_not_marked_suspicious(self):
        history = [1000.0, 1010.0, 990.0, 1005.0, 995.0]
        report, run_log_calls = self.run_process_route(950.0, history)

        self.assertFalse(report["suspicious"])
        self.assertNotIn("suspeito:", run_log_calls[0][1]["detail"])

    def test_price_is_still_recorded_normally_when_suspicious(self):
        """Etapa 4: 'dado é dado' — o preço suspeito é gravado no histórico, só o alerta é que não dispara."""
        history = [1000.0, 1010.0, 990.0, 1005.0, 995.0]
        with patch("main.get_prices_for_dates", side_effect=[[{
            "price": 400.0, "departure_at": "2026-11-27T00:00:00Z", "return_at": "2026-11-30T00:00:00Z",
            "transfers": 1,
        }], [], [], [], [], []]), \
             patch("main.insert_price") as mock_insert_price, \
             patch("main.insert_run_log"), \
             patch("main.get_price_history", return_value=[
                 {"price": p, "checked_at": "2026-07-01T10:00:00Z"} for p in history
             ]), \
             patch("main.get_last_alert", return_value=None), \
             patch("main.time.sleep", return_value=None):
            settings = {
                "window_3d_pct": 10, "window_7d_pct": 15, "notification_mode": "alert_only",
                "freshness_hours": 24, "stale_alert_policy": "warn",
                "realert_drop_pct": 5, "realert_days": 3, "suspicious_below_avg_pct": 50,
            }
            main.process_route(self.ROUTE, settings)

        mock_insert_price.assert_called_once()
        self.assertEqual(mock_insert_price.call_args[0][2], 400.0)  # price é o 3º posicional


class BuildNotesSuspiciousTest(unittest.TestCase):
    def test_suspicious_report_generates_note(self):
        route = {"origin": "BSB", "destination": "GIG"}
        reports = [{"route": route, "status": "ok", "suspicious": True, "price": 400.0}]
        notes = main.build_notes(reports)
        self.assertEqual(len(notes), 1)
        self.assertIn("suspeito", notes[0])
        self.assertIn("BSB", notes[0])

    def test_non_suspicious_ok_report_generates_no_note(self):
        route = {"origin": "BSB", "destination": "GIG"}
        reports = [{"route": route, "status": "ok", "suspicious": False, "price": 900.0}]
        notes = main.build_notes(reports)
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
