import { supabase } from './supabase-client.js';
import { requireAuth, wireLogout } from './auth-guard.js';
import { weekendTags } from './holidays.js';

const DEFAULT_CEILING = 200;

const VALID_FILTERS = ['todas', 'abaixo-do-teto', 'sem-preco', 'feriado-alta-temporada', 'proximos-60-dias'];
const URGENCY_WINDOW_DAYS = 60;

let allWeekends = [];
let currentTab = 'active';
let currentFilter = 'todas';

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

function escapeAttr(text) {
  return String(text).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function formatLastCheck(iso) {
  if (!iso) return 'nunca verificado';
  const diffHours = (Date.now() - new Date(iso).getTime()) / 3600000;
  if (diffHours < 24) return `há ${Math.max(1, Math.round(diffHours))}h`;
  const diffDays = Math.round(diffHours / 24);
  return `há ${diffDays} dia${diffDays === 1 ? '' : 's'}`;
}

// Mesma lógica de src/links.py:google_flights_link, adaptada pra one-way
// (as pernas de fim de semana são buscadas separadas, nunca ida-e-volta).
// "one way" no texto é obrigatório: sem isso o Google Flights assume
// ida-e-volta por padrão e mostra preço combinado, não o preço da perna
// (confirmado em teste real 24/07/2026).
function googleFlightsLink(origin, destination, isoDate) {
  const query = `Flights from ${origin} to ${destination} on ${isoDate} one way`;
  return `https://www.google.com/travel/flights?q=${encodeURIComponent(query)}&hl=pt-BR&gl=BR`;
}

function legPurchaseLink(leg, weekend) {
  const airport = leg.current_airport || 'GIG'; // GIG é o hub padrão até a primeira checagem real
  if (leg.direction === 'outbound') {
    return googleFlightsLink(airport, 'BSB', weekend.outbound_date);
  }
  const returnDate = leg.current_variant === 'monday' ? weekend.return_monday : weekend.return_sunday;
  return googleFlightsLink('BSB', airport, returnDate);
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
  const purchaseLink = legPurchaseLink(leg, weekend);

  row.innerHTML = `
    <div class="leg-row-main">
      <span class="leg-title">${title}${date ? ' ' + formatDateBr(date) : ''}</span>
      <span class="leg-price">${priceText}${sourceText}</span>
    </div>
    <div class="leg-row-meta">
      <span class="leg-updated">atualizado ${formatLastCheck(leg.last_live_check_at)}</span>
      <a class="small leg-buy-link" href="${purchaseLink}" target="_blank" rel="noopener">Ver/comprar</a>
    </div>
    <div class="leg-row-controls">
      <label class="leg-ceiling-label">
        teto R$ <input type="number" step="1" min="0" value="${leg.price_ceiling ?? DEFAULT_CEILING}" class="leg-ceiling-input">
        <span class="save-check leg-ceiling-check">✓</span>
      </label>
      <button type="button" class="small leg-ceiling-save">Salvar</button>
      <span class="badge ${isPurchased ? 'good' : 'neutral'}">${isPurchased ? 'Comprada ✓' : 'Monitorando'}</span>
      <button type="button" class="small leg-action">${isPurchased ? 'Desfazer' : 'Comprei'}</button>
    </div>
    <div class="leg-row-notes">
      <input type="text" class="leg-notes-input" placeholder="localizador, horário..." value="${escapeAttr(leg.notes ?? '')}">
      <span class="save-check leg-notes-check">✓</span>
      <button type="button" class="small leg-notes-save">Salvar</button>
    </div>
    ${isPurchased ? `
    <div class="leg-row-paid">
      <label class="leg-paid-label">pago R$ <input type="number" step="0.01" min="0" placeholder="ex: 245.90" class="leg-paid-input" value="${leg.paid_price ?? ''}">
        <span class="save-check leg-paid-check">✓</span>
      </label>
      <button type="button" class="small leg-paid-save">Salvar</button>
      <span class="leg-paid-hint">valor real, com taxas — diferente do preço monitorado</span>
    </div>
    ` : ''}
  `;

  // Estado visual "salvo" (botão discreto + ✓) vs "não salvo" (botão azul,
  // sem ✓) — pedido do usuário (25/07): o botão azul chamativo o tempo todo
  // dava a impressão de que sempre faltava fazer algo.
  const markFieldState = (button, check, saved, hasValue) => {
    button.classList.toggle('saved', saved);
    if (check) check.style.display = saved && hasValue ? 'inline' : 'none';
  };

  const ceilingInput = row.querySelector('.leg-ceiling-input');
  const ceilingBtn = row.querySelector('.leg-ceiling-save');
  const ceilingCheck = row.querySelector('.leg-ceiling-check');
  markFieldState(ceilingBtn, ceilingCheck, true, true); // valor renderizado = valor salvo
  ceilingInput.addEventListener('input', () => markFieldState(ceilingBtn, ceilingCheck, false, true));

  ceilingBtn.addEventListener('click', async () => {
    const value = Number(ceilingInput.value);
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
    await loadWeekends(); // recarrega tudo — o novo render já nasce "salvo"
  });

  const notesInput = row.querySelector('.leg-notes-input');
  const notesBtn = row.querySelector('.leg-notes-save');
  const notesCheck = row.querySelector('.leg-notes-check');
  markFieldState(notesBtn, notesCheck, true, !!notesInput.value.trim());
  let notesSaved = true;
  const saveNotes = async () => {
    if (notesSaved) return;
    notesSaved = true;
    markFieldState(notesBtn, notesCheck, true, !!notesInput.value.trim());
    const error = await updateLeg(leg.id, { notes: notesInput.value.trim() || null });
    if (error) {
      alert('Erro ao salvar observações: ' + error.message);
      notesSaved = false;
      markFieldState(notesBtn, notesCheck, false, !!notesInput.value.trim());
      return;
    }
    showFlash('Observações salvas.');
  };
  notesInput.addEventListener('input', () => {
    notesSaved = false;
    markFieldState(notesBtn, notesCheck, false, !!notesInput.value.trim());
  });
  notesInput.addEventListener('blur', saveNotes);
  notesBtn.addEventListener('click', saveNotes);

  const paidInput = row.querySelector('.leg-paid-input');
  if (paidInput) {
    const paidBtn = row.querySelector('.leg-paid-save');
    const paidCheck = row.querySelector('.leg-paid-check');
    markFieldState(paidBtn, paidCheck, true, paidInput.value !== '');
    let paidSaved = true;
    const savePaid = async () => {
      if (paidSaved) return;
      paidSaved = true;
      markFieldState(paidBtn, paidCheck, true, paidInput.value !== '');
      const value = paidInput.value === '' ? null : Number(paidInput.value);
      const error = await updateLeg(leg.id, { paid_price: value });
      if (error) {
        alert('Erro ao salvar valor pago: ' + error.message);
        paidSaved = false;
        markFieldState(paidBtn, paidCheck, false, paidInput.value !== '');
        return;
      }
      showFlash('Valor pago salvo.');
    };
    paidInput.addEventListener('input', () => {
      paidSaved = false;
      markFieldState(paidBtn, paidCheck, false, paidInput.value !== '');
    });
    paidInput.addEventListener('blur', savePaid);
    paidBtn.addEventListener('click', savePaid);
  }

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
  card.id = `weekend-${weekend.id}`;

  const legs = weekend.weekend_legs || [];
  const purchasedCount = legs.filter((leg) => leg.status === 'purchased').length;
  const days = daysUntil(weekend.outbound_date);
  const urgency = days < 0 ? 'já passou' : days === 0 ? 'é hoje' : `faltam ${days} dias`;

  const tags = weekendTags(weekend);
  const badges = tags.map(({ tag }) => {
    if (tag === 'feriado') return '<span class="badge holiday" title="Feriado — dificilmente fica abaixo do teto padrão">🎉 feriado</span>';
    return '<span class="badge high-season" title="Alta temporada — dificilmente fica abaixo do teto padrão">☀️ alta temporada</span>';
  }).join('');

  const header = document.createElement('div');
  header.className = 'weekend-card-header';
  header.innerHTML = `
    <h3>${formatDateBr(weekend.outbound_date)} → ${formatDateBr(weekend.return_sunday)} ou ${formatDateBr(weekend.return_monday)} ${badges}</h3>
    <span class="price-meta">${urgency} · ${purchasedCount}/2 compradas</span>
  `;
  card.appendChild(header);

  const outboundLeg = legs.find((leg) => leg.direction === 'outbound');
  const returnLeg = legs.find((leg) => leg.direction === 'return');
  if (outboundLeg) card.appendChild(renderLegRow(outboundLeg, weekend));
  if (returnLeg) card.appendChild(renderLegRow(returnLeg, weekend));

  return card;
}

// Mesmo predicado de "abaixo do teto" usado no Dashboard (renderAcaoDoDia,
// dashboard.js) — mantido em sincronia manualmente, os dois arquivos não
// compartilham módulo hoje.
function legBelowCeiling(leg) {
  return leg.status === 'monitoring' && leg.current_price != null &&
    Number(leg.current_price) <= Number(leg.price_ceiling);
}

function legHasNoPrice(leg) {
  return leg.status === 'monitoring' && leg.current_price == null;
}

// Filtros extra da aba Compras — combinam com a aba atual (E lógico), nunca
// substituem. Aplicados a nível de fim de semana: mostra o card se AO MENOS
// 1 perna bater o critério (mesmo espírito das abas Ativos/Comprados).
function weekendMatchesFilter(weekend, filter) {
  const legs = weekend.weekend_legs || [];
  switch (filter) {
    case 'abaixo-do-teto':
      return legs.some(legBelowCeiling);
    case 'sem-preco':
      return legs.some(legHasNoPrice);
    case 'feriado-alta-temporada':
      return weekendTags(weekend).length > 0;
    case 'proximos-60-dias': {
      const d = daysUntil(weekend.outbound_date);
      return d >= 0 && d <= URGENCY_WINDOW_DAYS;
    }
    default:
      return true;
  }
}

function renderWeekends() {
  const grid = document.getElementById('weekends-grid');
  const empty = document.getElementById('empty-state');
  grid.innerHTML = '';

  const filtered = allWeekends
    .filter((w) => (currentTab === 'active' ? !isWeekendComplete(w) : isWeekendComplete(w)))
    .filter((w) => weekendMatchesFilter(w, currentFilter));
  // Ordenação puramente temporal (outbound_date) — NUNCA reordenar por preço.
  // Um fim de semana próximo sem preço no meio da lista é sinal de alerta,
  // não deve ser escondido no fim (decisão de 24/07).
  filtered.sort((a, b) => a.outbound_date.localeCompare(b.outbound_date));

  empty.style.display = filtered.length ? 'none' : 'block';
  if (currentFilter !== 'todas') {
    empty.textContent = 'Nenhum fim de semana corresponde a esse filtro.';
  } else {
    empty.textContent = currentTab === 'active'
      ? 'Nenhum fim de semana ativo — todos já foram comprados!'
      : 'Nenhum fim de semana comprado ainda.';
  }

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

function wireFilterChips() {
  const chips = document.querySelectorAll('.filter-chip');
  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      currentFilter = chip.dataset.filter;
      chips.forEach((c) => c.classList.toggle('active', c === chip));
      renderWeekends();
    });
  });
}

function initialFilterFromUrl() {
  const requested = new URLSearchParams(location.search).get('filtro');
  return VALID_FILTERS.includes(requested) ? requested : 'todas';
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
  wireFilterChips();

  currentFilter = initialFilterFromUrl();
  document.querySelectorAll('.filter-chip').forEach((chip) => {
    chip.classList.toggle('active', chip.dataset.filter === currentFilter);
  });

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
