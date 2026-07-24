import { supabase } from './supabase-client.js';
import { requireAuth, wireLogout } from './auth-guard.js';
import { loadAirports, attachAirportPicker } from './airports.js';

const DEFAULT_SETTINGS = {
  window_3d_pct: 10,
  window_7d_pct: 15,
  notification_mode: 'alert_only',
  cost_per_thousand_brl: 25,
  freshness_hours: 24,
  stale_alert_policy: 'warn',
  realert_drop_pct: 5,
  realert_days: 3,
  suspicious_below_avg_pct: 50,
  weekend_opportunity_pct: 15,
  fast_flights_enabled: true,
  fast_flights_daily_batch_size: 20,
};

function showFlash() {
  const flash = document.getElementById('flash');
  flash.style.display = 'block';
  setTimeout(() => { flash.style.display = 'none'; }, 2000);
}

let currentTab = 'active';

async function loadRoutes() {
  const { data: routes, error } = await supabase
    .from('routes')
    .select('*')
    .eq('archived', currentTab === 'archived')
    .order('created_at');

  const tbody = document.getElementById('routes-body');
  const emptyEl = document.getElementById('routes-empty');
  tbody.innerHTML = '';

  if (error) {
    alert('Erro ao carregar rotas: ' + error.message);
    return;
  }

  emptyEl.textContent = currentTab === 'archived'
    ? 'Nenhuma rota arquivada.'
    : 'Nenhuma rota ativa cadastrada ainda.';
  emptyEl.style.display = routes && routes.length ? 'none' : 'block';

  for (const route of routes || []) {
    const tr = document.createElement('tr');
    const archiveLabel = currentTab === 'archived' ? 'Reativar' : 'Arquivar';
    const archiveClass = currentTab === 'archived' ? '' : 'danger';

    tr.innerHTML = `
      <td>${route.origin}</td>
      <td>${route.destination}</td>
      <td>${route.currency}</td>
      <td><input type="number" step="0.01" value="${route.target_price ?? ''}" data-field="target_price"></td>
      <td><input type="number" step="0.1" value="${route.target_percent_below_avg ?? ''}" data-field="target_percent_below_avg"></td>
      <td><input type="number" step="1" min="1" value="${route.trip_duration_weeks ?? ''}" placeholder="sem restrição" data-field="trip_duration_weeks"></td>
      <td style="white-space:nowrap;">
        <button type="button" class="small save-btn">Salvar</button>
        <button type="button" class="small ${archiveClass} archive-btn">${archiveLabel}</button>
      </td>
    `;

    tr.querySelector('.save-btn').addEventListener('click', async () => {
      const targetPrice = tr.querySelector('[data-field="target_price"]').value;
      const targetPercent = tr.querySelector('[data-field="target_percent_below_avg"]').value;
      const tripDuration = tr.querySelector('[data-field="trip_duration_weeks"]').value;
      const { error: updateError } = await supabase
        .from('routes')
        .update({
          target_price: targetPrice ? Number(targetPrice) : null,
          target_percent_below_avg: targetPercent ? Number(targetPercent) : null,
          trip_duration_weeks: tripDuration ? Number(tripDuration) : null,
        })
        .eq('id', route.id);
      if (updateError) {
        alert('Erro ao salvar: ' + updateError.message);
        return;
      }
      showFlash();
    });

    tr.querySelector('.archive-btn').addEventListener('click', async () => {
      const archiving = currentTab !== 'archived';
      if (archiving && !confirm('Arquivar esta rota? O robô para de buscar preços para ela, mas todo o histórico é mantido — você pode reativar quando quiser.')) {
        return;
      }
      const { error: archiveError } = await supabase
        .from('routes')
        .update({ archived: archiving })
        .eq('id', route.id);
      if (archiveError) {
        alert('Erro ao atualizar rota: ' + archiveError.message);
        return;
      }
      await loadRoutes();
    });

    tbody.appendChild(tr);
  }
}

function wireTabs() {
  const tabActive = document.getElementById('tab-active');
  const tabArchived = document.getElementById('tab-archived');

  tabActive.addEventListener('click', () => {
    currentTab = 'active';
    tabActive.classList.add('active');
    tabArchived.classList.remove('active');
    loadRoutes();
  });

  tabArchived.addEventListener('click', () => {
    currentTab = 'archived';
    tabArchived.classList.add('active');
    tabActive.classList.remove('active');
    loadRoutes();
  });
}

async function loadSettings(userId) {
  const { data: rows } = await supabase.from('settings').select('*').eq('user_id', userId).limit(1);
  const settings = rows && rows[0] ? rows[0] : DEFAULT_SETTINGS;

  const legacyForm = document.getElementById('legacy-settings-form');
  legacyForm.window_3d_pct.value = settings.window_3d_pct;
  legacyForm.window_7d_pct.value = settings.window_7d_pct;
  legacyForm.notification_mode.value = settings.notification_mode;
  legacyForm.cost_per_thousand_brl.value = settings.cost_per_thousand_brl;
  legacyForm.freshness_hours.value = settings.freshness_hours ?? DEFAULT_SETTINGS.freshness_hours;

  // 'suppress' foi desativado no corte da Etapa 6 (a fonte v3 não informa a idade
  // do preço, então suprimir seguraria 100% dos alertas). Se o valor salvo ainda
  // for 'suppress', mostra o aviso e força a exibição para 'warn' — o robô já
  // ignora suppress quando a idade é desconhecida, mas a UI não deve mentir.
  const savedPolicy = settings.stale_alert_policy ?? DEFAULT_SETTINGS.stale_alert_policy;
  const suppressNote = document.getElementById('suppress-note');
  if (savedPolicy === 'suppress') {
    if (suppressNote) suppressNote.style.display = 'block';
    legacyForm.stale_alert_policy.value = 'warn';
  } else {
    legacyForm.stale_alert_policy.value = savedPolicy;
  }

  const weekendForm = document.getElementById('weekend-settings-form');
  weekendForm.weekend_opportunity_pct.value = settings.weekend_opportunity_pct ?? DEFAULT_SETTINGS.weekend_opportunity_pct;
  weekendForm.realert_drop_pct.value = settings.realert_drop_pct ?? DEFAULT_SETTINGS.realert_drop_pct;
  weekendForm.realert_days.value = settings.realert_days ?? DEFAULT_SETTINGS.realert_days;
  weekendForm.suspicious_below_avg_pct.value = settings.suspicious_below_avg_pct ?? DEFAULT_SETTINGS.suspicious_below_avg_pct;
  weekendForm.fast_flights_enabled.checked = settings.fast_flights_enabled ?? DEFAULT_SETTINGS.fast_flights_enabled;
  weekendForm.fast_flights_daily_batch_size.value = settings.fast_flights_daily_batch_size ?? DEFAULT_SETTINGS.fast_flights_daily_batch_size;
}

const session = await requireAuth();
if (session) {
  wireLogout('logout');
  wireTabs();
  await loadRoutes();
  await loadSettings(session.user.id);

  const airports = await loadAirports();
  const addRouteForm = document.getElementById('add-route-form');

  attachAirportPicker({
    searchInput: document.getElementById('origin-search'),
    hiddenInput: document.getElementById('origin-code'),
    listEl: document.getElementById('origin-suggestions'),
    airports,
  });
  attachAirportPicker({
    searchInput: document.getElementById('destination-search'),
    hiddenInput: document.getElementById('destination-code'),
    listEl: document.getElementById('destination-suggestions'),
    airports,
  });

  addRouteForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;

    if (!form.origin.value || !form.destination.value) {
      alert('Selecione a origem e o destino a partir da lista de sugestões (não digite o código livremente).');
      return;
    }

    const { error } = await supabase.from('routes').insert({
      origin: form.origin.value,
      destination: form.destination.value,
      currency: (form.currency.value.trim() || 'BRL').toUpperCase(),
      target_price: form.target_price.value ? Number(form.target_price.value) : null,
      target_percent_below_avg: form.target_percent_below_avg.value
        ? Number(form.target_percent_below_avg.value)
        : null,
      trip_duration_weeks: form.trip_duration_weeks.value ? Number(form.trip_duration_weeks.value) : null,
    });
    if (error) {
      alert('Erro ao adicionar rota: ' + error.message);
      return;
    }
    form.reset();
    form.currency.value = 'BRL';
    if (currentTab === 'archived') {
      currentTab = 'active';
      document.getElementById('tab-active').classList.add('active');
      document.getElementById('tab-archived').classList.remove('active');
    }
    await loadRoutes();
    showFlash();
  });

  document.getElementById('legacy-settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const { error } = await supabase.from('settings').upsert({
      user_id: session.user.id,
      window_3d_pct: Number(form.window_3d_pct.value),
      window_7d_pct: Number(form.window_7d_pct.value),
      notification_mode: form.notification_mode.value,
      cost_per_thousand_brl: Number(form.cost_per_thousand_brl.value),
      freshness_hours: Number(form.freshness_hours.value),
      stale_alert_policy: form.stale_alert_policy.value,
      updated_at: new Date().toISOString(),
    });
    if (error) {
      alert('Erro ao salvar preferências: ' + error.message);
      return;
    }
    showFlash();
  });

  document.getElementById('weekend-settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const { error } = await supabase.from('settings').upsert({
      user_id: session.user.id,
      weekend_opportunity_pct: Number(form.weekend_opportunity_pct.value),
      realert_drop_pct: Number(form.realert_drop_pct.value),
      realert_days: Number(form.realert_days.value),
      suspicious_below_avg_pct: Number(form.suspicious_below_avg_pct.value),
      fast_flights_enabled: form.fast_flights_enabled.checked,
      fast_flights_daily_batch_size: Number(form.fast_flights_daily_batch_size.value),
      updated_at: new Date().toISOString(),
    });
    if (error) {
      alert('Erro ao salvar preferências: ' + error.message);
      return;
    }
    showFlash();
  });
}
