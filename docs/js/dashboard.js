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
};

const URGENCY_WINDOW_DAYS = 60;
const BLOCK_RECENT_HOURS = 48;

// Fatia B (08/08/2026) — etiqueta de escopo por bloco. O Dashboard mistura
// decisão pessoal do usuário logado (progresso, orçamento, tetos, rotas) com
// dado do sistema, igual para todo mundo (saúde do robô, feriados). Sem pista
// visual isso vira erro de leitura assim que existir um segundo usuário:
// "esse número é meu ou é dele?".
//
// Mapa + um passe único, em vez de colar a etiqueta em cada template: as
// funções de render abaixo somam 11 atribuições de `section.innerHTML`, várias
// em pares (ramo com dado / ramo vazio) — seriam 11 pontos de edição, e todo
// ramo novo nasceria sem etiqueta.
const BLOCK_SCOPE = {
  'acao-do-dia': 'own',
  progresso: 'own',
  oportunidades: 'own',
  orcamento: 'own',
  'rotas-legado': 'own',
  'saude-sistema': 'system',
  'feriados-alta-temporada': 'system',
  // 'urgencia' fica sem etiqueta de propósito (decisão de 08/08/2026).
};

const SCOPE_LABEL = { own: 'só seu', system: 'do sistema' };

// Chamada uma vez, ao fim de initPage: hoje nada reescreve o innerHTML de um
// bloco depois disso (os únicos listeners do arquivo são 'theme:change', que
// só recolore o Chart.js, e o clique do export CSV; não há timer nem filtro).
// A guarda de idempotência existe para o dia em que houver — rodar de novo não
// duplica pill.
function tagBlockScopes() {
  for (const [id, scope] of Object.entries(BLOCK_SCOPE)) {
    const block = document.getElementById(id);
    if (!block) continue;
    const heading = block.querySelector('h2, summary'); // h2 nas <section>, summary no <details> legado
    if (!heading || heading.querySelector('.badge.scope-own, .badge.scope-system')) continue;

    const badge = document.createElement('span');
    badge.className = `badge scope-${scope}`;
    badge.textContent = SCOPE_LABEL[scope]; // maiúsculas ficam por conta do CSS
    heading.appendChild(badge);
  }
}

// Gráficos de rota legada em tela, pra recolorir ao vivo quando o tema
// (docs/js/theme.js) alterna, sem re-buscar dados do Supabase.
const legacyCharts = [];

function chartColors() {
  const style = getComputedStyle(document.documentElement);
  const border = style.getPropertyValue('--primary').trim();
  const rgb = style.getPropertyValue('--primary-rgb').trim();
  return { border, background: `rgba(${rgb},0.08)` };
}

document.addEventListener('theme:change', () => {
  const { border, background } = chartColors();
  legacyCharts.forEach((chart) => {
    chart.data.datasets[0].borderColor = border;
    chart.data.datasets[0].backgroundColor = background;
    chart.update();
  });
});

// Primeiro fim de semana alvo de compra real (decisão de 28/07/2026, ver
// CLAUDE.md/STATE.md) — fins de semana antes disso são monitorados de
// propósito (histórico/teste), mas não contam nas métricas de progresso e
// orçamento abaixo.
const BUYING_CUTOFF_DATE = '2027-01-29';

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
    <a href="compras.html?filtro=abaixo-do-teto" style="text-decoration:none;">
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
  const inScopeWeekends = weekends.filter((w) => w.outbound_date >= BUYING_CUTOFF_DATE);
  const inScopeLegs = inScopeWeekends.flatMap((w) => w.weekend_legs || []);
  const purchasedLegs = inScopeLegs.filter((l) => l.status === 'purchased').length;
  const completeWeekends = inScopeWeekends.filter(isWeekendComplete).length;
  const pct = inScopeLegs.length ? Math.round((purchasedLegs / inScopeLegs.length) * 100) : 0;
  const earlyLegsCount = allLegs.length - inScopeLegs.length;

  section.innerHTML = `
    <h2>Progresso</h2>
    <p class="price-meta">${purchasedLegs} de ${inScopeLegs.length} pernas compradas · ${completeWeekends} de ${inScopeWeekends.length} fins de semana completos</p>
    <div class="progress-bar"><div class="progress-bar-fill" style="width:${pct}%"></div></div>
    ${earlyLegsCount > 0 ? `<p class="price-meta">+ ${earlyLegsCount} pernas em construção de histórico (set/2026–jan/2027) não entram nesse número — continuam sendo monitoradas normalmente.</p>` : ''}
  `;
}

// ---------- (d) Melhores oportunidades ----------

function opportunityItemHtml(leg, weekendById, priceNote) {
  const weekend = weekendById[leg.weekend_id];
  const label = leg.direction === 'outbound' ? 'Ida' : 'Volta';
  const dateLabel = weekend ? formatDateBrShort(weekend.outbound_date) : '';
  const sourceLabel = leg.current_source ? ` · <span class="price-meta">${leg.current_source}</span>` : '';
  return `<li><a href="compras.html#weekend-${leg.weekend_id}"><span>${dateLabel} · ${label}</span><span>R$ ${Number(leg.current_price).toFixed(2)} (${priceNote})${sourceLabel}</span></a></li>`;
}

function renderOportunidades(allLegs, weekendById) {
  const section = document.getElementById('oportunidades');
  const candidates = allLegs
    .filter((l) => l.status === 'monitoring' && l.current_price != null)
    .map((l) => ({
      leg: l,
      distPct: (Number(l.current_price) - Number(l.price_ceiling)) / Number(l.price_ceiling) * 100,
    }));

  if (!candidates.length) {
    section.innerHTML = `<h2>Melhores oportunidades</h2><p class="price-meta">Nenhuma perna com preço registrado ainda.</p>`;
    return;
  }

  // Duas listas sem sobreposição (Parte 9, 28/07/2026): "Abaixo do teto" é
  // ação (preço já bom pra comprar); "Mais baratas no momento" é só
  // informação (preço mais baixo disponível, mesmo que ainda acima do
  // teto) — antes as duas coisas apareciam misturadas sob "oportunidades".
  const belowCeiling = candidates
    .filter((c) => c.distPct <= 0)
    .sort((a, b) => a.distPct - b.distPct)
    .slice(0, 5);
  const aboveCeiling = candidates
    .filter((c) => c.distPct > 0)
    .sort((a, b) => Number(a.leg.current_price) - Number(b.leg.current_price))
    .slice(0, 5);

  const belowHtml = belowCeiling.length
    ? `<ul class="link-list">${belowCeiling.map(({ leg, distPct }) => opportunityItemHtml(leg, weekendById, `${Math.abs(distPct).toFixed(0)}% abaixo do teto`)).join('')}</ul>`
    : `<p class="price-meta">Nenhuma perna abaixo do teto agora.</p>`;

  const aboveHtml = aboveCeiling.length
    ? `<ul class="link-list">${aboveCeiling.map(({ leg, distPct }) => opportunityItemHtml(leg, weekendById, `${Math.abs(distPct).toFixed(0)}% acima do teto`)).join('')}</ul>`
    : `<p class="price-meta">Nenhuma outra perna com preço registrado.</p>`;

  section.innerHTML = `
    <h2>Melhores oportunidades</h2>
    <h3>Abaixo do teto</h3>
    ${belowHtml}
    <h3>Mais baratas no momento</h3>
    ${aboveHtml}
  `;
}

// ---------- (e) Orçamento ----------

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function renderOrcamento(weekends) {
  const section = document.getElementById('orcamento');
  const inScopeLegs = weekends
    .filter((w) => w.outbound_date >= BUYING_CUTOFF_DATE)
    .flatMap((w) => w.weekend_legs || []);

  const purchased = inScopeLegs.filter((l) => l.status === 'purchased');
  const withPaid = purchased.filter((l) => l.paid_price != null);

  if (!withPaid.length) {
    section.innerHTML = `
      <h2>Orçamento</h2>
      <p class="price-meta">Nenhum valor pago registrado ainda (a partir de ${formatDateBrShort(BUYING_CUTOFF_DATE)}) — preencha em Compras ao marcar uma perna como comprada.</p>
    `;
    return;
  }

  const totalPaid = withPaid.reduce((sum, l) => sum + Number(l.paid_price), 0);
  const remaining = inScopeLegs.length - purchased.length;

  // Mediana do preço monitorado hoje nas pernas ainda não compradas, não
  // mais a média do que já foi pago — com poucas compras reais essa média
  // fica instável demais pra projetar (Parte 9, 28/07/2026).
  const monitoringPrices = inScopeLegs
    .filter((l) => l.status === 'monitoring' && l.current_price != null)
    .map((l) => Number(l.current_price));

  let estimateLine = 'Sem preços suficientes nas pernas restantes ainda pra estimar o total.';
  if (remaining > 0 && monitoringPrices.length) {
    const medianPrice = median(monitoringPrices);
    const estimate = totalPaid + medianPrice * remaining;
    estimateLine = `Estimativa se as ${remaining} pernas restantes saírem na mediana atual (R$ ${medianPrice.toFixed(2)}): <strong>R$ ${estimate.toFixed(2)}</strong> — é estimativa, não projeção real.`;
  }

  section.innerHTML = `
    <h2>Orçamento</h2>
    <p class="stat-big">R$ ${totalPaid.toFixed(2)}</p>
    <p class="price-meta">gasto até agora, a partir de ${formatDateBrShort(BUYING_CUTOFF_DATE)} (com base em ${withPaid.length} perna${withPaid.length === 1 ? '' : 's'} com valor registrado)</p>
    <p class="price-meta">${estimateLine}</p>
  `;
}

// ---------- (f) Saúde do sistema ----------

async function renderSaude(liveActive) {
  const section = document.getElementById('saude-sistema');
  const since24h = new Date(Date.now() - 24 * 3600000).toISOString();
  const since7d = new Date(Date.now() - 7 * 24 * 3600000).toISOString();

  const [
    { count: count24h },
    { count: count7d },
    { data: lastRunRows },
    { data: blockedRows },
    { data: scrapeStateRows },
  ] = await Promise.all([
    supabase.from('weekend_leg_run_log').select('id', { count: 'exact', head: true }).gte('ran_at', since24h),
    supabase.from('weekend_leg_run_log').select('id', { count: 'exact', head: true }).gte('ran_at', since7d),
    supabase.from('weekend_leg_run_log').select('ran_at').order('ran_at', { ascending: false }).limit(1),
    supabase.from('bot_state').select('value').eq('key', 'weekend_batch_blocked_at').limit(1),
    supabase.from('bot_state').select('key, value').in('key', ['weekend_scrape_stage', 'weekend_scrape_clean_days']),
  ]);

  const lastRun = lastRunRows && lastRunRows[0] ? new Date(lastRunRows[0].ran_at) : null;
  const lastRunText = lastRun
    ? lastRun.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
    : 'ainda não executou';

  const blockedAt = blockedRows && blockedRows[0] ? new Date(blockedRows[0].value) : null;
  const blockedRecent = blockedAt && (Date.now() - blockedAt.getTime()) < BLOCK_RECENT_HOURS * 3600000;

  // liveActive: true/false vindo de system_config, ou null se a consulta
  // falhou/tabela ainda não existe — degrada pra "desconhecido" em vez de
  // quebrar o resto do painel.
  const liveStatusLabel = liveActive === null ? 'desconhecido' : (liveActive ? 'ativa' : 'desligada');
  const liveStatusClass = liveActive === null ? 'neutral' : (liveActive ? 'good' : 'neutral');

  // Escalonamento automático de frequência (Parte 10, 28/07/2026) — stage
  // 0/1/2 vem de bot_state, texto local em vez de importar telegram_notifier.
  const scrapeStateByKey = Object.fromEntries((scrapeStateRows || []).map((r) => [r.key, r.value]));
  const stage = Number(scrapeStateByKey.weekend_scrape_stage ?? 0);
  const cleanDays = Number(scrapeStateByKey.weekend_scrape_clean_days ?? 0);
  const EXECUTIONS_PER_STAGE = { 0: 1, 1: 2, 2: 3 };
  const stageLine = stage >= 2
    ? `Frequência de scraping: Estágio 2 (3x/dia) · teto automático atingido`
    : `Frequência de scraping: Estágio ${stage} (${EXECUTIONS_PER_STAGE[stage]}x/dia) · ${cleanDays} de 5 dias limpos pro próximo degrau`;

  section.innerHTML = `
    <h2>Saúde do sistema</h2>
    <p class="price-meta">Última execução do robô: ${lastRunText}</p>
    <p class="price-meta">Pernas checadas: ${count24h ?? 0} nas últimas 24h · ${count7d ?? 0} nos últimos 7 dias</p>
    <p class="price-meta">Consulta de preço ao vivo: <span class="badge ${liveStatusClass}">${liveStatusLabel}</span></p>
    <p class="price-meta">${stageLine}</p>
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
    const { border, background } = chartColors();
    const chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: history.map((h) => h.checked_at.slice(0, 10)),
        datasets: [{
          data: prices,
          borderColor: border,
          backgroundColor: background,
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
    legacyCharts.push(chart);
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
  const [
    { data: routes, error: routesError },
    { data: legacySettingsRows },
    airports,
    { data: lastRunRows },
  ] = await Promise.all([
    supabase.from('routes').select('*').eq('archived', false).order('created_at'),
    supabase.from('settings').select('*').eq('user_id', session.user.id).limit(1),
    loadAirports(),
    supabase.from('run_log').select('ran_at').order('ran_at', { ascending: false }).limit(1),
  ]);

  // Fatia B — o bloco todo é "só seu": nasce hidden no HTML e só é revelado
  // com rota ATIVA de verdade. Aqui a conta é só das ativas (a consulta acima
  // já filtra), diferente de Configurações, que conta ativas + arquivadas:
  // lá existe aba Arquivadas e botão Reativar para preservar, aqui não há
  // caminho nenhum a proteger, e contar arquivadas devolveria justamente o
  // card vazio que esta fatia elimina.
  const details = document.getElementById('rotas-legado');

  if (routesError) {
    // Falha de consulta NÃO pode virar bloco escondido em silêncio — o
    // usuário leria como "minhas rotas sumiram". Revela e avisa, no mesmo
    // alert() que initPage usa para weekends/pernas e que config.js usa em
    // loadRoutes.
    details.hidden = false;
    alert('Erro ao carregar rotas: ' + routesError.message);
    return;
  }

  // Atribuição explícita nos dois sentidos, e não só um `return` confiando no
  // `hidden` do markup: assim o estado do bloco é sempre função do resultado da
  // consulta, mesmo que um dia isto rode duas vezes no mesmo documento (mesma
  // forma do gate de config.js).
  details.hidden = !routes || routes.length === 0;
  if (details.hidden) return; // sem card vazio

  const settings = legacySettingsRows && legacySettingsRows[0] ? legacySettingsRows[0] : DEFAULT_SETTINGS;

  document.getElementById('notification-mode').textContent = settings.notification_mode;
  if (lastRunRows && lastRunRows[0]) {
    const ranAt = new Date(lastRunRows[0].ran_at);
    document.getElementById('last-run').textContent =
      `última verificação do robô: ${ranAt.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}`;
  }

  document.getElementById('export-csv').addEventListener('click', () => exportCsv(routes || []));

  // O ramo de zero rotas saiu daqui para o gate acima (Fatia B): em vez de
  // mostrar #empty-state, o bloco inteiro não aparece. O nó #empty-state
  // continua em index.html, deliberadamente intocado, apenas nunca exibido.
  const grid = document.getElementById('routes-grid');

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

// Corpo em função (e não solto no escopo do módulo) porque o tratamento de
// erro abaixo usa `return` — no top-level de um módulo isso é "Illegal return
// statement" no navegador (mesmo bug corrigido em compras.js, commit 9436bc0).
async function initPage(session) {
  wireLogout('logout');

  // Teto/status/notas/valor pago são estado por usuário desde a Etapa 4.1 —
  // vêm de weekend_leg_effective, não mais do embed weekend_legs(*), que lê as
  // colunas globais antigas (mesma fonte que compras.js usa desde a 4.2).
  const [
    { data: weekends, error: wErr },
    { data: legRows, error: lErr },
    { data: settingsRows },
    systemConfigResult,
  ] = await Promise.all([
    supabase.from('weekends').select('*').order('outbound_date', { ascending: true }),
    supabase.from('weekend_leg_effective').select('*'),
    supabase.from('settings').select('*').eq('user_id', session.user.id).limit(1),
    supabase.from('system_config').select('fast_flights_enabled').limit(1)
      .then((res) => res, (err) => ({ data: null, error: err })),
  ]);

  if (wErr) {
    alert('Erro ao carregar fins de semana: ' + wErr.message);
    return;
  }
  if (lErr) {
    alert('Erro ao carregar tetos e status: ' + lErr.message);
    return;
  }

  const settings = settingsRows && settingsRows[0] ? settingsRows[0] : DEFAULT_SETTINGS;

  // Sem normalizar leg_id -> id (o que compras.js precisa fazer): nenhuma
  // função deste arquivo referencia leg.id.
  const legsByWeekend = {};
  for (const row of legRows || []) {
    (legsByWeekend[row.weekend_id] ??= []).push(row);
  }

  const allWeekends = (weekends || []).map((w) => ({ ...w, weekend_legs: legsByWeekend[w.id] || [] }));
  const allLegs = allWeekends.flatMap((w) => w.weekend_legs || []);
  const weekendById = Object.fromEntries(allWeekends.map((w) => [w.id, w]));

  // system_config pode ainda não existir (SQL da Etapa 3 não rodado) ou a
  // consulta pode falhar — degrada pra "desconhecido" (null) em vez de
  // travar o carregamento do resto do Dashboard.
  const systemConfigRow = systemConfigResult && !systemConfigResult.error && systemConfigResult.data
    ? systemConfigResult.data[0]
    : null;
  const liveActive = systemConfigRow ? systemConfigRow.fast_flights_enabled !== false : null;

  renderAcaoDoDia(allLegs);
  renderUrgencia(allWeekends);
  renderProgresso(allLegs, allWeekends);
  renderOportunidades(allLegs, weekendById);
  renderOrcamento(allWeekends);
  await renderSaude(liveActive);
  renderFeriados(allWeekends);
  await renderLegacyRoutes(session);

  // Por último: todo bloco já está montado (as funções acima sobrescrevem
  // innerHTML), então a etiqueta não corre risco de ser apagada.
  tagBlockScopes();
}

const session = await requireAuth();
if (session) {
  await initPage(session);
}
