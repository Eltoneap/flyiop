// Regra única de "fim de semana já passou" (19/11/2026, HISTORICO.md item 30).
// Usada pela aba Compras e, no próximo item da fila (STATE.md, seção 3), pelo
// resumo de compras do Dashboard — os dois têm que responder igual, então a
// regra mora só aqui. Só visual: nada aqui toca o banco.

const TZ = 'America/Sao_Paulo';

// 'YYYY-MM-DD' no fuso de São Paulo, independente do fuso do aparelho.
// (en-CA formata data como ISO.)
export function todaySaoPaulo(now = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(now);
}

// Data REAL da perna:
// - ida: a sexta do fim de semana;
// - volta comprada: a data do voo registrado na compra (snapshot do próprio
//   usuário, `purchased_departure_time`, convertido para o fuso de SP);
// - volta não comprada: a variante que o robô escolheu (domingo/segunda);
// - variante ainda indefinida: segunda, a mais tardia — nunca esconde cedo.
export function legTravelDate(leg, weekend) {
  if (leg.direction === 'outbound') return weekend.outbound_date;
  const bought = leg.purchased_snapshot?.purchased_departure_time;
  if (leg.status === 'purchased' && bought) {
    const d = new Date(bought);
    if (!Number.isNaN(d.getTime())) return todaySaoPaulo(d);
  }
  if (leg.current_variant === 'sunday') return weekend.return_sunday;
  return weekend.return_monday;
}

// Maior data entre as pernas do fim de semana. Sem pernas carregadas, cai na
// segunda (a data mais tardia possível do fim de semana).
export function weekendLastTravelDate(weekend) {
  const legs = weekend.weekend_legs || [];
  const dates = legs.map((leg) => legTravelDate(leg, weekend)).filter(Boolean);
  if (!dates.length) return weekend.return_monday;
  return dates.reduce((max, d) => (d > max ? d : max));
}

// Some no dia SEGUINTE à última perna; no próprio dia da viagem continua.
export function isWeekendPast(weekend, today = todaySaoPaulo()) {
  return weekendLastTravelDate(weekend) < today;
}
