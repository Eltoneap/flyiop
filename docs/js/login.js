import { supabase } from './supabase-client.js';

const { data: { session } } = await supabase.auth.getSession();
if (session) window.location.href = 'index.html';

const form = document.getElementById('login-form');
const errorEl = document.getElementById('login-error');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errorEl.style.display = 'none';

  const email = form.email.value.trim();
  const password = form.password.value;
  const { error } = await supabase.auth.signInWithPassword({ email, password });

  if (error) {
    errorEl.textContent = 'Login inválido: ' + error.message;
    errorEl.style.display = 'block';
    return;
  }
  window.location.href = 'index.html';
});
