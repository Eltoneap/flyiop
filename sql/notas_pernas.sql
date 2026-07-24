-- Campo de observações livres por perna (localizador, horário etc.), preenchido
-- manualmente no painel de Compras depois da compra. Sem default: vazio até o usuário escrever.
alter table weekend_legs add column notes text;
