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
  body.innerHTML = entries.map(e => {
    const s = e.signal || {};
    return `<tr>
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
  el.innerHTML = setups.map(s => {
    const setup = s.setup || {};
    const entry = setup.entry;
    const sl = setup.stop_loss ?? setup.sl ?? setup.stop;
    const t1 = setup.target_1 ?? setup.t1;
    const rr = setup.rr_t1 ?? setup.rr;
    const dirCls = (s.direction || '').toLowerCase() === 'sell' ? 'dir-sell' : 'dir-buy';
    const gradeCls = `grade-${(s.grade || 'x').replace('+', 'plus').toLowerCase()}`;
    return `<article class="setup-card ${dirCls}">
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
        <tr><th>T1</th><td>${fmt(t1)}</td></tr>
        <tr><th>R:R</th><td>${fmt(rr, 2)}</td></tr>
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

// ─── Lazy-load per fane ───────────────────────────────────────
const loaders = {
  skipsloggen: loadSkipsloggen,
  financial: loadFinancialSetups,
  agri: loadAgriSetups,
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

// ─── Start ────────────────────────────────────────────────────
wireFilterBar('skipsloggen', renderTradeTableFiltered);
wireFilterBar('financial',   renderFinancialFiltered);
wireFilterBar('agri',        renderAgriFiltered);

loadSkipsloggen();
setInterval(loadSkipsloggen, REFRESH_INTERVAL_MS);
