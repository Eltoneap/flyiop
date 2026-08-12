"""Fatia D1 (12/08/2026): resumo semanal do Telegram passa a respeitar a
janela de compra (fins de semana >= corte) — as duas listas ("Mais baratas
agora"/"Mais próximas") e o aviso de fallback quando a leitura do corte
degrada. `build_weekly_weekend_summary` recorta pela `outbound_date` do
próprio report (ida ou volta, sempre a âncora do fim de semana).

Uso: python -m unittest tests/test_telegram.py -v  (a partir da raiz do repo)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import telegram_notifier as tn  # noqa: E402

CUTOFF = "2027-01-29"


def report(outbound_date: str, direction: str, price: float) -> dict:
    return {
        "status": "ok", "outbound_date": outbound_date, "direction": direction,
        "price": price,
    }


class BuildWeeklyWeekendSummaryTest(unittest.TestCase):
    def test_legs_before_cutoff_are_excluded_from_both_lists(self):
        reports = [
            report("2026-09-04", "outbound", 300.0),
            report("2026-12-25", "return", 425.0),
        ]
        msg = tn.build_weekly_weekend_summary(reports, total=0, purchased=0, cutoff=CUTOFF)
        self.assertNotIn("04/09/2026", msg)
        self.assertNotIn("25/12/2026", msg)

    def test_legs_on_or_after_cutoff_appear_in_both_lists(self):
        reports = [
            report("2027-01-29", "outbound", 280.0),
            report("2027-02-05", "return", 260.0),
        ]
        msg = tn.build_weekly_weekend_summary(reports, total=90, purchased=0, cutoff=CUTOFF)
        self.assertIn("29/01/2027", msg)
        self.assertIn("05/02/2027", msg)

    def test_cutoff_exactly_on_outbound_date_is_included(self):
        reports = [report(CUTOFF, "outbound", 300.0)]
        msg = tn.build_weekly_weekend_summary(reports, total=1, purchased=0, cutoff=CUTOFF)
        self.assertIn("29/01/2027", msg)

    def test_denominator_line_shows_cutoff(self):
        msg = tn.build_weekly_weekend_summary([], total=90, purchased=3, cutoff=CUTOFF)
        self.assertIn("3 de 90 pernas compradas", msg)
        self.assertIn("29/01/2027", msg)

    def test_empty_state_explains_the_window_not_a_failure(self):
        # Todas as pernas checadas hoje são antes do corte -> lista filtrada
        # fica vazia, mesmo com reports não vazios.
        reports = [report("2026-09-04", "outbound", 300.0)]
        msg = tn.build_weekly_weekend_summary(reports, total=0, purchased=0, cutoff=CUTOFF)
        self.assertIn("janela de compra", msg)
        self.assertNotIn("Sem preços coletados ainda esta semana", msg)

    def test_only_ok_status_reports_are_considered(self):
        reports = [
            {"status": "no_data", "outbound_date": "2027-02-05", "direction": "outbound"},
            report("2027-02-05", "return", 260.0),
        ]
        msg = tn.build_weekly_weekend_summary(reports, total=1, purchased=0, cutoff=CUTOFF)
        # só a linha 'ok' aparece com preço
        self.assertIn("R$ 260.00", msg)


class BuildBuyingCutoffFallbackMessageTest(unittest.TestCase):
    def test_mentions_the_fallback_value_used(self):
        msg = tn.build_buying_cutoff_fallback_message("2027-01-29")
        self.assertIn("29/01/2027", msg)
        self.assertIn("system_config", msg)


if __name__ == "__main__":
    unittest.main()
