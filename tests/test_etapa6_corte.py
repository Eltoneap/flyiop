"""Teste local da Etapa 6 (PLAN-FASE-A.md / PLAN-VALIDACAO-CRUZADA.md): corte para o v3.

Cobre o mapeamento de campos do v3 no process_route, a mensagem de frescor nova
("ℹ️ Fonte com cache de até 48h" no lugar de "⚠️ Dado antigo" quando found_at é
ausente na fonte v3) e a salvaguarda contra supressão total.

Roda 100% com mocks — sem API da Travelpayouts, sem Supabase.
Uso: python -m unittest tests/test_etapa6_corte.py -v  (a partir da raiz)
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main  # noqa: E402
from telegram_notifier import build_alert_message, build_route_block  # noqa: E402

ROUTE = {
    "id": "rota-1",
    "user_id": "user-1",
    "origin": "BSB",
    "destination": "GIG",
    "currency": "BRL",
    "target_price": 600,
    "target_percent_below_avg": None,
    "trip_duration_weeks": 2,  # deixou de ter efeito — não deve quebrar nada
}

# Entrada real do v3: sem found_at, datas com timestamp, escalas em "transfers".
V3_ENTRY = {
    "price": 520.0,
    "departure_at": "2026-11-27T07:00:00Z",
    "return_at": "2026-11-30T20:00:00Z",
    "transfers": 1,
}

SETTINGS = {
    "window_3d_pct": 10, "window_7d_pct": 15, "notification_mode": "alert_only",
    "freshness_hours": 24, "stale_alert_policy": "warn",
}


def run_process_route(v3_months, settings=None):
    """Roda process_route com o cliente v3 e o Supabase mockados."""
    calls = {"insert_price": [], "insert_run_log": []}
    with patch("main.get_prices_for_dates", side_effect=v3_months), \
         patch("main.insert_price", side_effect=lambda *a, **k: calls["insert_price"].append((a, k))), \
         patch("main.insert_run_log", side_effect=lambda *a, **k: calls["insert_run_log"].append((a, k))), \
         patch("main.get_price_history", return_value=[]), \
         patch("main.time.sleep", return_value=None):
        report = main.process_route(ROUTE, settings or SETTINGS)
    return report, calls


class V3FieldMappingTest(unittest.TestCase):
    def test_v3_fields_mapped_into_price_history(self):
        report, calls = run_process_route([[V3_ENTRY], [], [], [], [], []])

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["price"], 520.0)
        self.assertEqual(report["depart_date"], "2026-11-27")  # timestamp cortado em 10 chars
        self.assertEqual(report["return_date"], "2026-11-30")
        self.assertEqual(report["stops"], 1)  # veio de "transfers"
        self.assertIsNone(report["found_at"])
        self.assertTrue(report["cache_48h"])

        # insert_price recebeu os campos mapeados do v3
        args, kwargs = calls["insert_price"][0]
        self.assertEqual(args[2], 520.0)  # price posicional
        self.assertEqual(kwargs["return_date"], "2026-11-30")
        self.assertEqual(kwargs["stops"], 1)
        self.assertIsNone(kwargs["found_at"])

    def test_run_log_marks_source_v3_and_cache(self):
        _, calls = run_process_route([[V3_ENTRY], [], [], [], [], []])
        detail = calls["insert_run_log"][0][1]["detail"]
        self.assertIn("fonte: v3", detail)
        self.assertIn("cache ≤48h", detail)

    @patch("main.get_recent_run_outcomes", return_value=[])
    def test_no_data_still_logs_source_v3(self, _mock_streak):
        report, calls = run_process_route([[] for _ in range(6)])
        self.assertEqual(report["status"], "no_data")
        self.assertEqual(calls["insert_run_log"][0][1]["detail"], "fonte: v3")


class CacheMessageTest(unittest.TestCase):
    BASE_REPORT = {
        "origin": "BSB", "destination": "GIG", "currency": "BRL", "price": 520.0,
        "depart_date": "2026-11-27", "return_date": "2026-11-30", "stops": 1,
        "days_ahead": 130, "target_price": 600.0, "avg_30d": 700.0,
        "reason": "abaixo da meta fixa (R$ 600.0)",
    }

    def test_cache_48h_alert_uses_info_not_alarm(self):
        report = {**self.BASE_REPORT, "is_stale": True, "age_hours": None, "cache_48h": True}
        message = build_alert_message(report)
        self.assertIn("ℹ️ <b>Fonte com cache de até 48h</b>", message)
        self.assertNotIn("Dado antigo", message)

    def test_cache_48h_line_in_route_block(self):
        report = {**self.BASE_REPORT, "found_at": None, "cache_48h": True}
        block = build_route_block(report)
        self.assertIn("Fonte com cache de até 48h", block)

    def test_real_old_price_still_alarms(self):
        # found_at presente e realmente velho → o alarme "Dado antigo" continua.
        report = {**self.BASE_REPORT, "is_stale": True, "age_hours": 30.0, "cache_48h": False}
        message = build_alert_message(report)
        self.assertIn("⚠️ <b>Dado antigo (visto há 30h)</b>", message)
        self.assertNotIn("cache de até 48h", message)


class SuppressSafeguardTest(unittest.TestCase):
    def test_suppress_ignored_when_age_unknown(self):
        settings = {**SETTINGS, "stale_alert_policy": "suppress"}
        report, calls = run_process_route([[V3_ENTRY], [], [], [], [], []], settings)
        self.assertTrue(report["should_alert"])  # NÃO suprimido
        detail = calls["insert_run_log"][0][1]["detail"]
        self.assertIn("política suppress não aplicada", detail)


if __name__ == "__main__":
    unittest.main()
