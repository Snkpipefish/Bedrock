// Bedrock admin — rule-editor JS (Fase 9 runde 3 session 54).
//
// Gate-flyt:
// 1) Bruker oppgir admin-koden i input → lagres i sessionStorage
//    (default) eller localStorage (hvis "Husk for denne fanen")
// 2) Vi tester koden ved å POSTe til GET /admin/rules — 401 = feil
//    kode, 503 = server-config mangler admin_code, 200 = OK
// 3) Ved suksess vises sidebaren + editoren; koden blir værende i
//    storage og brukes som X-Admin-Code-header for hver request
//
// Editor-flyt:
// - Klikk på instrument → fetch /admin/rules/<id> → fyll textarea
// - Endring i textarea → 'dirty'-indikator + Lagre-knapp aktiveres
// - Klikk Lagre → PUT /admin/rules/<id> med JSON {yaml_content}
// - 200 = success-feedback, 400 = validation-feil med detaljer
// - Reload = forkast endringer og hent på nytt fra server
//
// Vanilla JS per PLAN § 15.

const STORAGE_KEY = 'bedrock-admin-code';

function getStoredCode() {
  return sessionStorage.getItem(STORAGE_KEY) || localStorage.getItem(STORAGE_KEY) || null;
}

function storeCode(code, persistent) {
  if (persistent) {
    localStorage.setItem(STORAGE_KEY, code);
    sessionStorage.removeItem(STORAGE_KEY);
  } else {
    sessionStorage.setItem(STORAGE_KEY, code);
    localStorage.removeItem(STORAGE_KEY);
  }
}

function clearStoredCode() {
  sessionStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(STORAGE_KEY);
}

// Authenticated fetch wrapper — alle admin-kall går gjennom denne.
async function authFetch(url, init = {}) {
  const code = getStoredCode();
  const headers = Object.assign({}, init.headers || {}, code ? { 'X-Admin-Code': code } : {});
  return fetch(url, Object.assign({}, init, { headers }));
}

// ─── Server-status (samme polling som dashboard) ──────────────
async function loadServerStatus() {
  const pill = document.getElementById('server-status');
  if (!pill) return;
  const txt = pill.querySelector('.status-text');
  try {
    const t0 = performance.now();
    const res = await fetch('/health', { cache: 'no-store' });
    const ms = Math.round(performance.now() - t0);
    if (res.ok) {
      pill.dataset.status = 'ok';
      const now = new Date();
      const hh = String(now.getHours()).padStart(2, '0');
      const mm = String(now.getMinutes()).padStart(2, '0');
      if (txt) txt.textContent = `online · ${hh}:${mm} · ${ms}ms`;
    } else {
      pill.dataset.status = 'down';
      if (txt) txt.textContent = `down · http ${res.status}`;
    }
  } catch (_) {
    pill.dataset.status = 'down';
    if (txt) txt.textContent = 'unreachable';
  }
}

// ─── Gate ─────────────────────────────────────────────────────
function showGate() {
  document.getElementById('gate').hidden = false;
  document.getElementById('admin-main').hidden = true;
}

function showMain() {
  document.getElementById('gate').hidden = true;
  document.getElementById('admin-main').hidden = false;
}

function showGateError(msg) {
  const el = document.getElementById('gate-error');
  el.textContent = msg;
  el.hidden = false;
}

function clearGateError() {
  const el = document.getElementById('gate-error');
  el.textContent = '';
  el.hidden = true;
}

async function tryAuth(code) {
  // Vi tester koden ved \u00e5 hente listen — er en lett operasjon som
  // returnerer 200/401/503 raskt.
  const res = await fetch('/admin/rules', { headers: { 'X-Admin-Code': code } });
  if (res.status === 200) return { ok: true };
  if (res.status === 401) return { ok: false, error: 'Ugyldig admin-kode.' };
  if (res.status === 503) {
    return { ok: false, error: 'Server har ikke konfigurert BEDROCK_ADMIN_CODE.' };
  }
  return { ok: false, error: `Uventet svar: HTTP ${res.status}` };
}

async function bootGate() {
  const code = getStoredCode();
  if (!code) {
    showGate();
    return;
  }
  const r = await tryAuth(code);
  if (r.ok) {
    showMain();
    loadInstrumentList();
  } else {
    clearStoredCode();
    showGate();
    showGateError(r.error || 'Lagret kode aksepteres ikke lenger.');
  }
}

function wireGate() {
  document.getElementById('gate-form').addEventListener('submit', async e => {
    e.preventDefault();
    clearGateError();
    const code = document.getElementById('gate-code').value;
    const persist = document.getElementById('gate-remember').checked;
    if (!code) return;
    const r = await tryAuth(code);
    if (!r.ok) {
      showGateError(r.error || 'Auth feilet.');
      return;
    }
    storeCode(code, persist);
    document.getElementById('gate-code').value = '';
    showMain();
    loadInstrumentList();
  });
  document.getElementById('logout-btn').addEventListener('click', () => {
    clearStoredCode();
    clearEditor();
    showGate();
  });
}

// ─── Instrument-liste ─────────────────────────────────────────
let CURRENT_INSTRUMENT = null;
let LAST_LOADED_YAML = '';

async function loadInstrumentList() {
  const list = document.getElementById('instr-list');
  list.innerHTML = '<li class="meta">Laster…</li>';
  try {
    const res = await authFetch('/admin/rules');
    if (!res.ok) {
      list.innerHTML = `<li class="meta">Feil: HTTP ${res.status}</li>`;
      return;
    }
    const data = await res.json();
    const items = data.instruments || [];
    if (!items.length) {
      list.innerHTML = '<li class="meta">Ingen instrument-YAML funnet.</li>';
      return;
    }
    list.innerHTML = items.map(it => `
      <li data-id="${it.instrument_id}" tabindex="0" role="button">
        <span>${it.instrument_id}</span>
        <span class="size">${it.size_bytes} B</span>
      </li>`).join('');
    list.querySelectorAll('li[data-id]').forEach(li => {
      li.addEventListener('click', () => loadInstrument(li.dataset.id));
      li.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          loadInstrument(li.dataset.id);
        }
      });
    });
  } catch (err) {
    list.innerHTML = `<li class="meta">Feil: ${err.message}</li>`;
  }
}

function setActiveListItem(id) {
  document.querySelectorAll('#instr-list li[data-id]').forEach(li => {
    li.classList.toggle('active', li.dataset.id === id);
  });
}

// ─── Editor ───────────────────────────────────────────────────
async function loadInstrument(instrumentId) {
  if (CURRENT_INSTRUMENT === instrumentId && !isDirty()) return;
  if (isDirty()) {
    if (!confirm('Du har ulagrede endringer. Forkast dem?')) return;
  }
  setActiveListItem(instrumentId);
  CURRENT_INSTRUMENT = instrumentId;
  showEditor();
  document.getElementById('editor-title').textContent = instrumentId;
  document.getElementById('editor-path').textContent = `config/instruments/${instrumentId}.yaml`;
  setFeedback(null);
  setDirty(false);
  const ta = document.getElementById('yaml-editor');
  ta.value = 'Laster…';
  try {
    const res = await authFetch(`/admin/rules/${encodeURIComponent(instrumentId)}`);
    if (!res.ok) {
      const body = await safeJson(res);
      setFeedback('error', `HTTP ${res.status}: ${body.error || 'ukjent feil'}`);
      ta.value = '';
      return;
    }
    const data = await res.json();
    LAST_LOADED_YAML = data.yaml_content || '';
    ta.value = LAST_LOADED_YAML;
    setDirty(false);
  } catch (err) {
    setFeedback('error', `Klarte ikke å hente YAML: ${err.message}`);
    ta.value = '';
  }
}

function showEditor() {
  document.getElementById('editor-empty').hidden = true;
  document.getElementById('editor-active').hidden = false;
}

function clearEditor() {
  CURRENT_INSTRUMENT = null;
  LAST_LOADED_YAML = '';
  document.getElementById('editor-empty').hidden = false;
  document.getElementById('editor-active').hidden = true;
  document.getElementById('yaml-editor').value = '';
  setActiveListItem(null);
}

function isDirty() {
  if (CURRENT_INSTRUMENT === null) return false;
  return document.getElementById('yaml-editor').value !== LAST_LOADED_YAML;
}

function setDirty(forceState) {
  const dirty = forceState !== undefined ? forceState : isDirty();
  document.getElementById('dirty-indicator').hidden = !dirty;
  document.getElementById('save-btn').disabled = !dirty;
}

function setFeedback(kind, msg) {
  const el = document.getElementById('feedback');
  if (!kind) {
    el.hidden = true;
    el.textContent = '';
    el.className = 'admin-editor-feedback';
    return;
  }
  el.hidden = false;
  el.textContent = msg;
  el.className = 'admin-editor-feedback ' + kind;
}

async function safeJson(res) {
  try { return await res.json(); } catch (_) { return {}; }
}

async function saveCurrent() {
  if (!CURRENT_INSTRUMENT) return;
  const ta = document.getElementById('yaml-editor');
  const yaml_content = ta.value;
  setFeedback(null);
  document.getElementById('save-btn').disabled = true;
  try {
    const res = await authFetch(`/admin/rules/${encodeURIComponent(CURRENT_INSTRUMENT)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yaml_content }),
    });
    const data = await safeJson(res);
    if (res.ok) {
      LAST_LOADED_YAML = yaml_content;
      setDirty(false);
      let gitLine = '';
      if (data.git) {
        if (data.git.committed) {
          gitLine = `\n✓ git-commit ${data.git.sha}: ${data.git.message}`;
        } else if (data.git.error) {
          gitLine = `\n⚠ git-commit feilet: ${data.git.error}`;
        } else if (data.git.reason) {
          gitLine = `\n(git: ${data.git.reason})`;
        }
      }
      setFeedback('success', `Lagret: ${data.written_to || CURRENT_INSTRUMENT}${gitLine}`);
      // Refresh-liste-størrelser kan være endret
      loadInstrumentList();
    } else if (res.status === 400 && data.details) {
      const details = (data.details || []).map(d =>
        `  ${(d.loc || []).join('.')}: ${d.msg}`).join('\n');
      setFeedback('error', `${data.error || 'Validering feilet'}\n${details}`);
      setDirty(true);
    } else {
      setFeedback('error', `HTTP ${res.status}: ${data.error || 'ukjent feil'}${data.detail ? '\n' + data.detail : ''}`);
      setDirty(true);
    }
  } catch (err) {
    setFeedback('error', `Save-feil: ${err.message}`);
    setDirty(true);
  }
}

function reloadCurrent() {
  if (!CURRENT_INSTRUMENT) return;
  if (isDirty() && !confirm('Forkast endringer og hent på nytt?')) return;
  const id = CURRENT_INSTRUMENT;
  CURRENT_INSTRUMENT = null;  // tving load
  loadInstrument(id);
}

async function dryRunCurrent() {
  if (!CURRENT_INSTRUMENT) return;
  const yaml_content = document.getElementById('yaml-editor').value;
  setFeedback(null);
  try {
    const res = await authFetch(`/admin/rules/${encodeURIComponent(CURRENT_INSTRUMENT)}/dry-run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yaml_content }),
    });
    const data = await safeJson(res);
    if (res.ok && data.valid) {
      const families = (data.config_summary && data.config_summary.families) || [];
      const summary = families.length
        ? `Familier: ${families.join(', ')}`
        : 'Ingen families i config';
      setFeedback('dry-run-ok',
        `✓ Dry-run OK · ${data.config_summary?.id || CURRENT_INSTRUMENT} · ${summary}\n` +
        `(Lagre er trygg — YAML er validert mot Pydantic + inherits-resolver)`);
    } else if (res.status === 400 && data.details) {
      const details = (data.details || []).map(d =>
        `  ${(d.loc || []).join('.')}: ${d.msg}`).join('\n');
      setFeedback('error', `Dry-run feilet: ${data.error || 'validering feilet'}\n${details}`);
    } else {
      setFeedback('error', `Dry-run feilet: ${data.error || 'HTTP ' + res.status}`);
    }
  } catch (err) {
    setFeedback('error', `Dry-run-feil: ${err.message}`);
  }
}


// ─── Section-nav (Rules / Logs) ───────────────────────────────
function showSection(name) {
  document.querySelectorAll('.admin-nav-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.adminSection === name);
  });
  document.querySelectorAll('[data-admin-section]').forEach(el => {
    if (el.classList.contains('admin-nav-btn')) return;
    el.hidden = el.dataset.adminSection !== name;
  });
  if (name === 'logs') loadLogs();
}

function wireNav() {
  document.querySelectorAll('.admin-nav-btn').forEach(btn => {
    btn.addEventListener('click', () => showSection(btn.dataset.adminSection));
  });
}

// ─── Logs-viewer ──────────────────────────────────────────────
async function loadLogs() {
  const out = document.getElementById('logs-output');
  const pathEl = document.getElementById('logs-path');
  out.classList.remove('empty');
  out.textContent = 'Laster…';
  pathEl.textContent = '–';
  const tail = Math.max(1, Math.min(2000, parseInt(document.getElementById('logs-tail').value, 10) || 200));
  try {
    const res = await authFetch(`/admin/logs?tail=${tail}`);
    if (res.status === 404) {
      const data = await safeJson(res);
      out.classList.add('empty');
      out.textContent = data.error || 'Log-fil ikke konfigurert. Sett BEDROCK_ADMIN_LOG_PATH og restart.';
      return;
    }
    if (!res.ok) {
      const data = await safeJson(res);
      out.classList.add('empty');
      out.textContent = `HTTP ${res.status}: ${data.error || 'ukjent feil'}`;
      return;
    }
    const data = await res.json();
    pathEl.textContent = `${data.path} · viser ${data.returned}/${data.total_lines} linjer`;
    out.textContent = (data.lines || []).join('\n') || '(tom log)';
  } catch (err) {
    out.classList.add('empty');
    out.textContent = `Feil: ${err.message}`;
  }
}

function wireLogs() {
  document.getElementById('logs-reload-btn').addEventListener('click', loadLogs);
  document.getElementById('logs-tail').addEventListener('change', loadLogs);
}

// ─── Init ─────────────────────────────────────────────────────
function wireEditor() {
  document.getElementById('yaml-editor').addEventListener('input', () => setDirty());
  document.getElementById('save-btn').addEventListener('click', saveCurrent);
  document.getElementById('reload-btn').addEventListener('click', reloadCurrent);
  document.getElementById('reload-list').addEventListener('click', loadInstrumentList);
  document.getElementById('dry-run-btn').addEventListener('click', dryRunCurrent);
  // Cmd/Ctrl+S = lagre
  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === 's') {
      e.preventDefault();
      if (CURRENT_INSTRUMENT && isDirty()) saveCurrent();
    }
  });
  // Advarsel ved navigation bort hvis dirty
  window.addEventListener('beforeunload', e => {
    if (isDirty()) {
      e.preventDefault();
      e.returnValue = '';
    }
  });
}

wireGate();
wireEditor();
wireNav();
wireLogs();
loadServerStatus();
setInterval(loadServerStatus, 30000);
bootGate();

// CommonJS-eksport for evt. Node-tester (ingen i denne sessionen, men
// klar for senere).
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { getStoredCode, storeCode, clearStoredCode, isDirty };
}
