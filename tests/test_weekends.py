"""Teste local do módulo de pernas de fim de semana (weekends.py) — revisão
de 23/07/2026 (ida/volta desacopladas, busca one-way GIG+SDU por mês).

Roda 100% com mocks — nenhuma chamada à API da Travelpayouts nem ao Supabase.
Uso: python -m unittest tests/test_weekends.py -v  (a partir da raiz do repo)
"""
import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import weekends  # noqa: E402


def iso_days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def days_from_today(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


WEEKEND = {"outbound_date": "2026-09-04", "return_sunday": "2026-09-06", "return_monday": "2026-09-07"}

USER_A = "user-a"

OUTBOUND_LEG = {
    "id": "leg-out-1", "weekend_id": "wknd-1", "direction": "outbound",
    "ceilings_by_user": {USER_A: 200}, "queue_ceiling": 200, "lowest_seen": None, **WEEKEND,
}

RETURN_LEG = {
    "id": "leg-ret-1", "weekend_id": "wknd-1", "direction": "return",
    "ceilings_by_user": {USER_A: 200}, "queue_ceiling": 200, "lowest_seen": None, **WEEKEND,
}

# Configuração de SISTEMA (o que main.py passa como `system_config`): igual
# para todos os usuários, lida uma vez por perna.
SYSTEM_SETTINGS = {
    "suspicious_below_avg_pct": 50,
    # Fatia D1 (12/08/2026): corte bem no passado para que os testes
    # existentes (fim de semana 2026-09-04) sigam dentro da janela de compra
    # sem precisar mudar nenhuma asserção já escrita. Os testes de janela,
    # abaixo, declaram o corte que precisam.
    "weekend_buying_cutoff_date": "2026-01-01",
}

# Configuração POR USUÁRIO (o `settings_cache` de main.py): lida dentro do laço.
USER_SETTINGS = {
    "notification_mode": "alert_only",
    "weekend_opportunity_pct": 15,
    "realert_drop_pct": 5,
    "realert_days": 3,
}

SETTINGS_BY_USER = {USER_A: USER_SETTINGS}


def leg_with_users(leg: dict, ceilings: dict) -> dict:
    """Perna com um conjunto explícito de (usuário -> teto). `queue_ceiling` é
    derivado do mesmo jeito que get_active_legs deriva — heurística de fila."""
    known = [c for c in ceilings.values() if c is not None]
    return {**leg, "ceilings_by_user": ceilings, "queue_ceiling": min(known) if known else None}


def entry(price: float, departure_date: str, transfers=0) -> dict:
    return {"price": price, "departure_at": f"{departure_date}T07:00:00Z", "transfers": transfers}


class ResolveBuyingCutoffTest(unittest.TestCase):
    """Fatia D1 (12/08/2026): degradação nunca remove o filtro, só cai no
    fallback e sinaliza — main.py decide se avisa no Telegram."""

    def test_reads_value_from_settings(self):
        cutoff, degraded = weekends.resolve_buying_cutoff({"weekend_buying_cutoff_date": "2027-06-01"})
        self.assertEqual(cutoff, "2027-06-01")
        self.assertFalse(degraded)

    def test_missing_key_falls_back_and_flags_degraded(self):
        cutoff, degraded = weekends.resolve_buying_cutoff({})
        self.assertEqual(cutoff, weekends.BUYING_CUTOFF_FALLBACK)
        self.assertTrue(degraded)

    def test_none_value_falls_back_and_flags_degraded(self):
        cutoff, degraded = weekends.resolve_buying_cutoff({"weekend_buying_cutoff_date": None})
        self.assertEqual(cutoff, weekends.BUYING_CUTOFF_FALLBACK)
        self.assertTrue(degraded)

    def test_empty_string_falls_back_and_flags_degraded(self):
        cutoff, degraded = weekends.resolve_buying_cutoff({"weekend_buying_cutoff_date": ""})
        self.assertEqual(cutoff, weekends.BUYING_CUTOFF_FALLBACK)
        self.assertTrue(degraded)


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


def state_rows(*leg_ids, user_id="user-a", ceiling=250, status="monitoring") -> list[dict]:
    """Linhas de weekend_leg_effective (uma por perna × usuário) como o robô as
    recebe: price_ceiling e status já resolvidos pela view."""
    return [
        {"leg_id": leg_id, "user_id": user_id, "price_ceiling": ceiling, "status": status}
        for leg_id in leg_ids
    ]


class GetActiveLegsTest(unittest.TestCase):
    def test_merges_weekend_dates_onto_legs(self):
        weekend_row = {"id": "wknd-1", "outbound_date": "2026-09-04", "return_sunday": "2026-09-06", "return_monday": "2026-09-07"}
        leg_row = {"id": "leg-out-1", "weekend_id": "wknd-1", "direction": "outbound"}
        with patch("weekends.get_monitoring_weekends", return_value=[weekend_row]), \
             patch("weekends.get_all_weekend_legs", return_value=[leg_row]), \
             patch("weekends.get_effective_leg_state", return_value=state_rows("leg-out-1")):
            legs = weekends.get_active_legs()
        self.assertEqual(len(legs), 1)
        self.assertEqual(legs[0]["outbound_date"], "2026-09-04")
        self.assertEqual(legs[0]["return_sunday"], "2026-09-06")

    def test_leg_of_expired_weekend_is_excluded(self):
        leg_row = {"id": "leg-out-1", "weekend_id": "wknd-passado", "direction": "outbound"}
        with patch("weekends.get_monitoring_weekends", return_value=[]), \
             patch("weekends.get_all_weekend_legs", return_value=[leg_row]), \
             patch("weekends.get_effective_leg_state", return_value=state_rows("leg-out-1")):
            legs = weekends.get_active_legs()
        self.assertEqual(legs, [])

    def test_outbound_expires_independently_while_return_still_valid(self):
        # Parte 9 (28/07/2026): a sexta já passou de D+1, mas domingo/segunda
        # ainda não — antes, o weekend inteiro saía junto (bug real).
        weekend_row = {
            "id": "wknd-1",
            "outbound_date": days_from_today(-2),
            "return_sunday": days_from_today(0),
            "return_monday": days_from_today(1),
        }
        outbound = {"id": "leg-out-1", "weekend_id": "wknd-1", "direction": "outbound"}
        ret = {"id": "leg-ret-1", "weekend_id": "wknd-1", "direction": "return"}
        with patch("weekends.get_monitoring_weekends", return_value=[weekend_row]), \
             patch("weekends.get_all_weekend_legs", return_value=[outbound, ret]), \
             patch("weekends.get_effective_leg_state", return_value=state_rows("leg-out-1", "leg-ret-1")):
            legs = weekends.get_active_legs()
        ids = [leg["id"] for leg in legs]
        self.assertNotIn("leg-out-1", ids)
        self.assertIn("leg-ret-1", ids)

    def test_outbound_still_checked_through_d_plus_1(self):
        weekend_row = {
            "id": "wknd-1",
            "outbound_date": days_from_today(-1),
            "return_sunday": days_from_today(1),
            "return_monday": days_from_today(2),
        }
        outbound = {"id": "leg-out-1", "weekend_id": "wknd-1", "direction": "outbound"}
        with patch("weekends.get_monitoring_weekends", return_value=[weekend_row]), \
             patch("weekends.get_all_weekend_legs", return_value=[outbound]), \
             patch("weekends.get_effective_leg_state", return_value=state_rows("leg-out-1")):
            legs = weekends.get_active_legs()
        self.assertEqual([leg["id"] for leg in legs], ["leg-out-1"])

    def test_return_expires_d_plus_1_after_return_monday(self):
        weekend_row = {
            "id": "wknd-1",
            "outbound_date": days_from_today(-5),
            "return_sunday": days_from_today(-3),
            "return_monday": days_from_today(-2),
        }
        ret = {"id": "leg-ret-1", "weekend_id": "wknd-1", "direction": "return"}
        with patch("weekends.get_monitoring_weekends", return_value=[weekend_row]), \
             patch("weekends.get_all_weekend_legs", return_value=[ret]), \
             patch("weekends.get_effective_leg_state", return_value=state_rows("leg-ret-1")):
            legs = weekends.get_active_legs()
        self.assertEqual(legs, [])


class EffectiveLegStateTest(unittest.TestCase):
    """Fila por status efetivo (pendência 9 da Etapa 4.2) e teto POR USUÁRIO
    (Fatia D4, 15/08/2026 — aposenta o MIN provisório da 4.2), a partir de
    weekend_leg_effective."""

    WEEKEND_ROW = {
        "id": "wknd-1", "outbound_date": "2026-09-04",
        "return_sunday": "2026-09-06", "return_monday": "2026-09-07",
    }
    # Sem `status`: a coluna antiga de weekend_legs sai na Etapa 4.3 e o robô
    # não a lê mais em ramo nenhum. Só o teste do status antigo monta a chave.
    LEG_ROW = {"id": "leg-out-1", "weekend_id": "wknd-1", "direction": "outbound"}

    def load(self, state, leg_rows=None):
        with patch("weekends.get_monitoring_weekends", return_value=[self.WEEKEND_ROW]), \
             patch("weekends.get_all_weekend_legs", return_value=leg_rows or [self.LEG_ROW]), \
             patch("weekends.get_effective_leg_state", return_value=state):
            return weekends.get_active_legs()

    def test_single_user_ceiling_comes_from_the_view(self):
        legs = self.load(state_rows("leg-out-1", ceiling=300))
        self.assertEqual(legs[0]["ceilings_by_user"], {"user-a": 300})
        self.assertEqual(legs[0]["queue_ceiling"], 300)

    def test_each_user_keeps_their_own_ceiling(self):
        # Fatia D4: o MIN morreu. Os dois tetos chegam à avaliação; quem
        # decide é o laço por usuário, não um colapso aqui.
        state = (state_rows("leg-out-1", user_id="user-a", ceiling=300)
                 + state_rows("leg-out-1", user_id="user-b", ceiling=180))
        legs = self.load(state)
        self.assertEqual(legs[0]["ceilings_by_user"], {"user-a": 300, "user-b": 180})

    def test_queue_ceiling_is_the_lowest_but_is_only_a_queue_hint(self):
        state = (state_rows("leg-out-1", user_id="user-a", ceiling=300)
                 + state_rows("leg-out-1", user_id="user-b", ceiling=180))
        legs = self.load(state)
        self.assertEqual(legs[0]["queue_ceiling"], 180)
        # ...e o menor teto NÃO substitui o teto de ninguém na avaliação.
        self.assertEqual(legs[0]["ceilings_by_user"]["user-a"], 300)

    def test_user_monitoring_without_ceiling_is_a_key_with_none_not_an_omission(self):
        """Guarda direta contra espelhar o filtro do MIN antigo dentro do dict:
        omitir quem não tem teto faria uma perna com um único usuário sem teto
        virar {} e ser lida como 'perna sem dono' — alerta sem registro em
        alert_log, e o estado 'usuário presente, sem teto' desapareceria."""
        state = (state_rows("leg-out-1", user_id="user-a", ceiling=300)
                 + state_rows("leg-out-1", user_id="user-b", ceiling=None))
        legs = self.load(state)
        self.assertEqual(legs[0]["ceilings_by_user"], {"user-a": 300, "user-b": None})
        self.assertEqual(legs[0]["queue_ceiling"], 300)  # só os tetos conhecidos entram

    def test_only_user_without_ceiling_still_has_a_key_and_is_not_degraded(self):
        legs = self.load(state_rows("leg-out-1", ceiling=None))
        self.assertEqual(legs[0]["ceilings_by_user"], {"user-a": None})
        self.assertIsNone(legs[0]["queue_ceiling"])
        self.assertFalse(weekends.LEG_LOAD_DIAGNOSTICS["degraded_no_settings"])

    def test_purchased_user_does_not_appear_in_the_dict(self):
        # user-b já comprou: o teto apertado dele não deve mais governar um
        # alerta que só interessa a quem ainda monitora.
        state = (state_rows("leg-out-1", user_id="user-a", ceiling=300)
                 + state_rows("leg-out-1", user_id="user-b", ceiling=180, status="purchased"))
        legs = self.load(state)
        self.assertEqual(legs[0]["ceilings_by_user"], {"user-a": 300})

    def test_leg_stays_in_queue_while_any_user_still_monitors(self):
        state = (state_rows("leg-out-1", user_id="user-a", status="purchased")
                 + state_rows("leg-out-1", user_id="user-b", status="monitoring"))
        legs = self.load(state)
        self.assertEqual([leg["id"] for leg in legs], ["leg-out-1"])
        # ...com UMA entrada só: a do comprado não entra.
        self.assertEqual(list(legs[0]["ceilings_by_user"]), ["user-b"])

    def test_leg_leaves_queue_only_when_every_user_stopped_monitoring(self):
        state = (state_rows("leg-out-1", user_id="user-a", status="purchased")
                 + state_rows("leg-out-1", user_id="user-b", status="purchased"))
        self.assertEqual(self.load(state), [])

    def test_missing_state_row_counts_as_monitoring(self):
        # A view já devolve coalesce(status, 'monitoring') — silêncio segue o
        # padrão, e o padrão é continuar monitorando.
        legs = self.load(state_rows("leg-out-1"))
        self.assertEqual([leg["id"] for leg in legs], ["leg-out-1"])

    def test_no_settings_keeps_the_whole_queue_without_inventing_ceiling(self):
        """A FILA NÃO ESVAZIA NO MODO DEGRADADO — é o teste que protege a
        ordem dos dois testes de get_active_legs. `degraded` (a carga inteira
        voltou vazia) tem que curto-circuitar o teste por perna de 'ninguém
        monitora'; se a implementação fundir os dois num `continue` só, as 132
        pernas somem da fila em silêncio e o alerta de oportunidade acaba.
        Nenhum outro teste pega essa regressão: no nível do report, a perna
        nem chegaria a ser produzida e o teste ficaria verde sobre vazio."""
        second_leg = {"id": "leg-ret-1", "weekend_id": "wknd-1", "direction": "return"}
        legs = self.load([], leg_rows=[self.LEG_ROW, second_leg])
        self.assertEqual([leg["id"] for leg in legs], ["leg-out-1", "leg-ret-1"])
        for leg in legs:
            self.assertEqual(leg["ceilings_by_user"], {})
            self.assertIsNone(leg["queue_ceiling"])
        self.assertTrue(weekends.LEG_LOAD_DIAGNOSTICS["degraded_no_settings"])

    def test_no_settings_ignores_the_old_purchased_status(self):
        # Etapa 4.3: o ramo degradado não lê mais weekend_legs.status — coluna
        # congelada desde 03/08/2026 e removida na 4.3. Guarda de regressão:
        # com o filtro de volta, o DROP esvaziaria a fila em silêncio.
        bought = {**self.LEG_ROW, "status": "purchased"}
        legs = self.load([], leg_rows=[bought])
        self.assertEqual([leg["id"] for leg in legs], ["leg-out-1"])
        self.assertEqual(legs[0]["ceilings_by_user"], {})

    def test_diagnostics_are_overwritten_not_accumulated(self):
        # get_active_legs roda 2x por execução (varredura cache + lote fli) e
        # recalcula os mesmos números — o dict é sobrescrito, nunca acumulado,
        # senão o aviso sairia 2x no Telegram.
        self.load([])
        self.assertTrue(weekends.LEG_LOAD_DIAGNOSTICS["degraded_no_settings"])
        self.load(state_rows("leg-out-1", ceiling=300))
        self.assertFalse(weekends.LEG_LOAD_DIAGNOSTICS["degraded_no_settings"])


class ProcessWeekendLegTest(unittest.TestCase):
    def run_process(self, month_cache, history_prices=None, leg=None, settings=None, last_alert=None):
        history = [{"price": p, "checked_at": "2026-08-01T10:00:00Z"} for p in (history_prices or [])]
        with patch("weekends.insert_weekend_leg_price") as mock_insert, \
             patch("weekends.get_weekend_leg_price_history", return_value=history), \
             patch("weekends.get_last_weekend_leg_alert", return_value=last_alert), \
             patch("weekends.update_weekend_leg") as mock_update, \
             patch("weekends.insert_weekend_leg_run_log") as mock_run_log:
            report = weekends.process_weekend_leg(
                leg or OUTBOUND_LEG, settings or SYSTEM_SETTINGS, SETTINGS_BY_USER, month_cache
            )
        return report, mock_insert, mock_update, mock_run_log

    def only(self, report: dict) -> dict:
        """A decisão do único usuário do report — com 1 usuário, `per_user`
        tem exatamente 1 entrada."""
        self.assertEqual(len(report["per_user"]), 1)
        return report["per_user"][0]

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
        mock_insert.assert_called_once_with("leg-out-1", 280.0, "SDU", None, "cache", 0, None, None)
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
        self.assertTrue(self.only(report)["is_ceiling_hit"])
        self.assertTrue(report["should_alert"])

    # --- Fatia D1 (12/08/2026): janela de compra --------------------------
    # Ajuste do mesmo dia: o filtro vale para os DOIS tipos de alerta de
    # perna (teto e oportunidade), não só oportunidade — um alerta de teto
    # fora da janela mandaria "compre" algo que nunca será comprado.

    def test_ceiling_hit_outside_buying_window_does_not_alert(self):
        settings = {**SYSTEM_SETTINGS, "weekend_buying_cutoff_date": "2027-01-29"}  # OUTBOUND_LEG é 2026-09-04
        month_cache = {("2026-09", "GIG", "outbound"): [entry(150.0, "2026-09-04")]}
        report, _, _, _ = self.run_process(month_cache, history_prices=[400.0, 420.0], settings=settings)
        self.assertTrue(self.only(report)["is_ceiling_hit"])
        self.assertFalse(report["should_alert"])

    def test_opportunity_outside_buying_window_does_not_alert(self):
        settings = {**SYSTEM_SETTINGS, "weekend_buying_cutoff_date": "2027-01-29"}
        leg = leg_with_users(OUTBOUND_LEG, {USER_A: None})  # sem teto: só a regra de oportunidade decide
        month_cache = {("2026-09", "GIG", "outbound"): [entry(150.0, "2026-09-04")]}
        report, _, _, _ = self.run_process(
            month_cache, history_prices=[400.0, 420.0], leg=leg, settings=settings
        )
        self.assertFalse(self.only(report)["is_ceiling_hit"])
        self.assertFalse(report["should_alert"])

    def test_ceiling_hit_inside_buying_window_still_alerts(self):
        settings = {**SYSTEM_SETTINGS, "weekend_buying_cutoff_date": "2026-01-01"}
        month_cache = {("2026-09", "GIG", "outbound"): [entry(150.0, "2026-09-04")]}
        report, _, _, _ = self.run_process(month_cache, history_prices=[400.0, 420.0], settings=settings)
        self.assertTrue(report["should_alert"])

    def test_cutoff_exactly_on_outbound_date_counts_as_inside_window(self):
        # OUTBOUND_LEG é 2026-09-04 — corte igual à data conta como dentro (>=).
        settings = {**SYSTEM_SETTINGS, "weekend_buying_cutoff_date": "2026-09-04"}
        month_cache = {("2026-09", "GIG", "outbound"): [entry(150.0, "2026-09-04")]}
        report, _, _, _ = self.run_process(month_cache, history_prices=[400.0, 420.0], settings=settings)
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

    def test_composite_hit_records_both_flags(self):
        # leg com teto 200 para user-a; preço 150 bate teto E oportunidade
        # (avg 400, 15% -> limiar 340). evaluate_and_record_leg_price compõe
        # uma única mensagem (rules.is_good_price junta com "; "); a linha
        # gravada em alert_log deve carregar as duas flags.
        month_cache = {("2026-09", "GIG", "outbound"): [entry(150.0, "2026-09-04")]}
        report, _, _, _ = self.run_process(month_cache, history_prices=[400.0])
        decision = self.only(report)
        self.assertTrue(decision["is_ceiling_hit"])
        self.assertTrue(decision["is_opportunity_hit"])
        self.assertIn("abaixo da meta fixa", decision["reason"])
        self.assertIn("abaixo da média histórica", decision["reason"])

    def test_opportunity_only_does_not_set_ceiling_hit(self):
        leg = leg_with_users(OUTBOUND_LEG, {USER_A: 100})  # preço 150 não bate o teto
        month_cache = {("2026-09", "GIG", "outbound"): [entry(150.0, "2026-09-04")]}
        report, _, _, _ = self.run_process(month_cache, history_prices=[400.0], leg=leg)
        decision = self.only(report)
        self.assertFalse(decision["is_ceiling_hit"])
        self.assertTrue(decision["is_opportunity_hit"])


class LegCooldownByTypeTest(unittest.TestCase):
    """Fatia D2 (13/08/2026): cooldown de perna passa a ser POR TIPO — um
    alerta de oportunidade em cooldown não segura mais um de teto liberado
    (e vice-versa), corrigindo o bug estrutural de STATE.md, seção 2, onde
    o cooldown só filtrava por leg_id.

    Fatia D4 (15/08/2026): a consulta ganhou o `user_id` — o cooldown passa a
    ser por (perna × tipo × usuário)."""

    def run_process(self, price: float, history_prices: list[float], last_alerts_by_type: dict[str, dict | None]):
        history = [{"price": p, "checked_at": "2026-08-01T10:00:00Z"} for p in history_prices]
        month_cache = {("2026-09", "GIG", "outbound"): [entry(price, "2026-09-04")]}

        def fake_last_alert(leg_id, alert_type, user_id):
            return last_alerts_by_type.get(alert_type)

        with patch("weekends.insert_weekend_leg_price"), \
             patch("weekends.get_weekend_leg_price_history", return_value=history), \
             patch("weekends.get_last_weekend_leg_alert", side_effect=fake_last_alert) as mock_get_last, \
             patch("weekends.update_weekend_leg"), \
             patch("weekends.insert_weekend_leg_run_log"):
            report = weekends.process_weekend_leg(OUTBOUND_LEG, SYSTEM_SETTINGS, SETTINGS_BY_USER, month_cache)
        return report, mock_get_last

    def only(self, report: dict) -> dict:
        self.assertEqual(len(report["per_user"]), 1)
        return report["per_user"][0]

    def test_ceiling_alert_not_blocked_by_recent_opportunity_cooldown(self):
        # OUTBOUND_LEG: teto 200 para user-a; preço 150 só bate teto (avg
        # alto o bastante pra não bater oportunidade). Só existe cooldown
        # recente do tipo OPORTUNIDADE — o alerta de teto não pode ser
        # bloqueado por ele.
        report, mock_get_last = self.run_process(
            150.0, history_prices=[155.0, 156.0],
            last_alerts_by_type={"opportunity": {"price": 150.0, "sent_at": iso_days_ago(0.1)}},
        )
        decision = self.only(report)
        self.assertTrue(decision["is_ceiling_hit"])
        self.assertFalse(decision["is_opportunity_hit"])
        self.assertTrue(report["should_alert"])
        mock_get_last.assert_called_once_with("leg-out-1", "ceiling", USER_A)

    def test_opportunity_alert_not_blocked_by_recent_ceiling_cooldown(self):
        # usuário sem teto -> só a regra de oportunidade decide. Só existe
        # cooldown recente do tipo TETO — não pode segurar oportunidade.
        leg = leg_with_users(OUTBOUND_LEG, {USER_A: None})
        month_cache = {("2026-09", "GIG", "outbound"): [entry(150.0, "2026-09-04")]}
        history = [{"price": p, "checked_at": "2026-08-01T10:00:00Z"} for p in [400.0, 420.0]]

        def fake_last_alert(leg_id, alert_type, user_id):
            return {"price": 150.0, "sent_at": iso_days_ago(0.1)} if alert_type == "ceiling" else None

        with patch("weekends.insert_weekend_leg_price"), \
             patch("weekends.get_weekend_leg_price_history", return_value=history), \
             patch("weekends.get_last_weekend_leg_alert", side_effect=fake_last_alert) as mock_get_last, \
             patch("weekends.update_weekend_leg"), \
             patch("weekends.insert_weekend_leg_run_log"):
            report = weekends.process_weekend_leg(leg, SYSTEM_SETTINGS, SETTINGS_BY_USER, month_cache)

        decision = self.only(report)
        self.assertFalse(decision["is_ceiling_hit"])
        self.assertTrue(decision["is_opportunity_hit"])
        self.assertTrue(report["should_alert"])
        mock_get_last.assert_called_once_with("leg-out-1", "opportunity", USER_A)

    def test_same_type_recent_alert_still_blocks(self):
        # Regressão: cooldown do MESMO tipo continua funcionando.
        report, _ = self.run_process(
            150.0, history_prices=[155.0, 156.0],
            last_alerts_by_type={"ceiling": {"price": 150.0, "sent_at": iso_days_ago(0.1)}},
        )
        self.assertTrue(self.only(report)["is_ceiling_hit"])
        self.assertFalse(report["should_alert"])

    def test_composite_alert_blocked_only_when_both_types_in_cooldown(self):
        # Composto (teto E oportunidade): sai se PELO MENOS UM tipo estiver
        # liberado — só é segurado quando os DOIS estão em cooldown.
        report, _ = self.run_process(
            150.0, history_prices=[400.0],
            last_alerts_by_type={"ceiling": {"price": 150.0, "sent_at": iso_days_ago(0.1)}, "opportunity": None},
        )
        decision = self.only(report)
        self.assertTrue(decision["is_ceiling_hit"])
        self.assertTrue(decision["is_opportunity_hit"])
        self.assertTrue(report["should_alert"])  # oportunidade liberada -> sai

    def test_composite_alert_blocked_when_both_types_recently_alerted(self):
        report, _ = self.run_process(
            150.0, history_prices=[400.0],
            last_alerts_by_type={
                "ceiling": {"price": 150.0, "sent_at": iso_days_ago(0.1)},
                "opportunity": {"price": 150.0, "sent_at": iso_days_ago(0.1)},
            },
        )
        decision = self.only(report)
        self.assertTrue(decision["is_ceiling_hit"])
        self.assertTrue(decision["is_opportunity_hit"])
        self.assertFalse(report["should_alert"])


USER_B = "user-b"


class EvaluateLegMixin:
    """Ferramenta comum aos testes de avaliação por usuário: chama
    evaluate_and_record_leg_price direto — é o ponto onde o laço por usuário
    vive — com todo o I/O mockado."""

    SETTINGS_TWO_USERS = {
        USER_A: USER_SETTINGS,
        USER_B: USER_SETTINGS,
    }

    def evaluate(self, ceilings: dict, history_prices=None, last_alerts=None,
                 settings_by_user=None, system_settings=None, price=150.0):
        """Chama evaluate_and_record_leg_price direto — é o ponto onde o laço
        por usuário vive. `last_alerts` é {(user_id, tipo): linha}."""
        history = [{"price": p, "checked_at": "2026-08-01T10:00:00Z"} for p in (history_prices or [])]
        last_alerts = last_alerts or {}

        def fake_last_alert(leg_id, alert_type, user_id):
            return last_alerts.get((user_id, alert_type))

        leg = leg_with_users(OUTBOUND_LEG, ceilings)
        with patch("weekends.insert_weekend_leg_price") as mock_price, \
             patch("weekends.get_weekend_leg_price_history", return_value=history) as mock_history, \
             patch("weekends.get_last_weekend_leg_alert", side_effect=fake_last_alert) as mock_last, \
             patch("weekends.update_weekend_leg") as mock_update, \
             patch("weekends.insert_weekend_leg_run_log") as mock_run_log:
            report = weekends.evaluate_and_record_leg_price(
                leg, system_settings or SYSTEM_SETTINGS,
                settings_by_user if settings_by_user is not None else self.SETTINGS_TWO_USERS,
                price, "GIG", None, 0, "live",
            )
        return report, {
            "price": mock_price, "history": mock_history, "last_alert": mock_last,
            "update": mock_update, "run_log": mock_run_log,
        }

    def by_user(self, report: dict) -> dict:
        return {u["user_id"]: u for u in report["per_user"]}


class PerUserEvaluationTest(EvaluateLegMixin, unittest.TestCase):
    """Fatia D4 (15/08/2026): a decisão de alertar passa a ser tomada POR
    USUÁRIO — cada um com seu teto, seus limiares e seu cooldown — SEM que
    nenhuma consulta de preço cresça com o número de usuários."""

    # --- D-1: o custo por perna NÃO cresce com o número de usuários -------

    def test_two_users_do_not_multiply_the_per_leg_work(self):
        """O ponto central da fatia: 2 usuários, os DOIS alertando, e mesmo
        assim uma gravação de preço, uma leitura de histórico, uma atualização
        de perna e um run_log. O leque abre na decisão, não na consulta."""
        report, mocks = self.evaluate({USER_A: 300, USER_B: 180}, history_prices=[400.0])
        self.assertEqual(len(report["per_user"]), 2)
        self.assertTrue(all(u["should_alert"] for u in report["per_user"]))
        mocks["price"].assert_called_once()
        mocks["history"].assert_called_once()
        mocks["update"].assert_called_once()
        mocks["run_log"].assert_called_once()

    def test_per_user_is_ordered_by_user_id(self):
        # Nem get_effective_leg_state nem get_all_weekend_legs pedem `order`,
        # então a ordem da mensagem não pode depender da ordem do banco.
        report, _ = self.evaluate({USER_B: 180, USER_A: 300})
        self.assertEqual([u["user_id"] for u in report["per_user"]], [USER_A, USER_B])

    # --- teto próprio de cada um ------------------------------------------

    def test_each_user_is_judged_against_their_own_ceiling(self):
        # preço 150: bate o teto de user-a (300) e não o de user-b (100).
        report, _ = self.evaluate({USER_A: 300, USER_B: 100}, history_prices=[155.0, 156.0])
        decisions = self.by_user(report)
        self.assertTrue(decisions[USER_A]["is_ceiling_hit"])
        self.assertTrue(decisions[USER_A]["should_alert"])
        self.assertFalse(decisions[USER_B]["is_ceiling_hit"])
        self.assertFalse(decisions[USER_B]["should_alert"])
        # O agregado existe para dedupe/resumo e é o OU das decisões.
        self.assertTrue(report["should_alert"])

    def test_user_without_ceiling_still_gets_opportunity_but_never_ceiling(self):
        """Contraparte da regra de chaveamento por presença: o usuário sem teto
        não some, e é avaliado — só a regra de teto não roda para ele."""
        report, _ = self.evaluate({USER_A: 300, USER_B: None}, history_prices=[400.0])
        decisions = self.by_user(report)
        self.assertIsNone(decisions[USER_B]["ceiling"])
        self.assertFalse(decisions[USER_B]["is_ceiling_hit"])
        self.assertTrue(decisions[USER_B]["is_opportunity_hit"])
        self.assertTrue(decisions[USER_B]["should_alert"])
        self.assertTrue(decisions[USER_A]["is_ceiling_hit"])
        self.assertTrue(decisions[USER_A]["is_opportunity_hit"])
        # E a perna NÃO foi lida como degradada.
        self.assertIsNone(report["degraded_alert"])

    def test_each_user_uses_their_own_opportunity_threshold(self):
        settings = {
            USER_A: {**USER_SETTINGS, "weekend_opportunity_pct": 15},
            USER_B: {**USER_SETTINGS, "weekend_opportunity_pct": 80},
        }
        # avg 200, preço 150 => 25% abaixo: passa o limiar de 15%, não o de 80%.
        report, _ = self.evaluate(
            {USER_A: 100, USER_B: 100}, history_prices=[200.0], settings_by_user=settings
        )
        decisions = self.by_user(report)
        self.assertTrue(decisions[USER_A]["is_opportunity_hit"])
        self.assertFalse(decisions[USER_B]["is_opportunity_hit"])

    def test_user_without_settings_row_falls_back_to_defaults(self):
        # Mesmo padrão defensivo de main.py: usuário na view sem linha em
        # settings não derruba a avaliação nem é silenciado.
        report, _ = self.evaluate(
            {USER_A: 300}, history_prices=[400.0], settings_by_user={}
        )
        self.assertEqual(len(report["per_user"]), 1)
        self.assertTrue(report["per_user"][0]["should_alert"])

    # --- cooldown próprio -------------------------------------------------

    def test_cooldown_of_one_user_does_not_silence_the_other(self):
        report, _ = self.evaluate(
            {USER_A: 300, USER_B: 300}, history_prices=[155.0, 156.0],
            last_alerts={(USER_A, "ceiling"): {"price": 150.0, "sent_at": iso_days_ago(0.1)}},
        )
        decisions = self.by_user(report)
        self.assertFalse(decisions[USER_A]["should_alert"])  # em cooldown
        self.assertTrue(decisions[USER_B]["should_alert"])   # nunca alertou

    def test_cooldown_matrix_user_times_type(self):
        """D2 × D4 num caso só: user-a em cooldown de teto e user-b em cooldown
        de oportunidade, com um alerta composto. Cada um só é segurado pelo
        tipo que ele já recebeu — e, como o outro tipo está liberado para os
        dois, os dois alertam (regra `all(blocks)` da D2, agora por usuário)."""
        recent = {"price": 150.0, "sent_at": iso_days_ago(0.1)}
        report, _ = self.evaluate(
            {USER_A: 300, USER_B: 300}, history_prices=[400.0],
            last_alerts={(USER_A, "ceiling"): recent, (USER_B, "opportunity"): recent},
        )
        decisions = self.by_user(report)
        for user in (USER_A, USER_B):
            self.assertTrue(decisions[user]["is_ceiling_hit"])
            self.assertTrue(decisions[user]["is_opportunity_hit"])
            self.assertTrue(decisions[user]["should_alert"])

    def test_cooldown_of_both_types_blocks_that_user_only(self):
        recent = {"price": 150.0, "sent_at": iso_days_ago(0.1)}
        report, _ = self.evaluate(
            {USER_A: 300, USER_B: 300}, history_prices=[400.0],
            last_alerts={(USER_A, "ceiling"): recent, (USER_A, "opportunity"): recent},
        )
        decisions = self.by_user(report)
        self.assertFalse(decisions[USER_A]["should_alert"])
        self.assertTrue(decisions[USER_B]["should_alert"])


class DegradedLegEvaluationTest(EvaluateLegMixin, unittest.TestCase):
    """Modo degradado (`perna sem dono`: nenhum usuário em `settings`, a view
    volta vazia). O alerta de oportunidade CONTINUA saindo — é o contrato que
    build_no_effective_ceiling_message anuncia — mas por um caminho próprio,
    sem entrada sentinela em `per_user` e sem gravar em alert_log."""

    def test_alert_goes_out_and_nothing_is_recorded_or_consulted(self):
        report, mocks = self.evaluate({}, history_prices=[400.0], settings_by_user={})
        self.assertEqual(report["per_user"], [])
        self.assertIsNotNone(report["degraded_alert"])
        self.assertTrue(report["should_alert"])
        self.assertIsNone(report["degraded_alert"]["ceiling"])
        self.assertFalse(report["degraded_alert"]["is_ceiling_hit"])
        self.assertTrue(report["degraded_alert"]["is_opportunity_hit"])
        # Sem dono, não há cooldown para consultar nem linha para gravar —
        # gravar NULL criaria um terceiro significado para alert_log.user_id.
        mocks["last_alert"].assert_not_called()

    def test_the_price_is_still_recorded_in_degraded_mode(self):
        # O histórico é o ativo que não dá pra recuperar depois: a COLETA nunca
        # é afetada pela falta de usuário.
        _, mocks = self.evaluate({}, history_prices=[400.0], settings_by_user={})
        mocks["price"].assert_called_once()
        mocks["update"].assert_called_once()
        mocks["run_log"].assert_called_once()

    def test_buying_window_still_applies_without_an_owner(self):
        """A janela de compra (Fatia D1, em produção desde 12/08/2026) não é
        negociável: o modo degradado não pode reabrir alerta para fim de
        semana anterior ao corte."""
        outside = {**SYSTEM_SETTINGS, "weekend_buying_cutoff_date": "2027-01-29"}
        report, _ = self.evaluate(
            {}, history_prices=[400.0], settings_by_user={}, system_settings=outside
        )
        self.assertIsNone(report["degraded_alert"])
        self.assertFalse(report["should_alert"])

    def test_buying_window_inside_cutoff_still_produces_in_degraded_mode(self):
        # Par simétrico do teste acima: sem o corte no caminho, o alerta sai.
        inside = {**SYSTEM_SETTINGS, "weekend_buying_cutoff_date": "2026-09-04"}
        report, _ = self.evaluate(
            {}, history_prices=[400.0], settings_by_user={}, system_settings=inside
        )
        self.assertIsNotNone(report["degraded_alert"])

    def test_suspicious_price_still_blocks_without_an_owner(self):
        report, _ = self.evaluate(
            {}, history_prices=[1000.0, 1010.0, 990.0, 1005.0, 995.0], settings_by_user={}
        )
        self.assertTrue(report["suspicious"])
        self.assertIsNone(report["degraded_alert"])
        self.assertFalse(report["should_alert"])


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
            reports = weekends.process_all_weekend_legs(SYSTEM_SETTINGS, SETTINGS_BY_USER)

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
            reports = weekends.process_all_weekend_legs(SYSTEM_SETTINGS, SETTINGS_BY_USER)

        by_id = {r["leg"]["id"]: r for r in reports}
        self.assertEqual(by_id["leg-out-1"]["status"], "error")
        self.assertEqual(by_id["leg-out-2"]["status"], "ok")

    def test_individual_leg_failure_does_not_crash_others(self):
        leg2 = {**OUTBOUND_LEG, "id": "leg-out-2", "weekend_id": "wknd-2"}

        def fake_process(leg, system_settings, settings_by_user, cache):
            if leg["id"] == "leg-out-2":
                raise RuntimeError("falha simulada")
            return {"leg": leg, "status": "ok", "price": 300.0}

        with patch("weekends.get_active_legs", return_value=[OUTBOUND_LEG, leg2]), \
             patch("weekends.fetch_leg_month_entries", return_value=[entry(300.0, "2026-09-04")]), \
             patch("weekends.process_weekend_leg", side_effect=fake_process), \
             patch("weekends.insert_weekend_leg_run_log") as mock_run_log, \
             patch("weekends.time.sleep", return_value=None):
            reports = weekends.process_all_weekend_legs(SYSTEM_SETTINGS, SETTINGS_BY_USER)

        self.assertEqual(reports[0]["status"], "ok")
        self.assertEqual(reports[1]["status"], "error")
        mock_run_log.assert_called_once()

    def test_no_legs_returns_empty_without_any_fetch(self):
        with patch("weekends.get_active_legs", return_value=[]), \
             patch("weekends.fetch_leg_month_entries") as mock_fetch:
            reports = weekends.process_all_weekend_legs(SYSTEM_SETTINGS, SETTINGS_BY_USER)
        self.assertEqual(reports, [])
        mock_fetch.assert_not_called()


class SuppressAlertTest(unittest.TestCase):
    """Radar de calendário, decisão 1 — refresh de metadado (live_check.py,
    regime 'metadata') não pode virar alerta. `suppress_alert=True` grava
    preço/companhia/horário e atualiza a perna normalmente, mas retorna
    ANTES de qualquer avaliação de teto/oportunidade — nem histórico de
    90d, nem suspeita, nem janela de compra, nem laço por usuário."""

    def call(self, **overrides):
        kwargs = dict(
            leg=OUTBOUND_LEG, system_settings=SYSTEM_SETTINGS, settings_by_user=SETTINGS_BY_USER,
            price=150.0, airport="GIG", variant=None, transfers=0, source="live",
            airline="GOL", departure_time="2026-09-04T07:00:00", suppress_alert=True,
        )
        kwargs.update(overrides)
        with patch("weekends.insert_weekend_leg_price") as mock_insert, \
             patch("weekends.get_weekend_leg_price_history") as mock_history, \
             patch("weekends.update_weekend_leg") as mock_update, \
             patch("weekends.insert_weekend_leg_run_log") as mock_run_log:
            report = weekends.evaluate_and_record_leg_price(**kwargs)
        return report, mock_insert, mock_history, mock_update, mock_run_log

    def test_records_price_and_updates_leg(self):
        report, mock_insert, _, mock_update, mock_run_log = self.call()
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["price"], 150.0)
        mock_insert.assert_called_once_with(
            "leg-out-1", 150.0, "GIG", None, "live", 0, "GOL", "2026-09-04T07:00:00"
        )
        mock_update.assert_called_once()
        update_fields = mock_update.call_args.kwargs
        self.assertEqual(update_fields["current_price"], 150.0)
        self.assertEqual(update_fields["current_airline"], "GOL")
        mock_run_log.assert_called_once_with("leg-out-1", "ok", price=150.0, source="live")

    def test_never_evaluates_ceiling(self):
        """Se avaliasse teto, R$150 < R$200 dispararia alerta — a prova de
        que a avaliação nem roda é o histórico nunca ser lido."""
        report, _, mock_history, _, _ = self.call()
        mock_history.assert_not_called()
        self.assertEqual(report["per_user"], [])
        self.assertIsNone(report["degraded_alert"])
        self.assertFalse(report["should_alert"])
        self.assertTrue(report["alert_suppressed"])

    def test_records_new_low_when_price_is_lower(self):
        leg = {**OUTBOUND_LEG, "lowest_seen": 300.0}
        _, _, _, mock_update, _ = self.call(leg=leg, price=150.0)
        self.assertEqual(mock_update.call_args.kwargs["lowest_seen"], 150.0)

    def test_does_not_lower_lowest_seen_when_price_is_higher(self):
        leg = {**OUTBOUND_LEG, "lowest_seen": 100.0}
        _, _, _, mock_update, _ = self.call(leg=leg, price=150.0)
        self.assertNotIn("lowest_seen", mock_update.call_args.kwargs)

    def test_default_suppress_alert_is_false_and_evaluates_normally(self):
        """Sem passar suppress_alert (todo o resto do código): comportamento
        idêntico ao de antes desta fatia — histórico É lido."""
        with patch("weekends.insert_weekend_leg_price"), \
             patch("weekends.get_weekend_leg_price_history", return_value=[]) as mock_history, \
             patch("weekends.get_last_weekend_leg_alert", return_value=None), \
             patch("weekends.update_weekend_leg"), \
             patch("weekends.insert_weekend_leg_run_log"):
            report = weekends.evaluate_and_record_leg_price(
                OUTBOUND_LEG, SYSTEM_SETTINGS, SETTINGS_BY_USER, 150.0, "GIG", None, 0, "live",
            )
        mock_history.assert_called_once()
        self.assertFalse(report["alert_suppressed"])


if __name__ == "__main__":
    unittest.main()
