// Setup-level-utleder for SignalEntry (Fase 9 + ADR-006).
//
// Stable-setupen i signals.json er nestet:
//   entry.setup = { setup_id, first_seen, last_updated, setup: { entry, sl, tp, rr, atr, ... } }
//
// Denne modulen unwrapper det og normaliserer til ett flatt felt-sett
// som UI bruker både på kort og i modal. Tolerer alternative felt-navn
// (stop_loss/stop, target_1/t1, rr_t1) for å støtte eldre fixtures og
// fremtidige schema-utvidelser uten å brekke renderingen.
//
// Pure (ingen DOM, ingen I/O) — eksportert via CommonJS for node:test
// og som global window.extractSetupLevels for nettleseren.

function extractSetupLevels(entry) {
  if (!entry || !entry.setup) return null;
  const wrap = entry.setup;
  const inner = (wrap && typeof wrap === 'object' && wrap.setup) ? wrap.setup : wrap;
  if (!inner || typeof inner !== 'object') return null;
  // Bruk `in`-sjekk så eksplisitt null (MAKRO trailing-only) bevares.
  // Hvis primær feltet er undefined, fall tilbake til alias-feltnavn.
  const pick = (...keys) => {
    for (const k of keys) {
      if (k in inner) return inner[k];
    }
    return undefined;
  };
  return {
    entry: inner.entry,
    sl: pick('sl', 'stop_loss', 'stop'),
    tp: pick('tp', 'target_1', 't1'),
    rr: pick('rr', 'rr_t1'),
    atr: inner.atr,
    entry_cluster_types: inner.entry_cluster_types,
    tp_cluster_types: inner.tp_cluster_types,
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { extractSetupLevels };
}
if (typeof window !== 'undefined') {
  window.extractSetupLevels = extractSetupLevels;
}
