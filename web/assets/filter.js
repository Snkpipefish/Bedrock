// Bedrock UI — pure filter-logikk (Fase 9 runde 2 session 51).
//
// Holder filter-state + applikasjons-funksjon. Ingen DOM-tilgang —
// derfor lastbar både i browser (som klassisk <script>) og i Node
// (via `require`) for unit-tester.
//
// Skal lastes FØR `app.js` — `app.js` bruker `FLT`, `fltActive`,
// `applyFilter`, `fltAxesFromTrade`, `fltAxesFromSetup` som
// script-level globals.

const FLT = {
  skipsloggen: { dir: 'ALL', grade: 'ALL', horizon: 'ALL', instr: '' },
  financial:   { dir: 'ALL', grade: 'ALL', horizon: 'ALL', instr: '' },
  agri:        { dir: 'ALL', grade: 'ALL', horizon: 'ALL', instr: '' },
};

function fltActive(scope) {
  const f = FLT[scope];
  return f.dir !== 'ALL' || f.grade !== 'ALL' || f.horizon !== 'ALL' || (f.instr || '').length > 0;
}

// Trade-log-entry: feltene ligger under `.signal`.
function fltAxesFromTrade(entry) {
  const s = entry.signal || {};
  return {
    dir: (s.direction || '').toUpperCase(),
    grade: s.grade || '',
    horizon: (s.horizon || '').toUpperCase(),
    instrument: s.instrument || '',
  };
}

// Setup-entry: feltene er top-level.
function fltAxesFromSetup(s) {
  return {
    dir: (s.direction || '').toUpperCase(),
    grade: s.grade || '',
    horizon: (s.horizon || '').toUpperCase(),
    instrument: s.instrument || '',
  };
}

function applyFilter(scope, items, axesOf) {
  const f = FLT[scope];
  return items.filter(item => {
    const a = axesOf(item);
    if (f.dir !== 'ALL' && a.dir !== f.dir) return false;
    if (f.grade !== 'ALL' && a.grade !== f.grade) return false;
    if (f.horizon !== 'ALL' && a.horizon !== f.horizon) return false;
    if (f.instr && !a.instrument.toLowerCase().includes(f.instr.toLowerCase())) return false;
    return true;
  });
}

// CommonJS-eksport for Node-tester. I browseren er `module` undefined,
// så denne blokken er en no-op der.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { FLT, fltActive, fltAxesFromTrade, fltAxesFromSetup, applyFilter };
}
