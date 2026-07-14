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

function renderCard(route, history, settings, isDomestic) {
  const card = document.createElement('div');
  card.className = 'card';

  const prices = history.map((h) => Number(h.price));
  const latest = prices.length ? prices[prices.length - 1] : null;
  const good = latest != null && isGoodPrice(latest, prices, route.target_price, route.target_percent_below_avg);
  const trend = detectTrend(
    history.map((h) => ({ ...h, price: Number(h.price) })),
    settings.window_3d_pct,
    settings.window_7d_pct
  );

  const badgeClass = good ? 'good' : trend === 'up' ? 'warn' : trend === 'down' ? 'info' : 'neutral';
  const badgeText = good ? 'Bom preço' : trend === 'up' ? 'Alta de preço' : trend === 'down' ? 'Queda de preço' : 'Normal';
  const advice = buyingWindowAdvice(history, isDomestic);

  card.innerHTML = `
    <h3>${route.origin} → ${route.destination}</h3>
    ${latest != null ? `
      <span class="badge ${badgeClass}">${badgeText}</span>
      <div class="price">${route.currency} ${latest.toFixed(2)}</div>
      <div class="price-meta">meta: ${route.target_price ?? '—'} · ${route.target_percent_below_avg ?? '—'}% abaixo da média · estadia: ${route.trip_duration_weeks ? route.trip_duration_weeks + ' semana(s)' : 'sem restrição'}</div>
      <canvas height="120"></canvas>
    ` : '<p class="price-meta">Ainda sem histórico. O robô roda diariamente via GitHub Actions.</p>'}
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

const session = await requireAuth();
if (session) {
  wireLogout('logout');

  const [{ data: routes }, { data: settingsRows }, airports] = await Promise.all([
    supabase.from('routes').select('*').eq('archived', false).order('created_at'),
    supabase.from('settings').select('*').eq('user_id', session.user.id).limit(1),
    loadAirports(),
  ]);
  const settings = settingsRows && settingsRows[0] ? settingsRows[0] : DEFAULT_SETTINGS;

  document.getElementById('notification-mode').textContent = settings.notification_mode;

  const grid = document.getElementById('routes-grid');
  const empty = document.getElementById('empty-state');

  if (!routes || routes.length === 0) {
    empty.style.display = 'block';
  } else {
    for (const route of routes) {
      const { data: history } = await supabase
        .from('price_history')
        .select('checked_at, flight_date, price')
        .eq('route_id', route.id)
        .order('checked_at', { ascending: true });

      const originAirport = findByIata(airports, route.origin);
      const destinationAirport = findByIata(airports, route.destination);
      const isDomestic = originAirport?.country === 'Brazil' && destinationAirport?.country === 'Brazil';

      grid.appendChild(renderCard(route, history || [], settings, isDomestic));
    }
  }
}
