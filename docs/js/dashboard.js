import { supabase } from './supabase-client.js';
import { requireAuth, wireLogout } from './auth-guard.js';

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

function isTrendingUp(history, window3dPct, window7dPct) {
  if (history.length < 2) return false;
  const current = history[history.length - 1].price;
  const past = history.slice(0, -1);
  for (const [days, pct] of [[3, window3dPct], [7, window7dPct]]) {
    if (!past.length) continue;
    const idx = Math.max(0, past.length - days);
    const ref = past[idx].price;
    if (ref > 0 && ((current - ref) / ref) * 100 >= pct) return true;
  }
  return false;
}

function renderCard(route, history, settings) {
  const card = document.createElement('div');
  card.className = 'card';

  const prices = history.map((h) => Number(h.price));
  const latest = prices.length ? prices[prices.length - 1] : null;
  const good = latest != null && isGoodPrice(latest, prices, route.target_price, route.target_percent_below_avg);
  const trending = isTrendingUp(
    history.map((h) => ({ ...h, price: Number(h.price) })),
    settings.window_3d_pct,
    settings.window_7d_pct
  );

  const badgeClass = good ? 'good' : trending ? 'warn' : 'neutral';
  const badgeText = good ? 'Bom preço' : trending ? 'Alta de preço' : 'Normal';

  card.innerHTML = `
    <h3>${route.origin} → ${route.destination}</h3>
    ${latest != null ? `
      <span class="badge ${badgeClass}">${badgeText}</span>
      <div class="price">${route.currency} ${latest.toFixed(2)}</div>
      <div class="price-meta">meta: ${route.target_price ?? '—'} · ${route.target_percent_below_avg ?? '—'}% abaixo da média</div>
      <canvas height="120"></canvas>
    ` : '<p class="price-meta">Ainda sem histórico. O robô roda diariamente via GitHub Actions.</p>'}
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

  const { data: routes } = await supabase.from('routes').select('*').order('created_at');
  const { data: settingsRows } = await supabase
    .from('settings')
    .select('*')
    .eq('user_id', session.user.id)
    .limit(1);
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
        .select('checked_at, price')
        .eq('route_id', route.id)
        .order('checked_at', { ascending: true });

      grid.appendChild(renderCard(route, history || [], settings));
    }
  }
}
