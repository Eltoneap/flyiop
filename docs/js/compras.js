import { supabase } from './supabase-client.js';
import { requireAuth, wireLogout } from './auth-guard.js';
import { weekendTags } from './holidays.js';

const VALID_FILTERS = ['todas', 'abaixo-do-teto', 'sem-preco', 'feriado-alta-temporada', 'proximos-60-dias'];
const URGENCY_WINDOW_DAYS = 60;

const DEFAULT_USER_LABEL = 'Outro usuário';

let allWeekends = [];
let currentTab = 'active';
let currentFilter = 'todas';
let currentUserId = null;

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

// Fatia C, Parte 2 — assimetria de fuso deliberada entre dois campos que
// parecem iguais mas não são:
//
// current_departure_time (robô, fli): a fli devolve datetime NAIVE — hora
// LOCAL do voo, sem offset (tests/test_live_check.py: "2026-09-04T08:30:00").
// Ao gravar numa coluna timestamptz, o Postgres rotula como +00. Um voo que
// sai 08:30 de Brasília fica gravado como 08:30+00. Ler o HH:MM/data CRUS da
// string, SEM conversão de fuso, é o comportamento CORRETO aqui — converter
// para America/Sao_Paulo daria 05:30, errado por 3h.
function rawDateFromRobotTimestamp(iso) {
  return iso ? iso.slice(0, 10) : null;
}
function rawTimeFromRobotTimestamp(iso) {
  return iso ? iso.slice(11, 16) : null;
}

// purchased_departure_time (esta fatia): gravado com offset -03:00 real —
// timestamptz correto. Aqui SIM convertemos para America/Sao_Paulo na
// leitura. Brasil não tem horário de verão desde 2019, então -03:00 fixo
// cobre toda a janela 2026-2027 monitorada.
const SP_DATE_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit',
});
// hourCycle: 'h23' em vez de hour12: false — com hour12 alguns motores
// (historicamente Safari/iOS) devolvem "24:00" para meia-noite, que é valor
// inválido num <input type="time">. Precaução, não bug reproduzido.
const SP_TIME_FORMATTER = new Intl.DateTimeFormat('pt-BR', {
  timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});
function spDateTimeParts(iso) {
  if (!iso) return { date: null, time: null };
  const d = new Date(iso);
  return { date: SP_DATE_FORMATTER.format(d), time: SP_TIME_FORMATTER.format(d) };
}

function composeDepartureTimestamp(date, time) {
  return date && time ? `${date}T${time}:00-03:00` : null;
}

function formatSharedFlight(row) {
  const label = DEFAULT_USER_LABEL;
  const { date, time } = spDateTimeParts(row.purchased_departure_time);
  const bits = [
    row.purchased_airline,
    row.purchased_airport,
    date && time ? `${formatDateBr(date)}, ${time}` : null,
  ].filter(Boolean);
  if (bits.length === 0) return `👥 ${label} já comprou · voo não informado`;
  return `👥 ${label} já comprou · ${bits.join(' · ')}`;
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

// Fallback de frescor (revisão do usuário, 04/09/2026): current_price_at
// nasce NULL em toda perna já existente antes desta fatia, e nunca é
// preenchido nas ~44 pernas além do alcance da fonte (305 dias — a
// correção de 01/09 as tirou do lote, e o radar nunca as alcança) — sem
// fallback, o rótulo "atualizado" ficaria vazio nelas pra sempre, mesmo já
// tendo sido verificadas antes. Quando o timestamp do preço que está
// sendo exibido não existe, cai pra last_live_check_at (idade da última
// TENTATIVA, sucesso ou falha — não a do preço) — e sinaliza isso via
// `verificationOnly`, pra renderLegRow trocar o rótulo de "atualizado"
// pra "verificado" em vez de fingir que é a idade do preço.
function priceAge(priceAt, leg) {
  if (priceAt != null) return { at: priceAt, verificationOnly: false };
  if (leg.last_live_check_at != null) return { at: leg.last_live_check_at, verificationOnly: true };
  return { at: null, verificationOnly: false };
}

// Radar de calendário, Fatia 2 (04/09/2026) — número principal da perna é o
// preço MAIS RECENTE entre radar_price (não confirmado, weekend_legs.
// radar_price/radar_price_at, gravado pra TODA perna dentro do alcance) e
// current_price (confirmado por SearchFlights/Travelpayouts, current_price_at).
// legPriceState/legStatusBadge (acima) e o filtro isBelowCeiling (abaixo)
// continuam lendo SÓ current_price de propósito — o selo de ação e o filtro
// "abaixo do teto" nunca consideram preço do radar (decisão do usuário,
// 04/09/2026: preço do radar aparece como número + rótulo, nunca como sinal
// de ação). Sem confirmado nem radar: null (renderLegRow mostra "sem preço").
function displayedLegPrice(leg) {
  const hasConfirmed = leg.current_price != null;
  const hasRadar = leg.radar_price != null;
  if (!hasConfirmed && !hasRadar) return null;
  if (hasConfirmed && !hasRadar) {
    return {
      price: leg.current_price, airport: leg.current_airport, source: leg.current_source,
      confirmed: true, ...priceAge(leg.current_price_at, leg),
    };
  }
  if (hasRadar && !hasConfirmed) {
    return {
      price: leg.radar_price, airport: leg.radar_airport, source: 'radar',
      confirmed: false, ...priceAge(leg.radar_price_at, leg),
    };
  }
  // Os dois existem — o mais recente vence. Sem timestamp de um dos dois
  // (não deveria acontecer em dado gravado por esta fatia em diante, mas
  // pode em pernas já confirmadas antes dela): quem TEM timestamp vence —
  // uma comparação com Invalid Date nunca decide sozinha.
  const radarAt = leg.radar_price_at;
  const confirmedAt = leg.current_price_at;
  const radarIsNewer = radarAt != null
    && (confirmedAt == null || new Date(radarAt).getTime() > new Date(confirmedAt).getTime());
  return radarIsNewer
    ? { price: leg.radar_price, airport: leg.radar_airport, source: 'radar', confirmed: false, ...priceAge(radarAt, leg) }
    : { price: leg.current_price, airport: leg.current_airport, source: leg.current_source, confirmed: true, ...priceAge(confirmedAt, leg) };
}

function renderLegRow(leg, weekend) {
  const { title, date } = legLabel(leg, weekend);
  const isPurchased = leg.status === 'purchased';
  const row = document.createElement('div');
  row.className = `leg-row${isPurchased ? ' is-bought' : ''}`;

  const displayed = displayedLegPrice(leg);
  const livePriceText = displayed
    ? `R$ ${Number(displayed.price).toFixed(2)}`
    : '— sem preço ainda';
  const sourceBits = displayed ? [displayed.airport, displayed.source].filter(Boolean) : [];
  const sourceText = displayed && sourceBits.length ? ` (${sourceBits.join(' · ')})` : '';
  // Preço não confirmado precisa ser identificável a olho nu, sem depender
  // de memória (pedido do usuário) — badge visível junto do número.
  const unconfirmedBadge = displayed && !displayed.confirmed
    ? ' <span class="leg-unconfirmed">não confirmado</span>' : '';
  // O confirmado NUNCA some da tela quando o radar assume a frente — some
  // aqui embaixo, discreto, com a própria idade (não a do preço principal;
  // mesmo fallback de priceAge, pro rótulo não ficar "nunca verificado"
  // quando current_price_at é nulo mas last_live_check_at não é).
  let secondaryConfirmedHtml = '';
  if (displayed && !displayed.confirmed && leg.current_price != null) {
    const confirmedAge = priceAge(leg.current_price_at, leg);
    const confirmedLabel = confirmedAge.verificationOnly ? 'verificado' : 'confirmado';
    secondaryConfirmedHtml = `<small class="leg-price-secondary">${confirmedLabel} ${formatLastCheck(confirmedAge.at)}: R$ ${Number(leg.current_price).toFixed(2)}</small>`;
  }

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
    priceHtml = `${livePriceText}${sourceText}${unconfirmedBadge}${secondaryConfirmedHtml}`;
  }

  // "verificado" (não "atualizado") quando caiu no fallback de
  // last_live_check_at — não é a idade do preço, é a da última tentativa.
  const updatedLabel = displayed && displayed.verificationOnly ? 'verificado' : 'atualizado';

  const notesFilled = !!(leg.notes ?? '').toString().trim();
  const paidFilled = leg.paid_price != null && leg.paid_price !== '';

  // Linha do outro usuário (item 3) — só existe se houver linha na projeção
  // filtrada (loadWeekends já removeu a própria linha via .neq). Nunca entra
  // em contadores/progresso/abas/filtros, que continuam lendo só leg.status.
  const sharedHtml = (leg.shared_purchases || [])
    .map((sharedRow) => `<span class="leg-shared">${escapeAttr(formatSharedFlight(sharedRow))}</span>`)
    .join('');

  row.innerHTML = `
    <div class="leg-row-main">
      <span class="leg-title">${title}${date ? ' ' + formatDateBr(date) : ''}</span>
      <span class="${priceClass}">${priceHtml}</span>
    </div>
    <div class="leg-row-meta">
      <span class="leg-updated">${updatedLabel} ${formatLastCheck(displayed && displayed.at)}</span>
      <a class="small leg-buy-link" href="${purchaseLink}" target="_blank" rel="noopener">Ver/comprar</a>
    </div>
    ${sharedHtml}
    <div class="leg-row-controls">
      <label class="leg-ceiling-label">
        teto R$ <input type="number" step="1" min="0" value="${leg.price_ceiling}" class="leg-ceiling-input field-filled">
        <span class="save-check leg-ceiling-check">✓</span>
      </label>
      <button type="button" class="small leg-ceiling-save">Salvar</button>
      <span class="badge ${badge.cls}">${badge.text}</span>
      ${isPurchased ? '<button type="button" class="btn-undo">Desfazer compra</button>' : ''}
    </div>
    <div class="leg-row-notes">
      <input type="text" class="leg-notes-input ${notesFilled ? 'field-filled' : 'field-empty'}" placeholder="localizador, observações..." value="${escapeAttr(leg.notes ?? '')}">
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
    <div class="leg-row-flight">
      <label class="leg-flight-label">Companhia
        <input type="text" class="leg-flight-airline leg-flight-input leg-flight-input--text" placeholder="ex: LATAM">
      </label>
      <div class="leg-flight-label">Aeroporto
        <button type="button" class="leg-airport-btn leg-flight-airport" data-airport="GIG">GIG</button>
        <button type="button" class="leg-airport-btn leg-flight-airport" data-airport="SDU">SDU</button>
      </div>
      <label class="leg-flight-label">Data
        <input type="date" class="leg-flight-date leg-flight-input leg-flight-input--date">
      </label>
      <label class="leg-flight-label">Hora
        <input type="time" class="leg-flight-time leg-flight-input leg-flight-input--time">
      </label>
      <button type="button" class="small leg-flight-save">Salvar</button>
      <span class="save-check leg-flight-check">✓</span>
      <span class="leg-flight-hint leg-confirm-hint" style="display:none;">Informe a data para salvar o horário.</span>
    </div>
    ` : ''}
    ${!isPurchased ? `
    <button type="button" class="btn-outline-full leg-mark-bought">Marcar como comprada</button>
    <div class="leg-row-confirm" style="display:none;">
      <label class="leg-confirm-label">Companhia
        <input type="text" class="leg-confirm-airline leg-confirm-input leg-confirm-input--text" placeholder="ex: LATAM">
      </label>
      <div class="leg-confirm-label">Aeroporto
        <button type="button" class="leg-airport-btn leg-confirm-airport" data-airport="GIG">GIG</button>
        <button type="button" class="leg-airport-btn leg-confirm-airport" data-airport="SDU">SDU</button>
      </div>
      <label class="leg-confirm-label">Data
        <input type="date" class="leg-confirm-date leg-confirm-input leg-confirm-input--date">
      </label>
      <label class="leg-confirm-label">Hora
        <input type="time" class="leg-confirm-time leg-confirm-input leg-confirm-input--time">
      </label>
      <div class="leg-confirm-actions">
        <button type="button" class="small leg-confirm-save">Confirmar compra</button>
        <button type="button" class="small leg-confirm-cancel">Cancelar</button>
      </div>
      <span class="leg-confirm-hint" style="display:none;">Informe a data para salvar o horário.</span>
    </div>
    ` : ''}
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

  // Desfazer compra (item 6) — sem mudança de comportamento: um clique, sem
  // diálogo. A trigger flyiop_sync_purchase_shared limpa a projeção sozinha;
  // as 3 colunas de snapshot permanecem na linha do usuário (não tocadas
  // aqui), o que é o que sustenta a recompra pré-preenchida (item 7).
  const undoBtn = row.querySelector('.btn-undo');
  if (undoBtn) {
    undoBtn.addEventListener('click', async () => {
      const error = await updateLegState(leg.id, { status: 'monitoring', purchased_at: null });
      if (error) {
        alert('Erro ao desfazer: ' + error.message);
        return;
      }
      showFlash('Desfeito — voltou para monitoramento.');
      await loadWeekends();
    });
  }

  // Toggle de seleção única com "clicar de novo desmarca" (ajuste B) —
  // reaproveitado no painel de confirmação e no bloco de edição pós-compra.
  const wireAirportToggle = (buttons, initial, onChange) => {
    let selected = initial;
    const paint = () => buttons.forEach((b) => b.classList.toggle('is-selected', b.dataset.airport === selected));
    paint();
    buttons.forEach((btn) => btn.addEventListener('click', () => {
      selected = selected === btn.dataset.airport ? null : btn.dataset.airport;
      paint();
      onChange(selected);
    }));
    return () => selected;
  };

  // Painel de confirmação de compra (item 4) — substitui o clique direto:
  // "Marcar como comprada" abre o painel, só o botão Confirmar salva.
  const markBoughtBtn = row.querySelector('.leg-mark-bought');
  if (markBoughtBtn) {
    const confirmPanel = row.querySelector('.leg-row-confirm');
    const airlineInput = row.querySelector('.leg-confirm-airline');
    const dateInput = row.querySelector('.leg-confirm-date');
    const timeInput = row.querySelector('.leg-confirm-time');
    const confirmHint = row.querySelector('.leg-row-confirm .leg-confirm-hint');
    const confirmSaveBtn = row.querySelector('.leg-confirm-save');
    const confirmCancelBtn = row.querySelector('.leg-confirm-cancel');
    const airportButtons = Array.from(row.querySelectorAll('.leg-confirm-airport'));

    const snapshot = leg.purchased_snapshot;
    const snapshotParts = spDateTimeParts(snapshot?.purchased_departure_time);
    const robotDate = rawDateFromRobotTimestamp(leg.current_departure_time);
    const robotTime = rawTimeFromRobotTimestamp(leg.current_departure_time);

    // Ajuste A: sempre que a hora vier pré-preenchida a partir do voo
    // monitorado, a data precisa vir junto — senão o painel nasce num estado
    // que a própria validação de baixo bloqueia (hora sem data). Cadeia:
    // snapshot → data da perna → data crua do voo monitorado → vazio.
    airlineInput.value = snapshot?.purchased_airline ?? leg.current_airline ?? '';
    dateInput.value = snapshotParts.date ?? date ?? robotDate ?? '';
    timeInput.value = snapshotParts.time ?? robotTime ?? '';
    const getSelectedAirport = wireAirportToggle(
      airportButtons,
      snapshot?.purchased_airport ?? leg.current_airport ?? null,
      () => {},
    );

    markBoughtBtn.addEventListener('click', () => {
      markBoughtBtn.style.display = 'none';
      confirmPanel.style.display = 'flex';
    });

    confirmCancelBtn.addEventListener('click', () => {
      confirmPanel.style.display = 'none';
      markBoughtBtn.style.display = ''; // remove o inline, devolve o botão ao que o CSS define
    });

    confirmSaveBtn.addEventListener('click', async () => {
      const purchasedDate = dateInput.value || null;
      const purchasedTime = timeInput.value || null;
      if (purchasedTime && !purchasedDate) {
        confirmHint.style.display = 'block';
        return;
      }
      confirmHint.style.display = 'none';
      const error = await updateLegState(leg.id, {
        status: 'purchased',
        purchased_at: new Date().toISOString(),
        purchased_airline: airlineInput.value.trim() || null,
        purchased_airport: getSelectedAirport(),
        purchased_departure_time: composeDepartureTimestamp(purchasedDate, purchasedTime),
      });
      if (error) {
        alert('Erro ao marcar como comprada: ' + error.message);
        return;
      }
      showFlash('Marcada como comprada — pode desfazer quando quiser.');
      await loadWeekends();
    });
  }

  // Bloco de edição pós-compra (item 5) — 1 botão Salvar para os 4 campos
  // juntos (diferente de paid/notes, que têm 1 por campo): data e hora se
  // combinam num timestamptz só, salvar separado quebraria o valor.
  const flightAirlineInput = row.querySelector('.leg-flight-airline');
  if (flightAirlineInput) {
    const flightDateInput = row.querySelector('.leg-flight-date');
    const flightTimeInput = row.querySelector('.leg-flight-time');
    const flightHint = row.querySelector('.leg-flight-hint');
    const flightSaveBtn = row.querySelector('.leg-flight-save');
    const flightCheck = row.querySelector('.leg-flight-check');
    const flightAirportButtons = Array.from(row.querySelectorAll('.leg-flight-airport'));
    const flightInputs = [flightAirlineInput, flightDateInput, flightTimeInput];

    const snapshot = leg.purchased_snapshot;
    const snapshotParts = spDateTimeParts(snapshot?.purchased_departure_time);
    flightAirlineInput.value = snapshot?.purchased_airline ?? '';
    flightDateInput.value = snapshotParts.date ?? '';
    flightTimeInput.value = snapshotParts.time ?? '';

    let flightSaved = true;
    // Mesmo padrão de markFieldState (saved && hasValue): o ✓ só aparece se
    // houver de fato algo salvo — bloco inteiro em branco não ganha check.
    const markFlightState = (saved) => {
      flightSaveBtn.classList.toggle('saved', saved);
      flightSaveBtn.classList.toggle('dirty', !saved);
      flightInputs.forEach((input) => input.classList.toggle('field-dirty', !saved));
      const hasValue = flightInputs.some((input) => input.value !== '') || !!getSelectedAirport();
      flightCheck.style.display = saved && hasValue ? 'inline' : 'none';
    };

    const getSelectedAirport = wireAirportToggle(flightAirportButtons, snapshot?.purchased_airport ?? null, () => {
      flightSaved = false;
      markFlightState(false);
    });
    markFlightState(true); // depois do toggle: markFlightState lê getSelectedAirport

    flightInputs.forEach((input) => input.addEventListener('input', () => {
      flightSaved = false;
      markFlightState(false);
    }));

    flightSaveBtn.addEventListener('click', async () => {
      if (flightSaved) return;
      const purchasedDate = flightDateInput.value || null;
      const purchasedTime = flightTimeInput.value || null;
      if (purchasedTime && !purchasedDate) {
        flightHint.style.display = 'block';
        return;
      }
      flightHint.style.display = 'none';
      const flight = {
        purchased_airline: flightAirlineInput.value.trim() || null,
        purchased_airport: getSelectedAirport(),
        purchased_departure_time: composeDepartureTimestamp(purchasedDate, purchasedTime),
      };
      const error = await updateLegState(leg.id, flight);
      if (error) {
        alert('Erro ao salvar dados do voo: ' + error.message);
        return;
      }
      // Este bloco não recarrega a página (igual a paid/notes), então o
      // snapshot em memória precisa acompanhar: sem isso, um re-render sem
      // reload (trocar de aba, trocar de filtro) redesenharia os campos com o
      // valor ANTIGO, parecendo que o salvamento falhou.
      leg.purchased_snapshot = { ...(leg.purchased_snapshot || {}), ...flight };
      flightSaved = true;
      markFlightState(true);
      showFlash('Dados do voo salvos.');
    });
  }

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
  // Fatia C, Parte 2 — 5 consultas independentes, nenhuma misturada num
  // select('*') só. As 2 primeiras mantêm o comportamento de erro bloqueante
  // de antes (sem elas o painel não tem o que mostrar); as 3 novas falham
  // suave — funcionalidade nova não deve derrubar o painel inteiro.
  const [wRes, lRes, legsRes, sharedRes, snapshotRes] = await Promise.all([
    supabase.from('weekends').select('*').order('outbound_date', { ascending: true }),
    supabase.from('weekend_leg_effective').select('*'),
    supabase.from('weekend_legs').select(
      'id, current_airline, current_departure_time, current_price_at, radar_price, radar_price_at, radar_airport'
    ),
    supabase.from('weekend_leg_purchase_shared')
      .select('leg_id, user_id, purchased_airline, purchased_airport, purchased_departure_time')
      .neq('user_id', currentUserId), // policy devolve a própria linha também — filtro no front é obrigatório
    supabase.from('weekend_leg_user_state')
      .select('leg_id, purchased_airline, purchased_airport, purchased_departure_time'),
  ]);

  if (wRes.error) {
    alert('Erro ao carregar fins de semana: ' + wRes.error.message);
    return;
  }
  if (lRes.error) {
    alert('Erro ao carregar tetos e status: ' + lRes.error.message);
    return;
  }
  if (legsRes.error) console.error('Erro ao carregar dados de voo (weekend_legs):', legsRes.error);
  if (sharedRes.error) console.error('Erro ao carregar compras de outros usuários:', sharedRes.error);
  if (snapshotRes.error) console.error('Erro ao carregar snapshot de compra:', snapshotRes.error);
  if (legsRes.error || sharedRes.error || snapshotRes.error) {
    showFlash('Alguns dados de compra podem não ter carregado — veja o console.');
  }

  const flightById = {};
  for (const row of legsRes.data || []) flightById[row.id] = row;

  const sharedByLeg = {};
  for (const row of sharedRes.data || []) (sharedByLeg[row.leg_id] ??= []).push(row);

  const snapshotByLeg = {};
  for (const row of snapshotRes.data || []) snapshotByLeg[row.leg_id] = row;

  const legsByWeekend = {};
  for (const row of lRes.data || []) {
    const leg = normalizeLegRow(row);
    const flight = flightById[leg.id];
    leg.current_airline = flight?.current_airline ?? null;
    leg.current_departure_time = flight?.current_departure_time ?? null;
    // Radar de calendário, Fatia 2 (04/09/2026) — weekend_leg_effective
    // (view) não foi recriada nesta fatia por decisão explícita (Dashboard
    // continua lendo só preço confirmado); Compras ganha as colunas novas
    // por este segundo select direto em weekend_legs, igual current_airline.
    leg.current_price_at = flight?.current_price_at ?? null;
    leg.radar_price = flight?.radar_price ?? null;
    leg.radar_price_at = flight?.radar_price_at ?? null;
    leg.radar_airport = flight?.radar_airport ?? null;
    leg.shared_purchases = sharedByLeg[leg.id] || [];
    leg.purchased_snapshot = snapshotByLeg[leg.id] || null;
    (legsByWeekend[leg.weekend_id] ??= []).push(leg);
  }

  allWeekends = (wRes.data || []).map((w) => ({ ...w, weekend_legs: legsByWeekend[w.id] || [] }));
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
  currentUserId = session.user.id;
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
