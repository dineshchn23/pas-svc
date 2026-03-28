const SAMPLE_PORTFOLIO = [
  { ticker: 'AAPL', weight: 0.35 },
  { ticker: 'MSFT', weight: 0.25 },
  { ticker: 'GOOGL', weight: 0.20 },
  { ticker: 'JNJ', weight: 0.20 }
];

const AGENTS = ['risk', 'compliance', 'rebalancing', 'reporting', 'aggregator'];
const charts = {};

const els = {
  portfolioRows: document.getElementById('portfolioRows'),
  addRowBtn: document.getElementById('addRowBtn'),
  sampleBtn: document.getElementById('sampleBtn'),
  weightSummary: document.getElementById('weightSummary'),
  benchmarkInput: document.getElementById('benchmarkInput'),
  riskProfileSelect: document.getElementById('riskProfileSelect'),
  stressToggle: document.getElementById('stressToggle'),
  analyzeBtn: document.getElementById('analyzeBtn'),
  geminiBtn: document.getElementById('geminiBtn'),
  status: document.getElementById('status'),
  activityLog: document.getElementById('activityLog'),
  progressBar: document.getElementById('progressBar'),
  progressLabel: document.getElementById('progressLabel'),
  agentStatus: document.getElementById('agentStatus'),
  correlationGrid: document.getElementById('correlationGrid'),
  riskContributionList: document.getElementById('riskContributionList'),
  topRiskyList: document.getElementById('topRiskyList'),
  complianceBadge: document.getElementById('complianceBadge'),
  complianceViolations: document.getElementById('complianceViolations'),
  insightsPanel: document.getElementById('insightsPanel'),
  cardTotalReturn: document.getElementById('cardTotalReturn'),
  cardVolatility: document.getElementById('cardVolatility'),
  cardSharpe: document.getElementById('cardSharpe'),
  cardVar: document.getElementById('cardVar')
};

const palette = ['#38bdf8', '#22c55e', '#f59e0b', '#a78bfa', '#f97316', '#14b8a6', '#ef4444', '#eab308'];

let pipelineState = {};
let completedAgents = new Set();
let t0 = null;

function fmtPct(v) {
  return v == null ? '-' : `${(v * 100).toFixed(2)}%`;
}

function fmtNum(v, digits = 2) {
  return v == null ? '-' : Number(v).toFixed(digits);
}

function setStatus(text, tone = 'info') {
  const colors = {
    info: 'text-slate-300',
    ok: 'text-fintech-positive',
    warn: 'text-fintech-negative'
  };
  els.status.className = `mt-3 text-sm ${colors[tone] || colors.info}`;
  els.status.textContent = text;
}

function addLog(text, level = 'info', detail = '') {
  const colorMap = {
    info: 'border-slate-700',
    running: 'border-fintech-accent',
    done: 'border-fintech-positive',
    error: 'border-fintech-negative'
  };
  const elapsed = t0 ? `+${((Date.now() - t0) / 1000).toFixed(2)}s` : '';
  const row = document.createElement('div');
  row.className = `rounded-lg border-l-2 ${colorMap[level] || colorMap.info} bg-slate-900/80 px-2 py-1`;
  row.innerHTML = `
    <div class="flex items-start justify-between gap-2">
      <div>
        <p class="text-slate-100">${text}</p>
        ${detail ? `<p class="text-[11px] text-slate-400">${detail}</p>` : ''}
      </div>
      <span class="text-[10px] text-slate-500">${elapsed}</span>
    </div>
  `;
  els.activityLog.prepend(row);
}

function createRow(item = {}) {
  const row = document.createElement('div');
  row.className = 'grid grid-cols-12 gap-2';
  row.innerHTML = `
    <input class="ticker-input col-span-5 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm uppercase" placeholder="Ticker" maxlength="10" />
    <div class="col-span-5 flex items-center gap-2">
      <input class="weight-input w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm" type="number" min="0" max="100" step="0.1" placeholder="Weight %" />
      <span class="text-sm text-slate-400">%</span>
    </div>
    <button type="button" class="remove-btn col-span-2 rounded-xl bg-slate-800 px-2 py-2 text-sm hover:bg-slate-700">Remove</button>
  `;
  row.querySelector('.ticker-input').value = item.ticker || '';
  row.querySelector('.weight-input').value = item.weight ? (item.weight * 100).toFixed(1) : '';
  row.querySelector('.remove-btn').addEventListener('click', () => {
    row.remove();
    updateWeightSummary();
    renderEditorPreview();
  });
  row.querySelector('.ticker-input').addEventListener('input', () => {
    updateWeightSummary();
    renderEditorPreview();
  });
  row.querySelector('.weight-input').addEventListener('input', () => {
    updateWeightSummary();
    renderEditorPreview();
  });
  els.portfolioRows.appendChild(row);
}

function loadSamplePortfolio() {
  els.portfolioRows.innerHTML = '';
  SAMPLE_PORTFOLIO.forEach(createRow);
  updateWeightSummary();
  renderEditorPreview();
}

function updateWeightSummary() {
  const total = Array.from(document.querySelectorAll('.weight-input'))
    .map((i) => parseFloat(i.value) || 0)
    .reduce((a, b) => a + b, 0);
  els.weightSummary.textContent = `Total: ${total.toFixed(1)}%`;
  els.weightSummary.className = `rounded-xl border px-3 py-2 text-sm ${Math.abs(total - 100) <= 2 ? 'border-fintech-positive text-fintech-positive' : 'border-fintech-negative text-fintech-negative'}`;
}

function getPayload() {
  ensurePortfolioRows();
  const rows = Array.from(els.portfolioRows.children);
  if (!rows.length) {
    throw new Error('Add at least one portfolio row.');
  }
  const portfolio = rows.map((row, index) => {
    const ticker = row.querySelector('.ticker-input').value.trim().toUpperCase();
    const weightPct = parseFloat(row.querySelector('.weight-input').value);
    if (!ticker) {
      throw new Error(`Row ${index + 1}: ticker is required.`);
    }
    if (Number.isNaN(weightPct)) {
      throw new Error(`Row ${index + 1}: weight must be numeric.`);
    }
    return { ticker, weight: Number((weightPct / 100).toFixed(4)) };
  });

  const total = portfolio.reduce((sum, p) => sum + p.weight, 0);
  if (Math.abs(total - 1) > 0.02) {
    throw new Error(`Weights sum to ${(total * 100).toFixed(1)}% and must be near 100%.`);
  }

  return {
    portfolio,
    analysis_config: {
      benchmark: els.benchmarkInput.value.trim() || 'SPY',
      risk_profile: els.riskProfileSelect.value,
      stress_test: els.stressToggle.checked,
      compliance_rules: {}
    }
  };
}

function getEditorPortfolio() {
  if (!els.portfolioRows) {
    return [];
  }
  return Array.from(els.portfolioRows.children)
    .map((row) => {
      const ticker = row.querySelector('.ticker-input')?.value.trim().toUpperCase();
      const weightPct = parseFloat(row.querySelector('.weight-input')?.value);
      if (!ticker || Number.isNaN(weightPct) || weightPct <= 0) {
        return null;
      }
      return { ticker, weight: weightPct / 100 };
    })
    .filter(Boolean);
}

function sectorGuessForTicker(ticker) {
  const map = {
    AAPL: 'Technology',
    MSFT: 'Technology',
    GOOGL: 'Communication Services',
    GOOG: 'Communication Services',
    JNJ: 'Healthcare',
    NVDA: 'Technology',
    META: 'Communication Services',
    AMZN: 'Consumer Discretionary',
    TSLA: 'Consumer Discretionary',
    SPY: 'ETF'
  };
  return map[ticker] || 'Unclassified';
}

function renderEditorPreview() {
  const portfolio = getEditorPortfolio();
  if (!portfolio.length) {
    destroyChart('allocationChart');
    destroyChart('sectorChart');
    return;
  }

  const sectorMap = {};
  portfolio.forEach((item) => {
    const sector = sectorGuessForTicker(item.ticker);
    sectorMap[sector] = (sectorMap[sector] || 0) + item.weight;
  });

  renderAllocationChart(portfolio);
  renderSectorChart(sectorMap);
}

function resetPipelineUi() {
  pipelineState = {};
  completedAgents = new Set();
  AGENTS.forEach((agent) => {
    pipelineState[agent] = 'idle';
  });
  renderAgentStatus();
  updateProgress();
}

function setAgentState(agent, state) {
  pipelineState[agent] = state;
  if (state === 'done') {
    completedAgents.add(agent);
  }
  renderAgentStatus();
  updateProgress();
}

function renderAgentStatus() {
  els.agentStatus.innerHTML = AGENTS.map((agent) => {
    const state = pipelineState[agent] || 'idle';
    const tone = state === 'done'
      ? 'bg-fintech-positive/20 text-fintech-positive border-fintech-positive/60'
      : state === 'running'
        ? 'bg-fintech-accent/20 text-fintech-accent border-fintech-accent/60'
        : state === 'error'
          ? 'bg-fintech-negative/20 text-fintech-negative border-fintech-negative/60'
          : 'bg-slate-900 text-slate-400 border-slate-700';
    return `<div class="rounded-lg border px-2 py-1 ${tone}"><p class="text-[10px] uppercase tracking-wide">${agent}</p><p class="font-medium">${state}</p></div>`;
  }).join('');
}

function updateProgress() {
  const pct = Math.round((completedAgents.size / AGENTS.length) * 100);
  els.progressBar.style.width = `${pct}%`;
  els.progressLabel.textContent = `${pct}%`;
}

function destroyChart(name) {
  if (charts[name]) {
    charts[name].destroy();
    delete charts[name];
  }
}

function makeChart(name, config) {
  destroyChart(name);
  charts[name] = new Chart(document.getElementById(name), config);
}

function renderOverview(risk) {
  const p = risk?.portfolio || {};
  const setColor = (el, val) => {
    if (val == null) return;
    el.classList.remove('text-fintech-positive', 'text-fintech-negative', 'text-fintech-text');
    el.classList.add(val >= 0 ? 'text-fintech-positive' : 'text-fintech-negative');
  };

  els.cardTotalReturn.textContent = fmtPct(p.cumulative_return);
  els.cardVolatility.textContent = fmtPct(p.volatility);
  els.cardSharpe.textContent = fmtNum(p.sharpe, 2);
  els.cardVar.textContent = fmtPct(p.var_95);

  setColor(els.cardTotalReturn, p.cumulative_return);
  setColor(els.cardSharpe, p.sharpe);
}

function renderAllocationChart(portfolio) {
  makeChart('allocationChart', {
    type: 'pie',
    data: {
      labels: portfolio.map((x) => x.ticker),
      datasets: [{
        data: portfolio.map((x) => x.weight * 100),
        backgroundColor: portfolio.map((_, i) => palette[i % palette.length])
      }]
    },
    options: {
      plugins: { legend: { labels: { color: '#e2e8f0' } } }
    }
  });
}

function renderSectorChart(sectors) {
  const labels = Object.keys(sectors || {});
  const values = Object.values(sectors || {}).map((v) => v * 100);
  makeChart('sectorChart', {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label: 'Weight %', data: values, backgroundColor: '#38bdf8' }]
    },
    options: {
      scales: {
        x: { ticks: { color: '#cbd5e1' }, grid: { color: '#334155' } },
        y: { ticks: { color: '#cbd5e1' }, grid: { color: '#334155' } }
      },
      plugins: { legend: { labels: { color: '#e2e8f0' } } }
    }
  });
}

function renderCumulativeChart(performance) {
  const p = performance?.series?.portfolio_cumulative || [];
  const b = performance?.series?.benchmark_cumulative || [];
  const labels = p.map((x) => x.date);
  makeChart('cumulativeChart', {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Portfolio',
          data: p.map((x) => x.value * 100),
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56,189,248,0.2)',
          tension: 0.2
        },
        {
          label: performance?.benchmark?.ticker || 'Benchmark',
          data: b.map((x) => x.value * 100),
          borderColor: '#22c55e',
          backgroundColor: 'rgba(34,197,94,0.2)',
          tension: 0.2
        }
      ]
    },
    options: {
      scales: {
        x: { ticks: { color: '#94a3b8', maxTicksLimit: 8 }, grid: { color: '#334155' } },
        y: { ticks: { color: '#cbd5e1' }, grid: { color: '#334155' } }
      },
      plugins: { legend: { labels: { color: '#e2e8f0' } } }
    }
  });
}

function renderDrawdownChart(riskInsights) {
  const series = riskInsights?.series?.drawdown || [];
  makeChart('drawdownChart', {
    type: 'line',
    data: {
      labels: series.map((x) => x.date),
      datasets: [{
        label: 'Drawdown %',
        data: series.map((x) => x.value * 100),
        borderColor: '#ef4444',
        backgroundColor: 'rgba(239,68,68,0.18)',
        fill: true,
        tension: 0.2
      }]
    },
    options: {
      scales: {
        x: { ticks: { color: '#94a3b8', maxTicksLimit: 8 }, grid: { color: '#334155' } },
        y: { ticks: { color: '#cbd5e1' }, grid: { color: '#334155' } }
      },
      plugins: { legend: { labels: { color: '#e2e8f0' } } }
    }
  });
}

function colorFromCorr(v) {
  const n = Math.max(-1, Math.min(1, Number(v)));
  if (n >= 0) {
    const alpha = 0.15 + n * 0.65;
    return `rgba(34,197,94,${alpha.toFixed(2)})`;
  }
  const alpha = 0.15 + Math.abs(n) * 0.65;
  return `rgba(239,68,68,${alpha.toFixed(2)})`;
}

function renderCorrelationGrid(matrix) {
  const keys = Object.keys(matrix || {});
  if (!keys.length) {
    els.correlationGrid.innerHTML = '<p class="text-sm text-slate-400">Correlation data unavailable.</p>';
    return;
  }

  let html = '<table class="min-w-full text-xs border-collapse"><thead><tr><th class="p-1"></th>';
  html += keys.map((k) => `<th class="p-1 text-slate-400">${k}</th>`).join('');
  html += '</tr></thead><tbody>';
  keys.forEach((row) => {
    html += `<tr><th class="p-1 text-slate-400">${row}</th>`;
    keys.forEach((col) => {
      const val = matrix[row]?.[col] ?? 0;
      html += `<td class="p-1 text-center border border-slate-700" style="background:${colorFromCorr(val)}">${Number(val).toFixed(2)}</td>`;
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  els.correlationGrid.innerHTML = html;
}

function renderRiskInsights(riskInsights, riskContribution) {
  const contributions = riskContribution || riskInsights?.risk_contribution || [];
  els.riskContributionList.innerHTML = contributions.map((item) => {
    return `
      <div class="rounded-lg border border-slate-700 bg-slate-900/80 px-3 py-2">
        <div class="flex items-center justify-between">
          <span>${item.ticker}</span>
          <span class="text-fintech-accent">${fmtPct(item.contribution_pct)}</span>
        </div>
      </div>
    `;
  }).join('') || '<p class="text-slate-400">No risk contribution data.</p>';

  els.topRiskyList.innerHTML = contributions.slice(0, 3)
    .map((item) => `<li>${item.ticker} (${fmtPct(item.contribution_pct)})</li>`)
    .join('') || '<li>No data.</li>';
}

function renderCompliance(compliance) {
  const ok = Boolean(compliance?.ok);
  els.complianceBadge.className = `mb-2 inline-flex rounded-full px-3 py-1 text-xs font-semibold ${ok ? 'bg-fintech-positive/20 text-fintech-positive' : 'bg-fintech-negative/20 text-fintech-negative'}`;
  els.complianceBadge.textContent = ok ? 'PASS' : 'FAIL';

  const violations = compliance?.violations || [];
  els.complianceViolations.innerHTML = violations.length
    ? violations.map((v) => `
        <div class="rounded-lg border border-slate-700 bg-slate-900/80 px-3 py-2">
          <p class="text-xs uppercase tracking-wide text-slate-400">${v.rule} · ${v.severity}</p>
          <p>${v.message}</p>
        </div>
      `).join('')
    : '<p class="text-sm text-fintech-positive">No violations under selected profile.</p>';
}

function renderInsights(report) {
  if (!report || typeof report !== 'object') {
    els.insightsPanel.innerHTML = '<p class="text-slate-400">No insight data.</p>';
    return;
  }
  const section = (title, content, asList = true) => `
    <div>
      <p class="mb-1 text-xs uppercase tracking-wide text-slate-400">${title}</p>
      ${asList
        ? `<ul class="list-disc space-y-1 pl-4">${(content || []).map((x) => `<li>${x}</li>`).join('') || '<li>-</li>'}</ul>`
        : `<p>${content || '-'}</p>`}
    </div>
  `;
  els.insightsPanel.innerHTML = [
    section('Summary', report.summary, false),
    section('Risks', report.risks),
    section('Opportunities', report.opportunities),
    section('Recommendations', report.recommendations)
  ].join('');
}

function renderAll(result) {
  const normalized = result?.aggregation || result || {};
  const risk = normalized?.risk || {};
  const compliance = normalized?.compliance || {};
  const performance = normalized?.performance || risk?.performance || {};
  const riskInsights = normalized?.risk_insights || risk?.risk_insights || {};
  const report = normalized?.report || normalized?.insights || {};

  renderOverview(risk);
  renderAllocationChart(normalized?.portfolio || []);
  renderSectorChart(compliance?.sectors || {});
  renderCumulativeChart(performance);
  renderDrawdownChart(riskInsights);
  renderCorrelationGrid(riskInsights?.correlation_matrix || risk?.correlation_matrix || {});
  renderRiskInsights(riskInsights, risk?.risk_contribution);
  renderCompliance(compliance);
  renderInsights(report);
}

function handleEvent(event, data) {
  const agent = data?.agent;
  if (event === 'started') {
    addLog('Pipeline started', 'running', (data.tasks || []).join(', '));
    setStatus('Running analysis stream...', 'info');
    return;
  }

  if (event === 'agent_running' && agent) {
    setAgentState(agent, 'running');
    addLog(`${agent} started`, 'running');
    return;
  }

  if (event === 'agent_done' && agent) {
    setAgentState(agent, 'done');
    addLog(`${agent} done`, 'done', data.duration != null ? `${data.duration.toFixed(2)}s` : '');
    if (agent === 'risk' && data.result) {
      renderOverview(data.result);
      renderRiskInsights(data.result.risk_insights, data.result.risk_contribution);
      renderCorrelationGrid(data.result.risk_insights?.correlation_matrix || data.result.correlation_matrix || {});
      renderDrawdownChart(data.result.risk_insights || {});
      renderCumulativeChart(data.result.performance || {});
    }
    if (agent === 'compliance' && data.result) {
      renderCompliance(data.result);
      renderSectorChart(data.result.sectors || {});
    }
    if (agent === 'reporting' && data.result) {
      renderInsights(data.result);
    }
    return;
  }

  if (event === 'agent_error' && agent) {
    setAgentState(agent, 'error');
    addLog(`${agent} error`, 'error', String(data.error || '').slice(0, 140));
    setStatus(`${agent} failed`, 'warn');
    return;
  }

  if (event === 'aggregated') {
    setAgentState('aggregator', 'done');
    addLog('aggregation complete', 'done');
    return;
  }

  if (event === 'done') {
    addLog('Pipeline complete', 'done');
    setStatus('Analysis complete', 'ok');
    return;
  }

  if (event === 'error') {
    addLog('Pipeline error', 'error', data.message || 'Unknown error');
    setStatus(`Error: ${data.message || 'Unknown'}`, 'warn');
  }
}

async function runAnalysis() {
  let payload;
  try {
    payload = getPayload();
  } catch (err) {
    setStatus(err.message, 'warn');
    return;
  }

  t0 = Date.now();
  resetPipelineUi();
  els.activityLog.innerHTML = '';
  setStatus('Starting analysis...', 'info');
  els.analyzeBtn.disabled = true;

  try {
    const resp = await fetch('/analyze/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!resp.ok) {
      throw new Error(`Server error ${resp.status}: ${await resp.text()}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buf += decoder.decode(value, { stream: true });
      const chunks = buf.split('\n\n');
      buf = chunks.pop() || '';
      for (const chunk of chunks) {
        let event = 'message';
        let data = '';
        chunk.split('\n').forEach((line) => {
          if (line.startsWith('event: ')) {
            event = line.slice(7).trim();
          }
          if (line.startsWith('data: ')) {
            data = line.slice(6);
          }
        });
        if (data) {
          handleEvent(event, JSON.parse(data));
        }
      }
    }

    const rest = await fetch('/results');
    if (rest.ok) {
      const result = await rest.json();
      renderAll(result);
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, 'warn');
    addLog('Analysis request failed', 'error', err.message);
  } finally {
    els.analyzeBtn.disabled = false;
  }
}

async function testGemini() {
  setStatus('Checking Gemini...', 'info');
  addLog('Gemini diagnostic started', 'running');
  try {
    const resp = await fetch('/debug/gemini');
    const data = await resp.json();
    if (data.connected) {
      setStatus(`Gemini connected (${data.model || 'default'})`, 'ok');
      addLog('Gemini reachable', 'done', data.model || '');
    } else {
      setStatus('Gemini not reachable', 'warn');
      addLog('Gemini failed', 'error', String(data.diagnostic || '').slice(0, 180));
    }
  } catch (err) {
    setStatus(`Gemini check failed: ${err.message}`, 'warn');
    addLog('Gemini check failed', 'error', err.message);
  }
}

function ensurePortfolioRows() {
  if (!els.portfolioRows) {
    return;
  }
  if (!els.portfolioRows.children.length) {
    loadSamplePortfolio();
  }
}

function initApp() {
  els.addRowBtn?.addEventListener('click', () => createRow());
  els.sampleBtn?.addEventListener('click', loadSamplePortfolio);
  els.analyzeBtn?.addEventListener('click', runAnalysis);
  els.geminiBtn?.addEventListener('click', testGemini);

  resetPipelineUi();
  ensurePortfolioRows();
  updateWeightSummary();
  renderEditorPreview();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}