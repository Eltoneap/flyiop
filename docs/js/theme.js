// Chave duplicada de propósito no script inline de anti-flash de cada
// HTML (precisa rodar de forma síncrona, antes deste módulo carregar).
// Se mudar aqui, mudar também nos 4 <head>.
const THEME_KEY = 'flyiop-theme';

function getTheme() {
  return localStorage.getItem(THEME_KEY) || 'dark';
}

function updateButtonIcon(button, theme) {
  button.textContent = theme === 'dark' ? '🌙' : '☀️';
}

function applyTheme(theme, button) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_KEY, theme);
  if (button) updateButtonIcon(button, theme);
  document.dispatchEvent(new CustomEvent('theme:change', { detail: { theme } }));
}

function initThemeToggle() {
  const button = document.getElementById('theme-toggle');
  if (!button) return;

  updateButtonIcon(button, getTheme());

  button.addEventListener('click', () => {
    const next = getTheme() === 'dark' ? 'light' : 'dark';
    applyTheme(next, button);
  });
}

initThemeToggle();
