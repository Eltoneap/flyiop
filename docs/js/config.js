import { supabase } from './supabase-client.js';
import { requireAuth, wireLogout } from './auth-guard.js';

const DEFAULT_SETTINGS = {
  window_3d_pct: 10,
  window_7d_pct: 15,
  notification_mode: 'alert_only',
  cost_per_thousand_brl: 25,
};

function showFlash() {
  const flash = document.getElementById('flash');
  flash.style.display = 'block';
  setTimeout(() => { flash.style.display = 'none'; }, 2000);
}

async function loadRoutes() {
  const { data: routes, error } = await supabase.from('routes').select('*').order('created_at');
  const tbody = document.getElementById('routes-body');
  const emptyEl = document.getElementById('routes-empty');
  tbody.innerHTML = '';

  if (error) {
    alert('Erro ao carregar rotas: ' + error.message);
    return;
  }

  emptyEl.style.display = routes && routes.length ? 'none' : 'block';

  for (const route of routes || []) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${route.origin}</td>
      <td>${route.destination}</td>
      <td>${route.currency}</td>
      <td><input type="number" step="0.01" value="${route.target_price ?? ''}" data-field="target_price"></td>
      <td><input type="number" step="0.1" value="${route.target_percent_below_avg ?? ''}" data-field="target_percent_below_avg"></td>
      <td style="white-space:nowrap;">
        <button type="button" class="small save-btn">Salvar</button>
        <button type="button" class="small danger delete-btn">Excluir</button>
      </td>
    `;

    tr.querySelector('.save-btn').addEventListener('click', async () => {
      const targetPrice = tr.querySelector('[data-field="target_price"]').value;
      const targetPercent = tr.querySelector('[data-field="target_percent_below_avg"]').value;
      const { error: updateError } = await supabase
        .from('routes')
        .update({
          target_price: targetPrice ? Number(targetPrice) : null,
          target_percent_below_avg: targetPercent ? Number(targetPercent) : null,
        })
        .eq('id', route.id);
      if (updateError) {
        alert('Erro ao salvar: ' + updateError.message);
        return;
      }
      showFlash();
    });

    tr.querySelector('.delete-btn').addEventListener('click', async () => {
      if (!confirm('Remover esta rota?')) return;
      const { error: deleteError } = await supabase.from('routes').delete().eq('id', route.id);
      if (deleteError) {
        alert('Erro ao excluir: ' + deleteError.message);
        return;
      }
      await loadRoutes();
    });

    tbody.appendChild(tr);
  }
}

async function loadSettings(userId) {
  const { data: rows } = await supabase.from('settings').select('*').eq('user_id', userId).limit(1);
  const settings = rows && rows[0] ? rows[0] : DEFAULT_SETTINGS;
  const form = document.getElementById('settings-form');
  form.window_3d_pct.value = settings.window_3d_pct;
  form.window_7d_pct.value = settings.window_7d_pct;
  form.notification_mode.value = settings.notification_mode;
  form.cost_per_thousand_brl.value = settings.cost_per_thousand_brl;
}

const session = await requireAuth();
if (session) {
  wireLogout('logout');
  await loadRoutes();
  await loadSettings(session.user.id);

  document.getElementById('add-route-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const { error } = await supabase.from('routes').insert({
      origin: form.origin.value.trim().toUpperCase(),
      destination: form.destination.value.trim().toUpperCase(),
      currency: (form.currency.value.trim() || 'BRL').toUpperCase(),
      target_price: form.target_price.value ? Number(form.target_price.value) : null,
      target_percent_below_avg: form.target_percent_below_avg.value
        ? Number(form.target_percent_below_avg.value)
        : null,
    });
    if (error) {
      alert('Erro ao adicionar rota: ' + error.message);
      return;
    }
    form.reset();
    form.currency.value = 'BRL';
    await loadRoutes();
    showFlash();
  });

  document.getElementById('settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const { error } = await supabase.from('settings').upsert({
      user_id: session.user.id,
      window_3d_pct: Number(form.window_3d_pct.value),
      window_7d_pct: Number(form.window_7d_pct.value),
      notification_mode: form.notification_mode.value,
      cost_per_thousand_brl: Number(form.cost_per_thousand_brl.value),
      updated_at: new Date().toISOString(),
    });
    if (error) {
      alert('Erro ao salvar preferências: ' + error.message);
      return;
    }
    showFlash();
  });
}
