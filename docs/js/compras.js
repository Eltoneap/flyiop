import { supabase } from './supabase-client.js';
import { requireAuth, wireLogout } from './auth-guard.js';
import { weekendTags } from './holidays.js';

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

async function updateLegState(legId, fields) {
  const { error } = await supabase
    .from('weekend_leg_user_state')
    .upsert({ leg_id: legId, ...fields }, { onConflict: 'leg_id,user_id' });
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

// Estado do preço vs. teto, só faz sentido pra pernas em monitoramento —
// pernas compradas têm sua própria exibição (ver isPurchased abaixo).
function legPriceState(leg) {
  if (leg.current_price == null) return 'none';
  const ceiling = Number(leg.price_ceiling);
  return Number(leg.current_price) <= ceiling ? 'below' : 'above';
}

function legStatusBadge(leg, priceState) {
  if (leg.status === 'purchased') return { cls: 'bought', text: '✓ Comprada' };
  const ceiling = Number(leg.price_ceiling);
  if (priceState === 'below') {
    const diff = Math.round(ceiling - Number(leg.current_price));
    return { cls: 'deal', text: `↓ R$ ${diff} abaixo do teto` };
  }
  if (priceState === 'above') {
    const pct = Math.round(((Number(leg.current_price) - ceiling) / ceiling) * 100);
    return { cls: 'neutral', text: `Monitorando · ${pct}% acima do teto` };
  }
  return { cls: 'neutral', text: 'Monitorando · ainda sem preço' };
}

function renderLegRow(leg, weekend) {
  const { title, date } = legLabel(leg, weekend);
  const isPurchased = leg.status === 'purchased';
  const row = document.createElement('div');
  row.className = `leg-row${isPurchased ? ' is-bought' : ''}`;

  const livePriceText = leg.current_price != null
    ? `R$ ${Number(leg.current_price).toFixed(2)}`
    : '— sem preço ainda';
  const sourceBits = [leg.current_airport, leg.current_source].filter(Boolean);
  const sourceText = leg.current_price != null && sourceBits.length ? ` (${sourceBits.join(' · ')})` : '';

  const priceState = legPriceState(leg);
  const badge = legStatusBadge(leg, priceState);
  const purchaseLink = legPurchaseLink(leg, weekend);

  // Perna comprada com valor pago: valor pago vira o número grande (dado que
  // já importa mais que o preço ao vivo), preço ao vivo passa a nota riscada.
  // Sem valor pago (comprar não exige preenchê-lo): NÃO inverter — o preço ao
  // vivo continua como número principal, sem riscar, com nota discreta no
  // lugar do valor pago (pedido do usuário, 27/07 — evita mostrar dado que
  // não existe como se fosse o principal).
  let priceClass = 'leg-price';
  let priceHtml;
  if (isPurchased && leg.paid_price != null) {
    priceClass += ' leg-price--paid';
    priceHtml = `R$ ${Number(leg.paid_price).toFixed(2)}` +
      `<s class="leg-price-live">hoje ${livePriceText}</s>` +
      `<small class="leg-price-note">você pagou</small>`;
  } else if (isPurchased) {
    priceHtml = `${livePriceText}${sourceText}<small class="leg-price-note">valor não informado</small>`;
  } else {
    priceClass += priceState === 'below' ? ' leg-price--below'
      : priceState === 'above' ? ' leg-price--above'
      : ' leg-price--none';
    priceHtml = `${livePriceText}${sourceText}`;
  }

  const notesFilled = !!(leg.notes ?? '').toString().trim();
  const paidFilled = leg.paid_price != null && leg.paid_price !== '';

  row.innerHTML = `
    <div class="leg-row-main">
      <span class="leg-title">${title}${date ? ' ' + formatDateBr(date) : ''}</span>
      <span class="${priceClass}">${priceHtml}</span>
    </div>
    <div class="leg-row-meta">
      <span class="leg-updated">atualizado ${formatLastCheck(leg.last_live_check_at)}</span>
      <a class="small leg-buy-link" href="${purchaseLink}" target="_blank" rel="noopener">Ver/comprar</a>
    </div>
    <div class="leg-row-controls">
      <label class="leg-ceiling-label">
        teto R$ <input type="number" step="1" min="0" value="${leg.price_ceiling}" class="leg-ceiling-input field-filled">
        <span class="save-check leg-ceiling-check">✓</span>
      </label>
      <button type="button" class="small leg-ceiling-save">Salvar</button>
      <span class="badge ${badge.cls}">${badge.text}</span>
      ${isPurchased ? '<button type="button" class="leg-action btn-undo">Desfazer compra</button>' : ''}
    </div>
    <div class="leg-row-notes">
      <input type="text" class="leg-notes-input ${notesFilled ? 'field-filled' : 'field-empty'}" placeholder="localizador, horário..." value="${escapeAttr(leg.notes ?? '')}">
      <span class="save-check leg-notes-check">✓</span>
      <button type="button" class="small leg-notes-save">Salvar</button>
    </div>
    ${isPurchased ? `
    <div class="leg-row-paid">
      <label class="leg-paid-label">pago R$ <input type="number" step="0.01" min="0" placeholder="ex: 245.90" class="leg-paid-input ${paidFilled ? 'field-filled' : 'field-empty'}" value="${leg.paid_price ?? ''}">
        <span class="save-check leg-paid-check">✓</span>
      </label>
      <button type="button" class="small leg-paid-save">Salvar</button>
      <span class="leg-paid-hint">valor real, com taxas — diferente do preço monitorado</span>
    </div>
    ` : ''}
    ${!isPurchased ? '<button type="button" class="leg-action btn-outline-full">Marcar como comprada</button>' : ''}
  `;

  // Estado visual "salvo" (botão discreto + ✓) vs "não salvo, alteração
  // pendente" (botão e campo âmbar — B1, 27/07) — pedido do usuário (25/07):
  // o botão azul chamativo o tempo todo dava a impressão de que sempre
  // faltava fazer algo; âmbar reserva o alerta visual só pra quando há de
  // fato algo não salvo.
  const markFieldState = (button, check, input, saved, hasValue) => {
    button.classList.toggle('saved', saved);
    button.classList.toggle('dirty', !saved);
    if (input) input.classList.toggle('field-dirty', !saved);
    if (check) check.style.display = saved && hasValue ? 'inline' : 'none';
  };

  // Vazio = borda tracejada, preenchido = borda sólida + texto em negrito
  // (A4) — atualizado a cada tecla, além do estado inicial já vir correto
  // do template acima.
  const markFieldFill = (input, hasValue) => {
    input.classList.toggle('field-filled', hasValue);
    input.classList.toggle('field-empty', !hasValue);
  };

  const ceilingInput = row.querySelector('.leg-ceiling-input');
  const ceilingBtn = row.querySelector('.leg-ceiling-save');
  const ceilingCheck = row.querySelector('.leg-ceiling-check');
  markFieldState(ceilingBtn, ceilingCheck, ceilingInput, true, true); // valor renderizado = valor salvo
  ceilingInput.addEventListener('input', () => markFieldState(ceilingBtn, ceilingCheck, ceilingInput, false, true));

  ceilingBtn.addEventListener('click', async () => {
    const value = Number(ceilingInput.value);
    if (!value || value <= 0) {
      alert('Informe um teto válido.');
      return;
    }
    const error = await updateLegState(leg.id, { price_ceiling: value });
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
  markFieldState(notesBtn, notesCheck, notesInput, true, !!notesInput.value.trim());
  let notesSaved = true;
  const saveNotes = async () => {
    if (notesSaved) return;
    notesSaved = true;
    markFieldState(notesBtn, notesCheck, notesInput, true, !!notesInput.value.trim());
    const error = await updateLegState(leg.id, { notes: notesInput.value.trim() || null });
    if (error) {
      alert('Erro ao salvar observações: ' + error.message);
      notesSaved = false;
      markFieldState(notesBtn, notesCheck, notesInput, false, !!notesInput.value.trim());
      return;
    }
    showFlash('Observações salvas.');
  };
  notesInput.addEventListener('input', () => {
    notesSaved = false;
    markFieldState(notesBtn, notesCheck, notesInput, false, !!notesInput.value.trim());
    markFieldFill(notesInput, !!notesInput.value.trim());
  });
  notesInput.addEventListener('blur', saveNotes);
  notesBtn.addEventListener('click', saveNotes);

  const paidInput = row.querySelector('.leg-paid-input');
  if (paidInput) {
    const paidBtn = row.querySelector('.leg-paid-save');
    const paidCheck = row.querySelector('.leg-paid-check');
    markFieldState(paidBtn, paidCheck, paidInput, true, paidInput.value !== '');
    let paidSaved = true;
    const savePaid = async () => {
      if (paidSaved) return;
      paidSaved = true;
      markFieldState(paidBtn, paidCheck, paidInput, true, paidInput.value !== '');
      const value = paidInput.value === '' ? null : Number(paidInput.value);
      const error = await updateLegState(leg.id, { paid_price: value });
      if (error) {
        alert('Erro ao salvar valor pago: ' + error.message);
        paidSaved = false;
        markFieldState(paidBtn, paidCheck, paidInput, false, paidInput.value !== '');
        return;
      }
      showFlash('Valor pago salvo.');
    };
    paidInput.addEventListener('input', () => {
      paidSaved = false;
      markFieldState(paidBtn, paidCheck, paidInput, false, paidInput.value !== '');
      markFieldFill(paidInput, paidInput.value !== '');
    });
    paidInput.addEventListener('blur', savePaid);
    paidBtn.addEventListener('click', savePaid);
  }

  row.querySelector('.leg-action').addEventListener('click', async () => {
    const nextStatus = isPurchased ? 'monitoring' : 'purchased';
    const error = await updateLegState(leg.id, {
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

// Total pago de um fim de semana 2/2 — nunca soma ignorando perna sem
// paid_price (produziria um total falso). Sem nenhum valor: sem total.
function weekendPaidTotal(legs) {
  const paidValues = legs
    .filter((leg) => leg.status === 'purchased')
    .map((leg) => leg.paid_price)
    .filter((v) => v != null);
  if (paidValues.length === 0) return null;
  const total = paidValues.reduce((sum, v) => sum + Number(v), 0);
  const label = paidValues.length === legs.length ? 'total pago' : 'total parcial';
  return { total, label };
}

function renderCard(weekend) {
  const card = document.createElement('div');
  const legs = weekend.weekend_legs || [];
  const purchasedCount = legs.filter((leg) => leg.status === 'purchased').length;
  const days = daysUntil(weekend.outbound_date);
  const urgency = days < 0 ? 'já passou' : days === 0 ? 'é hoje' : `faltam ${days} dias`;

  // Progresso do fim de semana (0/2, 1/2, 2/2) reaproveitado na faixa no
  // topo do card (A3), na cor do contador (A6) e no card colapsado (B2).
  const progressClass = purchasedCount === 0 ? ''
    : legs.length > 0 && purchasedCount === legs.length ? 'done'
    : 'part';
  const isDone = progressClass === 'done';

  // Card 2/2 nasce colapsado (B2) — estado só em memória/DOM, some ao
  // recarregar. Sem persistência nova.
  card.className = `card weekend-card${isDone ? ' is-collapsed' : ''}`;
  card.id = `weekend-${weekend.id}`;

  const rail = document.createElement('div');
  rail.className = `card-rail ${progressClass ? `rail-${progressClass}` : ''}`.trim();
  card.appendChild(rail);

  const tags = weekendTags(weekend);
  const badges = tags.map(({ tag }) => {
    if (tag === 'feriado') return '<span class="badge holiday" title="Feriado — dificilmente fica abaixo do teto padrão">🎉 feriado</span>';
    return '<span class="badge high-season" title="Alta temporada — dificilmente fica abaixo do teto padrão">☀️ alta temporada</span>';
  }).join('');

  const header = document.createElement('div');
  header.className = 'weekend-card-header';
  header.innerHTML = `
    <h3>${formatDateBr(weekend.outbound_date)} → ${formatDateBr(weekend.return_sunday)} ou ${formatDateBr(weekend.return_monday)} ${badges}</h3>
    <span class="price-meta">${urgency} · <span class="count ${progressClass ? `count-${progressClass}` : ''}">${purchasedCount}/2 compradas</span></span>
  `;
  card.appendChild(header);

  const outboundLeg = legs.find((leg) => leg.direction === 'outbound');
  const returnLeg = legs.find((leg) => leg.direction === 'return');
  if (outboundLeg) card.appendChild(renderLegRow(outboundLeg, weekend));
  if (returnLeg) card.appendChild(renderLegRow(returnLeg, weekend));

  if (isDone) {
    const paidTotal = weekendPaidTotal(legs);
    const doneHead = document.createElement('div');
    doneHead.className = 'card-done-head';
    doneHead.innerHTML = `
      <div class="card-done-left">
        <div class="card-done-dates">✓ ${formatDateBr(weekend.outbound_date)} → ${formatDateBr(weekend.return_sunday)} ou ${formatDateBr(weekend.return_monday)}</div>
        <div class="card-done-sub">2/2 compradas · ida e volta resolvidas</div>
      </div>
      ${paidTotal ? `<div class="card-done-total">R$ ${paidTotal.total.toFixed(2)}<small>${paidTotal.label}</small></div>` : ''}
      <div class="card-done-chev">▾</div>
    `;
    doneHead.addEventListener('click', () => card.classList.toggle('is-collapsed'));
    card.appendChild(doneHead);
  }

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

// weekend_leg_effective (view da Etapa 4.1/4.2) expõe a perna como `leg_id`,
// não `id` — normaliza aqui para o resto do arquivo continuar assumindo
// leg.id (renderLegRow, legLabel, updateLegState, etc.) sem outra mudança.
function normalizeLegRow(row) {
  return { ...row, id: row.leg_id };
}

async function loadWeekends() {
  const { data: weekends, error: wErr } = await supabase
    .from('weekends')
    .select('*')
    .order('outbound_date', { ascending: true });
  if (wErr) {
    alert('Erro ao carregar fins de semana: ' + wErr.message);
    return;
  }

  const { data: legRows, error: lErr } = await supabase
    .from('weekend_leg_effective')
    .select('*');
  if (lErr) {
    alert('Erro ao carregar tetos e status: ' + lErr.message);
    return;
  }

  const legsByWeekend = {};
  for (const row of legRows || []) {
    const leg = normalizeLegRow(row);
    (legsByWeekend[leg.weekend_id] ??= []).push(leg);
  }

  allWeekends = (weekends || []).map((w) => ({ ...w, weekend_legs: legsByWeekend[w.id] || [] }));
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

async function initPage(session) {
  wireLogout('logout');
  wireTabs();
  wireFilterChips();

  currentFilter = initialFilterFromUrl();
  document.querySelectorAll('.filter-chip').forEach((chip) => {
    chip.classList.toggle('active', chip.dataset.filter === currentFilter);
  });

  await loadWeekends();

  const { data: settingsRows, error: sErr } = await supabase
    .from('settings')
    .select('weekend_default_ceiling')
    .eq('user_id', session.user.id)
    .limit(1);
  if (sErr) {
    alert('Erro ao carregar teto padrão: ' + sErr.message);
    return;
  }
  document.getElementById('default-ceiling-input').value = settingsRows?.[0]?.weekend_default_ceiling ?? '';

  document.getElementById('apply-ceiling-btn').addEventListener('click', async () => {
    const value = Number(document.getElementById('default-ceiling-input').value);
    if (!value || value <= 0) {
      alert('Informe um teto válido.');
      return;
    }
    const confirmed = confirm(
      `Isso vai mudar seu teto padrão para R$ ${value}. Pernas sem ajuste próprio passam a usar ` +
      `esse valor automaticamente; pernas onde você já definiu um teto específico continuam com o ` +
      `valor próprio, sem mudança. Confirma?`
    );
    if (!confirmed) return;

    const { error } = await supabase
      .from('settings')
      .upsert({ user_id: session.user.id, weekend_default_ceiling: value });
    if (error) {
      alert('Erro ao salvar teto padrão: ' + error.message);
      return;
    }
    showFlash('Teto padrão salvo.');
    await loadWeekends();
  });
}

const session = await requireAuth();
if (session) {
  await initPage(session);
}
