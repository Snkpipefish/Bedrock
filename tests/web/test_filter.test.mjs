// Logiske tester for web/assets/filter.js (Fase 9 runde 2 session 51).
//
// Kjøres med: `node --test tests/web/test_filter.test.mjs`
//
// Filter-logikken er pure (ingen DOM, ingen I/O), så vi importerer
// filter.js direkte og verifiserer "gitt filter-state X og entries Y,
// forvent at Z passerer". Dette dekker:
//   - dir/grade/horizon/instr individuelt
//   - kombinasjoner (alle akser stacker)
//   - case-insensitive instr-substring-match
//   - ALL og tom string ⇒ akse hopper over
//   - manglende felt på entry behandles som tom (treffes kun av ALL)
//   - skoper isoleres (mutering av FLT.financial påvirker ikke FLT.agri)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { FLT, fltActive, fltAxesFromTrade, fltAxesFromSetup, applyFilter } =
  require('../../web/assets/filter.js');

// Reset alle filter-skoper mellom tester (FLT er delt module-state).
function resetAll() {
  for (const scope of Object.keys(FLT)) {
    FLT[scope] = { dir: 'ALL', grade: 'ALL', horizon: 'ALL', instr: '' };
  }
}

// ─── Fixtures ─────────────────────────────────────────────────
function setup(o) {
  return {
    instrument: o.instrument,
    direction: o.direction,
    horizon: o.horizon,
    grade: o.grade,
    score: o.score ?? 1.0,
    setup: o.setup ?? null,
  };
}

function tradeEntry(o) {
  return {
    timestamp: o.timestamp ?? '2026-04-25 10:00:00',
    closed_at: o.closed_at ?? null,
    result: o.result ?? null,
    exit_reason: o.exit_reason ?? null,
    signal: {
      id: o.id,
      instrument: o.instrument,
      direction: o.direction,
      horizon: o.horizon,
      grade: o.grade,
      entry: o.entry ?? 100,
      stop: o.stop ?? 99,
      t1: o.t1 ?? null,
    },
  };
}

const SETUPS = [
  setup({ instrument: 'GOLD',   direction: 'BUY',  horizon: 'SWING', grade: 'A+' }),
  setup({ instrument: 'EURUSD', direction: 'SELL', horizon: 'SCALP', grade: 'A'  }),
  setup({ instrument: 'BRENT',  direction: 'BUY',  horizon: 'MAKRO', grade: 'B'  }),
  setup({ instrument: 'GBPUSD', direction: 'SELL', horizon: 'SWING', grade: 'A+' }),
  setup({ instrument: 'SILVER', direction: 'BUY',  horizon: 'SCALP', grade: 'C'  }),
];

const TRADES = [
  tradeEntry({ id: 't1', instrument: 'GOLD',   direction: 'BUY',  horizon: 'SWING', grade: 'A+' }),
  tradeEntry({ id: 't2', instrument: 'EURUSD', direction: 'SELL', horizon: 'SCALP', grade: 'A'  }),
  tradeEntry({ id: 't3', instrument: 'COTTON', direction: 'BUY',  horizon: 'MAKRO', grade: 'B'  }),
];

// ─── fltAxesFrom* ─────────────────────────────────────────────
test('fltAxesFromSetup uppercases dir og horizon, beholder grade som-er', () => {
  const a = fltAxesFromSetup({ instrument: 'g', direction: 'buy', horizon: 'swing', grade: 'A+' });
  assert.deepEqual(a, { dir: 'BUY', grade: 'A+', horizon: 'SWING', instrument: 'g' });
});

test('fltAxesFromTrade leser fra .signal-undertre', () => {
  const a = fltAxesFromTrade({ signal: { instrument: 'X', direction: 'sell', horizon: 'makro', grade: 'B' } });
  assert.deepEqual(a, { dir: 'SELL', grade: 'B', horizon: 'MAKRO', instrument: 'X' });
});

test('fltAxesFromTrade håndterer entry uten signal-felt', () => {
  const a = fltAxesFromTrade({});
  assert.deepEqual(a, { dir: '', grade: '', horizon: '', instrument: '' });
});

// ─── fltActive ────────────────────────────────────────────────
test('fltActive er false på fresh state', () => {
  resetAll();
  for (const scope of Object.keys(FLT)) assert.equal(fltActive(scope), false);
});

test('fltActive er true når én akse er satt', () => {
  resetAll();
  FLT.financial.dir = 'BUY';
  assert.equal(fltActive('financial'), true);
  assert.equal(fltActive('agri'), false);
});

test('fltActive er true ved ikke-tom instr (også med ALL på resten)', () => {
  resetAll();
  FLT.skipsloggen.instr = 'gold';
  assert.equal(fltActive('skipsloggen'), true);
});

// ─── applyFilter — enkelt-akse ────────────────────────────────
test('applyFilter: ALL på alle akser ⇒ alle elementer passerer', () => {
  resetAll();
  assert.equal(applyFilter('financial', SETUPS, fltAxesFromSetup).length, SETUPS.length);
});

test('applyFilter: dir=BUY filtrerer SELL bort', () => {
  resetAll();
  FLT.financial.dir = 'BUY';
  const r = applyFilter('financial', SETUPS, fltAxesFromSetup);
  assert.equal(r.length, 3);
  for (const s of r) assert.equal(s.direction, 'BUY');
});

test('applyFilter: grade=A+ kun beholder A+', () => {
  resetAll();
  FLT.financial.grade = 'A+';
  const r = applyFilter('financial', SETUPS, fltAxesFromSetup);
  assert.equal(r.length, 2);
  for (const s of r) assert.equal(s.grade, 'A+');
});

test('applyFilter: horizon=SWING kun beholder SWING', () => {
  resetAll();
  FLT.financial.horizon = 'SWING';
  const r = applyFilter('financial', SETUPS, fltAxesFromSetup);
  assert.equal(r.length, 2);
  for (const s of r) assert.equal(s.horizon, 'SWING');
});

test('applyFilter: instr-substring er case-insensitive', () => {
  resetAll();
  FLT.financial.instr = 'eur';
  const r = applyFilter('financial', SETUPS, fltAxesFromSetup);
  assert.equal(r.length, 1);
  assert.equal(r[0].instrument, 'EURUSD');
});

test('applyFilter: instr matcher som substring (USD treffer EURUSD og GBPUSD)', () => {
  resetAll();
  FLT.financial.instr = 'USD';
  const r = applyFilter('financial', SETUPS, fltAxesFromSetup);
  assert.deepEqual(r.map(s => s.instrument).sort(), ['EURUSD', 'GBPUSD']);
});

// ─── applyFilter — kombinasjoner ──────────────────────────────
test('applyFilter: alle 4 akser stacker (BUY + A+ + SWING + GOLD)', () => {
  resetAll();
  FLT.financial.dir = 'BUY';
  FLT.financial.grade = 'A+';
  FLT.financial.horizon = 'SWING';
  FLT.financial.instr = 'gold';
  const r = applyFilter('financial', SETUPS, fltAxesFromSetup);
  assert.equal(r.length, 1);
  assert.equal(r[0].instrument, 'GOLD');
});

test('applyFilter: ingen treff returnerer tom liste, ikke null', () => {
  resetAll();
  FLT.financial.instr = 'INGENTING';
  assert.deepEqual(applyFilter('financial', SETUPS, fltAxesFromSetup), []);
});

// ─── Skopisolasjon ────────────────────────────────────────────
test('applyFilter: skoper er uavhengige (financial-mut påvirker ikke agri)', () => {
  resetAll();
  FLT.financial.dir = 'SELL';
  assert.equal(applyFilter('financial', SETUPS, fltAxesFromSetup).length, 2);
  assert.equal(applyFilter('agri',      SETUPS, fltAxesFromSetup).length, SETUPS.length);
});

// ─── Trade-entry semantikk ────────────────────────────────────
test('applyFilter på trade-log: filter mot .signal-felter virker', () => {
  resetAll();
  FLT.skipsloggen.dir = 'BUY';
  FLT.skipsloggen.horizon = 'SWING';
  const r = applyFilter('skipsloggen', TRADES, fltAxesFromTrade);
  assert.equal(r.length, 1);
  assert.equal(r[0].signal.id, 't1');
});

test('applyFilter på trade-log: instr-match leser .signal.instrument', () => {
  resetAll();
  FLT.skipsloggen.instr = 'cotton';
  const r = applyFilter('skipsloggen', TRADES, fltAxesFromTrade);
  assert.equal(r.length, 1);
  assert.equal(r[0].signal.instrument, 'COTTON');
});

// ─── Manglende felt på entry ──────────────────────────────────
test('applyFilter: entry uten grade matches kun grade=ALL', () => {
  resetAll();
  const incomplete = [setup({ instrument: 'X', direction: 'BUY', horizon: 'SCALP', grade: undefined })];
  // ALL ⇒ passerer
  assert.equal(applyFilter('financial', incomplete, fltAxesFromSetup).length, 1);
  // grade=A ⇒ filtrerer bort (manglende grade ≠ 'A')
  FLT.financial.grade = 'A';
  assert.equal(applyFilter('financial', incomplete, fltAxesFromSetup).length, 0);
});
