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

# Fatia D1 (12/08/2026): system_config passou a incluir weekend_buying_cutoff_date.
# Usado no lugar de `None` nos testes que não são sobre a leitura de
# system_config em si — `None` agora dispara o aviso de fallback da janela de
# compra (build_buying_cutoff_fallback_message), o que quebraria as
# asserções estritas de "nenhuma mensagem"/"só esta mensagem" destes testes.
# O comportamento de degradação em si tem teste dedicado, mais abaixo
# (BuyingCutoffFallbackTest).
SYSTEM_CONFIG = {
    "suspicious_below_avg_pct": 50, "fast_flights_enabled": True,
    "fast_flights_daily_batch_size": 20, "weekend_buying_cutoff_date": "2026-01-01",
}


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
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
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
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
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
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
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
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
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


class SettingsAreNotCollapsedToOneUserTest(unittest.TestCase):
    """Fatia D4 (15/08/2026): a escolha de UM usuário para ditar os limiares
    gerais — último resquício provisório da Etapa 4.2, e o aviso de Telegram
    que a anunciava — foi EXTINTA. O que segue para as pernas são dois dicts
    com papéis distintos: `system_config` (sistema) e `settings_cache`
    (por usuário).

    A classe SharedSettingsChoiceTest, que cobria a escolha por menor
    `user_id`, foi removida junto com a regra."""

    ALL_SETTINGS = [
        {"user_id": "user-z", "notification_mode": "alert_only", "weekend_opportunity_pct": 99},
        {"user_id": "user-a", "notification_mode": "alert_only", "weekend_opportunity_pct": 15},
    ]

    def run_main(self, all_settings=None, routes=None):
        with patch("main.get_routes", return_value=routes or []), \
             patch("main.get_all_settings", return_value=all_settings or self.ALL_SETTINGS), \
             patch("main.get_settings", return_value=None), \
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
             patch("main.process_route", side_effect=lambda route, _s: {"route": route, "status": "no_data"}), \
             patch("main.process_all_weekend_legs", return_value=[]) as mock_cache, \
             patch("main.run_daily_batch", return_value=([], False)) as mock_batch, \
             patch("main.LEG_LOAD_DIAGNOSTICS", {"degraded_no_settings": False}), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=dict(SCRAPE_STATE_FRESH)), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send:
            mock_date.today.return_value.weekday.return_value = 2
            main.main()
        return mock_cache, mock_batch, mock_send

    def test_every_user_reaches_the_evaluation_not_just_the_lowest_id(self):
        mock_cache, _, _ = self.run_main()
        settings_by_user = mock_cache.call_args.args[1]
        self.assertEqual(sorted(settings_by_user), ["user-a", "user-z"])
        # Os limiares de CADA um chegam intactos — nada foi colapsado.
        self.assertEqual(settings_by_user["user-a"]["weekend_opportunity_pct"], 15)
        self.assertEqual(settings_by_user["user-z"]["weekend_opportunity_pct"], 99)

    def test_system_config_and_per_user_settings_travel_separately(self):
        mock_cache, mock_batch, _ = self.run_main()
        system_settings = mock_cache.call_args.args[0]
        self.assertEqual(system_settings["weekend_buying_cutoff_date"], "2026-01-01")
        self.assertNotIn("weekend_opportunity_pct", system_settings)  # é de usuário, não de sistema
        # O lote fli recebe exatamente os mesmos dois.
        self.assertEqual(mock_batch.call_args.args, mock_cache.call_args.args)

    def test_more_than_one_user_no_longer_warns_on_telegram(self):
        _, _, mock_send = self.run_main()
        mock_send.assert_not_called()

    def test_single_user_is_silent(self):
        _, _, mock_send = self.run_main([{"user_id": "user-a", "notification_mode": "alert_only"}])
        mock_send.assert_not_called()


class WeekendDiagnosticWarningsTest(unittest.TestCase):
    """Degradação que não pode seguir em silêncio: nenhum usuário em
    `settings`, ou seja, nenhum teto efetivo para comparar."""

    def run_main(self, diag):
        with patch("main.get_routes", return_value=[]), \
             patch("main.get_all_settings", return_value=[{"user_id": "user-a", "notification_mode": "alert_only"}]), \
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
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
        sent = self.run_main({"degraded_no_settings": True})
        matches = [m for m in sent if "Teto indisponível" in m]
        self.assertEqual(len(matches), 1)

    def test_healthy_run_sends_nothing(self):
        self.assertEqual(self.run_main({"degraded_no_settings": False}), [])


class WeekendAlertFanOutTest(unittest.TestCase):
    """Fatia D4 (15/08/2026): o leque abre no laço de envio, e SÓ nele — uma
    mensagem e uma linha em alert_log por (perna × usuário que disparou)."""

    ALL_SETTINGS = [
        {"user_id": "user-a", "notification_mode": "alert_only", "display_name": "Elton"},
        {"user_id": "user-b", "notification_mode": "alert_only"},
    ]

    def decision(self, user_id, ceiling, should_alert=True, ceiling_hit=True, opportunity_hit=False):
        return {
            "user_id": user_id, "ceiling": ceiling, "reason": f"razão de {user_id}",
            "is_ceiling_hit": ceiling_hit, "is_opportunity_hit": opportunity_hit,
            "should_alert": should_alert,
        }

    def run_main(self, weekend_reports, all_settings=None):
        with patch("main.get_routes", return_value=[]), \
             patch("main.get_all_settings", return_value=all_settings or self.ALL_SETTINGS), \
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
             patch("main.process_all_weekend_legs", return_value=weekend_reports), \
             patch("main.run_daily_batch", return_value=([], False)), \
             patch("main.LEG_LOAD_DIAGNOSTICS", {"degraded_no_settings": False}), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=dict(SCRAPE_STATE_FRESH)), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send, \
             patch("main.insert_weekend_alert_log") as mock_insert, \
             patch("main.build_package_comparison", return_value=None), \
             patch("main.build_weekend_alert_message",
                   side_effect=lambda r, d, label, c=None: f"msg:{d.get('user_id')}:{label}"):
            mock_date.today.return_value.weekday.return_value = 2
            main.main()
        return mock_send, mock_insert

    def test_two_users_get_two_messages_and_two_rows_with_distinct_owners(self):
        report = {
            "leg": {"id": "leg-1"}, "status": "ok", "price": 150.0, "should_alert": True,
            "degraded_alert": None,
            "per_user": [self.decision("user-a", 300), self.decision("user-b", 180)],
        }
        mock_send, mock_insert = self.run_main([report])

        self.assertEqual(mock_send.call_count, 2)
        self.assertEqual(mock_insert.call_count, 2)
        owners = [c.kwargs["user_id"] for c in mock_insert.call_args_list]
        self.assertEqual(owners, ["user-a", "user-b"])
        # A razão gravada é a DAQUELE usuário, não uma razão do report.
        self.assertEqual([c.args[2] for c in mock_insert.call_args_list],
                         ["razão de user-a", "razão de user-b"])

    def test_the_name_in_each_message_is_that_users_label(self):
        report = {
            "leg": {"id": "leg-1"}, "status": "ok", "price": 150.0, "should_alert": True,
            "degraded_alert": None,
            "per_user": [self.decision("user-a", 300), self.decision("user-b", 180)],
        }
        mock_send, _ = self.run_main([report])
        sent = [c.args[0] for c in mock_send.call_args_list]
        # user-a tem display_name; user-b cai nos 8 primeiros chars do id.
        self.assertEqual(sent, ["msg:user-a:Elton", "msg:user-b:user-b"])

    def test_user_not_alerting_gets_neither_message_nor_row(self):
        report = {
            "leg": {"id": "leg-1"}, "status": "ok", "price": 150.0, "should_alert": True,
            "degraded_alert": None,
            "per_user": [self.decision("user-a", 300), self.decision("user-b", 100, should_alert=False)],
        }
        mock_send, mock_insert = self.run_main([report])
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual([c.kwargs["user_id"] for c in mock_insert.call_args_list], ["user-a"])

    def test_one_users_insert_failure_does_not_cancel_the_other(self):
        report = {
            "leg": {"id": "leg-1"}, "status": "ok", "price": 150.0, "should_alert": True,
            "degraded_alert": None,
            "per_user": [self.decision("user-a", 300), self.decision("user-b", 180)],
        }
        with patch("main.get_routes", return_value=[]), \
             patch("main.get_all_settings", return_value=self.ALL_SETTINGS), \
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
             patch("main.process_all_weekend_legs", return_value=[report]), \
             patch("main.run_daily_batch", return_value=([], False)), \
             patch("main.LEG_LOAD_DIAGNOSTICS", {"degraded_no_settings": False}), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=dict(SCRAPE_STATE_FRESH)), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send, \
             patch("main.insert_weekend_alert_log",
                   side_effect=[RuntimeError("400 do PostgREST"), None]) as mock_insert, \
             patch("main.build_package_comparison", return_value=None), \
             patch("main.build_weekend_alert_message", return_value="msg"):
            mock_date.today.return_value.weekday.return_value = 2
            with self.assertRaises(SystemExit) as ctx:
                main.main()

        self.assertEqual(ctx.exception.code, 1)   # had_error -> exit 1, visível no Actions
        self.assertEqual(mock_send.call_count, 2)
        self.assertEqual(mock_insert.call_count, 2)

    # --- modo degradado: mensagem sai, nada é gravado ---------------------

    def test_degraded_leg_alerts_without_writing_to_alert_log(self):
        report = {
            "leg": {"id": "leg-1"}, "status": "ok", "price": 150.0, "should_alert": True,
            "per_user": [],
            "degraded_alert": {"ceiling": None, "reason": "20% abaixo da média",
                               "is_ceiling_hit": False, "is_opportunity_hit": True},
        }
        mock_send, mock_insert = self.run_main([report], all_settings=[])
        self.assertEqual(mock_send.call_count, 1)
        # Sem dono não há o que gravar — e gravar NULL colidiria com a marca
        # d'água da D3, que separa "linha antiga" de "gravação que falhou".
        mock_insert.assert_not_called()

    def test_degraded_leg_message_has_no_user_label(self):
        report = {
            "leg": {"id": "leg-1"}, "status": "ok", "price": 150.0, "should_alert": True,
            "per_user": [],
            "degraded_alert": {"ceiling": None, "reason": "20% abaixo da média",
                               "is_ceiling_hit": False, "is_opportunity_hit": True},
        }
        mock_send, _ = self.run_main([report], all_settings=[])
        self.assertEqual(mock_send.call_args.args[0], "msg:None:None")

    # --- o agregado é o que mantém dedupe/resumo funcionando --------------

    def test_aggregate_should_alert_survives_dedupe(self):
        """`dedupe_weekend_reports` e o resumo semanal não sabem nada sobre
        usuários — leem só o agregado. Cache e live acham a mesma perna; fica
        1 report (o live), e o fan-out dele sai inteiro."""
        leg = {"id": "leg-1"}
        cache_report = {
            "leg": leg, "status": "ok", "source": "cache", "price": 400.0, "should_alert": False,
            "degraded_alert": None, "per_user": [self.decision("user-a", 300, should_alert=False)],
        }
        live_report = {
            "leg": leg, "status": "ok", "source": "live", "price": 150.0, "should_alert": True,
            "degraded_alert": None,
            "per_user": [self.decision("user-a", 300), self.decision("user-b", 180)],
        }
        deduped = main.dedupe_weekend_reports([cache_report, live_report])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["source"], "live")

        mock_send, mock_insert = self.run_main([cache_report, live_report])
        self.assertEqual(mock_send.call_count, 2)
        self.assertEqual([c.args[1] for c in mock_insert.call_args_list], [150.0, 150.0])


class RouteNotificationModeTest(unittest.TestCase):
    """Fatia D4 (D-4b): `notification_mode` das rotas passa a sair do DONO REAL
    da rota, como `freshness_hours` e `stale_alert_policy` já faziam. Era a
    única das três lendo do 'menor user_id', e perdeu a fonte quando a escolha
    única foi extinta."""

    def run_main(self, all_settings, routes, reports_by_route):
        with patch("main.get_routes", return_value=routes), \
             patch("main.get_all_settings", return_value=all_settings), \
             patch("main.get_settings", return_value=None), \
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
             patch("main.process_route", side_effect=lambda route, _s: reports_by_route[route["id"]]), \
             patch("main.process_all_weekend_legs", return_value=[]), \
             patch("main.run_daily_batch", return_value=([], False)), \
             patch("main.LEG_LOAD_DIAGNOSTICS", {"degraded_no_settings": False}), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=dict(SCRAPE_STATE_FRESH)), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send, \
             patch("main.insert_alert_log") as mock_insert, \
             patch("main.build_alert_message", side_effect=lambda r: f"alerta:{r['route']['id']}"), \
             patch("main.build_route_block", side_effect=lambda r: f"bloco:{r['route']['id']}"), \
             patch("main.build_summary_message", side_effect=lambda blocks, notes: f"resumo:{'+'.join(blocks)}"):
            mock_date.today.return_value.weekday.return_value = 2
            main.main()
        return mock_send, mock_insert

    def ok_report(self, route):
        return {
            "route": route, "status": "ok", "should_alert": True, "price": 520.0,
            "reason": "abaixo da meta", "is_ceiling_alert": True, "is_opportunity_alert": False,
        }

    def test_each_owner_gets_the_format_they_chose(self):
        route_a = {"id": "rota-a", "user_id": "user-a", "origin": "BSB", "destination": "GIG"}
        route_b = {"id": "rota-b", "user_id": "user-b", "origin": "GIG", "destination": "BSB"}
        all_settings = [
            {"user_id": "user-a", "notification_mode": "alert_only"},
            {"user_id": "user-b", "notification_mode": "daily_summary"},
        ]
        mock_send, mock_insert = self.run_main(
            all_settings, [route_a, route_b],
            {"rota-a": self.ok_report(route_a), "rota-b": self.ok_report(route_b)},
        )
        sent = [c.args[0] for c in mock_send.call_args_list]
        self.assertIn("alerta:rota-a", sent)          # user-a pediu alerta individual
        self.assertIn("resumo:bloco:rota-b", sent)    # user-b pediu resumo diário
        self.assertNotIn("alerta:rota-b", sent)
        # Resumo diário nunca grava alert_log — só o caminho de alerta grava.
        self.assertEqual([c.args[0] for c in mock_insert.call_args_list], ["rota-a"])

    def test_single_user_behaviour_is_unchanged(self):
        route = {"id": "rota-1", "user_id": "user-a", "origin": "BSB", "destination": "GIG"}
        mock_send, mock_insert = self.run_main(
            [{"user_id": "user-a", "notification_mode": "alert_only"}], [route],
            {"rota-1": self.ok_report(route)},
        )
        self.assertEqual([c.args[0] for c in mock_send.call_args_list], ["alerta:rota-1"])
        mock_insert.assert_called_once()


class BuyingCutoffFallbackTest(unittest.TestCase):
    """Fatia D1 (12/08/2026), Decisão 4: se `system_config` não tem linha
    (get_system_config() -> None), o corte da janela de compra cai no
    fallback embutido — o filtro CONTINUA valendo, e main.py avisa 1x por
    execução, mesmo padrão dos avisos de estado provisório da Etapa 4.2."""

    def run_main(self, system_config):
        diag = {"degraded_no_settings": False}
        with patch("main.get_routes", return_value=[]), \
             patch("main.get_all_settings", return_value=[{"user_id": "user-a", "notification_mode": "alert_only"}]), \
             patch("main.get_system_config", return_value=system_config), \
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

    def test_missing_system_config_row_warns_once_with_fallback_value(self):
        sent = self.run_main(None)
        matches = [m for m in sent if "janela de compra" in m and "indisponível" in m]
        self.assertEqual(len(matches), 1)
        self.assertIn("29/01/2027", matches[0])  # valor de fallback, não inventado

    def test_configured_cutoff_sends_no_fallback_warning(self):
        sent = self.run_main(SYSTEM_CONFIG)
        matches = [m for m in sent if "janela de compra" in m and "indisponível" in m]
        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
