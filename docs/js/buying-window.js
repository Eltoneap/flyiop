// Faixas de dias-de-antecedência (dias entre a busca e a data do voo)
const BUCKETS = [
  [0, 15], [16, 30], [31, 45], [46, 60], [61, 90], [91, 120], [121, 180], [181, 400],
];

function bucketLabel([lo, hi]) {
  return `${lo}–${hi} dias`;
}

// Fonte: recomendações consolidadas de Viaje na Viagem, Melhores Destinos e Exame (jul/2026)
export function staticAdvice(isDomestic) {
  return isDomestic
    ? 'Ainda sem histórico suficiente. Regra geral para rotas nacionais: procure comprar entre 30 e 60 dias antes do embarque.'
    : 'Ainda sem histórico suficiente. Regra geral para rotas internacionais: procure comprar entre 60 e 120 dias antes do embarque (em alta temporada, considere até 6 meses).';
}

/**
 * history: [{ checked_at, flight_date, price }]
 * Retorna a faixa de antecedência com o menor preço médio observado,
 * ou null se não houver dados suficientes para uma faixa (mínimo 2 pontos).
 */
export function dynamicAdvice(history) {
  const bucketStats = BUCKETS.map(() => ({ sum: 0, count: 0 }));

  for (const h of history) {
    if (!h.flight_date) continue;
    const flightDate = new Date(`${h.flight_date}T00:00:00Z`);
    const checkedDate = new Date(h.checked_at);
    const daysAhead = Math.round((flightDate - checkedDate) / 86400000);
    if (daysAhead < 0) continue;

    const idx = BUCKETS.findIndex(([lo, hi]) => daysAhead >= lo && daysAhead <= hi);
    if (idx === -1) continue;

    bucketStats[idx].sum += Number(h.price);
    bucketStats[idx].count += 1;
  }

  let best = null;
  let totalPoints = 0;
  for (let i = 0; i < BUCKETS.length; i++) {
    totalPoints += bucketStats[i].count;
    if (bucketStats[i].count < 2) continue;
    const avg = bucketStats[i].sum / bucketStats[i].count;
    if (!best || avg < best.avg) {
      best = { bucket: BUCKETS[i], avg, count: bucketStats[i].count };
    }
  }

  if (!best || totalPoints < 5) return null;

  return {
    text: `Com base no seu histórico (${totalPoints} buscas): preços mais baixos costumam aparecer com ${bucketLabel(best.bucket)} de antecedência (média ${best.avg.toFixed(2)}).`,
  };
}

export function buyingWindowAdvice(history, isDomestic) {
  const dynamic = dynamicAdvice(history);
  if (dynamic) return { text: dynamic.text, personalized: true };
  return { text: staticAdvice(isDomestic), personalized: false };
}
