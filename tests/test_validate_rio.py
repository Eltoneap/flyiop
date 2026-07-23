"""Teste local da Parte 0 (validação do RIO): lógica de seleção/filtro do
scripts/validate_rio.py, sem chamar a API real da Travelpayouts.

Uso: python -m unittest tests/test_validate_rio.py -v  (a partir da raiz)
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import validate_rio  # noqa: E402

ENTRY_SUNDAY = {
    "price": 450.0, "origin_airport": "SDU", "destination_airport": "BSB",
    "departure_at": "2026-09-04T07:00:00Z", "return_at": "2026-09-06T20:00:00Z", "transfers": 0,
}
ENTRY_MONDAY = {
    "price": 380.0, "origin_airport": "GIG", "destination_airport": "BSB",
    "departure_at": "2026-09-04T07:00:00Z", "return_at": "2026-09-07T06:00:00Z", "transfers": 1,
}


class CheapestTest(unittest.TestCase):
    def test_picks_lower_price(self):
        self.assertEqual(validate_rio.cheapest([ENTRY_SUNDAY, ENTRY_MONDAY])["price"], 380.0)

    def test_empty_list_returns_none(self):
        self.assertIsNone(validate_rio.cheapest([]))


class RunCheckTest(unittest.TestCase):
    @patch("validate_rio.get_prices_for_dates", return_value=[ENTRY_SUNDAY, ENTRY_MONDAY])
    def test_filters_by_exact_return_date(self, _mock):
        result = validate_rio.run_check("RIO→BSB, volta domingo", "RIO", "2026-09-06")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["price"], 450.0)  # a entrada de domingo, não a mais barata das duas

    @patch("validate_rio.get_prices_for_dates", return_value=[])
    def test_empty_response_is_vazio_not_erro(self, _mock):
        result = validate_rio.run_check("RIO→BSB, volta domingo", "RIO", "2026-09-06")
        self.assertEqual(result["status"], "vazio")

    @patch("validate_rio.get_prices_for_dates", side_effect=RuntimeError("timeout simulado"))
    def test_exception_is_caught_as_erro(self, _mock):
        result = validate_rio.run_check("RIO→BSB, volta domingo", "RIO", "2026-09-06")
        self.assertEqual(result["status"], "erro")

    @patch("validate_rio.get_prices_for_dates", return_value=[ENTRY_SUNDAY])
    def test_no_exact_match_falls_back_to_overall_cheapest(self, _mock):
        # nenhuma entrada bate a data pedida (2026-09-08) -> cai no mais barato geral
        result = validate_rio.run_check("RIO→BSB, volta terça (não existe)", "RIO", "2026-09-08")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["price"], 450.0)


class RunCheckMonthTest(unittest.TestCase):
    @patch("validate_rio.get_prices_for_dates", return_value=[ENTRY_SUNDAY, ENTRY_MONDAY])
    def test_picks_cheapest_of_the_month(self, _mock):
        result = validate_rio.run_check_month("RIO→BSB, mês inteiro", "RIO")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["price"], 380.0)

    @patch("validate_rio.get_prices_for_dates", return_value=[])
    def test_empty_month_is_vazio(self, _mock):
        result = validate_rio.run_check_month("RIO→BSB, mês inteiro", "RIO")
        self.assertEqual(result["status"], "vazio")

    @patch("validate_rio.get_prices_for_dates", side_effect=RuntimeError("timeout simulado"))
    def test_exception_is_caught_as_erro(self, _mock):
        result = validate_rio.run_check_month("RIO→BSB, mês inteiro", "RIO")
        self.assertEqual(result["status"], "erro")


if __name__ == "__main__":
    unittest.main()
