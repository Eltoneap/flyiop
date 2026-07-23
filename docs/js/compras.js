import { supabase } from './supabase-client.js';
import { requireAuth, wireLogout } from './auth-guard.js';

const DEFAULT_CEILING = 200;

let allWeekends = [];
let currentTab = 'active';

function showFlash(text) {
  const flash = document.getElementById('flash');
  flash.textContent = text || 'Salvo com sucesso.';
  flash.style.display = 'block';
  setTimeout(() => { flash.style.display = 'none'; }, 2500);
}

function formatDateBr(iso) {
  if (!iso) return '?';
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
}

function daysUntil(iso) {
  const target = new Date(`${iso}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target - today) / 86400000);
}

// Um weekend só sai de "Ativos" quando as DUAS pernas estiverem compradas —
// nunca por falta de preço (decisão de 24/07: card sem preço no meio da
// ordem certa é sinal de alerta, não deve ser escondido nem reordenado).
function isWeekendComplete(weekend) {
  const legs = weekend.weekend_legs || [];
  return legs.length > 0 && legs.every((leg) => leg.status === 'purchased');
}

function legLabel(leg, weekend) {
  if (leg.direction === 'outbound') {
    return { title: 'Ida (sex)', date: weekend.outbound_date };
  }
  if (leg.current_variant === 'sunday') return { title: 'Volta (dom)', date: weekend.return_sunday };
  if (leg.current_variant === 'monday') return { title: 'Volta (seg)', date: weekend.return_monday };
  return { title: 'Volta (dom/seg)', date: null }; // ainda não sabemos qual variante é mais barata
}

async function updateLeg(legId, fields) {
  const { error } = await supabase.from('weekend_legs').update(fields).eq('id', legId);
  return error;
}

function renderLegRow(leg, weekend) {
  const { title, date } = legLabel(leg, weekend);
  const row = document.createElement('div');
  row.className = 'leg-row';

  const priceText = leg.current_price != null
    ? `R$ ${Number(leg.current_price).toFixed(2)}`
    : '— sem preço ainda';
  const sourceBits = [leg.current_airport, leg.current_source].filter(Boolean);
  const sourceText = leg.current_price != null && sourceBits.length ? ` (${sourceBits.join(' · ')})` : '';

  const isPurchased = leg.status === 'purchased';

  row.innerHTML = `
    <div class="leg-row-main">
      <span class="leg-title">${title}${date ? ' ' + formatDateBr(date) : ''}</span>
      <span class="leg-price">${priceText}${sourceText}</span>
    </div>
    <div class="leg-row-controls">
      <label class="leg-ceiling-label">
        teto R$ <input type="number" step="1" min="0" value="${leg.price_ceiling ?? DEFAULT_CEILING}" class="leg-ceiling-input">
      </label>
      <button type="button" class="small leg-ceiling-save">Salvar</button>
      <span class="badge ${isPurchased ? 'good' : 'neutral'}">${isPurchased ? 'Comprada ✓' : 'Monitorando'}</span>
      <button type="button" class="small leg-action">${isPurchased ? 'Desfazer' : 'Comprei'}</button>
    </div>
  `;

  row.querySelector('.leg-ceiling-save').addEventListener('click', async () => {
    const value = Number(row.querySelector('.leg-ceiling-input').value);
    if (!value || value <= 0) {
      alert('Informe um teto válido.');
      return;
    }
    const error = await updateLeg(leg.id, { price_ceiling: value });
    if (error) {
      alert('Erro ao salvar teto: ' + error.message);
      return;
    }
    showFlash('Teto salvo.');
    await loadWeekends();
  });

  row.querySelector('.leg-action').addEventListener('click', async () => {
    const nextStatus = isPurchased ? 'monitoring' : 'purchased';
    const error = await updateLeg(leg.id, {
      status: nextStatus,
      purchased_at: isPurchased ? null : new Date().toISOString(),
    });
    if (error) {
      alert('Erro ao atualizar: ' + error.message);
      return;
    }
    showFlash(isPurchased ? 'Desfeito — voltou para monitoramento.' : 'Marcada como comprada — pode desfazer quando quiser.');
    await loadWeekends();
  });

  return row;
}

function renderCard(weekend) {
  const card = document.createElement('div');
  card.className = 'card';

  const legs = weekend.weekend_legs || [];
  const purchasedCount = legs.filter((leg) => leg.status === 'purchased').length;
  const days = daysUntil(weekend.outbound_date);
  const urgency = days < 0 ? 'já passou' : days === 0 ? 'é hoje' : `faltam ${days} dias`;

  const header = document.createElement('div');
  header.className = 'weekend-card-header';
  header.innerHTML = `
    <h3>${formatDateBr(weekend.outbound_date)} → ${formatDateBr(weekend.return_sunday)} ou ${formatDateBr(weekend.return_monday)}</h3>
    <span class="price-meta">${urgency} · ${purchasedCount}/2 compradas</span>
  `;
  card.appendChild(header);

  const outboundLeg = legs.find((leg) => leg.direction === 'outbound');
  const returnLeg = legs.find((leg) => leg.direction === 'return');
  if (outboundLeg) card.appendChild(renderLegRow(outboundLeg, weekend));
  if (returnLeg) card.appendChild(renderLegRow(returnLeg, weekend));

  return card;
}

function renderWeekends() {
  const grid = document.getElementById('weekends-grid');
  const empty = document.getElementById('empty-state');
  grid.innerHTML = '';

  const filtered = allWeekends.filter((w) =>
    currentTab === 'active' ? !isWeekendComplete(w) : isWeekendComplete(w)
  );
  // Ordenação puramente temporal (outbound_date) — NUNCA reordenar por preço.
  // Um fim de semana próximo sem preço no meio da lista é sinal de alerta,
  // não deve ser escondido no fim (decisão de 24/07).
  filtered.sort((a, b) => a.outbound_date.localeCompare(b.outbound_date));

  empty.style.display = filtered.length ? 'none' : 'block';
  empty.textContent = currentTab === 'active'
    ? 'Nenhum fim de semana ativo — todos já foram comprados!'
    : 'Nenhum fim de semana comprado ainda.';

  for (const weekend of filtered) {
    grid.appendChild(renderCard(weekend));
  }

  updateProgress();
}

function updateProgress() {
  const allLegs = allWeekends.flatMap((w) => w.weekend_legs || []);
  const purchasedLegs = allLegs.filter((leg) => leg.status === 'purchased').length;
  const completeWeekends = allWeekends.filter(isWeekendComplete).length;
  document.getElementById('progress-legs').textContent = `${purchasedLegs} de ${allLegs.length} pernas compradas`;
  document.getElementById('progress-weekends').textContent = `${completeWeekends} de ${allWeekends.length} fins de semana completos`;
}

async function loadWeekends() {
  const { data, error } = await supabase
    .from('weekends')
    .select('*, weekend_legs(*)')
    .order('outbound_date', { ascending: true });
  if (error) {
    alert('Erro ao carregar fins de semana: ' + error.message);
    return;
  }
  allWeekends = data || [];
  renderWeekends();
}

function wireTabs() {
  const tabActive = document.getElementById('tab-active');
  const tabPurchased = document.getElementById('tab-purchased');

  tabActive.addEventListener('click', () => {
    currentTab = 'active';
    tabActive.classList.add('active');
    tabPurchased.classList.remove('active');
    renderWeekends();
  });

  tabPurchased.addEventListener('click', () => {
    currentTab = 'purchased';
    tabPurchased.classList.add('active');
    tabActive.classList.remove('active');
    renderWeekends();
  });
}

const session = await requireAuth();
if (session) {
  wireLogout('logout');
  wireTabs();
  await loadWeekends();

  document.getElementById('apply-ceiling-btn').addEventListener('click', async () => {
    const value = Number(document.getElementById('default-ceiling-input').value);
    if (!value || value <= 0) {
      alert('Informe um teto válido antes de aplicar.');
      return;
    }
    const confirmed = confirm(
      `Isso vai sobrescrever o teto de TODAS as pernas ainda não compradas para R$ ${value} — ` +
      `inclusive as que você já ajustou manualmente (ex.: datas de feriado com teto mais alto). ` +
      `Pernas já compradas não são afetadas. Confirma?`
    );
    if (!confirmed) return;

    const { error } = await supabase
      .from('weekend_legs')
      .update({ price_ceiling: value })
      .eq('status', 'monitoring');
    if (error) {
      alert('Erro ao aplicar teto padrão: ' + error.message);
      return;
    }
    showFlash('Teto padrão aplicado a todas as pernas em monitoramento.');
    await loadWeekends();
  });
}
