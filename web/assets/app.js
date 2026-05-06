// Bedrock UI — Fase 9 runde 1 session 47: Skipsloggen
// Runde 2 session 51: filter-bar (horizon/grade/instrument/direction).
// Session 148 (Mål 2): event-driven via SSE; safety-poll erstatter
// gammel 30-sek-polling.
// Vanilla JS (per PLAN § 15).

// Safety-poll: hver 30. sek lastes alt på nytt selv uten SSE-events.
// Fanger SSE-disconnect, server-restart, eller event-tap. SSE er fortsatt
// primær path (≤2 sek latens via file-watcher); dette er fallback.
// Bumpet ned fra 5 min 2026-05-06 etter operatør ønsket oftere
// oppdatering av åpne/lukkede posisjoner i Handelslogg-fanen.
const SAFETY_POLL_INTERVAL_MS = 30_000;

// ─── Tab-navigasjon ───────────────────────────────────────────
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.tab;
    document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.tab-panel').forEach(p =>
      p.classList.toggle('active', p.id === target)
    );
  });
});

// ─── Filter-modul (session 51) ─────────────────────────────────
// Pure state + filter-funksjoner ligger i `filter.js` (lastet før denne
// fila). Resten — DOM-bygging, event-wiring, treff-teller — bor her.
// KPI-sammendrag (Skipsloggen) påvirkes ikke av filteret; det aggregeres
// fortsatt over full logg på server-siden.

function buildFilterBarHtml() {
  return `
    <div class="flt-group"><span class="flt-label">Retning</span>
      <button class="flt-pill active" data-flt="dir" data-val="ALL">Alle</button>
      <button class="flt-pill" data-flt="dir" data-val="BUY">Buy</button>
      <button class="flt-pill" data-flt="dir" data-val="SELL">Sell</button>
    </div>
    <div class="flt-group"><span class="flt-label">Grade</span>
      <button class="flt-pill active" data-flt="grade" data-val="ALL">Alle</button>
      <button class="flt-pill" data-flt="grade" data-val="A+">A+</button>
      <button class="flt-pill" data-flt="grade" data-val="A">A</button>
      <button class="flt-pill" data-flt="grade" data-val="B">B</button>
      <button class="flt-pill" data-flt="grade" data-val="C">C</button>
    </div>
    <div class="flt-group"><span class="flt-label">Horisont</span>
      <button class="flt-pill active" data-flt="horizon" data-val="ALL">Alle</button>
      <button class="flt-pill" data-flt="horizon" data-val="SCALP">Scalp</button>
      <button class="flt-pill" data-flt="horizon" data-val="SWING">Swing</button>
      <button class="flt-pill" data-flt="horizon" data-val="MAKRO">Makro</button>
    </div>
    <div class="flt-group"><span class="flt-label">Instrument</span>
      <input class="flt-search" data-flt="instr" placeholder="filter…" autocomplete="off">
    </div>
    <span class="flt-count" data-flt-count></span>
    <button class="flt-reset" data-flt="reset" disabled>Nullstill</button>
  `;
}

function _syncBarUi(bar, scope) {
  const f = FLT[scope];
  bar.querySelectorAll('.flt-pill[data-flt]').forEach(p => {
    if (p.dataset.flt === 'reset') return;
    p.classList.toggle('active', p.dataset.val === f[p.dataset.flt]);
  });
  const inp = bar.querySelector('.flt-search');
  if (inp && inp.value !== f.instr) inp.value = f.instr;
  const reset = bar.querySelector('.flt-reset');
  if (reset) reset.disabled = !fltActive(scope);
}

function wireFilterBar(scope, onChange) {
  const mount = document.querySelector(`.filter-bar-mount[data-flt-scope="${scope}"]`);
  if (!mount) return;
  mount.innerHTML = `<div class="filter-bar">${buildFilterBarHtml()}</div>`;
  const bar = mount.querySelector('.filter-bar');
  bar.addEventListener('click', e => {
    const t = e.target.closest('[data-flt]');
    if (!t || t.tagName !== 'BUTTON') return;
    const k = t.dataset.flt;
    if (k === 'reset') {
      FLT[scope] = { dir: 'ALL', grade: 'ALL', horizon: 'ALL', instr: '' };
    } else {
      FLT[scope][k] = t.dataset.val;
    }
    _syncBarUi(bar, scope);
    onChange();
  });
  bar.querySelector('.flt-search').addEventListener('input', e => {
    FLT[scope].instr = e.target.value.trim();
    _syncBarUi(bar, scope);
    onChange();
  });
  _syncBarUi(bar, scope);
}

// ─── Modal (session 52) ────────────────────────────────────────
// Klikk på setup-kort → openSetupModal med full explain-trace fra
// `families` (persistert i SignalEntry fra Engine via _build_entry).
// Klikk på trade-rad → openTradeModal (eksisterende felt; driver-trace
// per trade kommer i senere session via signal_id-lookup).

function _modalEl() { return document.getElementById('modal'); }

function _fmt2(n) { return (n == null || isNaN(n)) ? '–' : Number(n).toFixed(2); }
function _fmt5(n) { return (n == null || isNaN(n)) ? '–' : Number(n).toFixed(5); }
function _fmt1(n) { return (n == null || isNaN(n)) ? '–' : Number(n).toFixed(1); }

// `_extractSetupLevels` lastes fra setup_levels.js (pure, DOM-fri, testbar).
// Dette skriptet er lastet via <script> før app.js i index.html og setter
// window.extractSetupLevels.
const _extractSetupLevels = window.extractSetupLevels;

function _pctOf(score, max) {
  if (!max || max <= 0) return 0;
  return Math.max(0, Math.min(100, (score / max) * 100));
}

function _scoreBarHtml(score, maxScore, minPublish) {
  const scorePct = _pctOf(score, maxScore);
  const publishPct = _pctOf(minPublish || 0, maxScore);
  return `
    <div class="modal-scorebar">
      <div class="modal-scorebar-fill" style="width:${scorePct.toFixed(1)}%"></div>
      <div class="modal-scorebar-mark" style="left:${publishPct.toFixed(1)}%"></div>
    </div>
    <div class="modal-scorebar-label">
      <span>score ${_fmt2(score)} / ${_fmt2(maxScore)}</span>
      <span>publish-gulv ${_fmt2(minPublish)}</span>
    </div>`;
}

function _analogHtml(analog) {
  if (!analog) return '';
  const n = analog.n_neighbors ?? 0;
  const hits = Math.round((analog.hit_rate_pct ?? 0) / 100 * n);
  const avg = analog.avg_return_pct ?? 0;
  const avgClass = avg >= 0 ? 'pos' : 'neg';
  const horizon = analog.horizon_days ?? 30;
  const threshold = analog.outcome_threshold_pct ?? 3.0;
  const dims = (analog.dims_used || []).join(', ') || '–';
  const neighbors = analog.neighbors || [];
  const dropped = (4 - (analog.dims_used || []).length); // §6.5 har 4 dim per asset-klasse
  const dimNote = dropped > 0
    ? `<span class="meta">(${dropped} av 4 § 6.5-dim mangler data)</span>`
    : '';
  return `
    <section class="modal-section">
      <h3>Analog-historikk</h3>
      <p class="modal-analog-narrative">
        <strong>${hits} av ${n}</strong> nærmeste historiske naboer steg
        <strong>≥ ${_fmt1(threshold)}%</strong> innen ${horizon} dager.
        Snitt-return: <span class="${avgClass}">${avg >= 0 ? '+' : ''}${_fmt2(avg)}%</span>.
      </p>
      <p class="meta">Dimensjoner brukt: ${dims} ${dimNote}</p>
      ${neighbors.length ? `<table class="modal-analog-table">
        <thead>
          <tr><th>Ref-dato</th><th class="num">Sim</th><th class="num">Fwd ret</th><th class="num">Max DD</th></tr>
        </thead>
        <tbody>
          ${neighbors.map(n => {
            const fwd = n.forward_return_pct ?? 0;
            const fwdCls = fwd >= 0 ? 'pos' : 'neg';
            const dd = n.max_drawdown_pct;
            return `<tr>
              <td>${n.ref_date}</td>
              <td class="num">${_fmt2(n.similarity)}</td>
              <td class="num ${fwdCls}">${fwd >= 0 ? '+' : ''}${_fmt2(fwd)}%</td>
              <td class="num">${dd == null ? '–' : `${_fmt2(dd)}%`}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>` : '<p class="meta">Ingen naboer funnet.</p>'}
    </section>`;
}

// Sub-fase 12.9 Fase 3: per-driver horisont-chips i modal-driver-tabell.
// Drivere uten horizons-felt = alle 3 (status quo, ingen chip vist).
// Drivere med satt felt rendres med M/Sw/Sc-chips (samme palett som
// pipeline-tabell-chips) for å gjøre filteret synlig for operatør.
function _driverHorizonChips(horizons) {
  if (!horizons || !Array.isArray(horizons) || horizons.length === 0) {
    return '<span class="meta" title="Bidrar til alle horisonter">alle</span>';
  }
  // Map full horisont-navn til kort-form. Engine normaliserer til
  // uppercase, men vær defensiv om lower-case kommer gjennom.
  const SHORT = {SCALP: 'Sc', SWING: 'Sw', MAKRO: 'M'};
  const CLS = {SCALP: 'hz-scalp', SWING: 'hz-swing', MAKRO: 'hz-macro'};
  const TITLE = {
    SCALP: 'Scalp (minutter–timer)',
    SWING: 'Swing (dager–uker)',
    MAKRO: 'Macro (uker–måneder)',
  };
  // Bevarer YAML-rekkefølge slik at f.eks. [SCALP, SWING] vises Sc Sw.
  return horizons.map(h => {
    const up = String(h).toUpperCase();
    const cls = CLS[up] || 'hz-none';
    const short = SHORT[up] || up;
    const title = TITLE[up] || up;
    return `<span class="hz-chip ${cls}" title="${title}">${short}</span>`;
  }).join('');
}

function _familyHtml(name, fam) {
  const score = fam.score ?? 0;
  const drivers = (fam.drivers || []).slice().sort(
    (a, b) => Math.abs(b.contribution || 0) - Math.abs(a.contribution || 0)
  );
  return `
    <details class="modal-family" ${drivers.length ? '' : 'data-empty="1"'}>
      <summary>
        <span class="modal-family-name">${name}</span>
        <span class="modal-family-score">${_fmt2(score)}</span>
        <span class="modal-family-count">${drivers.length} driver${drivers.length === 1 ? '' : 'e'}</span>
      </summary>
      ${drivers.length ? `<table class="modal-driver-table">
        <thead>
          <tr><th>Driver</th><th>Horisont</th><th class="num">Value</th><th class="num">Weight</th><th class="num">Bidrag</th></tr>
        </thead>
        <tbody>
          ${drivers.map(d => `<tr>
            <td>${_driverLabelHtml(d.name)}</td>
            <td>${_driverHorizonChips(d.horizons)}</td>
            <td class="num">${_fmt2(d.value)}</td>
            <td class="num">${_fmt2(d.weight)}</td>
            <td class="num"><strong>${_fmt2(d.contribution)}</strong></td>
          </tr>`).join('')}
        </tbody>
      </table>` : '<p class="meta" style="padding:0 12px 8px">Ingen aktive drivere i denne familien.</p>'}
    </details>`;
}

function openSetupModal(entry) {
  const m = _modalEl();
  if (!m || !entry) return;
  const setupWrap = entry.setup || null;
  const lv = _extractSetupLevels(entry);
  const setup = setupWrap ? (setupWrap.setup || setupWrap) : null;
  const families = entry.families || {};
  const familyKeys = Object.keys(families);
  const dirCls = (entry.direction || '').toUpperCase() === 'SELL' ? 'dir-sell' : 'dir-buy';
  const gradeCls = `grade-${(entry.grade || 'x').replace('+', 'plus').toLowerCase()}`;

  m.querySelector('.modal-content').innerHTML = `
    <button class="modal-close" type="button" aria-label="Lukk">×</button>
    <header class="modal-head ${dirCls}">
      <div>
        <span class="modal-instrument" id="modal-title">${entry.instrument || '–'}</span>
        <span class="modal-direction">${entry.direction || '–'}</span>
        <span class="modal-horizon">${entry.horizon || '–'}</span>
      </div>
      <div>
        <span class="grade ${gradeCls}">${entry.grade || '?'}</span>
        <span class="modal-published-pill ${entry.published ? 'yes' : 'no'}">${entry.published ? 'published' : 'below floor'}</span>
      </div>
    </header>

    <section class="modal-section">
      <h3>Score</h3>
      ${_scoreBarHtml(entry.score, entry.max_score, entry.min_score_publish)}
      <p class="meta" style="margin-top:6px">Aktive familier: ${entry.active_families ?? '–'} av ${familyKeys.length || '–'}</p>
    </section>

    ${familyKeys.length ? `
    <section class="modal-section">
      <h3>Driver-trace</h3>
      ${familyKeys.map(k => _familyHtml(k, families[k])).join('')}
    </section>` : `
    <section class="modal-section">
      <h3>Driver-trace</h3>
      <p class="meta">Ingen driver-trace persistert. Re-kjør orchestrator etter session 52 for full trace.</p>
    </section>`}

    ${_analogHtml(entry.analog)}

    ${lv ? `
    <section class="modal-section">
      <h3>Setup</h3>
      <table class="modal-kv">
        <tr><th>Entry</th><td>${_fmt5(lv.entry)}</td></tr>
        <tr><th>Stop</th><td>${_fmt5(lv.sl)}</td></tr>
        <tr><th>T1 / TP</th><td>${lv.tp == null ? '<span class="meta">trailing only (MAKRO)</span>' : _fmt5(lv.tp)}</td></tr>
        <tr><th>R:R</th><td>${lv.rr == null ? '<span class="meta">–</span>' : _fmt2(lv.rr)}</td></tr>
        <tr><th>ATR</th><td>${_fmt5(lv.atr)}</td></tr>
      </table>
      ${lv.entry_cluster_types ? `<p class="meta" style="margin-top:6px">Entry-nivå: ${(lv.entry_cluster_types || []).join(', ') || '–'}</p>` : ''}
      ${lv.tp_cluster_types ? `<p class="meta">TP-nivå: ${(lv.tp_cluster_types || []).join(', ') || '–'}</p>` : ''}
    </section>` : ''}

    ${setupWrap && setupWrap.first_seen ? `
    <section class="modal-section">
      <h3>Persistens</h3>
      <table class="modal-kv">
        <tr><th>Setup-ID</th><td><code>${setupWrap.setup_id || '–'}</code></td></tr>
        <tr><th>First seen</th><td>${setupWrap.first_seen}</td></tr>
        <tr><th>Last updated</th><td>${setupWrap.last_updated}</td></tr>
      </table>
    </section>` : ''}

    ${entry.gates_triggered && entry.gates_triggered.length ? `
    <section class="modal-section">
      <h3>Gates utløst</h3>
      <ul class="modal-list">${entry.gates_triggered.map(g => `<li>${g}</li>`).join('')}</ul>
    </section>` : ''}

    ${entry.skip_reason ? `
    <section class="modal-section">
      <h3>Skip-grunn</h3>
      <p>${entry.skip_reason}</p>
    </section>` : ''}
  `;
  m.showModal();
}

function openTradeModal(entry) {
  const m = _modalEl();
  if (!m || !entry) return;
  const sig = entry.signal || {};
  const pnl = entry.pnl || null;
  const open = !entry.closed_at;
  const dirCls = (sig.direction || '').toUpperCase() === 'SELL' ? 'dir-sell' : 'dir-buy';
  const gradeCls = `grade-${(sig.grade || 'x').replace('+', 'plus').toLowerCase()}`;
  const result = (entry.result || '').toLowerCase();

  m.querySelector('.modal-content').innerHTML = `
    <button class="modal-close" type="button" aria-label="Lukk">×</button>
    <header class="modal-head ${dirCls}">
      <div>
        <span class="modal-instrument" id="modal-title">${sig.instrument || '–'}</span>
        <span class="modal-direction">${sig.direction || '–'}</span>
        <span class="modal-horizon">${sig.horizon || '–'}</span>
      </div>
      <div>
        ${sig.grade ? `<span class="grade ${gradeCls}">${sig.grade}</span>` : ''}
        ${open ? '<span class="pill open">åpen</span>' : `<span class="pill ${result}">${entry.result || '–'}</span>`}
      </div>
    </header>

    <section class="modal-section">
      <h3>Tidslinje</h3>
      <table class="modal-kv">
        <tr><th>Åpnet</th><td>${entry.timestamp || '–'}</td></tr>
        <tr><th>Lukket</th><td>${entry.closed_at || '(åpen)'}</td></tr>
        ${entry.exit_reason ? `<tr><th>Exit-grunn</th><td>${entry.exit_reason}</td></tr>` : ''}
      </table>
    </section>

    <section class="modal-section">
      <h3>Setup</h3>
      <table class="modal-kv">
        <tr><th>Entry</th><td>${_fmt5(sig.entry)}</td></tr>
        <tr><th>Stop</th><td>${_fmt5(sig.stop)}</td></tr>
        <tr><th>T1</th><td>${_fmt5(sig.t1)}</td></tr>
      </table>
    </section>

    <section class="modal-section">
      <h3>Posisjon</h3>
      <table class="modal-kv">
        <tr><th>Signal-ID</th><td><code>${sig.id || '–'}</code></td></tr>
        <tr><th>Position-ID</th><td><code>${sig.position_id ?? '–'}</code></td></tr>
        <tr><th>Lots</th><td>${sig.lots ?? '–'}</td></tr>
        <tr><th>Risiko</th><td>${sig.risk_pct != null ? sig.risk_pct + ' %' : '–'}</td></tr>
      </table>
    </section>

    ${pnl ? `
    <section class="modal-section">
      <h3>PnL</h3>
      <table class="modal-kv">
        <tr><th>USD</th><td><span class="${pnl.pnl_usd > 0 ? 'pos' : pnl.pnl_usd < 0 ? 'neg' : ''}">${pnl.pnl_usd != null ? (pnl.pnl_usd >= 0 ? '+' : '') + _fmt2(pnl.pnl_usd) : '–'}${pnl.pnl_real ? ' ✓ realisert' : ''}</span></td></tr>
        ${pnl.pips != null ? `<tr><th>Pips</th><td>${_fmt1(pnl.pips)}</td></tr>` : ''}
        ${pnl.close_price != null ? `<tr><th>Close-pris</th><td>${_fmt5(pnl.close_price)}</td></tr>` : ''}
      </table>
    </section>` : ''}

    <p class="meta modal-disclaimer">Driver-trace lagres ikke per trade enda — se setup-modalen via Financial / Soft commodities for full forklaring.</p>
  `;
  m.showModal();
}

function closeModal() {
  const m = _modalEl();
  if (m && m.open) m.close();
}

function _wireModalGlobal() {
  const m = _modalEl();
  if (!m) return;
  m.addEventListener('click', e => {
    // Klikk på selve dialog-elementet (utenfor .modal-content) ELLER
    // på .modal-close → lukk
    if (e.target === m || e.target.classList.contains('modal-close')) {
      closeModal();
    }
  });
}

function setFilterCount(scope, shown, total) {
  const mount = document.querySelector(`.filter-bar-mount[data-flt-scope="${scope}"]`);
  if (!mount) return;
  const el = mount.querySelector('[data-flt-count]');
  if (!el) return;
  el.textContent = fltActive(scope) ? `${shown} av ${total}` : `${total}`;
}


// ─── Hjelpefunksjoner ─────────────────────────────────────────
function fmt(v, digits = 5) {
  if (v === null || v === undefined) return '–';
  if (typeof v === 'number') return v.toFixed(digits);
  return String(v);
}

function fmtPnl(pnl) {
  if (!pnl || pnl.pnl_usd === undefined || pnl.pnl_usd === null) return '–';
  const v = pnl.pnl_usd;
  const cls = v > 0 ? 'pos' : v < 0 ? 'neg' : '';
  const suffix = pnl.pnl_real ? ' ✓' : '';
  return `<span class="${cls}">${v >= 0 ? '+' : ''}${v.toFixed(2)}${suffix}</span>`;
}

function fmtResult(r) {
  if (!r) return '<span class="pill open">åpen</span>';
  return `<span class="pill ${r}">${r}</span>`;
}

// ─── Skipsloggen: KPI + trade-tabell ──────────────────────────
let TRADE_ENTRIES = [];

async function loadSkipsloggen() {
  try {
    const [summary, log] = await Promise.all([
      fetch('/api/ui/trade_log/summary').then(r => r.json()),
      fetch('/api/ui/trade_log?limit=100').then(r => r.json()),
    ]);
    renderKpi(summary);
    TRADE_ENTRIES = log.entries || [];
    renderTradeTableFiltered();
    const el = document.getElementById('last-updated');
    if (el) el.textContent = log.last_updated || '–';
  } catch (err) {
    console.error('Skipsloggen load feilet:', err);
    const body = document.getElementById('trade-log-body');
    if (body) body.innerHTML = `<tr><td colspan="12" class="empty">Fetch feilet: ${err.message}</td></tr>`;
  }
}

function renderTradeTableFiltered() {
  const filtered = applyFilter('skipsloggen', TRADE_ENTRIES, fltAxesFromTrade);
  setFilterCount('skipsloggen', filtered.length, TRADE_ENTRIES.length);
  renderTradeTable(filtered);
}

function renderKpi(summary) {
  const keys = ['total', 'open', 'wins', 'losses', 'win_rate', 'total_pnl_usd'];
  keys.forEach(k => {
    const el = document.querySelector(`[data-kpi="${k}"]`);
    if (!el) return;
    let v = summary[k];
    if (k === 'win_rate') v = `${(v * 100).toFixed(1)}%`;
    else if (k === 'total_pnl_usd') v = (v >= 0 ? '+' : '') + v.toFixed(2);
    el.textContent = v;
    if (k === 'total_pnl_usd') {
      el.classList.remove('pos', 'neg');
      if (summary.total_pnl_usd > 0) el.classList.add('pos');
      else if (summary.total_pnl_usd < 0) el.classList.add('neg');
    }
  });
}

function renderTradeTable(entries) {
  const body = document.getElementById('trade-log-body');
  if (!body) return;
  if (!entries || entries.length === 0) {
    const msg = TRADE_ENTRIES.length === 0
      ? 'Ingen trades ennå.'
      : 'Ingen trades matcher filteret.';
    body.innerHTML = `<tr><td colspan="12" class="empty">${msg}</td></tr>`;
    return;
  }
  // Filtrert subset blir oppslagskilde for trade-modal
  body.__bedrockEntries = entries;
  body.innerHTML = entries.map((e, i) => {
    const s = e.signal || {};
    return `<tr class="clickable" data-modal-idx="${i}" tabindex="0" role="button" aria-label="Vis trade-detaljer">
      <td>${e.timestamp || '–'}</td>
      <td>${s.id || '–'}</td>
      <td>${s.instrument || '–'}</td>
      <td>${s.direction || '–'}</td>
      <td>${s.horizon || '–'}</td>
      <td>${fmt(s.entry)}</td>
      <td>${fmt(s.stop)}</td>
      <td>${fmt(s.t1)}</td>
      <td>${e.closed_at || '–'}</td>
      <td>${fmtResult(e.result)}</td>
      <td>${e.exit_reason || '–'}</td>
      <td class="align-right">${fmtPnl(e.pnl)}</td>
    </tr>`;
  }).join('');
}

// ─── Klikk-delegering for modal ────────────────────────────────
function _wireModalDelegation() {
  // Setup-kort (Financial + Agri) — hver container holder filtrert subset
  // i `el.__bedrockSetups`. Klikk på `.setup-card[data-modal-idx]`
  // \u00e5pner modal med riktig entry.
  for (const id of ['financial-cards', 'agri-cards']) {
    const el = document.getElementById(id);
    if (!el) continue;
    el.addEventListener('click', e => {
      const card = e.target.closest('.setup-card[data-modal-idx]');
      if (!card) return;
      const setups = el.__bedrockSetups || [];
      const idx = parseInt(card.dataset.modalIdx, 10);
      if (!isNaN(idx) && setups[idx]) openSetupModal(setups[idx]);
    });
    // Tastatur: Enter / Space på fokusert kort
    el.addEventListener('keydown', e => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const card = e.target.closest('.setup-card[data-modal-idx]');
      if (!card) return;
      e.preventDefault();
      const setups = el.__bedrockSetups || [];
      const idx = parseInt(card.dataset.modalIdx, 10);
      if (!isNaN(idx) && setups[idx]) openSetupModal(setups[idx]);
    });
  }

  // Trade-rad
  const body = document.getElementById('trade-log-body');
  if (body) {
    body.addEventListener('click', e => {
      const row = e.target.closest('tr[data-modal-idx]');
      if (!row) return;
      const entries = body.__bedrockEntries || [];
      const idx = parseInt(row.dataset.modalIdx, 10);
      if (!isNaN(idx) && entries[idx]) openTradeModal(entries[idx]);
    });
    body.addEventListener('keydown', e => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const row = e.target.closest('tr[data-modal-idx]');
      if (!row) return;
      e.preventDefault();
      const entries = body.__bedrockEntries || [];
      const idx = parseInt(row.dataset.modalIdx, 10);
      if (!isNaN(idx) && entries[idx]) openTradeModal(entries[idx]);
    });
  }
}

// ─── Financial setups (session 48) ────────────────────────────
let FINANCIAL_SETUPS = [];

async function loadFinancialSetups() {
  try {
    const res = await fetch('/api/ui/setups/financial').then(r => r.json());
    FINANCIAL_SETUPS = res.setups || [];
    const visEl = document.getElementById('financial-count');
    const totEl = document.getElementById('financial-total');
    if (visEl) visEl.textContent = res.visible_count;
    if (totEl) totEl.textContent = res.total_count;
    renderFinancialFiltered();
  } catch (err) {
    console.error('Financial setups load feilet:', err);
    const el = document.getElementById('financial-cards');
    if (el) el.innerHTML = `<p class="empty">Fetch feilet: ${err.message}</p>`;
  }
}

function renderFinancialFiltered() {
  const filtered = applyFilter('financial', FINANCIAL_SETUPS, fltAxesFromSetup);
  setFilterCount('financial', filtered.length, FINANCIAL_SETUPS.length);
  renderSetupCards('financial-cards', filtered, FINANCIAL_SETUPS.length);
}

// Horisont-pille med fargekodet bakgrunn (scalp/swing/makro).
function _horizonBadgeHtml(horizon) {
  const h = (horizon || '').toLowerCase();
  const cls = h === 'scalp' || h === 'swing' || h === 'makro' ? `hz-${h}` : 'hz-unknown';
  const label = horizon ? horizon.toUpperCase() : '–';
  return `<span class="hz-badge ${cls}">${label}</span>`;
}

// Mini-score-bar som viser score / max_score med publish-floor markert.
function _scoreBarMiniHtml(score, maxScore, minPublish) {
  const sPct = _pctOf(score, maxScore);
  const pPct = _pctOf(minPublish || 0, maxScore);
  return `<div class="card-scorebar" title="score ${_fmt2(score)} / ${_fmt2(maxScore)} · publish-gulv ${_fmt2(minPublish)}">
    <div class="card-scorebar-fill" style="width:${sPct.toFixed(1)}%"></div>
    <div class="card-scorebar-mark" style="left:${pPct.toFixed(1)}%"></div>
  </div>`;
}

// Familie-breakdown på kort: liste av små bars per familie.
// `families` har form { name: { score, drivers: [...] } }. Vi viser
// alle familier i synkende score-rekkefølge — inaktive (score=0)
// dempes ned. Stripens bredde er score / makspoeng-i-settet, slik at
// relativ-rangering er lesbar uavhengig av horisont-vekter.
function _familyMiniHtml(families) {
  if (!families || typeof families !== 'object') return '';
  const items = Object.entries(families).map(([name, fam]) => ({
    name,
    score: Number(fam?.score || 0),
    n: (fam?.drivers || []).length,
  }));
  if (!items.length) return '';
  const peak = Math.max(...items.map(i => Math.abs(i.score)), 0.01);
  items.sort((a, b) => Math.abs(b.score) - Math.abs(a.score));
  return `<div class="family-mini">
    ${items.map(i => {
      const w = Math.max(2, Math.min(100, (Math.abs(i.score) / peak) * 100));
      const inactive = i.score === 0 ? ' inactive' : '';
      const sign = i.score < 0 ? ' neg' : '';
      return `<div class="fm-row${inactive}${sign}" title="${i.n} driver${i.n === 1 ? '' : 'e'}">
        <span class="fm-name">${i.name}</span>
        <span class="fm-bar"><span class="fm-bar-fill" style="width:${w.toFixed(1)}%"></span></span>
        <span class="fm-score">${_fmt2(i.score)}</span>
      </div>`;
    }).join('')}
  </div>`;
}

function renderSetupCards(containerId, setups, totalBeforeFilter) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!setups || setups.length === 0) {
    const msg = (totalBeforeFilter && totalBeforeFilter > 0)
      ? 'Ingen setups matcher filteret.'
      : 'Ingen aktive setups.';
    el.innerHTML = `<p class="empty">${msg}</p>`;
    return;
  }
  // setups (filtered subset) brukes til modal-oppslag — kortets index
  // i denne lista er nøkkelen.
  el.__bedrockSetups = setups;
  el.innerHTML = setups.map(s => {
    const lv = _extractSetupLevels(s) || {};
    const entry = lv.entry;
    const sl = lv.sl;
    // MAKRO trailing-only: tp/rr er eksplisitt null. Vis det som tekst
    // istedenfor "–" så kortet er informativt.
    const isTrailing = (s.horizon || '').toLowerCase() === 'makro' && lv.tp == null;
    const t1Cell = isTrailing ? '<span class="meta">trailing</span>' : fmt(lv.tp);
    const rrCell = isTrailing ? '<span class="meta">–</span>' : fmt(lv.rr, 2);
    const dirCls = (s.direction || '').toLowerCase() === 'sell' ? 'dir-sell' : 'dir-buy';
    const gradeCls = `grade-${(s.grade || 'x').replace('+', 'plus').toLowerCase()}`;
    const idx = setups.indexOf(s);
    return `<article class="setup-card clickable ${dirCls}" data-modal-idx="${idx}" tabindex="0" role="button" aria-label="Vis detaljer">
      <header>
        <span class="instrument">${s.instrument || '–'}</span>
        <span class="direction">${s.direction || '–'}</span>
        <span class="grade ${gradeCls}">${s.grade || '?'}</span>
      </header>
      <div class="card-row">
        ${_horizonBadgeHtml(s.horizon)}
        <span class="score">${_fmt2(s.score)} / ${_fmt2(s.max_score)}</span>
      </div>
      ${_scoreBarMiniHtml(s.score, s.max_score, s.min_score_publish)}
      <table class="levels">
        <tr><th>Entry</th><td>${fmt(entry)}</td></tr>
        <tr><th>Stop</th><td>${fmt(sl)}</td></tr>
        <tr><th>T1</th><td>${t1Cell}</td></tr>
        <tr><th>R:R</th><td>${rrCell}</td></tr>
      </table>
      ${_familyMiniHtml(s.families)}
    </article>`;
  }).join('');
}

// ─── Agri-fanen: setups + weather-overlay (Etappe 5) ──────────
// Setup-kort gjenbrukes via renderSetupCards, men blir post-prosessert
// med en weather-strip per kort hvor instrument finnes i ENSO/region-
// mappingen. Weather-data fetches en gang per fane-load.
let AGRI_SETUPS = [];
let AGRI_WEATHER = null;  // { enso, instruments: { [name]: {...} } }

async function loadAgriSetups() {
  // Setups + weather hentes parallelt — uavhengige.
  const [setupsRes, weatherRes] = await Promise.allSettled([
    fetch('/api/ui/setups/agri').then(r => r.json()),
    fetch('/api/ui/agri_weather').then(r => r.json()),
  ]);

  if (weatherRes.status === 'fulfilled' && weatherRes.value?.available) {
    AGRI_WEATHER = weatherRes.value;
  } else {
    AGRI_WEATHER = null;
    if (weatherRes.status === 'rejected') {
      console.error('Agri-weather load feilet:', weatherRes.reason);
    }
  }

  if (setupsRes.status === 'fulfilled') {
    const res = setupsRes.value;
    AGRI_SETUPS = res.setups || [];
    const visEl = document.getElementById('agri-count');
    const totEl = document.getElementById('agri-total');
    if (visEl) visEl.textContent = res.visible_count;
    if (totEl) totEl.textContent = res.total_count;
    renderAgriFiltered();
  } else {
    console.error('Agri setups load feilet:', setupsRes.reason);
    const el = document.getElementById('agri-cards');
    if (el) el.innerHTML = `<p class="empty">Fetch feilet: ${setupsRes.reason.message}</p>`;
  }
}

function renderAgriFiltered() {
  const filtered = applyFilter('agri', AGRI_SETUPS, fltAxesFromSetup);
  setFilterCount('agri', filtered.length, AGRI_SETUPS.length);
  renderSetupCards('agri-cards', filtered, AGRI_SETUPS.length);
  // Etter render — injiser weather-strip på hvert kort som har data.
  if (AGRI_WEATHER) _decorateAgriWeather('agri-cards', filtered, AGRI_WEATHER);
}

// Bygger en kompakt weather-strip og setter den inn i hvert agri-kort.
// Gjøres post-render istedenfor å endre signaturen til renderSetupCards
// (som er delt med Finans-fanen). Strip-en plasseres rett under family-mini.
function _decorateAgriWeather(containerId, setups, weather) {
  const root = document.getElementById(containerId);
  if (!root) return;
  const cards = root.querySelectorAll('.setup-card');
  if (cards.length !== setups.length) return;
  const enso = weather.enso;
  const instruments = weather.instruments || {};
  setups.forEach((s, i) => {
    const ctx = instruments[s.instrument];
    if (!ctx && !enso) return;
    const card = cards[i];
    if (!card || card.querySelector('.weather-strip')) return;
    card.insertAdjacentHTML('beforeend', _weatherStripHtml(enso, ctx));
  });
}

function _weatherStripHtml(enso, ctx) {
  const parts = [];
  if (enso) {
    const cls = `wt-enso-${enso.class || 'neutral'}`;
    parts.push(`<span class="wt-pill ${cls}" title="NOAA ONI per ${enso.as_of || '–'}">
      <span class="wt-pill-key">ENSO</span>
      <span class="wt-pill-val">${enso.label || '–'} ${_signedNum(enso.value)}</span>
    </span>`);
  }
  if (ctx) {
    const wm = ctx.weather_monthly;
    if (wm) {
      const wb = wm.water_bal;
      const wbCls = (wb == null) ? 'wt-neutral' : (wb < -20 ? 'wt-dry' : (wb > 20 ? 'wt-wet' : 'wt-neutral'));
      parts.push(`<span class="wt-pill ${wbCls}" title="${ctx.region} per ${wm.month || '–'}">
        <span class="wt-pill-key">${(ctx.region || '').replace(/_/g, ' ')}</span>
        <span class="wt-pill-val">vannbalanse ${wb == null ? '–' : _signedNum(wb)}mm · tørr ${wm.dry_days ?? '–'}d</span>
      </span>`);
    }
    const dr = ctx.drought;
    if (dr) {
      const cls = `wt-drought-${dr.class || 'low'}`;
      parts.push(`<span class="wt-pill ${cls}" title="US Drought Monitor per ${dr.as_of || '–'}">
        <span class="wt-pill-key">Tørke</span>
        <span class="wt-pill-val">${dr.drought_pct.toFixed(1)}% (D2+ ${(dr.d2_pct + dr.d3_pct + dr.d4_pct).toFixed(1)}%)</span>
      </span>`);
    }
  }
  if (!parts.length) return '';
  return `<div class="weather-strip">${parts.join('')}</div>`;
}

function _signedNum(v) {
  if (v == null || isNaN(v)) return '–';
  const n = Number(v);
  return (n >= 0 ? '+' : '') + n.toFixed(2).replace(/\.?0+$/, '');
}

// ─── Datakilder: bot-status + pipeline-helse + daglig systemsjekk ──────────
// Henter bot_status (sub-fase 12.9 D5: service-state + daily-loss + last
// trade + signals_bot.json-alder), pipeline_health (per-fetcher freshness +
// horisont-bruk per § 20.2) og system_health (daglig monitor-rapport).
async function loadKartrommet() {
  const [botRes, pipeRes, sysRes] = await Promise.allSettled([
    fetch('/api/ui/bot_status').then(r => r.json()),
    fetch('/api/ui/pipeline_health').then(r => r.json()),
    fetch('/api/ui/system_health').then(r => r.json()),
  ]);

  if (botRes.status === 'fulfilled') {
    renderBotStatus(botRes.value);
  } else {
    console.error('Bot-status load feilet:', botRes.reason);
    const el = document.getElementById('kartrom-bot-status');
    if (el) el.innerHTML = '';
  }

  if (sysRes.status === 'fulfilled') {
    renderSystemHealth(sysRes.value);
  } else {
    console.error('System-health load feilet:', sysRes.reason);
    const el = document.getElementById('kartrom-system-health');
    if (el) el.innerHTML = '';
  }

  if (pipeRes.status === 'fulfilled') {
    renderKartrommet(pipeRes.value);
  } else {
    console.error('Kartrommet load feilet:', pipeRes.reason);
    const el = document.getElementById('kartrom-groups');
    if (el) el.innerHTML = `<p class="empty">Fetch feilet: ${pipeRes.reason.message}</p>`;
  }
}

function _formatAge(seconds) {
  if (seconds === null || seconds === undefined) return '–';
  if (seconds < 60) return Math.round(seconds) + 's';
  if (seconds < 3600) return Math.round(seconds / 60) + 'm';
  if (seconds < 86400) return (seconds / 3600).toFixed(1) + 't';
  return (seconds / 86400).toFixed(1) + 'd';
}

function _serviceClass(state) {
  if (state === 'active') return 'ok';
  if (state === 'failed') return 'fail';
  if (state === 'activating' || state === 'reloading') return 'warn';
  if (state === 'unknown') return 'unknown';
  return 'idle'; // inactive / dead
}

function _serviceLabel(state, subState) {
  if (state === 'unknown') return 'Ukjent';
  if (state === 'active' && subState === 'running') return 'Kjører';
  if (state === 'active') return 'Aktiv';
  if (state === 'inactive') return 'Stoppet';
  if (state === 'failed') return 'Feilet';
  if (state === 'activating') return 'Starter';
  return state;
}

function renderBotStatus(res) {
  const root = document.getElementById('kartrom-bot-status');
  if (!root) return;
  if (!res || !res.service) {
    root.innerHTML = '';
    return;
  }
  const svc = res.service;
  const cls = _serviceClass(svc.state);
  const label = _serviceLabel(svc.state, svc.sub_state);

  const dl = res.daily_loss || {};
  const dlVal = (dl.daily_loss !== null && dl.daily_loss !== undefined)
    ? '$' + Number(dl.daily_loss).toFixed(2) : '–';
  const dlDate = dl.date || '–';

  const sb = res.signals_bot || {};
  const sbAge = sb.exists ? _formatAge(sb.age_seconds) : 'mangler';
  const sbCls = !sb.exists ? 'fail' : (sb.age_seconds > 7200 ? 'warn' : 'ok');

  const t = res.last_trade;
  const lastTradeHtml = t
    ? `<strong>${t.instrument || '?'}</strong> ${t.direction || ''} ${t.horizon || ''}
       → ${t.result || '?'} ${t.pnl_usd !== null && t.pnl_usd !== undefined ? '($' + Number(t.pnl_usd).toFixed(2) + ')' : ''}
       <span class="bot-stat-meta">${t.closed_at || ''}</span>`
    : '<span class="bot-stat-meta">Ingen trades logget</span>';

  root.innerHTML = `
    <div class="bot-status">
      <div class="bot-status-head">
        <span class="bot-status-pill ${cls}">${label}</span>
        <strong>bedrock-bot</strong>
        <code class="bot-status-svc">${svc.name}</code>
        <span class="bot-status-sub">${svc.sub_state}</span>
      </div>
      <div class="bot-status-grid">
        <div class="bot-stat">
          <span class="bot-stat-label">signals_bot.json</span>
          <span class="bot-stat-value status-${sbCls}">alder ${sbAge}</span>
        </div>
        <div class="bot-stat">
          <span class="bot-stat-label">Daily loss (${dlDate})</span>
          <span class="bot-stat-value">${dlVal}</span>
        </div>
        <div class="bot-stat bot-stat-wide">
          <span class="bot-stat-label">Siste trade</span>
          <span class="bot-stat-value">${lastTradeHtml}</span>
        </div>
      </div>
    </div>`;
}

function renderSystemHealth(res) {
  const root = document.getElementById('kartrom-system-health');
  if (!root) return;
  if (!res || !res.available) {
    root.innerHTML = `<div class="sys-health unknown">
      <span class="sys-health-pill">Ukjent</span>
      <span class="sys-health-text">Daglig systemsjekk ikke tilgjengelig${res?.reason ? ` — ${res.reason}` : ''}.</span>
    </div>`;
    return;
  }
  const ok = !!res.overall_ok;
  const cls = ok ? 'ok' : 'fail';
  const label = ok ? 'OK' : 'FAIL';
  const checks = res.checks || [];
  const generated = res.generated_utc ? res.generated_utc.replace('T', ' ').replace(/\.\d+.*$/, ' UTC') : '–';
  root.innerHTML = `
    <div class="sys-health ${cls}">
      <span class="sys-health-pill">${label}</span>
      <span class="sys-health-text">
        <strong>Daglig systemsjekk</strong> · generert ${generated} · kilde <code>${res.report_file || '–'}</code>
      </span>
    </div>
    <div class="sys-checks">
      ${checks.map(c => {
        const okFlag = !!c.ok;
        const checkCls = okFlag ? 'ok' : 'fail';
        const detail = c.detail || '';
        return `<div class="sys-check ${checkCls}">
          <div class="sys-check-head">
            <span class="sys-check-pill">${okFlag ? 'OK' : 'FAIL'}</span>
            <span class="sys-check-name">${c.name}</span>
          </div>
          <div class="sys-check-detail">${detail}</div>
        </div>`;
      }).join('')}
    </div>`;
}

function renderKartrommet(res) {
  const lastCheckEl = document.getElementById('kartrom-last-check');
  if (lastCheckEl) lastCheckEl.textContent = res.last_check || '–';

  const root = document.getElementById('kartrom-groups');
  if (!root) return;

  if (res.error) {
    root.innerHTML = `<p class="empty">${res.error}</p>`;
    return;
  }

  if (!res.groups || res.groups.length === 0) {
    root.innerHTML = '<p class="empty">Ingen fetch-kilder konfigurert.</p>';
    return;
  }

  root.innerHTML = res.groups.map(grp => `
    <section class="pipeline-group">
      <h3>${grp.name}</h3>
      <table class="pipeline-table">
        <thead>
          <tr><th>Kilde</th><th>Tabell</th><th>Status</th><th>Horisont</th><th>Alder</th><th>Stale-grense</th><th>Siste obs</th><th>Cron</th></tr>
        </thead>
        <tbody>
          ${grp.sources.map(s => `<tr>
            <td>${_fetcherLabelHtml(s.name)}</td>
            <td><code class="src-name">${_escapeHtml(s.table)}</code></td>
            <td><span class="status-pill status-${s.status}">${s.status}</span></td>
            <td>${renderHorizonChips(s.horizons)}</td>
            <td>${s.age_hours !== null ? s.age_hours.toFixed(1) + ' t' : '–'}</td>
            <td>${s.stale_hours} t</td>
            <td>${s.latest_observation || '–'}</td>
            <td><code>${s.cron || '–'}</code></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </section>
  `).join('');
}

// Per § 20.2: kilden bidrar til M (Macro), Sw (Swing) og/eller Sc (Scalp).
function renderHorizonChips(horizons) {
  if (!horizons || horizons.length === 0) return '<span class="hz-chip hz-none">–</span>';
  return horizons.map(h => {
    const cls = h === 'M' ? 'hz-macro' : h === 'Sw' ? 'hz-swing' : h === 'Sc' ? 'hz-scalp' : 'hz-none';
    const title = h === 'M' ? 'Macro (uker–måneder)' : h === 'Sw' ? 'Swing (dager–uker)' : h === 'Sc' ? 'Scalp (minutter–timer)' : '';
    return `<span class="hz-chip ${cls}" title="${title}">${h}</span>`;
  }).join('');
}

// ─── Markedspuls-fane (sentiment + risk-indikatorer) ────────
async function loadSentiment() {
  // Last alle tre parallelt — ingen avhengighet mellom dem.
  const [newsRes, cryptoRes, riskRes] = await Promise.allSettled([
    fetch('/api/ui/news_intel?days=7&limit=120').then(r => r.json()),
    fetch('/api/ui/crypto_sentiment?history_days=30').then(r => r.json()),
    fetch('/api/ui/risk_indicators').then(r => r.json()),
  ]);

  if (riskRes.status === 'fulfilled') {
    renderRiskIndicators(riskRes.value);
  } else {
    console.error('Risk-indikatorer load feilet:', riskRes.reason);
    const el = document.getElementById('risk-indicators');
    if (el) el.innerHTML = `<p class="empty">Fetch feilet: ${riskRes.reason.message}</p>`;
  }

  if (newsRes.status === 'fulfilled') {
    renderSentimentNews(newsRes.value);
  } else {
    console.error('News load feilet:', newsRes.reason);
    const el = document.getElementById('sentiment-news-grid');
    if (el) el.innerHTML = `<p class="empty">Fetch feilet: ${newsRes.reason.message}</p>`;
  }

  if (cryptoRes.status === 'fulfilled') {
    renderSentimentCrypto(cryptoRes.value);
  } else {
    console.error('Crypto load feilet:', cryptoRes.reason);
    const el = document.getElementById('sentiment-crypto');
    if (el) el.innerHTML = `<p class="empty">Crypto fetch feilet: ${cryptoRes.reason.message}</p>`;
  }
}

// Render risk-indikator-grid: ett kort per indikator med klassifisert
// fargekant og guide-tekst. Fortegn-pil viser om verdien er positiv/
// negativ (kun for kontekst — klasse-fargen styrer alvor).
function renderRiskIndicators(res) {
  const root = document.getElementById('risk-indicators');
  if (!root) return;
  if (!res || !res.available || !res.indicators?.length) {
    root.innerHTML = `<p class="empty">${res?.reason || 'Ingen risk-indikatorer tilgjengelig.'}</p>`;
    return;
  }
  root.innerHTML = `<div class="risk-grid">${res.indicators.map(ind => {
    const cls = `ri-${ind.class || 'normal'}`;
    const v = ind.value;
    const sign = (typeof v === 'number' && v > 0) ? '+' : '';
    const valStr = (typeof v === 'number') ? `${sign}${v}` : '–';
    const unit = ind.unit ? `<span class="ri-unit">${ind.unit}</span>` : '';
    return `<article class="ri-card ${cls}" title="${ind.guide || ''}">
      <div class="ri-head">
        <span class="ri-name">${ind.name}</span>
        <span class="ri-class">${(ind.class || '').toUpperCase()}</span>
      </div>
      <div class="ri-value">${valStr}${unit}</div>
      <div class="ri-context">${ind.context || ''}</div>
      <div class="ri-asof">per ${ind.as_of || '–'}</div>
    </article>`;
  }).join('')}</div>`;
}

function _formatMcap(usd) {
  if (usd === null || usd === undefined) return '–';
  if (usd >= 1e12) return (usd / 1e12).toFixed(2) + ' T USD';
  if (usd >= 1e9) return (usd / 1e9).toFixed(2) + ' B USD';
  return usd.toLocaleString('nb-NO') + ' USD';
}

function _formatPct(v, digits = 2) {
  if (v === null || v === undefined) return '–';
  const sign = v > 0 ? '+' : '';
  return sign + v.toFixed(digits) + '%';
}

function _fngColor(value) {
  if (value === null || value === undefined) return 'var(--c-ink-muted)';
  if (value < 25) return 'var(--c-neg, #c62828)';      // Extreme Fear
  if (value < 45) return 'var(--c-warn, #ef6c00)';     // Fear
  if (value < 55) return 'var(--c-ink-muted, #757575)';// Neutral
  if (value < 75) return 'var(--c-pos, #2e7d32)';      // Greed
  return 'var(--c-warn, #ef6c00)';                     // Extreme Greed (også advarsel)
}

function _fngSparkline(history) {
  if (!history || history.length < 2) return '';
  const w = 100, h = 28, pad = 2;
  const min = 0, max = 100;
  const xs = history.map((_, i) => pad + (i / (history.length - 1)) * (w - 2 * pad));
  const ys = history.map(v => h - pad - ((v - min) / (max - min)) * (h - 2 * pad));
  const points = xs.map((x, i) => `${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ');
  const lastV = history[history.length - 1];
  const stroke = _fngColor(lastV);
  return `<svg class="fng-sparkline" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <polyline points="${points}" fill="none" stroke="${stroke}" stroke-width="1.5"/>
  </svg>`;
}

function renderSentimentCrypto(res) {
  const root = document.getElementById('sentiment-crypto');
  if (!root) return;
  if (!res || !res.available) {
    root.innerHTML = '<p class="empty">Crypto-sentiment ikke populert ennå (fetcher kjører daglig 07:00).</p>';
    return;
  }

  const fng = res.fng || {};
  const market = res.market || {};
  const fngColor = _fngColor(fng.latest);
  const fngVal = fng.latest !== null && fng.latest !== undefined
    ? Math.round(fng.latest)
    : '–';

  root.innerHTML = `
    <div class="crypto-sentiment-row">
      <article class="crypto-card crypto-fng-card" data-clickable="fng" tabindex="0" role="button" aria-label="Vis F&amp;G-historikk">
        <header><h3>Fear &amp; Greed</h3></header>
        <div class="crypto-fng-value" style="color: ${fngColor}">${fngVal}</div>
        <div class="crypto-fng-label">${_escapeHtml(fng.label || '–')}</div>
        ${_fngSparkline(fng.history)}
        <div class="crypto-fng-hint">Klikk for ${(fng.history || []).length} dagers historikk</div>
      </article>
      <article class="crypto-card">
        <header><h3>BTC dominance</h3></header>
        <div class="crypto-metric">${market.btc_dominance !== null ? market.btc_dominance.toFixed(1) + '%' : '–'}</div>
      </article>
      <article class="crypto-card">
        <header><h3>ETH dominance</h3></header>
        <div class="crypto-metric">${market.eth_dominance !== null ? market.eth_dominance.toFixed(1) + '%' : '–'}</div>
      </article>
      <article class="crypto-card">
        <header><h3>Total market cap</h3></header>
        <div class="crypto-metric">${_escapeHtml(_formatMcap(market.total_mcap_usd))}</div>
        <div class="crypto-metric-sub">24h: ${_escapeHtml(_formatPct(market.total_mcap_chg24h_pct))}</div>
      </article>
    </div>
  `;

  // F&G-kort åpner modal med full historikk
  const fngCard = root.querySelector('.crypto-fng-card');
  if (fngCard) {
    const open = () => openFngModal(fng);
    fngCard.addEventListener('click', open);
    fngCard.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        open();
      }
    });
  }
}

function openFngModal(fng) {
  const modal = document.getElementById('modal');
  if (!modal) return;
  const content = modal.querySelector('.modal-content');
  if (!content) return;

  const history = fng.history || [];
  const rows = history.length === 0
    ? '<tr><td colspan="3" class="empty">Ingen historikk.</td></tr>'
    : history
        .map((v, i) => {
          const daysAgo = history.length - 1 - i;
          const label = _escapeHtml(_fngClassify(v));
          const color = _fngColor(v);
          return `<tr>
            <td>T-${daysAgo}d</td>
            <td style="color:${color}; font-weight: 600">${Math.round(v)}</td>
            <td>${label}</td>
          </tr>`;
        })
        .reverse()
        .join('');

  content.innerHTML = `
    <header class="modal-header">
      <h2 id="modal-title">Fear &amp; Greed Index <small>(${history.length} dager)</small></h2>
      <button class="modal-close" aria-label="Lukk">×</button>
    </header>
    <div class="fng-modal-body">
      <p class="meta">
        Verdier 0-100 fra <a href="https://alternative.me/crypto/fear-and-greed-index/" target="_blank" rel="noopener">alternative.me</a>.
        &lt;25 = Extreme Fear (contrarian bullish), &gt;75 = Extreme Greed (contrarian bearish).
      </p>
      <table class="fng-history-table">
        <thead><tr><th>Dag</th><th>Verdi</th><th>Klassifisering</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
  content.querySelector('.modal-close').addEventListener('click', () => modal.close());
  modal.showModal();
}

function _fngClassify(v) {
  if (v < 25) return 'Extreme Fear';
  if (v < 45) return 'Fear';
  if (v < 55) return 'Neutral';
  if (v < 75) return 'Greed';
  return 'Extreme Greed';
}

function _escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Render-hjelpere for datakilde-/driver-navn. Slår opp lesbar label +
// forklarings-tooltip i `source_labels.js`. Tooltip-format: "tech_name —
// beskrivelse" slik at hover alltid viser hvilken teknisk kilde dette er.
// Ukjente navn faller tilbake til <code>tech_name</code> så det er
// synlig at mappingen mangler.
function _fetcherLabelHtml(name) {
  const lib = window.BedrockSourceLabels;
  const info = lib ? lib.getFetcherLabel(name) : null;
  if (!info || info.isFallback) {
    return `<code class="src-name">${_escapeHtml(name)}</code>`;
  }
  const tip = `${name} — ${info.desc}`;
  return `<span class="src-label" title="${_escapeHtml(tip)}">${_escapeHtml(info.label)}</span>`;
}

function _driverLabelHtml(name) {
  const lib = window.BedrockSourceLabels;
  const info = lib ? lib.getDriverLabel(name) : null;
  if (!info || info.isFallback) {
    return `<code class="src-name">${_escapeHtml(name)}</code>`;
  }
  const tip = `${name} — ${info.desc}`;
  return `<span class="src-label" title="${_escapeHtml(tip)}">${_escapeHtml(info.label)}</span>`;
}

function _formatNewsTime(iso) {
  if (!iso) return '–';
  try {
    const d = new Date(iso);
    return d.toLocaleString('nb-NO', { dateStyle: 'short', timeStyle: 'short' });
  } catch (e) {
    return String(iso).slice(0, 16);
  }
}

function renderSentimentNews(res) {
  const lastCheckEl = document.getElementById('sentiment-last-check');
  const totalEl = document.getElementById('sentiment-total');
  const grid = document.getElementById('sentiment-news-grid');
  if (!grid) return;

  if (lastCheckEl) {
    lastCheckEl.textContent = res.as_of
      ? new Date(res.as_of).toLocaleTimeString('nb-NO', { timeStyle: 'short' })
      : '–';
  }
  if (totalEl) totalEl.textContent = res.total ?? '0';

  const cats = res.categories || [];
  if (cats.length === 0) {
    grid.innerHTML = '<p class="empty">Ingen kategorier konfigurert.</p>';
    return;
  }

  grid.innerHTML = cats.map(cat => {
    const top = (cat.articles || []).slice(0, 3);
    const previewItems = top.length === 0
      ? '<li class="empty">Ingen artikler siste 7 dager</li>'
      : top.map(a => `
          <li>
            <a href="${_escapeHtml(a.url)}" target="_blank" rel="noopener" title="${_escapeHtml(a.source || '')}">
              ${_escapeHtml(a.title)}
            </a>
            <span class="news-time">${_escapeHtml(_formatNewsTime(a.event_ts))}</span>
          </li>`
        ).join('');
    const moreBtn = cat.count > 3
      ? `<button class="news-more-btn" data-cat="${_escapeHtml(cat.id)}">+${cat.count - 3} til</button>`
      : '';
    return `
      <article class="news-card" data-cat="${_escapeHtml(cat.id)}">
        <header>
          <h3>${_escapeHtml(cat.label)}</h3>
          <span class="news-count">${cat.count}</span>
        </header>
        <ul>${previewItems}</ul>
        ${moreBtn}
      </article>`;
  }).join('');

  // Wire popup-modal-knapper
  grid.querySelectorAll('.news-more-btn').forEach(btn => {
    btn.addEventListener('click', () => openNewsModal(cats, btn.dataset.cat));
  });
}

function openNewsModal(allCats, catId) {
  const cat = (allCats || []).find(c => c.id === catId);
  if (!cat) return;
  const modal = document.getElementById('modal');
  if (!modal) return;
  const content = modal.querySelector('.modal-content');
  if (!content) return;

  const items = (cat.articles || []).map(a => `
    <li>
      <a href="${_escapeHtml(a.url)}" target="_blank" rel="noopener">${_escapeHtml(a.title)}</a>
      <div class="news-meta">
        <span>${_escapeHtml(a.source || '–')}</span>
        <span>${_escapeHtml(_formatNewsTime(a.event_ts))}</span>
      </div>
    </li>`).join('');

  content.innerHTML = `
    <header class="modal-header">
      <h2 id="modal-title">${_escapeHtml(cat.label)} <small>(${cat.count})</small></h2>
      <button class="modal-close" aria-label="Lukk">×</button>
    </header>
    <ul class="news-list-full">${items || '<li class="empty">Ingen artikler.</li>'}</ul>
  `;
  content.querySelector('.modal-close').addEventListener('click', () => modal.close());
  modal.showModal();
}

// ─── Drivers-fane (sub-fase 12.10 follow-up post-Spor-F) ─────
let _driversCache = null;

async function loadDrivers() {
  const summaryEl = document.getElementById('drivers-summary');
  const tbody = document.querySelector('#drivers-table tbody');
  if (!tbody) return;

  try {
    if (!_driversCache) {
      const res = await fetch('/api/ui/drivers', { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      _driversCache = await res.json();
    }
    renderDrivers();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty">Kunne ikke laste: ${_escapeHtml(String(err))}</td></tr>`;
    if (summaryEl) summaryEl.textContent = 'feil';
  }

  // Wire filter (idempotent)
  const search = document.getElementById('drivers-search');
  const select = document.getElementById('drivers-filter');
  if (search && !search.dataset.wired) {
    search.dataset.wired = '1';
    search.addEventListener('input', renderDrivers);
  }
  if (select && !select.dataset.wired) {
    select.dataset.wired = '1';
    select.addEventListener('change', renderDrivers);
  }
}

function renderDrivers() {
  if (!_driversCache) return;
  const data = _driversCache;
  const summaryEl = document.getElementById('drivers-summary');
  const tbody = document.querySelector('#drivers-table tbody');
  const search = (document.getElementById('drivers-search')?.value || '').toLowerCase().trim();
  const filter = document.getElementById('drivers-filter')?.value || 'all';

  if (summaryEl) {
    const s = data.summary;
    summaryEl.textContent = `${s.registered_total} registrert · ${s.wired_total} brukt · ${s.unused_total} ubrukt · ${s.instruments_count} instrumenter`;
  }

  let drivers = data.drivers;
  if (filter === 'wired') drivers = drivers.filter(d => d.wired);
  else if (filter === 'unused') drivers = drivers.filter(d => !d.wired);
  if (search) drivers = drivers.filter(d => d.name.toLowerCase().includes(search));

  if (drivers.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty">Ingen drivere matcher filteret.</td></tr>';
    return;
  }

  tbody.innerHTML = drivers.map(d => {
    const status = d.wired
      ? '<span style="color: #2a8d2a; font-weight: 600;">● BRUKT</span>'
      : '<span style="color: #999;">○ UBRUKT</span>';
    const moduleShort = (d.module || '').replace('bedrock.engine.drivers.', '');
    const insts = d.instruments.length === 0 ? '–' : d.instruments.join(', ');
    const wires = d.wirings.map(w => {
      const horiz = w.horizons[0] === 'all' ? '' : ` [${w.horizons.join(',')}]`;
      return `${w.instrument}/${w.family}@${w.weight}${horiz}`;
    });
    const wiresPreview = d.wirings.length === 0
      ? '–'
      : `${d.wiring_count}× <small style="color:#666;">(${_escapeHtml(wires.slice(0,2).join(' · '))}${wires.length > 2 ? ' …' : ''})</small>`;
    return `<tr>
      <td><code>${_escapeHtml(d.name)}</code>${d.doc ? `<br><small style="color:#777;">${_escapeHtml(d.doc.slice(0, 120))}${d.doc.length > 120 ? '…' : ''}</small>` : ''}</td>
      <td>${status}</td>
      <td><small>${_escapeHtml(moduleShort)}</small></td>
      <td>${wiresPreview}</td>
      <td><small>${_escapeHtml(insts)}</small></td>
    </tr>`;
  }).join('');
}

// ─── Lazy-load per fane ───────────────────────────────────────
const loaders = {
  skipsloggen: loadSkipsloggen,
  financial: loadFinancialSetups,
  agri: loadAgriSetups,
  sentiment: loadSentiment,
  kartrom: loadKartrommet,
  drivers: loadDrivers,
};

function activateTab(tabId) {
  const fn = loaders[tabId];
  if (fn) fn();
}

// Re-wire tab-klikk til å trigge lazy-load (uten å duplisere handleren fra
// override-et tab-handleren over er det enklere å lytte på klikk her i tillegg):
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => activateTab(btn.dataset.tab));
});

// ─── Server-status (session 53) ────────────────────────────────
// Polling /health for å vise live ok/down-pill i header. Endrer ikke
// data-flyt — endpointet finnes allerede fra Fase 7.
async function loadServerStatus() {
  const pill = document.getElementById('server-status');
  if (!pill) return;
  const txt = pill.querySelector('.status-text');
  try {
    const t0 = performance.now();
    const res = await fetch('/health', { cache: 'no-store' });
    const latencyMs = Math.round(performance.now() - t0);
    if (res.ok) {
      pill.dataset.status = 'ok';
      const now = new Date();
      const hh = String(now.getHours()).padStart(2, '0');
      const mm = String(now.getMinutes()).padStart(2, '0');
      if (txt) txt.textContent = `online · ${hh}:${mm} · ${latencyMs}ms`;
    } else {
      pill.dataset.status = 'down';
      if (txt) txt.textContent = `down · http ${res.status}`;
    }
  } catch (_) {
    pill.dataset.status = 'down';
    if (txt) txt.textContent = 'unreachable';
  }
}

// ─── Start ────────────────────────────────────────────────────
wireFilterBar('skipsloggen', renderTradeTableFiltered);
wireFilterBar('financial',   renderFinancialFiltered);
wireFilterBar('agri',        renderAgriFiltered);
_wireModalGlobal();
_wireModalDelegation();

loadSkipsloggen();
loadServerStatus();

// ─── Live updates via SSE (Mål 2) ─────────────────────────────
// Server pusher events når relevante filer endrer seg. UI re-laster
// kun det som faktisk er endret. Ingen 30-sek-polling.
//
// Safety-poll under (5 min) fanger:
//   - SSE-kobling som dør silent (proxy-timeout, server-restart)
//   - Event-tap mellom server og browser
//   - Server som ikke har broker registrert (returnerer 503)
function _setupLiveEvents() {
  let es;
  try {
    es = new EventSource('/api/ui/events');
  } catch (e) {
    console.warn('[live-events] EventSource ikke tilgjengelig:', e);
    return;
  }
  es.addEventListener('connected', () => {
    console.info('[live-events] SSE-kobling opp');
  });
  es.addEventListener('trade_log_changed', () => {
    loadSkipsloggen();
  });
  es.addEventListener('signals_changed', () => {
    // Re-last bare faner som faktisk leser signals*.json. Lazy-load
    // håndterer at brukere som er på andre faner ikke fetcher unødig.
    const activeTab = document.querySelector('.tab.active')?.dataset.tab;
    if (activeTab === 'financial')      loadFinancialSetups();
    else if (activeTab === 'agri')      loadAgriSetups();
    else if (activeTab === 'skipsloggen') loadSkipsloggen();
  });
  es.onerror = () => {
    // EventSource reconnecter selv. Logger kun for synlighet i devtools.
    if (es.readyState === EventSource.CLOSED) {
      console.warn('[live-events] SSE-kobling lukket, browser reconnecter');
    }
  };
}
_setupLiveEvents();

// Safety-poll: re-last alt på en lavere kadens uavhengig av SSE-state.
setInterval(loadSkipsloggen, SAFETY_POLL_INTERVAL_MS);
setInterval(loadServerStatus, SAFETY_POLL_INTERVAL_MS);
