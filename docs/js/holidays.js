// Feriados nacionais 2026/2027 (fixos + móveis calculados a partir da
// Páscoa) e a lógica de "feriado"/"alta temporada" por fim de semana —
// Parte 8 do plano ativo. Lista validada em 24/07/2026 (bate com o cálculo
// independente do usuário: 66 sextas, 24 fins de semana marcados).
//
// Regra de feriado: cai na quinta anterior à sexta (emenda), na sexta
// (ida), sábado, domingo (return_sunday), segunda (return_monday), ou na
// terça seguinte à segunda (emenda seguinte).
// Regra de alta temporada (rótulo separado, pode coexistir com feriado):
// julho inteiro (só 2027 — não há weekends monitorados em julho/2026),
// segunda quinzena de dezembro (dias 16-31), primeira quinzena de janeiro
// (dias 1-15).

const EASTER = { 2026: '2026-04-05', 2027: '2027-03-28' };

function parseISO(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function toISO(date) {
  return date.toISOString().slice(0, 10);
}

function addDays(iso, days) {
  const d = parseISO(iso);
  d.setUTCDate(d.getUTCDate() + days);
  return toISO(d);
}

function holidaysForYear(year) {
  const easter = EASTER[year];
  return {
    'Confraternização Universal': `${year}-01-01`,
    'Carnaval (segunda)': addDays(easter, -48),
    'Carnaval (terça)': addDays(easter, -47),
    'Sexta-feira Santa': addDays(easter, -2),
    'Tiradentes': `${year}-04-21`,
    'Dia do Trabalho': `${year}-05-01`,
    'Corpus Christi': addDays(easter, 60),
    'Independência do Brasil': `${year}-09-07`,
    'Nossa Senhora Aparecida': `${year}-10-12`,
    'Finados': `${year}-11-02`,
    'Proclamação da República': `${year}-11-15`,
    'Consciência Negra': `${year}-11-20`,
    'Natal': `${year}-12-25`,
  };
}

// Mapa data ISO -> nome do feriado, pros anos cobertos pelos 66 fins de semana.
const HOLIDAY_BY_DATE = {};
for (const year of Object.keys(EASTER).map(Number)) {
  const items = holidaysForYear(year);
  for (const [name, date] of Object.entries(items)) {
    HOLIDAY_BY_DATE[date] = name;
  }
}

// Retorna um array com 0, 1 ou 2 entradas ({ tag, motivo }) — um fim de
// semana pode ser feriado E alta temporada ao mesmo tempo (ex.: Natal cai
// na segunda quinzena de dezembro).
export function weekendTags(weekend) {
  const fri = weekend.outbound_date;
  const sun = weekend.return_sunday;
  const mon = weekend.return_monday;

  const thu = addDays(fri, -1);
  const sat = addDays(fri, 1);
  const tue = addDays(mon, 1);

  const motivos = [];
  const check = (date, label) => {
    if (HOLIDAY_BY_DATE[date]) motivos.push(`${label} = ${HOLIDAY_BY_DATE[date]}`);
  };
  check(thu, 'quinta anterior');
  check(fri, 'sexta');
  check(sat, 'sábado');
  check(sun, 'domingo');
  check(mon, 'segunda');
  check(tue, 'terça seguinte');

  const [friYear, friMonth, friDay] = fri.split('-').map(Number);
  const seasons = [];
  if (friYear === 2027 && friMonth === 7) seasons.push('julho');
  if (friMonth === 12 && friDay >= 16) seasons.push('2ª quinzena de dezembro');
  if (friMonth === 1 && friDay <= 15) seasons.push('1ª quinzena de janeiro');

  const tags = [];
  if (motivos.length) tags.push({ tag: 'feriado', motivo: motivos.join('; ') });
  if (seasons.length) tags.push({ tag: 'alta_temporada', motivo: seasons.join(', ') });
  return tags;
}
