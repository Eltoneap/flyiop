"""Fatia D1 (12/08/2026): resumo semanal do Telegram passa a respeitar a
janela de compra (fins de semana >= corte) — as duas listas ("Mais baratas
agora"/"Mais próximas") e o aviso de fallback quando a leitura do corte
degrada. `build_weekly_weekend_summary` recorta pela `outbound_date` do
próprio report (ida ou volta, sempre a âncora do fim de semana).

E7-7 (05/09/2026): o cabeçalho passou a trazer UMA LINHA DE PROGRESSO POR
USUÁRIO (`per_user`, no lugar do par `total`/`purchased`), porque cada um
compra a própria passagem. As listas de preço seguem únicas — preço de
mercado é o mesmo para todo mundo.

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


def counts(label: str, purchased: int, total: int) -> dict:
    return {"label": label, "purchased": purchased, "total": total}


ONE_USER = [counts("Elton", 0, 90)]


class BuildWeeklyWeekendSummaryTest(unittest.TestCase):
    def test_legs_before_cutoff_are_excluded_from_both_lists(self):
        reports = [
            report("2026-09-04", "outbound", 300.0),
            report("2026-12-25", "return", 425.0),
        ]
        msg = tn.build_weekly_weekend_summary(reports, ONE_USER, CUTOFF)
        self.assertNotIn("04/09/2026", msg)
        self.assertNotIn("25/12/2026", msg)

    def test_legs_on_or_after_cutoff_appear_in_both_lists(self):
        reports = [
            report("2027-01-29", "outbound", 280.0),
            report("2027-02-05", "return", 260.0),
        ]
        msg = tn.build_weekly_weekend_summary(reports, ONE_USER, CUTOFF)
        self.assertIn("29/01/2027", msg)
        self.assertIn("05/02/2027", msg)

    def test_cutoff_exactly_on_outbound_date_is_included(self):
        reports = [report(CUTOFF, "outbound", 300.0)]
        msg = tn.build_weekly_weekend_summary(reports, ONE_USER, CUTOFF)
        self.assertIn("29/01/2027", msg)

    def test_buying_window_line_shows_cutoff(self):
        msg = tn.build_weekly_weekend_summary([], ONE_USER, CUTOFF)
        self.assertIn("Janela de compra a partir de 29/01/2027", msg)

    def test_empty_state_explains_the_window_not_a_failure(self):
        # Todas as pernas checadas hoje são antes do corte -> lista filtrada
        # fica vazia, mesmo com reports não vazios.
        reports = [report("2026-09-04", "outbound", 300.0)]
        msg = tn.build_weekly_weekend_summary(reports, ONE_USER, CUTOFF)
        self.assertIn("janela de compra", msg)
        self.assertNotIn("Sem preços coletados ainda esta semana", msg)

    def test_only_ok_status_reports_are_considered(self):
        reports = [
            {"status": "no_data", "outbound_date": "2027-02-05", "direction": "outbound"},
            report("2027-02-05", "return", 260.0),
        ]
        msg = tn.build_weekly_weekend_summary(reports, ONE_USER, CUTOFF)
        # só a linha 'ok' aparece com preço
        self.assertIn("R$ 260.00", msg)

    # --- E7-7 (05/09/2026): progresso por usuário -------------------------

    def test_one_line_per_user_with_each_name(self):
        per_user = [counts("Elton", 3, 90), counts("Gustavo", 1, 90)]
        msg = tn.build_weekly_weekend_summary([], per_user, CUTOFF)
        self.assertIn("👤 Elton: 3 de 90 pernas compradas", msg)
        self.assertIn("👤 Gustavo: 1 de 90 pernas compradas", msg)

    def test_user_order_follows_the_caller(self):
        # main.py entrega já ordenado por user_id (get_weekend_leg_counts); o
        # notifier não reordena — senão a ordem passaria a depender do nome.
        per_user = [counts("Gustavo", 1, 90), counts("Elton", 3, 90)]
        msg = tn.build_weekly_weekend_summary([], per_user, CUTOFF)
        self.assertLess(msg.index("Gustavo"), msg.index("Elton"))

    def test_single_user_still_reads_naturally(self):
        msg = tn.build_weekly_weekend_summary([], [counts("Elton", 3, 90)], CUTOFF)
        self.assertIn("👤 Elton: 3 de 90 pernas compradas", msg)
        self.assertNotIn("indisponível", msg)

    def test_degraded_no_users_says_unavailable_not_zero_of_zero(self):
        # Modo degradado (nenhum usuário em `settings`): "0 de 0 pernas
        # compradas" pareceria progresso zerado; a mensagem tem que dizer que
        # a contagem não existe.
        msg = tn.build_weekly_weekend_summary([], [], CUTOFF)
        self.assertIn("contagem por usuário indisponível", msg)
        self.assertNotIn("0 de 0 pernas compradas", msg)
        self.assertIn("Janela de compra a partir de 29/01/2027", msg)

    def test_price_lists_are_shared_not_per_user(self):
        # Preço de mercado é o mesmo para todo mundo: as listas saem uma vez
        # só, não uma por usuário.
        per_user = [counts("Elton", 3, 90), counts("Gustavo", 1, 90)]
        reports = [report("2027-02-05", "outbound", 260.0)]
        msg = tn.build_weekly_weekend_summary(reports, per_user, CUTOFF)
        self.assertEqual(msg.count("Mais baratas agora"), 1)
        self.assertEqual(msg.count("R$ 260.00"), 2)  # uma vez em cada lista


class BuildBuyingCutoffFallbackMessageTest(unittest.TestCase):
    def test_mentions_the_fallback_value_used(self):
        msg = tn.build_buying_cutoff_fallback_message("2027-01-29")
        self.assertIn("29/01/2027", msg)
        self.assertIn("system_config", msg)


if __name__ == "__main__":
    unittest.main()
