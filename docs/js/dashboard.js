import { supabase } from './supabase-client.js';
import { requireAuth, wireLogout } from './auth-guard.js';
import { loadAirports, findByIata } from './airports.js';
import { buyingWindowAdvice } from './buying-window.js';
import { weekendTags } from './holidays.js';

const DEFAULT_SETTINGS = {
  window_3d_pct: 10,
  window_7d_pct: 15,
  notification_mode: 'alert_only',
  cost_per_thousand_brl: 25,
  fast_flights_enabled: true,
};

const URGENCY_WINDOW_DAYS = 60;
const BLOCK_RECENT_HOURS = 48;

function formatDateBr(iso) {
  if (!iso) return '?';
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
}

function formatDateBrShort(iso) {
  if (!iso) return '?';
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
}

function daysUntil(iso) {
  const target = new Date(`${iso}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target - today) / 86400000);
}

function isWeekendComplete(weekend) {
  const legs = weekend.weekend_legs || [];
  return legs.length > 0 && legs.every((leg) => leg.status === 'purchased');
}

// ---------- (a) Ação do dia ----------

function renderAcaoDoDia(allLegs) {
  const section = document.getElementById('acao-do-dia');
  const hits = allLegs.filter((leg) =>
    leg.status === 'monitoring' && leg.current_price != null &&
    Number(leg.current_price) <= Number(leg.price_ceiling)
  );

  if (!hits.length) {
    section.innerHTML = `
      <h2>Ação do dia</h2>
      <p class="price-meta">Nada exigindo ação hoje — todas as pernas monitoradas estão acima do teto.</p>
    `;
    return;
  }

  section.innerHTML = `
    <h2>Ação do dia</h2>
    <a href="compras.html" style="text-decoration:none;">
      <p class="stat-big" style="color:var(--good);margin:0;">${hits.length} perna${hits.length === 1 ? '' : 's'} abaixo do teto agora</p>
      <p class="price-meta">Toque para ver em Compras →</p>
    </a>
  `;
}

// ---------- (b) Urgência ----------

function renderUrgencia(weekends) {
  const section = document.getElementById('urgencia');
  const items = weekends
    .filter((w) => {
      const d = daysUntil(w.outbound_date);
      return d >= 0 && d <= URGENCY_WINDOW_DAYS && !isWeekendComplete(w);
    })
    .sort((a, b) => a.outbound_date.localeCompare(b.outbound_date));

  if (!items.length) {
    section.style.display = 'none';
    return;
  }

  section.style.display = '';
  section.innerHTML = `
    <h2>Urgência — próximos ${URGENCY_WINDOW_DAYS} dias</h2>
    <ul class="link-list">
      ${items.map((w) => {
        const d = daysUntil(w.outbound_date);
        const legs = w.weekend_legs || [];
        const purchased = legs.filter((l) => l.status === 'purchased').length;
        return `<li><a href="compras.html#weekend-${w.id}"><span>${formatDateBrShort(w.outbound_date)}</span><span>faltam ${d} dias · ${purchased}/2 compradas</span></a></li>`;
      }).join('')}
    </ul>
  `;
}

// ---------- (c) Progresso ----------

function renderProgresso(allLegs, weekends) {
  const section = document.getElementById('progresso');
  const purchasedLegs = allLegs.filter((l) => l.status === 'purchased').length;
  const completeWeekends = weekends.filter(isWeekendComplete).length;
  const pct = allLegs.length ? Math.round((purchasedLegs / allLegs.length) * 100) : 0;

  section.innerHTML = `
    <h2>Progresso</h2>
    <p class="price-meta">${purchasedLegs} de ${allLegs.length} pernas compradas · ${completeWeekends} de ${weekends.length} fins de semana completos</p>
    <div class="progress-bar"><div class="progress-bar-fill" style="width:${pct}%"></div></div>
  `;
}

// ---------- (d) Melhores oportunidades ----------

function renderOportunidades(allLegs, weekendById) {
  const section = document.getElementById('oportunidades');
  const candidates = allLegs
    .filter((l) => l.status === 'monitoring' && l.current_price != null)
    .map((l) => ({
      leg: l,
      distPct: (Number(l.current_price) - Number(l.price_ceiling)) / Number(l.price_ceiling) * 100,
    }))
    .sort((a, b) => a.distPct - b.distPct)
    .slice(0, 5);

  if (!candidates.length) {
    section.innerHTML = `<h2>Melhores oportunidades</h2><p class="price-meta">Nenhuma perna com preço registrado ainda.</p>`;
    return;
  }

  section.innerHTML = `
    <h2>Melhores oportunidades</h2>
    <ul class="link-list">
      ${candidates.map(({ leg, distPct }) => {
        const weekend = weekendById[leg.weekend_id];
        const label = leg.direction === 'outbound' ? 'Ida' : 'Volta';
        const dateLabel = weekend ? formatDateBrShort(weekend.outbound_date) : '';
        const sign = distPct <= 0 ? 'abaixo' : 'acima';
        return `<li><a href="compras.html#weekend-${leg.weekend_id}"><span>${dateLabel} · ${label}</span><span>R$ ${Number(leg.current_price).toFixed(2)} (${Math.abs(distPct).toFixed(0)}% ${sign} do teto)</span></a></li>`;
      }).join('')}
    </ul>
  `;
}

// ---------- (e) Orçamento ----------

function renderOrcamento(allLegs) {
  const section = document.getElementById('orcamento');
  const purchased = allLegs.filter((l) => l.status === 'purchased');
  const withPaid = purchased.filter((l) => l.paid_price != null);

  if (!withPaid.length) {
    section.innerHTML = `
      <h2>Orçamento</h2>
      <p class="price-meta">Nenhum valor pago registrado ainda — preencha em Compras ao marcar uma perna como comprada.</p>
    `;
    return;
  }

  const totalPaid = withPaid.reduce((sum, l) => sum + Number(l.paid_price), 0);
  const avg = totalPaid / withPaid.length;
  const remaining = allLegs.length - purchased.length;
  const estimate = totalPaid + avg * remaining;

  section.innerHTML = `
    <h2>Orçamento</h2>
    <p class="stat-big">R$ ${totalPaid.toFixed(2)}</p>
    <p class="price-meta">gasto até agora · média R$ ${avg.toFixed(2)}/perna (com base em ${withPaid.length} perna${withPaid.length === 1 ? '' : 's'} com valor registrado)</p>
    <p class="price-meta">Estimativa se as ${remaining} pernas restantes saírem na média: <strong>R$ ${estimate.toFixed(2)}</strong> — é estimativa, não projeção real.</p>
  `;
}

// ---------- (f) Saúde do sistema ----------

async function renderSaude(settings) {
  const section = document.getElementById('saude-sistema');
  const since24h = new Date(Date.now() - 24 * 3600000).toISOString();
  const since7d = new Date(Date.now() - 7 * 24 * 3600000).toISOString();

  const [
    { count: count24h },
    { count: count7d },
    { data: lastRunRows },
    { data: blockedRows },
  ] = await Promise.all([
    supabase.from('weekend_leg_run_log').select('id', { count: 'exact', head: true }).gte('ran_at', since24h),
    supabase.from('weekend_leg_run_log').select('id', { count: 'exact', head: true }).gte('ran_at', since7d),
    supabase.from('weekend_leg_run_log').select('ran_at').order('ran_at', { ascending: false }).limit(1),
    supabase.from('bot_state').select('value').eq('key', 'weekend_batch_blocked_at').limit(1),
  ]);

  const lastRun = lastRunRows && lastRunRows[0] ? new Date(lastRunRows[0].ran_at) : null;
  const lastRunText = lastRun
    ? lastRun.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
    : 'ainda não executou';

  const blockedAt = blockedRows && blockedRows[0] ? new Date(blockedRows[0].value) : null;
  const blockedRecent = blockedAt && (Date.now() - blockedAt.getTime()) < BLOCK_RECENT_HOURS * 3600000;

  const liveActive = settings.fast_flights_enabled !== false;

  section.innerHTML = `
    <h2>Saúde do sistema</h2>
    <p class="price-meta">Última execução do robô: ${lastRunText}</p>
    <p class="price-meta">Pernas checadas: ${count24h ?? 0} nas últimas 24h · ${count7d ?? 0} nos últimos 7 dias</p>
    <p class="price-meta">Consulta de preço ao vivo: <span class="badge ${liveActive ? 'good' : 'neutral'}">${liveActive ? 'ativa' : 'desligada'}</span></p>
    ${blockedRecent
      ? `<p class="price-meta"><span class="badge warn">⚠️ bloqueio detectado</span> em ${blockedAt.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}</p>`
      : '<p class="price-meta">Sem bloqueios recentes.</p>'}
  `;
}

// ---------- (g) Feriados / alta temporada ----------

function renderFeriados(weekends) {
  const section = document.getElementById('feriados-alta-temporada');
  const items = weekends
    .map((w) => ({ weekend: w, tags: weekendTags(w) }))
    .filter((item) => item.tags.length)
    .sort((a, b) => a.weekend.outbound_date.localeCompare(b.weekend.outbound_date));

  if (!items.length) {
    section.innerHTML = `<h2>Fins de semana com feriado / alta temporada</h2><p class="price-meta">Nenhum encontrado.</p>`;
    return;
  }

  section.innerHTML = `
    <h2>Fins de semana com feriado / alta temporada</h2>
    <p class="price-meta">Esses fins de semana dificilmente ficam abaixo do teto padrão — considere subir o teto individual deles em Compras.</p>
    <ul class="link-list">
      ${items.map(({ weekend, tags }) => {
        const badges = tags.map((t) => (t.tag === 'feriado' ? '🎉' : '☀️')).join(' ');
        const motivo = tags.map((t) => t.motivo).join(' · ');
        return `<li><a href="compras.html#weekend-${weekend.id}"><span>${badges} ${formatDateBrShort(weekend.outbound_date)}</span><span>${motivo}</span></a></li>`;
      }).join('')}
    </ul>
  `;
}

// ---------- (h) Rotas flexíveis (legado) ----------

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

function renderLegacyCard(route, history, settings, isDomestic, lastOutcome) {
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

async function renderLegacyRoutes(session) {
  const [{ data: routes }, { data: legacySettingsRows }, airports, { data: lastRunRows }] = await Promise.all([
    supabase.from('routes').select('*').eq('archived', false).order('created_at'),
    supabase.from('settings').select('*').eq('user_id', session.user.id).limit(1),
    loadAirports(),
    supabase.from('run_log').select('ran_at').order('ran_at', { ascending: false }).limit(1),
  ]);
  const settings = legacySettingsRows && legacySettingsRows[0] ? legacySettingsRows[0] : DEFAULT_SETTINGS;

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
    return;
  }

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

    grid.appendChild(renderLegacyCard(route, history || [], settings, isDomestic, lastOutcome));
  }
}

// ---------- Bootstrap ----------

const session = await requireAuth();
if (session) {
  wireLogout('logout');

  const [{ data: weekends }, { data: settingsRows }] = await Promise.all([
    supabase.from('weekends').select('*, weekend_legs(*)').order('outbound_date', { ascending: true }),
    supabase.from('settings').select('*').eq('user_id', session.user.id).limit(1),
  ]);

  const settings = settingsRows && settingsRows[0] ? settingsRows[0] : DEFAULT_SETTINGS;
  const allWeekends = weekends || [];
  const allLegs = allWeekends.flatMap((w) => w.weekend_legs || []);
  const weekendById = Object.fromEntries(allWeekends.map((w) => [w.id, w]));

  renderAcaoDoDia(allLegs);
  renderUrgencia(allWeekends);
  renderProgresso(allLegs, allWeekends);
  renderOportunidades(allLegs, weekendById);
  renderOrcamento(allLegs);
  await renderSaude(settings);
  renderFeriados(allWeekends);
  await renderLegacyRoutes(session);
}
