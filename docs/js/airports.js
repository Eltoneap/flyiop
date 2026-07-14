let airportsPromise = null;

export function loadAirports() {
  if (!airportsPromise) {
    airportsPromise = fetch('data/airports.json').then((r) => r.json());
  }
  return airportsPromise;
}

function normalize(text) {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();
}

// Nomes de cidades em português que divergem do nome em inglês usado na base
const PT_CITY_ALIASES = {
  lisboa: 'lisbon',
  londres: 'london',
  'nova york': 'new york',
  'nova iorque': 'new york',
  madri: 'madrid',
  roma: 'rome',
  toquio: 'tokyo',
  pequim: 'beijing',
  moscou: 'moscow',
  genebra: 'geneva',
  florenca: 'florence',
  veneza: 'venice',
  milao: 'milan',
  napoles: 'naples',
  atenas: 'athens',
  varsovia: 'warsaw',
  praga: 'prague',
  viena: 'vienna',
  bruxelas: 'brussels',
  copenhague: 'copenhagen',
  estocolmo: 'stockholm',
  zurique: 'zurich',
  'cidade do mexico': 'mexico city',
  'cidade do cabo': 'cape town',
};

export function searchAirports(airports, query, limit = 8) {
  const q = normalize(query.trim());
  if (q.length < 2) return [];

  const terms = PT_CITY_ALIASES[q] ? [q, PT_CITY_ALIASES[q]] : [q];
  const starts = [];
  const contains = [];
  const seen = new Set();

  for (const term of terms) {
    for (const a of airports) {
      if (seen.has(a.iata)) continue;
      const iata = normalize(a.iata);
      const city = normalize(a.city);
      if (iata === term || iata.startsWith(term) || city.startsWith(term)) {
        starts.push(a);
        seen.add(a.iata);
      } else {
        const hay = normalize(`${a.iata} ${a.name} ${a.city} ${a.country}`);
        if (hay.includes(term)) {
          contains.push(a);
          seen.add(a.iata);
        }
      }
    }
  }
  return [...starts, ...contains].slice(0, limit);
}

export function findByIata(airports, iata) {
  return airports.find((a) => a.iata === iata);
}

export function attachAirportPicker({ searchInput, hiddenInput, listEl, airports, onSelect }) {
  function render(matches) {
    listEl.innerHTML = '';
    if (!matches.length) {
      listEl.style.display = 'none';
      return;
    }
    for (const a of matches) {
      const li = document.createElement('li');
      li.textContent = `${a.iata} — ${a.city} (${a.name}), ${a.country}`;
      li.addEventListener('mousedown', (e) => {
        e.preventDefault();
        hiddenInput.value = a.iata;
        searchInput.value = `${a.iata} — ${a.city}`;
        listEl.style.display = 'none';
        if (onSelect) onSelect(a);
      });
      listEl.appendChild(li);
    }
    listEl.style.display = 'block';
  }

  searchInput.addEventListener('input', () => {
    hiddenInput.value = '';
    render(searchAirports(airports, searchInput.value));
  });

  searchInput.addEventListener('focus', () => {
    if (searchInput.value.trim().length >= 2 && !hiddenInput.value) {
      render(searchAirports(airports, searchInput.value));
    }
  });

  searchInput.addEventListener('blur', () => {
    setTimeout(() => { listEl.style.display = 'none'; }, 150);
  });
}
