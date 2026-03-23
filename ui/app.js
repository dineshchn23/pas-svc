// ── DOM refs ─────────────────────────────────────────────────────
const statusEl      = document.getElementById('status');
const portfolioRows = document.getElementById('portfolioRows');
const addRowBtn     = document.getElementById('addRowBtn');
const resetBtn      = document.getElementById('resetBtn');
const weightSummary = document.getElementById('weightSummary');
const analyzeBtn    = document.getElementById('analyzeBtn');
const geminiBtn     = document.getElementById('geminiBtn');
const activityLog   = document.getElementById('activityLog');

const SAMPLE_PORTFOLIO = [
  { ticker: 'AAPL',  weight: 0.35 },
  { ticker: 'MSFT',  weight: 0.25 },
  { ticker: 'GOOGL', weight: 0.20 },
  { ticker: 'JNJ',   weight: 0.20 },
];

const NODE_IDS = { risk: 'nodeRisk', compliance: 'nodeCompliance', reporting: 'nodeReporting', aggregator: 'nodeAggregator' };
const LOG_ICONS = { started: '\uD83D\uDE80', running: '\u2699\uFE0F', done: '\u2705', error: '\u274C', aggregate: '\uD83D\uDD00', info: '\u2139\uFE0F', gemini: '\uD83E\uDD16' };

let t0 = null;

// ── Status bar ────────────────────────────────────────────────────
function setStatus(text, level = 'info') {
  statusEl.textContent = text;
  statusEl.className = `status ${level}`;
}

// ── Portfolio editor ──────────────────────────────────────────────
function createRow(item = {}) {
  const row = document.createElement('div');
  row.className = 'portfolio-row';
  row.innerHTML = `
    <input class="ticker-input" type="text" maxlength="10" placeholder="e.g. AAPL" autocomplete="off" />
    <div class="weight-field">
      <input class="weight-input" type="number" min="0" max="100" step="0.1" placeholder="25.0" />
      <span>%</span>
    </div>
    <button type="button" class="row-remove ghost sm" title="Remove">✕</button>
  `;
  row.querySelector('.ticker-input').value = item.ticker || '';
  row.querySelector('.weight-input').value = item.weight ? (item.weight * 100).toFixed(1) : '';
  row.querySelector('.row-remove').addEventListener('click', () => { row.remove(); updateWeightSummary(); });
  row.querySelector('.ticker-input').addEventListener('input', updateWeightSummary);
  row.querySelector('.weight-input').addEventListener('input', updateWeightSummary);
  portfolioRows.appendChild(row);
}

function loadSamplePortfolio() {
  portfolioRows.innerHTML = '';
  SAMPLE_PORTFOLIO.forEach(createRow);
  updateWeightSummary();
}

function updateWeightSummary() {
  const total = Array.from(portfolioRows.querySelectorAll('.weight-input'))
    .map(i => parseFloat(i.value) || 0).reduce((a, b) => a + b, 0);
  weightSummary.textContent = `Total: ${total.toFixed(1)}%`;
  const balanced = Math.abs(total - 100) <= 2;
  weightSummary.className = `weight-summary ${balanced ? 'balanced' : 'unbalanced'}`;
}

function getPortfolio() {
  const rows = Array.from(portfolioRows.querySelectorAll('.portfolio-row'));
  if (!rows.length) throw new Error('Add at least one asset');
  const portfolio = rows.map((row, i) => {
    const ticker = row.querySelector('.ticker-input').value.trim().toUpperCase();
    const w = parseFloat(row.querySelector('.weight-input').value);
    if (!ticker)       throw new Error(`Row ${i + 1}: ticker is required`);
    if (isNaN(w))      throw new Error(`Row ${i + 1}: weight must be numeric`);
    return { ticker, weight: parseFloat((w / 100).toFixed(4)) };
  });
  const total = portfolio.reduce((s, x) => s + x.weight, 0);
  if (Math.abs(total - 1) > 0.02)
    throw new Error(`Weights sum to ${(total * 100).toFixed(1)}% — should be ~100%`);
  return portfolio;
}

// ── Agent pipeline nodes ───────────────────────────────────────────
function resetPipeline() {
  Object.keys(NODE_IDS).forEach(a => setAgent(a, 'idle', ''));
}

function setAgent(agent, state, timeStr = '') {
  const id = NODE_IDS[agent];
  if (!id) return;
  const node = document.getElementById(id);
  if (!node) return;
  node.className = `agent-node ${state}`;
  const badge = node.querySelector('.node-badge');
  if (badge) {
    badge.dataset.state = state;
    badge.textContent = { idle: 'Waiting', running: 'Running…', done: 'Done', error: 'Error' }[state] || state;
  }
  const timeEl = node.querySelector('.node-time');
  if (timeEl && timeStr) timeEl.textContent = timeStr;
}

// ── Activity log ───────────────────────────────────────────────────
function clearLog() { activityLog.innerHTML = ''; }

function addLog(message, type = 'info', detail = '') {
  const empty = activityLog.querySelector('.log-empty');
  if (empty) empty.remove();
  const elapsed = t0 ? `+${((Date.now() - t0) / 1000).toFixed(2)}s` : '';
  const entry = document.createElement('div');
  entry.className = `log-entry log-${type}`;
  entry.innerHTML = `
    <span class="log-icon">${LOG_ICONS[type] || '\u2139\uFE0F'}</span>
    <div class="log-body">
      <span class="log-msg">${message}</span>
      ${detail ? `<span class="log-detail">${detail}</span>` : ''}
    </div>
    ${elapsed ? `<span class="log-time">${elapsed}</span>` : ''}
  `;
  activityLog.appendChild(entry);
  activityLog.scrollTop = activityLog.scrollHeight;
}

// ── Result renderers ───────────────────────────────────────────────
function renderRisk(risk) {
  const p = risk.portfolio || {};
  const fmt = (v, pct) => v != null ? (pct ? (v * 100).toFixed(2) + '%' : v.toFixed(3)) : '—';
  document.getElementById('riskContent').innerHTML = `
    <div class="metric-tiles">
      <div class="metric-tile">
        <div class="metric-label">Volatility (Ann.)</div>
        <div class="metric-value">${fmt(p.volatility, true)}</div>
      </div>
      <div class="metric-tile">
        <div class="metric-label">Sharpe Ratio</div>
        <div class="metric-value ${(p.sharpe || 0) >= 1 ? 'good' : ''}">${fmt(p.sharpe, false)}</div>
      </div>
      <div class="metric-tile">
        <div class="metric-label">VaR 95% (Ann.)</div>
        <div class="metric-value warn">${fmt(p.var_95, true)}</div>
      </div>
      <div class="metric-tile">
        <div class="metric-label">Beta vs SPY</div>
        <div class="metric-value">${fmt(p.beta, false)}</div>
      </div>
    </div>
    <p class="sub-head">Per Asset</p>
    <div class="asset-rows">
      ${Object.entries(risk.assets || {}).map(([ticker, a]) =>
        `<div class="asset-row">
          <span class="asset-ticker">${ticker}</span>
          <span class="asset-stat">Vol: ${fmt(a.volatility, true)}</span>
          <span class="asset-stat">Ret: ${fmt(a.mean_annual_return, true)}</span>
        </div>`
      ).join('')}
    </div>`;
}

function renderCompliance(comp) {
  const ok = comp.ok;
  document.getElementById('complianceContent').innerHTML = `
    <div class="compliance-badge ${ok ? 'pass' : 'fail'}">${ok ? '\u2705 PASS' : '\u274C FAIL'}</div>
    ${!ok
      ? `<div class="compliance-issues"><p class="issues-head">Issues</p><ul>${(comp.issues || []).map(i => `<li>${i}</li>`).join('')}</ul></div>`
      : '<p class="compliance-ok-msg">All compliance rules satisfied.</p>'}
    <p class="sub-head">Sector Allocation</p>
    <div class="sector-rows">
      ${Object.entries(comp.sectors || {}).map(([sector, w]) =>
        `<div class="sector-row">
          <span class="sector-name">${sector}</span>
          <div class="sector-bar-wrap"><div class="sector-bar" style="width:${Math.min(w * 100, 100).toFixed(1)}%"></div></div>
          <span class="sector-pct">${(w * 100).toFixed(1)}%</span>
        </div>`
      ).join('')}
    </div>`;
}

function renderInsights(text) {
  const html = String(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>');
  document.getElementById('insightsContent').innerHTML =
    `<div class="insights-prose"><p>${html}</p></div>`;
}

function renderTimings(timings) {
  const entries = [
    { label: 'Risk Agent',       key: 'risk_seconds',       color: '#6b9fd4' },
    { label: 'Compliance Agent', key: 'compliance_seconds', color: '#82c996' },
    { label: 'Reporting Agent',  key: 'reporting_seconds',  color: '#f4a55e' },
    { label: 'Total',            key: 'total_seconds',      color: '#c86a30', bold: true },
  ];
  const max = Math.max(...entries.map(e => timings[e.key] || 0), 0.1);
  document.getElementById('timingsContent').innerHTML = `
    <div class="timing-bars">
      ${entries.map(e => {
        const val = timings[e.key];
        if (val == null) return '';
        const pct = Math.min((val / max) * 100, 100).toFixed(1);
        return `<div class="timing-row ${e.bold ? 'bold-row' : ''}">
          <span class="timing-label">${e.label}</span>
          <div class="timing-bar-wrap"><div class="timing-bar" style="width:${pct}%;background:${e.color}"></div></div>
          <span class="timing-val">${val.toFixed(3)}s</span>
        </div>`;
      }).join('')}
    </div>
    <p class="timing-note">Risk + Compliance ran in parallel — total is less than the sum of both.</p>`;
}

function resetCards() {
  ['riskContent','complianceContent','insightsContent','timingsContent'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="placeholder-msg">Running…</div>';
  });
}

// ── SSE streaming consumer ─────────────────────────────────────────
async function runAnalysis() {
  let portfolio;
  try { portfolio = getPortfolio(); }
  catch (e) { setStatus(e.message, 'warn'); return; }

  analyzeBtn.disabled = true;
  analyzeBtn.textContent = '\u23F3 Analyzing…';
  clearLog();
  resetCards();
  resetPipeline();
  t0 = Date.now();
  setStatus('Streaming live agent events…', 'info');

  try {
    const resp = await fetch('/analyze/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ portfolio }),
    });
    if (!resp.ok) { throw new Error(`Server error ${resp.status}: ${await resp.text()}`); }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split('\n\n');
      buf = parts.pop();
      for (const part of parts) {
        let event = 'message', data = '';
        for (const line of part.split('\n')) {
          if (line.startsWith('event: ')) event = line.slice(7).trim();
          if (line.startsWith('data: '))  data  = line.slice(6).trim();
        }
        if (data) handleEvent(event, JSON.parse(data));
      }
    }
    setStatus('Analysis complete.', 'ok');
  } catch (err) {
    setStatus('Error: ' + err.message, 'warn');
    addLog(err.message, 'error');
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = '\u25B6 Run Analysis';
  }
}

function handleEvent(event, data) {
  const cap = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
  switch (event) {
    case 'started':
      addLog('Pipeline started — tasks: ' + (data.tasks || []).join(', '), 'started');
      ['risk', 'compliance'].forEach(a => setAgent(a, 'running'));
      break;
    case 'agent_running':
      setAgent(data.agent, 'running');
      addLog(`${cap(data.agent)} Agent is running`, 'running');
      break;
    case 'agent_done':
      setAgent(data.agent, 'done', data.duration != null ? `${data.duration.toFixed(2)}s` : '');
      addLog(`${cap(data.agent)} Agent completed`, 'done', data.duration != null ? `${data.duration.toFixed(2)}s` : '');
      if (data.agent === 'risk'        && data.result) renderRisk(data.result);
      if (data.agent === 'compliance'  && data.result) renderCompliance(data.result);
      if (data.agent === 'reporting'   && data.result) renderInsights(data.result);
      break;
    case 'agent_error':
      setAgent(data.agent, 'error');
      addLog(`${cap(data.agent)} Agent error`, 'error', (data.error || '').slice(0, 120));
      break;
    case 'aggregated':
      setAgent('aggregator', 'done');
      addLog('Aggregator merged all results', 'aggregate');
      if (data.timings) renderTimings(data.timings);
      break;
    case 'done':
      addLog('\uD83C\uDFC1 Pipeline complete', 'done');
      break;
    case 'error':
      addLog('Pipeline error: ' + data.message, 'error');
      break;
  }
}

// ── Gemini test ────────────────────────────────────────────────────
async function testGemini() {
  clearLog();
  addLog('Testing Gemini connectivity…', 'gemini');
  setStatus('Checking Gemini…', 'info');
  try {
    const data = await (await fetch('/debug/gemini')).json();
    const ok = Boolean(data.connected);
    addLog(`Gemini ${ok ? 'connected' : 'failed'}: ${data.model || ''}`, ok ? 'done' : 'error', (data.diagnostic || '').slice(0, 200));
    setStatus((ok ? 'Gemini connected: ' : 'Gemini failed: ') + (data.model || ''), ok ? 'ok' : 'warn');
    document.getElementById('insightsContent').innerHTML =
      `<div class="insights-prose"><p>${data.diagnostic || ''}</p></div>`;
  } catch (e) {
    setStatus('Gemini check failed: ' + e.message, 'warn');
    addLog(e.message, 'error');
  }
}

// ── Init ───────────────────────────────────────────────────────────
analyzeBtn.addEventListener('click', runAnalysis);
geminiBtn.addEventListener('click', testGemini);
addRowBtn.addEventListener('click', () => createRow());
resetBtn.addEventListener('click', loadSamplePortfolio);

loadSamplePortfolio();
