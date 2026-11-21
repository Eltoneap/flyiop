-- Desliga o Gustavo do monitoramento (sem alertas de preço, fora do fan-out e do resumo de segunda, nenhuma perna mantida ativa por ele). Login preservado. Só depois de sql/perna_dispensada_usuario_ativo.sql. Religar: sql/usuario_monitoramento_religar_gustavo.sql
update settings set monitoring_active = false where user_id = '2446ec67-06b8-478c-bc5d-6a17eab1fe76';
