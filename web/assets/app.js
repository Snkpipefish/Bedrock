// Bedrock UI — Fase 9 runde 1 session 47: Skipsloggen
// Vanilla JS (per PLAN § 15). Runde 2 legger til polish/filtrering.

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
async function loadSkipsloggen() {
  try {
    const [summary, log] = await Promise.all([
      fetch('/api/ui/trade_log/summary').then(r => r.json()),
      fetch('/api/ui/trade_log?limit=100').then(r => r.json()),
    ]);
    renderKpi(summary);
    renderTradeTable(log.entries);
    const el = document.getElementById('last-updated');
    if (el) el.textContent = log.last_updated || '–';
  } catch (err) {
    console.error('Skipsloggen load feilet:', err);
    const body = document.getElementById('trade-log-body');
    if (body) body.innerHTML = `<tr><td colspan="12" class="empty">Fetch feilet: ${err.message}</td></tr>`;
  }
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
    body.innerHTML = '<tr><td colspan="12" class="empty">Ingen trades ennå.</td></tr>';
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

// ─── Start ────────────────────────────────────────────────────
loadSkipsloggen();
setInterval(loadSkipsloggen, REFRESH_INTERVAL_MS);
