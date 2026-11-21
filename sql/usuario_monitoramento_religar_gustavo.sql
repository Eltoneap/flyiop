-- Religa o Gustavo no monitoramento (volta à fila, ao fan-out de alertas e ao resumo de segunda, com as decisões por perna que ele já tinha).
update settings set monitoring_active = true where user_id = '2446ec67-06b8-478c-bc5d-6a17eab1fe76';
