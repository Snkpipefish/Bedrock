// Bedrock UI — Fase 9 runde 1 session 47: Skipsloggen
// Runde 2 session 51: filter-bar (horizon/grade/instrument/direction).
// Vanilla JS (per PLAN § 15).

const REFRESH_INTERVAL_MS = 30_000;

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
          <tr><th>Driver</th><th class="num">Value</th><th class="num">Weight</th><th class="num">Bidrag</th></tr>
        </thead>
        <tbody>
          ${drivers.map(d => `<tr>
            <td>${d.name}</td>
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
        <span class="horizon">${s.horizon || '–'}</span>
        <span class="score">score: ${fmt(s.score, 2)}</span>
      </div>
      <table class="levels">
        <tr><th>Entry</th><td>${fmt(entry)}</td></tr>
        <tr><th>Stop</th><td>${fmt(sl)}</td></tr>
        <tr><th>T1</th><td>${t1Cell}</td></tr>
        <tr><th>R:R</th><td>${rrCell}</td></tr>
      </table>
    </article>`;
  }).join('');
}

// ─── Soft commodities setups (session 49) ─────────────────────
// Gjenbruker renderSetupCards — ingen agri-spesifikke felt i setup-
// dict enda. Runde 2 / Fase 10 legger til weather/ENSO/Conab-badges
// når fetch-lagene er ferdige.
let AGRI_SETUPS = [];

async function loadAgriSetups() {
  try {
    const res = await fetch('/api/ui/setups/agri').then(r => r.json());
    AGRI_SETUPS = res.setups || [];
    const visEl = document.getElementById('agri-count');
    const totEl = document.getElementById('agri-total');
    if (visEl) visEl.textContent = res.visible_count;
    if (totEl) totEl.textContent = res.total_count;
    renderAgriFiltered();
  } catch (err) {
    console.error('Agri setups load feilet:', err);
    const el = document.getElementById('agri-cards');
    if (el) el.innerHTML = `<p class="empty">Fetch feilet: ${err.message}</p>`;
  }
}

function renderAgriFiltered() {
  const filtered = applyFilter('agri', AGRI_SETUPS, fltAxesFromSetup);
  setFilterCount('agri', filtered.length, AGRI_SETUPS.length);
  renderSetupCards('agri-cards', filtered, AGRI_SETUPS.length);
}

// ─── Kartrommet: pipeline-helse (session 50) ──────────────────
async function loadKartrommet() {
  try {
    const res = await fetch('/api/ui/pipeline_health').then(r => r.json());
    renderKartrommet(res);
  } catch (err) {
    console.error('Kartrommet load feilet:', err);
    const el = document.getElementById('kartrom-groups');
    if (el) el.innerHTML = `<p class="empty">Fetch feilet: ${err.message}</p>`;
  }
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
          <tr><th>Kilde</th><th>Tabell</th><th>Status</th><th>Alder</th><th>Stale-grense</th><th>Siste obs</th><th>Cron</th></tr>
        </thead>
        <tbody>
          ${grp.sources.map(s => `<tr>
            <td>${s.name}</td>
            <td>${s.table}</td>
            <td><span class="status-pill status-${s.status}">${s.status}</span></td>
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

// ─── Sentiment-fane (session 114 news_intel + 115 crypto) ────────
async function loadSentiment() {
  try {
    const res = await fetch('/api/ui/news_intel?days=7&limit=120').then(r => r.json());
    renderSentimentNews(res);
  } catch (err) {
    console.error('Sentiment load feilet:', err);
    const el = document.getElementById('sentiment-news-grid');
    if (el) el.innerHTML = `<p class="empty">Fetch feilet: ${err.message}</p>`;
  }
}

function _escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
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

// ─── Lazy-load per fane ───────────────────────────────────────
const loaders = {
  skipsloggen: loadSkipsloggen,
  financial: loadFinancialSetups,
  agri: loadAgriSetups,
  sentiment: loadSentiment,
  kartrom: loadKartrommet,
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
setInterval(loadSkipsloggen, REFRESH_INTERVAL_MS);
setInterval(loadServerStatus, REFRESH_INTERVAL_MS);
