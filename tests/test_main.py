"""Teste local da orquestração de main() — Parte 10 (28/07/2026), escalonamento
automático de frequência de scraping. Cobre especificamente o cenário mais
perigoso apontado na revisão do plano: bloqueio detectado exatamente no
último lote esperado do estágio atual (o mesmo instante em que a subida de
estágio seria avaliada) — o resultado final tem que ser sempre Estágio 0,
nunca uma subida no mesmo ciclo em que acabou de cair.

Correção de 30/07/2026: "último lote esperado do dia" deixou de ser "hora
bate com a última da lista do estágio" (bug real em produção — atraso de
cron do GitHub Actions caía fora de todos os horários e zerava a execução)
e passou a ser "quantos lotes já rodaram hoje" — os testes abaixo simulam
isso via `batches_run_today`/`last_batch_run_date` no estado, não mais via
`current_brt_hour`.

Usa as funções REAIS de scrape_schedule.py (não mockadas) — só I/O
(Supabase, fli, Telegram) é mockado — pra exercitar a ordem de verdade do
main.py, não uma reimplementação da lógica no teste.

Uso: python -m unittest tests/test_main.py -v  (a partir da raiz do repo)
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main  # noqa: E402

TODAY = "2026-07-30"


class BlockAtLastExpectedBatchTest(unittest.TestCase):
    def test_block_at_last_expected_batch_never_escalates_same_cycle(self):
        # Estágio 1 (2 lotes/dia), primária já rodou hoje, 1 dos 2 lotes já
        # rodou hoje — esta execução é a 2ª (última esperada). 4 dias limpos
        # acumulados (1 a menos pro degrau seguinte).
        scrape_state = {
            "stage": 1, "clean_days": 4, "blocked_today": False,
            "last_change_at": None, "last_change_reason": None,
            "last_primary_run_date": TODAY,
            "last_batch_run_date": TODAY, "batches_run_today": 1,
        }

        with patch("main.get_routes", return_value=[]), \
             patch("main.get_all_settings", return_value=[]), \
             patch("main.get_system_config", return_value=None), \
             patch("main.process_all_weekend_legs", return_value=[]), \
             patch("main.run_daily_batch", return_value=([], True)), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=scrape_state), \
             patch("main.set_weekend_scrape_state") as mock_set_state, \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send, \
             patch("main.build_stage_change_message", side_effect=lambda stage, reason: f"stage={stage}"):
            mock_date.today.return_value.weekday.return_value = 2  # quarta — sem resumo semanal
            main.main()

        # A ÚLTIMA gravação de estágio tem que ser 0 — nunca uma subida
        # depois da queda na mesma execução.
        stage_calls = [c.kwargs["stage"] for c in mock_set_state.call_args_list if "stage" in c.kwargs]
        self.assertTrue(stage_calls, "esperava pelo menos 1 gravação de estágio")
        self.assertEqual(stage_calls[-1], 0)
        self.assertNotIn(2, stage_calls)  # nunca chegou a considerar subir pro 2

        # Só 1 alerta de mudança de estágio (a queda) — nunca queda + subida.
        stage_change_sends = [c.args[0] for c in mock_send.call_args_list if c.args[0].startswith("stage=")]
        self.assertEqual(stage_change_sends, ["stage=0"])

    def test_no_block_at_last_expected_batch_does_escalate(self):
        # Controle: sem bloqueio, mesmo cenário (Estágio 1, 4 dias limpos,
        # último lote esperado) tem que subir pro Estágio 2 normalmente —
        # confirma que o teste acima falha por causa do bloqueio, não por
        # algum outro bug que sempre impede a subida.
        scrape_state = {
            "stage": 1, "clean_days": 4, "blocked_today": False,
            "last_change_at": None, "last_change_reason": None,
            "last_primary_run_date": TODAY,
            "last_batch_run_date": TODAY, "batches_run_today": 1,
        }

        with patch("main.get_routes", return_value=[]), \
             patch("main.get_all_settings", return_value=[]), \
             patch("main.get_system_config", return_value=None), \
             patch("main.process_all_weekend_legs", return_value=[]), \
             patch("main.run_daily_batch", return_value=([], False)), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=scrape_state), \
             patch("main.set_weekend_scrape_state") as mock_set_state, \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send, \
             patch("main.build_stage_change_message", side_effect=lambda stage, reason: f"stage={stage}"):
            mock_date.today.return_value.weekday.return_value = 2
            main.main()

        stage_calls = [c.kwargs["stage"] for c in mock_set_state.call_args_list if "stage" in c.kwargs]
        self.assertEqual(stage_calls[-1], 2)
        stage_change_sends = [c.args[0] for c in mock_send.call_args_list if c.args[0].startswith("stage=")]
        self.assertEqual(stage_change_sends, ["stage=2"])


class DelayedScheduleDoesNotNoOpTest(unittest.TestCase):
    """Reprodução direta do incidente de 30/07/2026 (runs #41/#42): a run
    dispara numa hora BRT que não bate com nenhum horário "esperado" (cron
    atrasado). Antes da correção isso zerava rotas, cache e lote fli
    silencialmente; agora só importa se já rodou hoje ou não."""

    def test_first_run_of_the_day_is_primary_and_runs_batch_no_matter_the_hour(self):
        scrape_state = {
            "stage": 0, "clean_days": 0, "blocked_today": False,
            "last_change_at": None, "last_change_reason": None,
            "last_primary_run_date": None,
            "last_batch_run_date": None, "batches_run_today": 0,
        }
        route = {"id": "rota-1", "user_id": "user-1", "origin": "BSB", "destination": "GIG"}

        with patch("main.get_routes", return_value=[route]), \
             patch("main.get_all_settings", return_value=[{"user_id": "user-1", "notification_mode": "alert_only"}]), \
             patch("main.get_settings", return_value={"notification_mode": "daily_summary"}), \
             patch("main.get_system_config", return_value=None), \
             patch("main.process_route") as mock_process_route, \
             patch("main.process_all_weekend_legs", return_value=[]) as mock_cache, \
             patch("main.run_daily_batch", return_value=([], False)) as mock_batch, \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=scrape_state), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message"), \
             patch("main.build_summary_message", return_value="resumo"):
            mock_process_route.return_value = {"route": route, "status": "no_data", "streak": 0}
            mock_date.today.return_value.weekday.return_value = 2
            main.main()

        # Mesmo caindo numa "hora errada" (não simulamos hour nenhum — é
        # justamente o ponto: não importa mais), rotas, cache e lote fli
        # rodam normalmente na primeira execução do dia.
        mock_process_route.assert_called_once()
        mock_cache.assert_called_once()
        mock_batch.assert_called_once()


class DuplicateFireSameDayIsIdempotentTest(unittest.TestCase):
    """Cenário (c) pedido na correção: se o Actions disparar a mesma janela
    (ou qualquer janela) duas vezes no mesmo dia, a segunda chamada não pode
    reprocessar rotas nem rodar lote fli de novo além da cota do estágio."""

    def test_second_call_same_day_skips_primary_and_batch_already_done(self):
        route = {"id": "rota-1", "user_id": "user-1", "origin": "BSB", "destination": "GIG"}
        # Estado como ficaria gravado depois de uma primeira execução bem
        # sucedida hoje: primária já rodou, 1 lote (cota do Estágio 0) já rodou.
        scrape_state_after_first_run = {
            "stage": 0, "clean_days": 0, "blocked_today": False,
            "last_change_at": None, "last_change_reason": None,
            "last_primary_run_date": TODAY,
            "last_batch_run_date": TODAY, "batches_run_today": 1,
        }

        with patch("main.get_routes", return_value=[route]), \
             patch("main.get_all_settings", return_value=[{"user_id": "user-1", "notification_mode": "alert_only"}]), \
             patch("main.get_settings", return_value={"notification_mode": "alert_only"}), \
             patch("main.get_system_config", return_value=None), \
             patch("main.process_route") as mock_process_route, \
             patch("main.process_all_weekend_legs") as mock_cache, \
             patch("main.run_daily_batch") as mock_batch, \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=scrape_state_after_first_run), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send:
            mock_date.today.return_value.weekday.return_value = 2
            main.main()

        mock_process_route.assert_not_called()
        mock_cache.assert_not_called()
        mock_batch.assert_not_called()
        mock_send.assert_not_called()


SCRAPE_STATE_FRESH = {
    "stage": 0, "clean_days": 0, "blocked_today": False,
    "last_change_at": None, "last_change_reason": None,
    "last_primary_run_date": None,
    "last_batch_run_date": None, "batches_run_today": 0,
}


class SharedSettingsChoiceTest(unittest.TestCase):
    """Etapa 4.2, pendência 7 (versão leve): a escolha de quem dita os limiares
    gerais deixa de ser implícita (`next(iter(...))`, ordem de dicionário) e
    passa a ser determinística e barulhenta — sobre TODOS os usuários com linha
    em `settings`, não só os que têm rota flexível."""

    def run_main(self, all_settings, routes=None, weekend_diag=None):
        diag = {"degraded_no_settings": False, "multi_user_ceiling_legs": 0}
        diag.update(weekend_diag or {})
        with patch("main.get_routes", return_value=routes or []), \
             patch("main.get_all_settings", return_value=all_settings), \
             patch("main.get_settings", return_value=None), \
             patch("main.get_system_config", return_value=None), \
             patch("main.process_route", side_effect=lambda route, _s: {"route": route, "status": "no_data"}), \
             patch("main.process_all_weekend_legs", return_value=[]), \
             patch("main.run_daily_batch", return_value=([], False)), \
             patch("main.LEG_LOAD_DIAGNOSTICS", diag), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=dict(SCRAPE_STATE_FRESH)), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send:
            mock_date.today.return_value.weekday.return_value = 2
            main.main()
        return mock_send

    def test_settings_choice_is_the_lowest_user_id_not_dictionary_order(self):
        # Ordem de chegada proposital: quem vem primeiro na lista NÃO é o
        # escolhido — a escolha é por user_id, não por ordem.
        all_settings = [
            {"user_id": "user-z", "notification_mode": "alert_only", "weekend_opportunity_pct": 99},
            {"user_id": "user-a", "notification_mode": "alert_only", "weekend_opportunity_pct": 15},
        ]
        with patch("main.get_routes", return_value=[]), \
             patch("main.get_all_settings", return_value=all_settings), \
             patch("main.get_system_config", return_value=None), \
             patch("main.process_all_weekend_legs", return_value=[]) as mock_cache, \
             patch("main.run_daily_batch", return_value=([], False)), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=dict(SCRAPE_STATE_FRESH)), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message"):
            mock_date.today.return_value.weekday.return_value = 2
            main.main()
        used_settings = mock_cache.call_args.args[0]
        self.assertEqual(used_settings["weekend_opportunity_pct"], 15)

    def test_more_than_one_user_warns_on_telegram(self):
        all_settings = [
            {"user_id": "user-a", "notification_mode": "alert_only"},
            {"user_id": "user-b", "notification_mode": "alert_only"},
        ]
        mock_send = self.run_main(all_settings)
        warnings = [c.args[0] for c in mock_send.call_args_list if "usuário" in c.args[0]]
        self.assertEqual(len(warnings), 1)
        self.assertIn("user-a", warnings[0])  # nomeia QUEM está ditando os limiares

    def test_single_user_is_silent(self):
        mock_send = self.run_main([{"user_id": "user-a", "notification_mode": "alert_only"}])
        mock_send.assert_not_called()

    def test_user_without_flexible_route_still_counts(self):
        """O furo que a pendência 7 corrige: settings_cache vinha de `routes`,
        então usuário só com pernas de fim de semana nunca entrava na conta e o
        aviso jamais disparava."""
        all_settings = [
            {"user_id": "user-a", "notification_mode": "alert_only"},
            {"user_id": "user-b", "notification_mode": "alert_only"},
        ]
        route = {"id": "rota-1", "user_id": "user-a", "origin": "BSB", "destination": "GIG"}
        mock_send = self.run_main(all_settings, routes=[route])
        self.assertTrue(any("usuário" in c.args[0] for c in mock_send.call_args_list))


class WeekendDiagnosticWarningsTest(unittest.TestCase):
    """Etapa 4.2: as duas situações provisórias que não podem seguir em
    silêncio — sem teto efetivo, e teto de mais de um usuário na mesma perna."""

    def run_main(self, diag):
        with patch("main.get_routes", return_value=[]), \
             patch("main.get_all_settings", return_value=[{"user_id": "user-a", "notification_mode": "alert_only"}]), \
             patch("main.get_system_config", return_value=None), \
             patch("main.process_all_weekend_legs", return_value=[]), \
             patch("main.run_daily_batch", return_value=([], False)), \
             patch("main.LEG_LOAD_DIAGNOSTICS", diag), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=dict(SCRAPE_STATE_FRESH)), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send:
            mock_date.today.return_value.weekday.return_value = 2
            main.main()
        return [c.args[0] for c in mock_send.call_args_list]

    def test_no_effective_ceiling_warns_once(self):
        sent = self.run_main({"degraded_no_settings": True, "multi_user_ceiling_legs": 0})
        matches = [m for m in sent if "Teto indisponível" in m]
        self.assertEqual(len(matches), 1)

    def test_multi_user_ceiling_warns_once_with_the_count(self):
        sent = self.run_main({"degraded_no_settings": False, "multi_user_ceiling_legs": 3})
        matches = [m for m in sent if "mesma perna" in m]
        self.assertEqual(len(matches), 1)
        self.assertIn("3 pernas", matches[0])

    def test_healthy_run_sends_nothing(self):
        self.assertEqual(self.run_main({"degraded_no_settings": False, "multi_user_ceiling_legs": 0}), [])


if __name__ == "__main__":
    unittest.main()
