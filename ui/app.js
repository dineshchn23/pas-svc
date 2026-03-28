const SAMPLE_SCENARIOS = {
  diversified_multi_sector: [
    { ticker: 'AAPL', weight: 0.2 },
    { ticker: 'JNJ', weight: 0.18 },
    { ticker: 'XOM', weight: 0.16 },
    { ticker: 'JPM', weight: 0.16 },
    { ticker: 'PG', weight: 0.15 },
    { ticker: 'MSFT', weight: 0.15 }
  ],
  same_sector_tech: [
    { ticker: 'AAPL', weight: 0.22 },
    { ticker: 'MSFT', weight: 0.22 },
    { ticker: 'NVDA', weight: 0.2 },
    { ticker: 'GOOGL', weight: 0.18 },
    { ticker: 'META', weight: 0.18 }
  ],
  same_sector_healthcare: [
    { ticker: 'JNJ', weight: 0.26 },
    { ticker: 'PFE', weight: 0.2 },
    { ticker: 'MRK', weight: 0.2 },
    { ticker: 'ABBV', weight: 0.18 },
    { ticker: 'LLY', weight: 0.16 }
  ],
  mega_cap_blend: [
    { ticker: 'AAPL', weight: 0.18 },
    { ticker: 'MSFT', weight: 0.18 },
    { ticker: 'AMZN', weight: 0.16 },
    { ticker: 'GOOGL', weight: 0.16 },
    { ticker: 'META', weight: 0.16 },
    { ticker: 'BRK-B', weight: 0.16 }
  ],
  defensive_income: [
    { ticker: 'PG', weight: 0.2 },
    { ticker: 'KO', weight: 0.2 },
    { ticker: 'JNJ', weight: 0.2 },
    { ticker: 'XOM', weight: 0.2 },
    { ticker: 'PFE', weight: 0.2 }
  ],
  growth_plus_stability: [
    { ticker: 'AAPL', weight: 0.24 },
    { ticker: 'MSFT', weight: 0.22 },
    { ticker: 'GOOGL', weight: 0.16 },
    { ticker: 'JNJ', weight: 0.14 },
    { ticker: 'PG', weight: 0.12 },
    { ticker: 'JPM', weight: 0.12 }
  ]
};

const AGENTS = ['risk', 'compliance', 'rebalancing', 'reporting', 'aggregator'];
const charts = {};
const palette = ['#38bdf8', '#22c55e', '#f59e0b', '#a78bfa', '#f97316', '#14b8a6', '#ef4444', '#eab308'];

const els = {
  portfolioRows: document.getElementById('portfolioRows'),
  addRowBtn: document.getElementById('addRowBtn'),
  sampleBtn: document.getElementById('sampleBtn'),
  sampleScenarioSelect: document.getElementById('sampleScenarioSelect'),
  weightSummary: document.getElementById('weightSummary'),
  benchmarkInput: document.getElementById('benchmarkInput'),
  riskProfileSelect: document.getElementById('riskProfileSelect'),
  stressToggle: document.getElementById('stressToggle'),
  analyzeBtn: document.getElementById('analyzeBtn'),
  geminiBtn: document.getElementById('geminiBtn'),
  status: document.getElementById('status'),
  progressBar: document.getElementById('progressBar'),
  progressLabel: document.getElementById('progressLabel'),
  advancedModeBtn: document.getElementById('advancedModeBtn'),
  simpleModeBtn: document.getElementById('simpleModeBtn'),
  activityLog: document.getElementById('activityLog'),
  agentStatus: document.getElementById('agentStatus'),
  correlationGrid: document.getElementById('correlationGrid'),
  correlationHighlights: document.getElementById('correlationHighlights'),
  correlationSummary: document.getElementById('correlationSummary'),
  correlationToggle: document.getElementById('correlationToggle'),
  correlationToggleLabel: document.getElementById('correlationToggleLabel'),
  correlationChevron: document.getElementById('correlationChevron'),
  correlationBody: document.getElementById('correlationBody'),
  complianceBadge: document.getElementById('complianceBadge'),
  complianceViolations: document.getElementById('complianceViolations'),
  insightsPanel: document.getElementById('insightsPanel'),
  portfolioSummaryCard: document.getElementById('portfolioSummaryCard'),
  aiSummaryCard: document.getElementById('aiSummaryCard'),
  rollingMetricsPanel: document.getElementById('rollingMetricsPanel'),
  characteristicsPanel: document.getElementById('characteristicsPanel'),
  compositionInsights: document.getElementById('compositionInsights'),
  aiReportToggle: document.getElementById('aiReportToggle'),
  aiReportChevron: document.getElementById('aiReportChevron'),
  activityToggle: document.getElementById('activityToggle'),
  activityChevron: document.getElementById('activityChevron'),
  activitySectionBody: document.getElementById('activitySectionBody'),
  cardReturnLabel: document.getElementById('cardReturnLabel'),
  cardVolatilityLabel: document.getElementById('cardVolatilityLabel'),
  cardSharpeLabel: document.getElementById('cardSharpeLabel'),
  cardVarLabel: document.getElementById('cardVarLabel'),
  cardAlphaLabel: document.getElementById('cardAlphaLabel'),
  cardTotalReturn: document.getElementById('cardTotalReturn'),
  cardVolatility: document.getElementById('cardVolatility'),
  cardSharpe: document.getElementById('cardSharpe'),
  cardVar: document.getElementById('cardVar'),
  cardAlpha: document.getElementById('cardAlpha'),
  cardReturnContext: document.getElementById('cardReturnContext'),
  cardVolatilityContext: document.getElementById('cardVolatilityContext'),
  cardSharpeContext: document.getElementById('cardSharpeContext'),
  cardVarContext: document.getElementById('cardVarContext'),
  cardAlphaContext: document.getElementById('cardAlphaContext')
};

let currentMode = 'advanced';
let pipelineState = {};
let completedAgents = new Set();
let t0 = null;
let latestResult = null;
let isAiReportOpen = true;
let isActivityOpen = true;
let isCorrelationOpen = true;
let summaryResizeRaf = null;
let equalizeResizeRaf = null;

function fmtPct(v) {
  return v == null ? '-' : `${(v * 100).toFixed(2)}%`;
}

function fmtNum(v, digits = 2) {
  return v == null ? '-' : Number(v).toFixed(digits);
}

function fmtSigned(v, digits = 2) {
  if (v == null) return '-';
  const n = Number(v);
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}`;
}

function esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function styleFlagLabel(flag) {
  const labels = {
    large_cap_dominated: 'Large-Cap Dominated',
    growth_heavy: 'Growth Heavy',
    low_income_exposure: 'Low Income Exposure'
  };
  return labels[flag] || flag;
}

function setStatus(text, tone = 'info') {
  const colors = {
    info: 'text-slate-300',
    ok: 'text-green-400',
    warn: 'text-red-400'
  };
  els.status.className = `text-sm ${colors[tone] || colors.info}`;
  els.status.textContent = text;
}

function nowStamp() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function cardTone(value) {
  if (value == null) return 'text-slate-200';
  return value >= 0 ? 'text-green-400' : 'text-red-400';
}

function riskTone(volatility) {
  if (volatility == null) return 'bg-slate-700 text-slate-200';
  if (volatility >= 0.3) return 'bg-red-500/20 text-red-400';
  if (volatility >= 0.2) return 'bg-amber-500/20 text-amber-300';
  return 'bg-green-500/20 text-green-400';
}

function concentrationTone(weight) {
  if (weight == null) return 'bg-slate-700 text-slate-200';
  if (weight >= 0.4) return 'bg-red-500/20 text-red-400';
  if (weight >= 0.25) return 'bg-amber-500/20 text-amber-300';
  return 'bg-green-500/20 text-green-400';
}

function addLog(text, level = 'info', detail = '') {
  const border = {
    info: 'border-slate-700',
    running: 'border-cyan-400',
    done: 'border-green-400',
    error: 'border-red-400'
  };
  const elapsed = t0 ? `+${((Date.now() - t0) / 1000).toFixed(2)}s` : '';
  const row = document.createElement('div');
  row.className = `rounded-lg border-l-2 ${border[level] || border.info} bg-slate-900/80 px-2 py-1`;
  row.innerHTML = `
    <div class="flex items-start justify-between gap-2">
      <div>
        <p class="text-slate-100">${esc(text)}</p>
        ${detail ? `<p class="text-[11px] text-slate-400">${esc(detail)}</p>` : ''}
      </div>
      <div class="text-right text-[10px] text-slate-500">
        <div>${nowStamp()}</div>
        <div>${elapsed}</div>
      </div>
    </div>
  `;
  els.activityLog.prepend(row);
}

function SectionContainer({ eyebrow, title, subtitle, body, accent = false }) {
  return `
    <div class="${accent ? 'ring-1 ring-cyan-400/40 rounded-2xl p-1' : ''}">
      ${eyebrow ? `<p class="text-[11px] uppercase tracking-[0.2em] text-slate-500">${esc(eyebrow)}</p>` : ''}
      <h3 class="mt-1 text-lg font-semibold text-slate-100">${esc(title || '')}</h3>
      ${subtitle ? `<p class="mt-1 text-sm text-slate-400">${esc(subtitle)}</p>` : ''}
      <div class="mt-4">${body || ''}</div>
    </div>
  `;
}

function KPICard({ label, value, context, toneClass = 'text-slate-200' }) {
  return `
    <div class="rounded-xl border border-slate-700 bg-slate-900/65 p-3">
      <p class="text-[11px] uppercase tracking-[0.18em] text-slate-400">${esc(label)}</p>
      <p class="mt-1 text-xl font-semibold ${toneClass}">${esc(value)}</p>
      <p class="mt-1 text-xs text-slate-400">${esc(context || '')}</p>
    </div>
  `;
}

function ChartCard({ title, subtitle, content }) {
  return `
    <div>
      <p class="text-xs uppercase tracking-[0.16em] text-slate-500">${esc(title)}</p>
      ${subtitle ? `<p class="mt-1 text-sm text-slate-400">${esc(subtitle)}</p>` : ''}
      <div class="mt-3">${content || ''}</div>
    </div>
  `;
}

function AIInsightsCard({ summary, recommendations = [] }) {
  const items = recommendations.slice(0, 3);
  return `
    ${SectionContainer({
    eyebrow: 'AI Decision Layer',
    title: currentMode === 'simple' ? 'What This Means' : 'AI Executive Summary',
    subtitle: currentMode === 'simple' ? 'Simple language overview with practical next steps.' : 'Top narrative and actionable recommendations from the model.',
    accent: true,
    body: `
      <p class="text-sm leading-6 text-slate-200">${esc(summary || '-')}</p>
      <div class="mt-4 space-y-2">
        ${(items.length ? items : ['No recommendations yet.']).map((rec, idx) => `
          <div class="rounded-xl border border-cyan-400/30 bg-cyan-400/10 p-3 text-sm text-cyan-100">
            <p class="text-[11px] uppercase tracking-wide text-cyan-300">Recommendation ${idx + 1}</p>
            <p class="mt-1">${esc(rec)}</p>
          </div>
        `).join('')}
      </div>
    `
  })}
  `;
}

function ComplianceCard({ ok, violations = [] }) {
  const severityClass = {
    high: 'bg-red-500/20 text-red-300 border-red-400/40',
    medium: 'bg-amber-500/20 text-amber-300 border-amber-400/40',
    low: 'bg-green-500/20 text-green-300 border-green-400/40'
  };
  return `
    ${violations.length ? violations.map((item) => {
    const sev = String(item?.severity || 'low').toLowerCase();
    return `
        <div class="rounded-xl border border-slate-700 bg-slate-900/70 p-3">
          <div class="flex items-center justify-between gap-2">
            <p class="text-xs uppercase tracking-wide text-slate-400">${esc(item.rule || 'rule')}</p>
            <span class="rounded-full border px-2 py-0.5 text-[10px] font-semibold ${severityClass[sev] || severityClass.low}">${esc(sev)}</span>
          </div>
          <p class="mt-1 text-sm">${esc(item.message || '')}</p>
        </div>
      `;
  }).join('') : `<p class="text-sm ${ok ? 'text-green-400' : 'text-slate-300'}">${ok ? 'No violations under the selected profile.' : 'No detailed violations were returned.'}</p>`}
  `;
}

function setMode(mode) {
  currentMode = mode;
  els.advancedModeBtn.className = mode === 'advanced' ? 'mode-btn mode-btn-active' : 'mode-btn';
  els.simpleModeBtn.className = mode === 'simple' ? 'mode-btn mode-btn-active' : 'mode-btn';

  if (latestResult) {
    renderAll(latestResult);
  }
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
    <button type="button" class="remove-btn col-span-2 rounded-xl bg-slate-700 px-2 py-2 text-sm hover:bg-slate-600">Remove</button>
  `;
  row.querySelector('.ticker-input').value = item.ticker || '';
  row.querySelector('.weight-input').value = item.weight ? (item.weight * 100).toFixed(1) : '';
  row.querySelector('.remove-btn').addEventListener('click', () => {
    row.remove();
    updateWeightSummary();
    renderEditorPreview();
  });
  row.querySelector('.ticker-input').addEventListener('input', onEditorChange);
  row.querySelector('.weight-input').addEventListener('input', onEditorChange);
  els.portfolioRows.appendChild(row);
}

function onEditorChange() {
  updateWeightSummary();
  renderEditorPreview();
}

function loadSamplePortfolio() {
  const scenarioKey = els.sampleScenarioSelect?.value || 'diversified_multi_sector';
  const samplePortfolio = SAMPLE_SCENARIOS[scenarioKey] || SAMPLE_SCENARIOS.diversified_multi_sector;
  els.portfolioRows.innerHTML = '';
  samplePortfolio.forEach(createRow);
  updateWeightSummary();
  renderEditorPreview();
  addLog(`Loaded sample scenario: ${scenarioKey.replace(/_/g, ' ')}`, 'info');
}

function ensurePortfolioRows() {
  if (els.portfolioRows && !els.portfolioRows.children.length) {
    loadSamplePortfolio();
  }
}

function updateWeightSummary() {
  const total = Array.from(document.querySelectorAll('.weight-input'))
    .map((i) => parseFloat(i.value) || 0)
    .reduce((a, b) => a + b, 0);
  els.weightSummary.textContent = `Total: ${total.toFixed(1)}%`;
  els.weightSummary.className = `rounded-xl border px-3 py-2 text-sm ${Math.abs(total - 100) <= 2 ? 'border-green-400 text-green-400' : 'border-red-400 text-red-400'}`;
}

function getEditorPortfolio() {
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

function getPayload() {
  ensurePortfolioRows();
  const portfolio = getEditorPortfolio().map((item) => ({
    ticker: item.ticker,
    weight: Number(item.weight.toFixed(4))
  }));
  if (!portfolio.length) {
    throw new Error('Add at least one portfolio row.');
  }
  const total = portfolio.reduce((sum, p) => sum + p.weight, 0);
  if (Math.abs(total - 1) > 0.02) {
    throw new Error(`Weights sum to ${(total * 100).toFixed(1)}% and must be near 100%.`);
  }
  return {
    portfolio,
    analysis_config: {
      benchmark: els.benchmarkInput.value,
      risk_profile: els.riskProfileSelect.value,
      mode: currentMode,
      stress_test: els.stressToggle.checked,
      compliance_rules: {}
    }
  };
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
    'BRK-B': 'Financials',
    JPM: 'Financials',
    XOM: 'Energy',
    JNJ: 'Healthcare',
    PFE: 'Healthcare',
    MRK: 'Healthcare',
    ABBV: 'Healthcare',
    LLY: 'Healthcare',
    PG: 'Consumer Staples',
    KO: 'Consumer Staples',
    SPY: 'ETF',
    '^NSEI': 'Index'
  };
  return map[ticker] || 'Unclassified';
}

function destroyChart(name) {
  if (charts[name]) {
    charts[name].destroy();
    delete charts[name];
  }
}

function makeChart(id, config) {
  destroyChart(id);
  const canvas = document.getElementById(id);
  if (!canvas) return;
  charts[id] = new Chart(canvas, config);
}

function setChartLoadingState(isLoading) {
  document.querySelectorAll('.chart-frame').forEach((frame) => {
    frame.classList.toggle('is-loading', isLoading);
  });
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
      ? 'bg-green-400/20 text-green-300 border-green-400/60'
      : state === 'running'
        ? 'bg-cyan-400/20 text-cyan-300 border-cyan-400/60'
        : state === 'error'
          ? 'bg-red-400/20 text-red-300 border-red-400/60'
          : 'bg-slate-900 text-slate-400 border-slate-700';
    return `<div class="rounded-lg border px-2 py-1 ${tone}"><p class="text-[10px] uppercase tracking-wide">${agent}</p><p class="font-medium">${state}</p></div>`;
  }).join('');
}

function updateProgress() {
  const pct = Math.round((completedAgents.size / AGENTS.length) * 100);
  els.progressBar.style.width = `${pct}%`;
  els.progressLabel.textContent = `${pct}%`;
}

function updateKpiText() {
  const simple = currentMode === 'simple';
  els.cardVolatilityLabel.textContent = simple ? 'Price Swings' : 'Volatility';
  els.cardSharpeLabel.textContent = simple ? 'Risk vs Reward' : 'Sharpe Ratio';
  els.cardVarLabel.textContent = simple ? 'Worst Expected Loss' : 'VaR 95%';
  els.cardAlphaLabel.textContent = simple ? 'Beating the Market' : 'Alpha';
}

function recommendationForMetric(metric, value) {
  switch (metric) {
    case 'return':
      if (value == null) return 'Run analysis to understand total gains.';
      if (value >= 0.18) return 'Strong performance; protect gains with periodic rebalance.';
      if (value >= 0.08) return 'Healthy return; keep monitoring benchmark spread.';
      return 'Return is soft; review allocation and risk budget.';
    case 'volatility':
      if (value == null) return 'No volatility signal yet.';
      if (value >= 0.3) return 'High turbulence; reduce concentration or hedge exposure.';
      if (value >= 0.2) return 'Moderate swings; monitor downside scenarios.';
      return 'Stable volatility profile.';
    case 'sharpe':
      if (value == null) return 'Risk-adjusted quality pending.';
      if (value >= 1.2) return 'Strong risk-adjusted return.';
      if (value >= 0.8) return 'Acceptable risk-adjusted return.';
      return 'Risk-adjusted return is weak; tighten portfolio quality.';
    case 'var':
      if (value == null) return 'No downside estimate yet.';
      if (Math.abs(value) >= 0.1) return 'Tail-loss risk is elevated; size positions conservatively.';
      if (Math.abs(value) >= 0.06) return 'Manageable downside with periodic stress checks.';
      return 'Contained downside risk.';
    case 'alpha':
      if (value == null) return 'Benchmark comparison pending.';
      if (value > 0.02) return 'Portfolio is beating the benchmark.';
      if (value >= -0.01) return 'Portfolio is tracking the benchmark closely.';
      return 'Portfolio is lagging benchmark; reassess exposures.';
    default:
      return '';
  }
}

function renderCompositionInsights(normalized) {
  const concentration = normalized?.risk_insights?.concentration || {};
  const top3 = concentration?.top3_weight;
  const largestSector = concentration?.largest_sector;
  const badges = [];

  if (largestSector?.sector) {
    badges.push(`Tech heavy`.replace('Tech', largestSector.sector));
  }
  if (top3 != null) {
    badges.push(`Top 3 = ${(top3 * 100).toFixed(0)}%`);
  }

  const html = badges.length
    ? badges.map((item) => `<span class="rounded-full border border-slate-600 bg-slate-900/70 px-2 py-1 text-slate-300">${esc(item)}</span>`).join('')
    : '<span class="rounded-full border border-slate-700 bg-slate-900/70 px-2 py-1 text-slate-400">Composition insights available after analysis.</span>';

  if (els.compositionInsights) {
    els.compositionInsights.innerHTML = html;
  }
}

function chartAxisOptions(maxTicks = 8) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { ticks: { color: '#94a3b8', maxTicksLimit: maxTicks }, grid: { color: '#334155' } },
      y: { ticks: { color: '#cbd5e1' }, grid: { color: '#334155' } }
    },
    plugins: {
      legend: { labels: { color: '#e2e8f0' } },
      tooltip: {
        backgroundColor: '#0f172a',
        titleColor: '#e2e8f0',
        bodyColor: '#cbd5e1',
        borderColor: '#334155',
        borderWidth: 1
      }
    }
  };
}

function renderOverview(normalized) {
  updateKpiText();
  const risk = normalized?.risk || {};
  const portfolio = risk?.portfolio || {};
  const benchmark = normalized?.benchmark || normalized?.performance?.benchmark || {};

  els.cardTotalReturn.textContent = fmtPct(portfolio.cumulative_return);
  els.cardVolatility.textContent = fmtPct(portfolio.volatility);
  els.cardSharpe.textContent = fmtNum(portfolio.sharpe);
  els.cardVar.textContent = fmtPct(portfolio.var_95);
  els.cardAlpha.textContent = fmtPct(benchmark.alpha ?? portfolio.alpha);

  els.cardTotalReturn.className = `kpi-value ${cardTone(portfolio.cumulative_return)}`;
  els.cardVolatility.className = 'kpi-value text-slate-200';
  els.cardSharpe.className = `kpi-value ${cardTone(portfolio.sharpe)}`;
  els.cardVar.className = 'kpi-value text-red-400';
  els.cardAlpha.className = `kpi-value ${cardTone(benchmark.alpha ?? portfolio.alpha)}`;

  els.cardReturnContext.textContent = benchmark.cumulative_return == null
    ? recommendationForMetric('return', portfolio.cumulative_return)
    : `${benchmark.symbol || 'Benchmark'} returned ${fmtPct(benchmark.cumulative_return)}. ${recommendationForMetric('return', portfolio.cumulative_return)}`;
  els.cardVolatilityContext.textContent = currentMode === 'simple'
    ? `${recommendationForMetric('volatility', portfolio.volatility)} Higher means bumpier price moves.`
    : `${recommendationForMetric('volatility', portfolio.volatility)} 30d ${fmtPct(portfolio?.rolling_volatility_latest?.['30d'])} · 90d ${fmtPct(portfolio?.rolling_volatility_latest?.['90d'])}`;
  els.cardSharpeContext.textContent = currentMode === 'simple'
    ? `${recommendationForMetric('sharpe', portfolio.sharpe)} Higher means better reward for the risk.`
    : `${recommendationForMetric('sharpe', portfolio.sharpe)} 30d ${fmtNum(portfolio?.rolling_sharpe_latest?.['30d'])} · 90d ${fmtNum(portfolio?.rolling_sharpe_latest?.['90d'])}`;
  els.cardVarContext.textContent = currentMode === 'simple'
    ? `${recommendationForMetric('var', portfolio.var_95)} Estimated bad-case loss in a tough market.`
    : `${recommendationForMetric('var', portfolio.var_95)} Max drawdown ${fmtPct(portfolio.max_drawdown)}`;
  els.cardAlphaContext.textContent = benchmark.symbol
    ? `${recommendationForMetric('alpha', benchmark.alpha ?? portfolio.alpha)} Against ${benchmark.symbol}`
    : recommendationForMetric('alpha', benchmark.alpha ?? portfolio.alpha);

  renderTopCards(normalized);
  renderRollingMetrics(normalized);
  renderCharacteristics(normalized);
  renderCompositionInsights(normalized);
}

function syncSummaryPanelHeights() {
  if (!els.portfolioSummaryCard || !els.aiSummaryCard) return;

  if (window.innerWidth < 1024) {
    els.aiSummaryCard.style.maxHeight = '';
    els.aiSummaryCard.style.overflowY = '';
    return;
  }

  const summaryHeight = els.portfolioSummaryCard.offsetHeight;
  if (!summaryHeight) return;

  els.aiSummaryCard.style.maxHeight = `${summaryHeight}px`;
  els.aiSummaryCard.style.overflowY = 'auto';
}

function queueSummaryHeightSync() {
  if (summaryResizeRaf != null) {
    cancelAnimationFrame(summaryResizeRaf);
  }
  summaryResizeRaf = requestAnimationFrame(() => {
    syncSummaryPanelHeights();
    summaryResizeRaf = null;
  });
}

function clearDesktopEqualHeights() {
  document.querySelectorAll('[data-equal-row] [data-equal-card]').forEach((card) => {
    card.style.minHeight = '';
  });
}

function syncDesktopEqualHeights() {
  if (window.innerWidth < 1024) {
    clearDesktopEqualHeights();
    return;
  }

  const rows = document.querySelectorAll('[data-equal-row]');
  rows.forEach((row) => {
    const cards = Array.from(row.querySelectorAll('[data-equal-card]'));
    if (cards.length < 2) return;

    cards.forEach((card) => {
      card.style.minHeight = '';
    });

    const maxHeight = Math.max(...cards.map((card) => card.offsetHeight || 0));
    cards.forEach((card) => {
      card.style.minHeight = `${maxHeight}px`;
    });
  });
}

function queueDesktopEqualHeights() {
  if (equalizeResizeRaf != null) {
    cancelAnimationFrame(equalizeResizeRaf);
  }
  equalizeResizeRaf = requestAnimationFrame(() => {
    syncDesktopEqualHeights();
    equalizeResizeRaf = null;
  });
}

function renderTopCards(normalized) {
  const risk = normalized?.risk || {};
  const portfolio = risk?.portfolio || {};
  const benchmark = normalized?.benchmark || {};
  const concentration = normalized?.risk_insights?.concentration || {};
  const largestHolding = concentration?.largest_holding;
  const largestSector = concentration?.largest_sector;
  const report = normalized?.report || {};

  const riskTag = portfolio?.volatility != null
    ? `${portfolio.volatility >= 0.3 ? 'High' : portfolio.volatility >= 0.2 ? 'Moderate' : 'Low'} Risk`
    : 'Risk N/A';
  const concentrationTag = largestHolding?.weight != null
    ? `${largestHolding.weight >= 0.35 ? 'Concentrated' : 'Balanced'} Holdings`
    : 'Concentration N/A';

  els.portfolioSummaryCard.innerHTML = SectionContainer({
    eyebrow: 'Decision Layer',
    title: 'Portfolio Summary',
    subtitle: 'Return, benchmark spread, and concentration diagnostics for faster decisions.',
    body: `
      <div class="flex flex-col gap-3">
        ${KPICard({ label: 'Portfolio Return', value: fmtPct(portfolio.cumulative_return), context: 'Total cumulative return', toneClass: cardTone(portfolio.cumulative_return) })}
        ${KPICard({ label: 'Benchmark Alpha', value: fmtPct(benchmark.alpha), context: benchmark.symbol ? `Relative to ${benchmark.symbol}` : 'Relative performance', toneClass: cardTone(benchmark.alpha) })}
        ${KPICard({ label: 'Largest Holding', value: largestHolding ? `${largestHolding.ticker}` : '-', context: largestHolding ? fmtPct(largestHolding.weight) : '-', toneClass: 'text-slate-100' })}
      </div>
      <div class="mt-3 flex flex-wrap gap-2 text-xs">
        <span class="rounded-full px-2 py-1 ${riskTone(portfolio.volatility)}">${portfolio.volatility >= 0.3 ? '🔴 High Risk' : portfolio.volatility >= 0.2 ? '🟡 Moderate Risk' : '🟢 Controlled Risk'}</span>
        <span class="rounded-full px-2 py-1 ${concentrationTone(largestHolding?.weight)}">${largestHolding?.weight >= 0.35 ? '🟡 Concentrated' : '🟢 Diversified'}</span>
        <span class="rounded-full bg-slate-700 px-2 py-1 text-slate-200">${esc(riskTag)} | ${esc(concentrationTag)}</span>
        <span class="rounded-full bg-slate-700 px-2 py-1 text-slate-200">Largest sector: ${esc(largestSector?.sector || '-')}</span>
      </div>
    `
  });

  const summary = currentMode === 'simple' ? (report.simple_summary || report.summary) : report.summary;
  const recommendations = report.recommendations || [];
  els.aiSummaryCard.innerHTML = AIInsightsCard({ summary, recommendations });
  queueSummaryHeightSync();
  queueDesktopEqualHeights();
}

function renderRollingMetrics(normalized) {
  const portfolio = normalized?.risk?.portfolio || {};
  const drawdownSummary = normalized?.risk_insights?.drawdown_summary || {};
  const topRisky = (normalized?.risk_contribution || []).slice(0, 3);

  const body = `
    <div class="grid grid-cols-2 gap-3">
      ${KPICard({ label: currentMode === 'simple' ? 'Price Swings (30d)' : 'Rolling Vol 30d', value: fmtPct(portfolio?.rolling_volatility_latest?.['30d']), context: 'Recent volatility', toneClass: 'text-slate-200' })}
      ${KPICard({ label: currentMode === 'simple' ? 'Price Swings (90d)' : 'Rolling Vol 90d', value: fmtPct(portfolio?.rolling_volatility_latest?.['90d']), context: 'Longer window', toneClass: 'text-slate-200' })}
      ${KPICard({ label: currentMode === 'simple' ? 'Risk vs Reward (30d)' : 'Rolling Sharpe 30d', value: fmtNum(portfolio?.rolling_sharpe_latest?.['30d']), context: 'Recent risk-adjusted return', toneClass: cardTone(portfolio?.rolling_sharpe_latest?.['30d']) })}
      ${KPICard({ label: currentMode === 'simple' ? 'Risk vs Reward (90d)' : 'Rolling Sharpe 90d', value: fmtNum(portfolio?.rolling_sharpe_latest?.['90d']), context: 'Longer risk-adjusted view', toneClass: cardTone(portfolio?.rolling_sharpe_latest?.['90d']) })}
    </div>
    <div class="mt-4 rounded-xl border border-slate-700 bg-slate-900/60 p-3">
      <p class="text-xs uppercase tracking-wide text-slate-400">Drawdown Snapshot</p>
      <p class="mt-1 text-sm">Max drawdown ${fmtPct(drawdownSummary.max_drawdown)} · Latest drawdown ${fmtPct(drawdownSummary.latest_drawdown)}</p>
    </div>
    <div class="mt-4 rounded-xl border border-slate-700 bg-slate-900/60 p-3">
      <p class="text-xs uppercase tracking-wide text-slate-400">Top 3 Risk Contributors</p>
      <ul class="mt-1 list-disc space-y-1 pl-4 text-sm">
        ${topRisky.length ? topRisky.map((item) => `<li>${esc(item.ticker)} (${fmtPct(item.contribution_percent)})</li>`).join('') : '<li>No data.</li>'}
      </ul>
    </div>
  `;

  els.rollingMetricsPanel.innerHTML = ChartCard({
    title: 'Risk Intelligence: Rolling Metrics',
    subtitle: 'Rolling behavior explains whether risk is improving or compounding.',
    content: body
  });
  queueDesktopEqualHeights();
}

function renderCharacteristics(normalized) {
  const portfolio = normalized?.risk?.portfolio || {};
  const fundamentals = portfolio?.fundamentals || {};
  const characteristics = portfolio?.characteristics || {};
  const sizeWeights = characteristics?.size_weights || {};
  const styleFlags = characteristics?.style_flags || [];

  const growthVsValue = styleFlags.includes('growth_heavy') ? 'Growth Tilt' : 'Balanced / Value Tilt';

  els.characteristicsPanel.innerHTML = SectionContainer({
    eyebrow: 'Portfolio Characteristics',
    title: 'Style and Fundamentals Profile',
    subtitle: 'Interpretation of growth/value bias, income profile, and size exposure.',
    body: `
      <div class="grid gap-3 sm:grid-cols-2">
        ${KPICard({ label: 'Style Bias', value: growthVsValue, context: styleFlags.length ? styleFlags.map(styleFlagLabel).join(', ') : 'No dominant style flag', toneClass: 'text-cyan-300' })}
        ${KPICard({ label: 'Dividend Yield', value: fmtPct(fundamentals.dividend_yield_weighted), context: 'Weighted portfolio yield', toneClass: 'text-slate-200' })}
        ${KPICard({ label: 'Forward PE', value: fmtNum(fundamentals.forward_pe_weighted), context: 'Weighted valuation proxy', toneClass: 'text-slate-200' })}
        ${KPICard({ label: 'Market Cap', value: fundamentals.total_market_cap ? `${(fundamentals.total_market_cap / 1e12).toFixed(2)}T` : '-', context: 'Total covered market cap', toneClass: 'text-slate-200' })}
      </div>
      <div class="mt-4 rounded-xl border border-slate-700 bg-slate-900/60 p-3">
        <p class="text-xs uppercase tracking-wide text-slate-400">Market Cap Distribution</p>
        <div class="mt-2 grid gap-2 text-sm sm:grid-cols-2">
          ${Object.keys(sizeWeights).length
      ? Object.entries(sizeWeights).map(([bucket, weight]) => `
                <div class="rounded-lg border border-slate-700 bg-slate-800/60 px-2 py-1">
                  <span class="text-slate-300">${esc(bucket.replace(/_/g, ' '))}</span>
                  <span class="float-right text-slate-100">${fmtPct(weight)}</span>
                </div>
              `).join('')
      : '<p class="text-slate-400">No market cap distribution available.</p>'}
        </div>
      </div>
    `
  });
  queueDesktopEqualHeights();
}

function renderAllocationChart(portfolio) {
  makeChart('allocationChart', {
    type: 'pie',
    data: {
      labels: portfolio.map((item) => item.ticker),
      datasets: [{ data: portfolio.map((item) => item.weight * 100), backgroundColor: portfolio.map((_, idx) => palette[idx % palette.length]) }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#e2e8f0' } },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#e2e8f0',
          bodyColor: '#cbd5e1',
          borderColor: '#334155',
          borderWidth: 1
        }
      }
    }
  });
}

function renderSectorChart(sectors) {
  const labels = Object.keys(sectors || {});
  const values = Object.values(sectors || {}).map((value) => value * 100);
  makeChart('sectorChart', {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label: 'Weight %', data: values, backgroundColor: '#38bdf8', borderRadius: 8, maxBarThickness: 28 }]
    },
    options: {
      ...chartAxisOptions(6),
      indexAxis: 'y'
    }
  });
}

function renderCumulativeChart(normalized) {
  const performance = normalized?.performance || {};
  const portfolioSeries = performance?.cumulative_returns?.portfolio || performance?.series?.portfolio_cumulative || [];
  const benchmarkSeries = performance?.cumulative_returns?.benchmark || performance?.series?.benchmark_cumulative || [];
  makeChart('cumulativeChart', {
    type: 'line',
    data: {
      labels: portfolioSeries.map((item) => item.date),
      datasets: [
        {
          label: 'Portfolio',
          data: portfolioSeries.map((item) => item.value * 100),
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56,189,248,0.12)',
          tension: 0.2
        },
        {
          label: normalized?.benchmark?.symbol || performance?.benchmark?.symbol || 'Benchmark',
          data: benchmarkSeries.map((item) => item.value * 100),
          borderColor: '#22c55e',
          backgroundColor: 'rgba(34,197,94,0.12)',
          tension: 0.2
        }
      ]
    },
    options: chartAxisOptions(8)
  });
}

function renderDrawdownChart(normalized) {
  const series = normalized?.risk_insights?.series?.drawdown || [];
  makeChart('drawdownChart', {
    type: 'line',
    data: {
      labels: series.map((item) => item.date),
      datasets: [{
        label: 'Drawdown %',
        data: series.map((item) => item.value * 100),
        borderColor: '#ef4444',
        backgroundColor: 'rgba(239,68,68,0.18)',
        fill: true,
        tension: 0.2
      }]
    },
    options: chartAxisOptions(6)
  });
}

function renderRiskContributionChart(normalized) {
  const items = normalized?.risk_contribution || normalized?.risk?.risk_contribution || [];
  makeChart('riskContributionChart', {
    type: 'bar',
    data: {
      labels: items.map((item) => item.ticker),
      datasets: [{
        label: 'Contribution %',
        data: items.map((item) => item.contribution_percent * 100),
        backgroundColor: '#f59e0b'
      }]
    },
    options: chartAxisOptions(6)
  });
}

function correlationColor(value) {
  const abs = Math.abs(Number(value));
  const red = Math.round(239 * abs + 34 * (1 - abs));
  const green = Math.round(68 * abs + 197 * (1 - abs));
  return `rgba(${red},${green},80,0.9)`;
}

function renderCorrelationGrid(normalized) {
  const matrix = normalized?.correlation_matrix || normalized?.risk_insights?.correlation_matrix || {};
  const labels = matrix.labels || [];
  const values = matrix.values || [];
  if (!labels.length || !values.length) {
    if (els.correlationSummary) {
      els.correlationSummary.innerHTML = '<div class="rounded-xl border border-slate-700 bg-slate-900/60 p-3 text-sm text-slate-400 md:col-span-3">Correlation summary will appear after analysis.</div>';
    }
    els.correlationGrid.innerHTML = '<p class="text-sm text-slate-400">Correlation data unavailable.</p>';
    els.correlationHighlights.innerHTML = '';
    return;
  }

  const offDiagonal = [];
  values.forEach((row, i) => {
    row.forEach((value, j) => {
      if (i !== j) offDiagonal.push(Number(value));
    });
  });
  const avgCorrelation = offDiagonal.length
    ? offDiagonal.reduce((sum, val) => sum + val, 0) / offDiagonal.length
    : null;

  let html = `<div class="inline-grid min-w-full gap-0.5" style="grid-template-columns: 88px repeat(${labels.length}, minmax(42px, 1fr));">`;
  html += '<div></div>' + labels.map((label) => `<div class="px-1 py-0.5 text-center text-[10px] text-slate-400">${esc(label)}</div>`).join('');
  labels.forEach((rowLabel, rowIndex) => {
    html += `<div class="px-1 py-0.5 text-[10px] text-slate-400">${esc(rowLabel)}</div>`;
    values[rowIndex].forEach((value) => {
      html += `<div class="flex h-9 items-center justify-center rounded-md text-[10px] font-semibold text-white transition-transform" style="background:${correlationColor(value)}" title="Correlation ${Number(value).toFixed(2)}">${Number(value).toFixed(2)}</div>`;
    });
  });
  html += '</div>';
  els.correlationGrid.innerHTML = html;

  const strong = matrix.strong_pairs || [];
  const weak = matrix.weak_pairs || [];

  if (els.correlationSummary) {
    const summaryCards = [
      {
        title: 'Average Correlation',
        value: fmtSigned(avgCorrelation),
        context: avgCorrelation == null
          ? 'Not enough data yet.'
          : avgCorrelation >= 0.6
            ? 'High co-movement across holdings.'
            : avgCorrelation >= 0.35
              ? 'Moderate co-movement level.'
              : 'Good diversification potential.'
      },
      {
        title: 'Most Correlated Pair',
        value: strong.length ? `${strong[0].left} / ${strong[0].right}` : '-',
        context: strong.length ? `Corr ${fmtNum(strong[0].value)}` : 'No strong pair above threshold.'
      },
      {
        title: 'Diversifying Pair',
        value: weak.length ? `${weak[0].left} / ${weak[0].right}` : '-',
        context: weak.length ? `Corr ${fmtNum(weak[0].value)}` : 'No weak pair below threshold.'
      }
    ];

    els.correlationSummary.innerHTML = summaryCards.map((card) => `
      <div class="rounded-xl border border-slate-700 bg-slate-900/60 p-2">
        <p class="text-[11px] uppercase tracking-[0.14em] text-slate-400">${esc(card.title)}</p>
        <p class="mt-1 text-sm font-semibold text-slate-100">${esc(card.value)}</p>
        <p class="mt-1 text-xs text-slate-400">${esc(card.context)}</p>
      </div>
    `).join('');
  }

  els.correlationHighlights.innerHTML = `
    <div class="rounded-xl border border-red-400/30 bg-red-500/10 p-2">
      <p class="mb-1 text-xs uppercase tracking-wide text-red-300">High Correlation</p>
      <p>${strong.length ? `${esc(strong[0].left)} / ${esc(strong[0].right)} at ${fmtNum(strong[0].value)}` : 'No pair above 0.80.'}</p>
    </div>
    <div class="rounded-xl border border-green-400/30 bg-green-500/10 p-2">
      <p class="mb-1 text-xs uppercase tracking-wide text-green-300">Diversifying Pair</p>
      <p>${weak.length ? `${esc(weak[0].left)} / ${esc(weak[0].right)} at ${fmtNum(weak[0].value)}` : 'No pair below 0.30.'}</p>
    </div>
  `;
}

function renderCompliance(normalized) {
  const compliance = normalized?.compliance || {};
  const ok = Boolean(compliance.ok);
  els.complianceBadge.className = `mb-2 inline-flex rounded-full px-3 py-1 text-xs font-semibold ${ok ? 'bg-green-400/20 text-green-300' : 'bg-red-400/20 text-red-300'}`;
  els.complianceBadge.textContent = ok ? 'PASS' : 'FAIL';
  const violations = compliance.violations || [];
  els.complianceViolations.innerHTML = ComplianceCard({ ok, violations });
  queueDesktopEqualHeights();
}

function renderInsights(normalized) {
  const report = normalized?.report || normalized?.insights || {};
  if (!report || typeof report !== 'object') {
    els.insightsPanel.innerHTML = '<p class="text-slate-400">No insight data.</p>';
    return;
  }
  const useSimple = currentMode === 'simple';
  const summary = useSimple ? (report.simple_summary || report.summary) : report.summary;
  const insights = useSimple ? (report.simple_insights || report.key_insights || []) : (report.key_insights || []);
  const explanations = report.explanations || {};
  const keys = ['volatility', 'sharpe', 'var', 'alpha', 'concentration'];

  const explanationHtml = keys.map((key) => {
    const item = explanations[key];
    if (!item) return '';
    const content = typeof item === 'object' ? (useSimple ? item.simple : item.advanced) : item;
    return `
      <div class="rounded-xl border border-slate-700 bg-slate-900/70 p-3">
        <p class="text-xs uppercase tracking-wide text-slate-400">${esc(key.replace('_', ' '))}</p>
        <p class="mt-1">${esc(content)}</p>
      </div>
    `;
  }).join('');

  els.insightsPanel.innerHTML = `
    <div>
      <p class="mb-1 text-xs uppercase tracking-wide text-slate-400">Summary</p>
      <p>${esc(summary || '-')}</p>
    </div>
    <div>
      <p class="mb-1 text-xs uppercase tracking-wide text-slate-400">Key Insights</p>
      <ul class="list-disc space-y-1 pl-4">${(insights || []).map((item) => `<li>${esc(item)}</li>`).join('') || '<li>-</li>'}</ul>
    </div>
    <div>
      <p class="mb-1 text-xs uppercase tracking-wide text-slate-400">Risks</p>
      <ul class="list-disc space-y-1 pl-4">${(report.risks || []).map((item) => `<li>${esc(item)}</li>`).join('') || '<li>-</li>'}</ul>
    </div>
    <div>
      <p class="mb-1 text-xs uppercase tracking-wide text-slate-400">Opportunities</p>
      <ul class="list-disc space-y-1 pl-4">${(report.opportunities || []).map((item) => `<li>${esc(item)}</li>`).join('') || '<li>-</li>'}</ul>
    </div>
    <div class="rounded-xl border border-cyan-400/40 bg-cyan-400/10 p-3">
      <p class="mb-1 text-xs uppercase tracking-wide text-cyan-300">Recommendations</p>
      <ul class="list-disc space-y-1 pl-4">${(report.recommendations || []).map((item) => `<li>${esc(item)}</li>`).join('') || '<li>-</li>'}</ul>
    </div>
    <div class="grid gap-2">${explanationHtml}</div>
  `;
}

function renderAll(result) {
  latestResult = result?.aggregation || result || {};
  renderOverview(latestResult);
  renderAllocationChart(latestResult.portfolio || getEditorPortfolio());
  renderSectorChart(latestResult.compliance?.sectors || {});
  renderCumulativeChart(latestResult);
  renderDrawdownChart(latestResult);
  renderRiskContributionChart(latestResult);
  renderCorrelationGrid(latestResult);
  renderCompliance(latestResult);
  renderInsights(latestResult);
  queueSummaryHeightSync();
  queueDesktopEqualHeights();
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    window.lucide.createIcons();
  }
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
      renderOverview({ risk: data.result, benchmark: data.result.benchmark, performance: data.result.performance, risk_insights: data.result.risk_insights, risk_contribution: data.result.risk_contribution });
      renderCumulativeChart({ performance: data.result.performance, benchmark: data.result.benchmark });
      renderDrawdownChart({ risk_insights: data.result.risk_insights });
      renderRiskContributionChart({ risk_contribution: data.result.risk_contribution });
      renderCorrelationGrid({ correlation_matrix: data.result.correlation_matrix });
      renderCompositionInsights({ risk_insights: data.result.risk_insights });
    }
    if (agent === 'compliance' && data.result) {
      renderCompliance({ compliance: data.result });
      renderSectorChart(data.result.sectors || {});
    }
    if (agent === 'reporting' && data.result) {
      renderInsights({ report: data.result, insights: data.result });
      renderTopCards({ report: data.result, benchmark: latestResult?.benchmark || {}, risk: latestResult?.risk || {}, risk_insights: latestResult?.risk_insights || {} });
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
    addLog('Aggregation complete', 'done');
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

function setCollapseState(panel, open) {
  if (panel === 'ai') {
    isAiReportOpen = open;
    els.insightsPanel.classList.toggle('hidden', !open);
    els.aiReportChevron.textContent = open ? 'Collapse' : 'Expand';
  }
  if (panel === 'activity') {
    isActivityOpen = open;
    els.activitySectionBody.classList.toggle('hidden', !open);
    els.activityChevron.textContent = open ? 'Collapse' : 'Expand';
  }
  if (panel === 'correlation') {
    isCorrelationOpen = open;
    els.correlationBody.classList.toggle('hidden', !open);
    if (els.correlationToggleLabel) {
      els.correlationToggleLabel.textContent = open ? 'Hide Correlation Matrix' : 'Show Correlation Matrix';
    }
    els.correlationChevron.textContent = open ? 'Collapse' : 'Expand';
  }
}

function wireCollapseEvents() {
  els.aiReportToggle?.addEventListener('click', () => {
    setCollapseState('ai', !isAiReportOpen);
  });
  els.activityToggle?.addEventListener('click', () => {
    setCollapseState('activity', !isActivityOpen);
  });
  els.correlationToggle?.addEventListener('click', () => {
    setCollapseState('correlation', !isCorrelationOpen);
  });
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
  setChartLoadingState(true);

  try {
    const response = await fetch('/analyze/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      throw new Error(`Server error ${response.status}: ${await response.text()}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split('\n\n');
      buffer = chunks.pop() || '';
      for (const chunk of chunks) {
        let event = 'message';
        let data = '';
        chunk.split('\n').forEach((line) => {
          if (line.startsWith('event: ')) event = line.slice(7).trim();
          if (line.startsWith('data: ')) data = line.slice(6);
        });
        if (data) handleEvent(event, JSON.parse(data));
      }
    }

    const resultsResponse = await fetch('/results');
    if (resultsResponse.ok) {
      const result = await resultsResponse.json();
      renderAll(result);
    }
  } catch (err) {
    setStatus(`Error: ${err.message}`, 'warn');
    addLog('Analysis request failed', 'error', err.message);
  } finally {
    setChartLoadingState(false);
    els.analyzeBtn.disabled = false;
  }
}

async function testGemini() {
  setStatus('Checking Gemini...', 'info');
  addLog('Gemini diagnostic started', 'running');
  try {
    const response = await fetch('/debug/gemini');
    const data = await response.json();
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

function renderInitialPanels() {
  els.portfolioSummaryCard.innerHTML = SectionContainer({
    eyebrow: 'Decision Layer',
    title: 'Portfolio Summary',
    subtitle: 'Run analysis to populate return, alpha, and risk flags.',
    body: '<p class="text-sm text-slate-400">No analysis yet.</p>'
  });
  els.aiSummaryCard.innerHTML = AIInsightsCard({
    summary: 'Run analysis to receive an AI-generated executive summary.',
    recommendations: []
  });
  els.rollingMetricsPanel.innerHTML = ChartCard({
    title: 'Risk Intelligence: Rolling Metrics',
    subtitle: 'Volatility and risk-adjusted return windows will appear after analysis.',
    content: '<p class="text-sm text-slate-400">No rolling metrics yet.</p>'
  });
  els.characteristicsPanel.innerHTML = SectionContainer({
    eyebrow: 'Portfolio Characteristics',
    title: 'Style and Fundamentals Profile',
    subtitle: 'Growth/value, dividend profile, and size distribution.',
    body: '<p class="text-sm text-slate-400">No characteristics yet.</p>'
  });
  if (els.compositionInsights) {
    els.compositionInsights.innerHTML = '<span class="rounded-full border border-slate-700 bg-slate-900/70 px-2 py-1 text-slate-400">Composition insights available after analysis.</span>';
  }
  if (els.correlationSummary) {
    els.correlationSummary.innerHTML = '<div class="rounded-xl border border-slate-700 bg-slate-900/60 p-3 text-sm text-slate-400 md:col-span-3">Correlation summary will appear after analysis.</div>';
  }
  queueSummaryHeightSync();
  queueDesktopEqualHeights();
}

function initApp() {
  els.addRowBtn?.addEventListener('click', () => createRow());
  els.sampleBtn?.addEventListener('click', loadSamplePortfolio);
  els.analyzeBtn?.addEventListener('click', runAnalysis);
  els.geminiBtn?.addEventListener('click', testGemini);
  els.advancedModeBtn?.addEventListener('click', () => setMode('advanced'));
  els.simpleModeBtn?.addEventListener('click', () => setMode('simple'));

  wireCollapseEvents();
  setCollapseState('ai', true);
  setCollapseState('activity', true);
  setCollapseState('correlation', false);
  renderInitialPanels();
  resetPipelineUi();
  if (els.sampleScenarioSelect && !els.sampleScenarioSelect.value) {
    els.sampleScenarioSelect.value = 'diversified_multi_sector';
  }
  ensurePortfolioRows();
  updateWeightSummary();
  renderEditorPreview();
  setMode('advanced');
  setChartLoadingState(false);
  window.addEventListener('resize', queueSummaryHeightSync);
  window.addEventListener('resize', queueDesktopEqualHeights);
  queueSummaryHeightSync();
  queueDesktopEqualHeights();

  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    window.lucide.createIcons();
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
