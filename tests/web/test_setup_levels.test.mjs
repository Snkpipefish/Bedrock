// Logiske tester for web/assets/setup_levels.js (fix/ui-duplicates-setup-fields).
//
// Kjøres med: `node --test tests/web/test_setup_levels.test.mjs`
//
// extractSetupLevels er pure (ingen DOM, ingen I/O), så vi importerer
// modulen direkte og verifiserer at den unwrapper stable-setupen
// korrekt på tvers av schema-varianter.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { extractSetupLevels } = require('../../web/assets/setup_levels.js');

// ─── Stable-setup (produksjons-shape: nested) ────────────────

test('unwrapper nested stable-setup (entry.setup.setup.entry/sl/tp/rr)', () => {
  const entry = {
    instrument: 'Gold',
    direction: 'buy',
    setup: {
      setup_id: 'abc123',
      first_seen: '2026-04-26T15:00:00Z',
      setup: {
        entry: 4541.79,
        sl: 4518.14,
        tp: 4936.0,
        rr: 16.6,
        atr: 23.65,
      },
    },
  };
  const lv = extractSetupLevels(entry);
  assert.equal(lv.entry, 4541.79);
  assert.equal(lv.sl, 4518.14);
  assert.equal(lv.tp, 4936.0);
  assert.equal(lv.rr, 16.6);
  assert.equal(lv.atr, 23.65);
});

test('inkluderer cluster-types fra nested setup', () => {
  const entry = {
    setup: {
      setup_id: 'x',
      setup: {
        entry: 100,
        sl: 95,
        tp: 120,
        entry_cluster_types: ['prior_low', 'swing'],
        tp_cluster_types: ['prior_high'],
      },
    },
  };
  const lv = extractSetupLevels(entry);
  assert.deepEqual(lv.entry_cluster_types, ['prior_low', 'swing']);
  assert.deepEqual(lv.tp_cluster_types, ['prior_high']);
});

// ─── MAKRO trailing-only (tp + rr null) ──────────────────────

test('beholder null tp/rr for MAKRO trailing-only', () => {
  const entry = {
    horizon: 'makro',
    setup: {
      setup_id: 'm1',
      setup: { entry: 100, sl: 95, tp: null, rr: null, atr: 2.0 },
    },
  };
  const lv = extractSetupLevels(entry);
  assert.equal(lv.entry, 100);
  assert.equal(lv.sl, 95);
  assert.equal(lv.tp, null);
  assert.equal(lv.rr, null);
});

// ─── Flat-setup fallback (test fixtures uten stable wrapper) ─

test('faller tilbake til flat setup når .setup.setup mangler', () => {
  const entry = {
    setup: {
      entry: 50,
      sl: 48,
      tp: 60,
      rr: 5.0,
    },
  };
  const lv = extractSetupLevels(entry);
  assert.equal(lv.entry, 50);
  assert.equal(lv.sl, 48);
  assert.equal(lv.tp, 60);
  assert.equal(lv.rr, 5.0);
});

// ─── Alternative felt-navn (eldre fixtures) ──────────────────

test('aksepterer stop_loss som alias for sl', () => {
  const entry = { setup: { setup_id: 'x', setup: { entry: 100, stop_loss: 95, tp: 110 } } };
  assert.equal(extractSetupLevels(entry).sl, 95);
});

test('aksepterer target_1 + rr_t1 som aliaser', () => {
  const entry = { setup: { setup_id: 'x', setup: { entry: 100, sl: 95, target_1: 110, rr_t1: 3.0 } } };
  const lv = extractSetupLevels(entry);
  assert.equal(lv.tp, 110);
  assert.equal(lv.rr, 3.0);
});

test('foretrekker primær feltnavn over alias når begge er satt', () => {
  const entry = {
    setup: {
      setup_id: 'x',
      setup: { entry: 100, sl: 95, stop_loss: 999, tp: 110, target_1: 999, rr: 3.0, rr_t1: 999 },
    },
  };
  const lv = extractSetupLevels(entry);
  assert.equal(lv.sl, 95);
  assert.equal(lv.tp, 110);
  assert.equal(lv.rr, 3.0);
});

// ─── Defensive: ugyldig input ────────────────────────────────

test('returnerer null når entry mangler', () => {
  assert.equal(extractSetupLevels(null), null);
  assert.equal(extractSetupLevels(undefined), null);
});

test('returnerer null når entry.setup mangler', () => {
  assert.equal(extractSetupLevels({}), null);
  assert.equal(extractSetupLevels({ instrument: 'Gold' }), null);
  assert.equal(extractSetupLevels({ setup: null }), null);
});

test('returnerer felt med undefined når inner setup er tom', () => {
  const lv = extractSetupLevels({ setup: {} });
  assert.equal(lv.entry, undefined);
  assert.equal(lv.sl, undefined);
});
