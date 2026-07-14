import { supabase } from './supabase-client.js';
import { requireAuth, wireLogout } from './auth-guard.js';
import { loadAirports, findByIata } from './airports.js';
import { buyingWindowAdvice } from './buying-window.js';

const DEFAULT_SETTINGS = {
  window_3d_pct: 10,
  window_7d_pct: 15,
  notification_mode: 'alert_only',
  cost_per_thousand_brl: 25,
};

function isGoodPrice(price, historyPrices, targetPrice, targetPercent) {
  if (targetPrice != null && price <= targetPrice) return true;
  if (targetPercent != null && historyPrices.length) {
    const avg = historyPrices.reduce((a, b) => a + b, 0) / historyPrices.length;
    if (price <= avg * (1 - targetPercent / 100)) return true;
  }
  return false;
}

function detectTrend(history, window3dPct, window7dPct) {
  if (history.length < 2) return null;
  const current = history[history.length - 1].price;
  const past = history.slice(0, -1);
  for (const [days, pct] of [[3, window3dPct], [7, window7dPct]]) {
    if (!past.length) continue;
    const idx = Math.max(0, past.length - days);
    const ref = past[idx].price;
    if (ref <= 0) continue;
    const changePct = ((current - ref) / ref) * 100;
    if (Math.abs(changePct) >= pct) return changePct > 0 ? 'up' : 'down';
  }
  return null;
}

function formatDateBr(iso) {
  if (!iso) return '?';
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
}

function stopsLabel(stops) {
  if (stops == null) return null;
  if (stops === 0) return 'voo direto';
  if (stops === 1) return '1 escala';
  return `${stops} escalas`;
}

function aviasalesLink(origin, destination, departDate, returnDate) {
  const ddmm = (iso) => `${iso.slice(8, 10)}${iso.slice(5, 7)}`;
  let leg = `${origin}${ddmm(departDate)}${destination}`;
  if (returnDate) leg += ddmm(returnDate);
  return `https://www.aviasales.com/search/${leg}1`;
}

function renderCard(route, history, settings, isDomestic, lastOutcome) {
  const card = document.createElement('div');
  card.className = 'card';

  const prices = history.map((h) => Number(h.price));
  const latestRow = history.length ? history[history.length - 1] : null;
  const latest = latestRow ? Number(latestRow.price) : null;
  const good = latest != null && isGoodPrice(latest, prices, route.target_price, route.target_percent_below_avg);
  const trend = detectTrend(
    history.map((h) => ({ ...h, price: Number(h.price) })),
    settings.window_3d_pct,
    settings.window_7d_pct
  );

  const badgeClass = good ? 'good' : trend === 'up' ? 'warn' : trend === 'down' ? 'info' : 'neutral';
  const badgeText = good ? 'Bom preço' : trend === 'up' ? 'Alta de preço' : trend === 'down' ? 'Queda de preço' : 'Normal';
  const advice = buyingWindowAdvice(history, isDomestic);

  let emptyMessage = 'Aguardando a primeira execução do robô (roda diariamente às 08:00).';
  if (latest == null && lastOutcome === 'no_data') {
    emptyMessage = 'Sem cobertura de dados de ida e volta na fonte (Aviasales) para esta rota até agora — o robô continua tentando diariamente.';
  }

  let flightLine = '';
  if (latestRow && latestRow.flight_date) {
    let text = `Ida ${formatDateBr(latestRow.flight_date)}`;
    if (latestRow.return_date) text += ` → Volta ${formatDateBr(latestRow.return_date)}`;
    const stops = stopsLabel(latestRow.stops);
    if (stops) text += ` · ${stops}`;
    const link = aviasalesLink(route.origin, route.destination, latestRow.flight_date, latestRow.return_date);
    flightLine = `<div class="price-meta">${text} · <a href="${link}" target="_blank" rel="noopener">ver na Aviasales</a></div>`;
  }

  card.innerHTML = `
    <h3>${route.origin} → ${route.destination}</h3>
    ${latest != null ? `
      <span class="badge ${badgeClass}">${badgeText}</span>
      <div class="price">${route.currency} ${latest.toFixed(2)}</div>
      ${flightLine}
      <div class="price-meta">meta: ${route.target_price ?? '—'} · ${route.target_percent_below_avg ?? '—'}% abaixo da média · estadia: ${route.trip_duration_weeks ? route.trip_duration_weeks + ' semana(s)' : 'sem restrição'}</div>
      <canvas height="120"></canvas>
    ` : `<p class="price-meta">${emptyMessage}</p>`}
    <div class="advisory ${advice.personalized ? 'personalized' : ''}">${advice.text}</div>
  `;

  if (latest != null) {
    const canvas = card.querySelector('canvas');
    new Chart(canvas, {
      type: 'line',
      data: {
        labels: history.map((h) => h.checked_at.slice(0, 10)),
        datasets: [{
          data: prices,
          borderColor: '#2563eb',
          backgroundColor: 'rgba(37,99,235,0.08)',
          fill: true,
          tension: 0.25,
          pointRadius: 2,
        }],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: { x: { display: false }, y: { display: true, ticks: { font: { size: 10 } } } },
      },
    });
  }

  return card;
}

async function exportCsv(routes) {
  const routeById = Object.fromEntries(routes.map((r) => [r.id, r]));
  const { data: rows, error } = await supabase
    .from('price_history')
    .select('route_id, checked_at, flight_date, return_date, stops, days_ahead, price, currency')
    .order('checked_at', { ascending: true });
  if (error) {
    alert('Erro ao exportar: ' + error.message);
    return;
  }

  const header = 'rota,consultado_em,data_ida,data_volta,escalas,dias_antecedencia,preco,moeda';
  const lines = (rows || []).map((r) => {
    const route = routeById[r.route_id];
    const label = route ? `${route.origin}-${route.destination}` : r.route_id;
    return [label, r.checked_at, r.flight_date ?? '', r.return_date ?? '', r.stops ?? '', r.days_ahead ?? '', r.price, r.currency].join(',');
  });

  const blob = new Blob([[header, ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `flyiop-historico-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

const session = await requireAuth();
if (session) {
  wireLogout('logout');

  const [{ data: routes }, { data: settingsRows }, airports, { data: lastRunRows }] = await Promise.all([
    supabase.from('routes').select('*').eq('archived', false).order('created_at'),
    supabase.from('settings').select('*').eq('user_id', session.user.id).limit(1),
    loadAirports(),
    supabase.from('run_log').select('ran_at').order('ran_at', { ascending: false }).limit(1),
  ]);
  const settings = settingsRows && settingsRows[0] ? settingsRows[0] : DEFAULT_SETTINGS;

  document.getElementById('notification-mode').textContent = settings.notification_mode;
  if (lastRunRows && lastRunRows[0]) {
    const ranAt = new Date(lastRunRows[0].ran_at);
    document.getElementById('last-run').textContent =
      `última verificação do robô: ${ranAt.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}`;
  }

  document.getElementById('export-csv').addEventListener('click', () => exportCsv(routes || []));

  const grid = document.getElementById('routes-grid');
  const empty = document.getElementById('empty-state');

  if (!routes || routes.length === 0) {
    empty.style.display = 'block';
  } else {
    for (const route of routes) {
      const [{ data: history }, { data: lastOutcomeRows }] = await Promise.all([
        supabase
          .from('price_history')
          .select('checked_at, flight_date, return_date, stops, price')
          .eq('route_id', route.id)
          .order('checked_at', { ascending: true }),
        supabase
          .from('run_log')
          .select('outcome')
          .eq('route_id', route.id)
          .order('ran_at', { ascending: false })
          .limit(1),
      ]);

      const originAirport = findByIata(airports, route.origin);
      const destinationAirport = findByIata(airports, route.destination);
      const isDomestic = originAirport?.country === 'Brazil' && destinationAirport?.country === 'Brazil';
      const lastOutcome = lastOutcomeRows && lastOutcomeRows[0] ? lastOutcomeRows[0].outcome : null;

      grid.appendChild(renderCard(route, history || [], settings, isDomestic, lastOutcome));
    }
  }
}
