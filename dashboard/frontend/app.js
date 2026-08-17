// Dashboard frontend for the EGX Strategy Lab.
const API = "http://localhost:8000";
const state = {
  assets: [],
  results: null,
  strategyPerformance: null,
  newsSentiment: null,
  chatHistory: [],
  chatOpen: false,
  theme: "dark",
  charts: {},
};

const els = {
  backendBadge: document.getElementById("backendBadge"),
  statusBanner: document.getElementById("statusBanner"),
  assetSelect: document.getElementById("assetSelect"),
  initialCash: document.getElementById("initialCash"),
  fastWindow: document.getElementById("fastWindow"),
  slowWindow: document.getElementById("slowWindow"),
  strategyComparisonChart: document.getElementById("strategyComparisonChart"),
  leaderboardEmptyState: document.getElementById("leaderboardEmptyState"),
  leaderboardContent: document.getElementById("leaderboardContent"),
  leaderboardTableBody: document.getElementById("leaderboardTableBody"),
  leaderboardMetricsChart: document.getElementById("leaderboardMetricsChart"),
  bestTitle: document.getElementById("bestTitle"),
  bestSummary: document.getElementById("bestSummary"),
  bestBadges: document.getElementById("bestBadges"),
  bestChart: document.getElementById("bestChart"),
  bestDrawdownChart: document.getElementById("bestDrawdownChart"),
  tiktokChart: document.getElementById("tiktokChart"),
  referenceEmptyState: document.getElementById("referenceEmptyState"),
  referenceContent: document.getElementById("referenceContent"),
  referenceSource: document.getElementById("referenceSource"),
  referenceSummary: document.getElementById("referenceSummary"),
  referenceTableBody: document.getElementById("referenceTableBody"),
  referenceSeedSummary: document.getElementById("referenceSeedSummary"),
  runBtn: document.getElementById("runBtn"),
  resetBtn: document.getElementById("resetBtn"),
  refreshBtn: document.getElementById("refreshBtn"),
  themeToggle: document.getElementById("themeToggle"),
  kpiRow: document.getElementById("kpiRow"),
  resultsSection: document.getElementById("resultsSection"),
  emptyState: document.getElementById("emptyState"),
  summaryText: document.getElementById("summaryText"),
  summaryBadges: document.getElementById("summaryBadges"),
  positionSnapshot: document.getElementById("positionSnapshot"),
  tradeTableBody: document.getElementById("tradeTableBody"),
  tradeSearch: document.getElementById("tradeSearch"),
  tradeFilter: document.getElementById("tradeFilter"),
  tradeSort: document.getElementById("tradeSort"),
  fullscreenBtn: document.getElementById("fullscreenBtn"),
  downloadBtn: document.getElementById("downloadBtn"),
  sectionSelect: document.getElementById("sectionSelect"),
  newsAssetSelect: document.getElementById("newsAssetSelect"),
  newsFetchBtn: document.getElementById("newsFetchBtn"),
  newsStatusBanner: document.getElementById("newsStatusBanner"),
  newsEmptyState: document.getElementById("newsEmptyState"),
  newsContent: document.getElementById("newsContent"),
  newsPanelTitle: document.getElementById("newsPanelTitle"),
  newsSentimentBadge: document.getElementById("newsSentimentBadge"),
  newsHeadlineList: document.getElementById("newsHeadlineList"),
  newsSummary: document.getElementById("newsSummary"),
  chatFab: document.getElementById("chatFab"),
  chatPanel: document.getElementById("chatPanel"),
  chatCloseBtn: document.getElementById("chatCloseBtn"),
  chatMessages: document.getElementById("chatMessages"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  chatSendBtn: document.getElementById("chatSendBtn"),
};

function setBanner(message, kind = "") {
  els.statusBanner.textContent = message;
  els.statusBanner.className = `status-banner ${kind}`.trim();
}

function setTheme(theme) {
  document.documentElement.classList.toggle("light", theme === "light");
  state.theme = theme;
  els.themeToggle.textContent = theme === "light" ? "🌙 Dark" : "☀️ Light";
}

function setLoading(isLoading) {
  els.runBtn.disabled = isLoading;
}

async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const j = await r.json();
    els.backendBadge.textContent = `backend: ${j.status}`;
    els.backendBadge.className = "badge good";
    setBanner("Backend ready. Select an asset and run a backtest.");
  } catch (e) {
    els.backendBadge.textContent = "backend: offline";
    els.backendBadge.className = "badge bad";
    setBanner("Backend not reachable — start uvicorn on port 8000.", "error");
  }
}

async function loadAssets() {
  try {
    const r = await fetch(`${API}/assets`);
    const j = await r.json();
    state.assets = j.assets || [];
    const options = state.assets.map((asset) => `<option value="${asset}">${asset}</option>`).join("");
    els.assetSelect.innerHTML = options;
    els.newsAssetSelect.innerHTML = options;
  } catch (e) {
    setBanner("Unable to load assets from the backend.", "error");
  }
}

function validateInputs() {
  const initialCash = Number(els.initialCash.value);
  const fastWindow = Number(els.fastWindow.value);
  const slowWindow = Number(els.slowWindow.value);
  if (!Number.isFinite(initialCash) || initialCash <= 0) {
    setBanner("Initial cash must be a positive number.", "error");
    return false;
  }
  if (!Number.isFinite(fastWindow) || fastWindow <= 0) {
    setBanner("Fast MA must be a positive integer.", "error");
    return false;
  }
  if (!Number.isFinite(slowWindow) || slowWindow <= 0) {
    setBanner("Slow MA must be a positive integer.", "error");
    return false;
  }
  if (fastWindow >= slowWindow) {
    setBanner("Fast MA must be smaller than Slow MA.", "error");
    return false;
  }
  return true;
}

async function runBacktest() {
  if (!validateInputs()) return;
  setLoading(true);
  setBanner("Running backtest…");
  try {
    const payload = {
      symbol: els.assetSelect.value,
      initial_cash: Number(els.initialCash.value),
      fast_window: Number(els.fastWindow.value),
      slow_window: Number(els.slowWindow.value),
    };

    const [backtestRes, performanceRes] = await Promise.all([
      fetch(`${API}/backtest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
      fetch(
        `${API}/api/strategy-performance?symbol=${encodeURIComponent(payload.symbol)}&initial_cash=${encodeURIComponent(
          payload.initial_cash,
        )}&fast_window=${encodeURIComponent(payload.fast_window)}&slow_window=${encodeURIComponent(payload.slow_window)}`,
      ),
    ]);

    const backtestResult = await backtestRes.json();
    const strategyPerformance = await performanceRes.json();

    if (!backtestRes.ok) throw new Error(backtestResult.detail || "Backtest failed");
    if (!performanceRes.ok) throw new Error(strategyPerformance.detail || "Strategy performance failed");

    state.results = backtestResult;
    state.strategyPerformance = strategyPerformance;
    renderResults(backtestResult);
    renderStrategyPerformance(strategyPerformance, backtestResult);
    setBanner(`Backtest complete for ${backtestResult.symbol}.`, "success");
  } catch (e) {
    setBanner(e.message || "Backtest failed.", "error");
  } finally {
    setLoading(false);
  }
}

function fmtCurrency(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "EGP", maximumFractionDigits: 2 }).format(value || 0);
}

function fmtPercent(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function getMetricClass(value) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

function renderKpis(result) {
  const metrics = [
    { title: "Final Value", value: fmtCurrency(result.final_value), cls: getMetricClass(result.final_value - result.initial_cash) },
    { title: "P/L", value: fmtCurrency(result.profit_loss), cls: getMetricClass(result.profit_loss) },
    { title: "Return %", value: fmtPercent(result.return_percent), cls: getMetricClass(result.return_percent) },
    { title: "Drawdown", value: fmtCurrency(result.max_drawdown_egp), cls: "negative" },
    { title: "Buy Ops", value: result.buy_count, cls: "neutral" },
    { title: "Sell Ops", value: result.sell_count, cls: "neutral" },
    { title: "Open Pos", value: result.open_position ? "Yes" : "No", cls: result.open_position ? "positive" : "neutral" },
  ];

  els.kpiRow.innerHTML = metrics
    .map((item) => `<article class="metric-card ${item.cls}"><h3>${item.title}</h3><div class="metric-value">${item.value}</div></article>`)
    .join("");
}

function renderSummary(result) {
  els.summaryText.innerHTML = [
    `Buy when ${result.symbol} is above the fast MA and the fast MA is above the slow MA.`,
    `Sell when the fast MA falls below the slow MA.`,
    `Starting cash: ${fmtCurrency(result.initial_cash)}`,
    `Selected asset: ${result.symbol}`,
    `Position remains open at the end: ${result.open_position ? "Yes" : "No"}`,
  ].map((line) => `<div>${line}</div>`).join("");

  const lastTrade = result.trades?.[result.trades.length - 1];
  els.summaryBadges.innerHTML = `
    <span class="pill">${result.return_percent > 0 ? "Positive" : result.return_percent < 0 ? "Loss" : "Neutral"}</span>
    <span class="pill">${result.open_position ? "Open Position" : "Flat Position"}</span>
  `;

  els.positionSnapshot.innerHTML = `
    <div><strong>Last Trade</strong><br />${lastTrade ? `${lastTrade.operation} · ${lastTrade.date}` : "None yet"}</div>
    <div><strong>Current Position</strong><br />${result.remaining_shares > 0 ? `${result.remaining_shares} shares` : "No open shares"}</div>
  `;
}

function destroyCharts() {
  Object.values(state.charts).forEach((chart) => chart.destroy());
  state.charts = {};
}

function destroyStrategyCharts() {
  ["strategyComparison", "leaderboardMetrics", "best", "bestDrawdown", "tiktok"].forEach((key) => {
    if (state.charts[key]) {
      state.charts[key].destroy();
      delete state.charts[key];
    }
  });
}

function initSectionSwitcher() {
  const pages = document.querySelectorAll(".tab-page");
  els.sectionSelect.addEventListener("change", () => {
    const target = els.sectionSelect.value;
    pages.forEach((page) => {
      page.hidden = page.dataset.tabPage !== target;
    });
    // Charts created while their section was hidden measure a zero-size canvas;
    // force a re-measure now that the section is visible.
    requestAnimationFrame(() => {
      Object.values(state.charts).forEach((chart) => chart.resize());
    });
  });
}

function buildTooltipLabel(context) {
  const item = context[0];
  if (!item) return "";
  const index = item.dataIndex;
  const date = state.results?.dates?.[index];
  const price = state.results?.prices?.[index];
  const fastMa = state.results?.fast_ma?.[index];
  const slowMa = state.results?.slow_ma?.[index];
  const portfolio = state.results?.portfolio_values?.[index];
  const trade = state.results?.trades?.find((entry) => entry.date === date);
  const rows = [
    `Date: ${date}`,
    `Price: ${fmtCurrency(price)}`,
    `MA9: ${fastMa != null ? fmtCurrency(fastMa) : "n/a"}`,
    `MA20: ${slowMa != null ? fmtCurrency(slowMa) : "n/a"}`,
    `Portfolio: ${fmtCurrency(portfolio)}`,
  ];
  if (trade) rows.push(`Trade: ${trade.operation}`);
  return rows.join("\n");
}

function renderCharts(result) {
  destroyCharts();
  const labels = result.dates || [];
  const priceCtx = document.getElementById("priceChart").getContext("2d");
  const portfolioCtx = document.getElementById("portfolioChart").getContext("2d");
  const drawdownCtx = document.getElementById("drawdownChart").getContext("2d");

  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { labels: { color: getComputedStyle(document.documentElement).getPropertyValue("--muted").trim(), boxWidth: 10, usePointStyle: true } },
      tooltip: { enabled: true, backgroundColor: "rgba(7, 12, 24, 0.92)", titleColor: "#fff", bodyColor: "#fff", borderColor: "rgba(255,255,255,0.1)", borderWidth: 1, padding: 10, displayColors: false, callbacks: { label: () => "" , title: (items) => buildTooltipLabel(items) } },
    },
    scales: {
      x: { grid: { color: "rgba(255,255,255,0.06)" }, ticks: { color: getComputedStyle(document.documentElement).getPropertyValue("--muted").trim(), maxTicksLimit: 8 } },
      y: { grid: { color: "rgba(255,255,255,0.06)" }, ticks: { color: getComputedStyle(document.documentElement).getPropertyValue("--muted").trim() } },
    },
  };

  const buyPoints = [];
  const sellPoints = [];
  (result.trades || []).forEach((trade) => {
    const index = labels.indexOf(trade.date);
    if (index >= 0) {
      if (trade.operation === "BUY") buyPoints.push({ x: index, y: trade.price });
      else sellPoints.push({ x: index, y: trade.price });
    }
  });

  state.charts.price = new Chart(priceCtx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Close",
          data: result.prices,
          borderColor: "#6f7dff",
          backgroundColor: "rgba(111,125,255,0.15)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.35,
          cubicInterpolationMode: "monotone",
        },
        {
          label: "MA9",
          data: result.fast_ma,
          borderColor: "#35d7a8",
          borderWidth: 1.6,
          pointRadius: 0,
          tension: 0.35,
          cubicInterpolationMode: "monotone",
        },
        {
          label: "MA20",
          data: result.slow_ma,
          borderColor: "#ffc36b",
          borderWidth: 1.4,
          pointRadius: 0,
          tension: 0.35,
          cubicInterpolationMode: "monotone",
        },
        {
          label: "Buy",
          data: buyPoints,
          showLine: false,
          pointRadius: 4,
          pointStyle: "circle",
          pointBackgroundColor: "#35d7a8",
          pointBorderColor: "#35d7a8",
        },
        {
          label: "Sell",
          data: sellPoints,
          showLine: false,
          pointRadius: 4,
          pointStyle: "circle",
          pointBackgroundColor: "#ff6474",
          pointBorderColor: "#ff6474",
        },
      ],
    },
    options: { ...baseOptions, plugins: { ...baseOptions.plugins, legend: { ...baseOptions.plugins.legend, position: "bottom" } } },
  });

  state.charts.portfolio = new Chart(portfolioCtx, {
    type: "line",
    data: {
      labels,
      datasets: [{ label: "Portfolio", data: result.portfolio_values, borderColor: "#6f7dff", backgroundColor: "rgba(111,125,255,0.12)", borderWidth: 2, fill: false, tension: 0.35, pointRadius: 0 }],
    },
    options: baseOptions,
  });

  state.charts.drawdown = new Chart(drawdownCtx, {
    type: "line",
    data: {
      labels,
      datasets: [{ label: "Drawdown", data: result.drawdown_values, borderColor: "#ff6474", backgroundColor: "rgba(255,100,116,0.16)", fill: true, borderWidth: 2, tension: 0.25, pointRadius: 0 }],
    },
    options: baseOptions,
  });
}

function filterTrades(result) {
  const query = els.tradeSearch.value.trim().toLowerCase();
  const mode = els.tradeFilter.value;
  const sortMode = els.tradeSort.value;
  const trades = (result.trades || []).filter((trade) => {
    const matchesText = [trade.date, trade.operation, trade.price, trade.shares].join(" ").toLowerCase().includes(query);
    const matchesMode = mode === "ALL" || trade.operation === mode;
    return matchesText && matchesMode;
  });
  trades.sort((a, b) => {
    const aDate = new Date(a.date);
    const bDate = new Date(b.date);
    return sortMode === "newest" ? bDate - aDate : aDate - bDate;
  });
  return trades;
}

function renderTrades(result) {
  const trades = filterTrades(result);
  els.tradeTableBody.innerHTML = trades.length
    ? trades.map((trade) => `<tr><td>${trade.date}</td><td><span class="badge-${trade.operation.toLowerCase()}">${trade.operation}</span></td><td>${fmtCurrency(trade.price)}</td><td>${trade.shares}</td><td>${fmtCurrency(trade.portfolio_value)}</td></tr>`).join("")
    : '<tr><td colspan="5">No trades match the current filters.</td></tr>';
}

function renderResults(result) {
  els.resultsSection.hidden = false;
  els.emptyState.hidden = true;
  renderKpis(result);
  renderSummary(result);
  renderCharts(result);
  renderTrades(result);
}

async function loadNewsSentiment(symbol) {
  if (!symbol) return;
  els.newsFetchBtn.disabled = true;
  els.newsStatusBanner.textContent = `Fetching latest news for ${symbol}…`;
  els.newsStatusBanner.className = "status-banner";
  els.newsEmptyState.hidden = true;
  els.newsContent.hidden = false;
  els.newsSentimentBadge.textContent = "loading…";
  els.newsSentimentBadge.className = "pill pill--neutral";
  els.newsHeadlineList.innerHTML = "";
  els.newsSummary.textContent = "";
  els.newsPanelTitle.textContent = `📰 Latest News & Sentiment — ${symbol}`;

  try {
    const r = await fetch(`${API}/api/news-sentiment?symbol=${encodeURIComponent(symbol)}`);
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "News sentiment failed");
    state.newsSentiment = data;
    renderNewsSentiment(data);
    els.newsStatusBanner.textContent = `Loaded for ${symbol}.`;
    els.newsStatusBanner.className = "status-banner success";
  } catch (e) {
    els.newsSentimentBadge.textContent = "unavailable";
    els.newsSummary.textContent = "Could not load news sentiment for this stock right now.";
    els.newsStatusBanner.textContent = e.message || "News sentiment failed.";
    els.newsStatusBanner.className = "status-banner error";
  } finally {
    els.newsFetchBtn.disabled = false;
  }
}

function renderNewsSentiment(data) {
  const score = Number(data.score || 0);
  const cls = score > 0.15 ? "pill--positive" : score < -0.15 ? "pill--negative" : "pill--neutral";
  const label = score > 0.15 ? "Bullish tone" : score < -0.15 ? "Bearish tone" : "Neutral tone";
  els.newsSentimentBadge.className = `pill ${cls}`;
  els.newsSentimentBadge.textContent = `${label} (${score.toFixed(2)})`;

  els.newsHeadlineList.innerHTML = (data.headlines || []).length
    ? data.headlines.map((h) => `<li>${h}</li>`).join("")
    : '<li>No sample headlines for this stock in this demo dataset.</li>';

  els.newsSummary.textContent = data.summary || "";
}

function renderStrategyPerformance(performance, baseResult) {
  destroyStrategyCharts();
  renderMaVsWeeklyChart(performance);
  renderLeaderboard(performance);
  renderBestStrategy(performance.best_strategy);
  renderTiktokChart(performance.tiktok_strategy);
  renderReferenceComparison(performance.reference_notebooks, performance.best_strategy);
}

const muted = () => getComputedStyle(document.documentElement).getPropertyValue("--muted").trim();

function renderMaVsWeeklyChart(performance) {
  const ma = performance.ma_crossover;
  const weekly = performance.weekly_mean_reversion;
  const comparisonLabels = ma.dates.length <= weekly.dates.length ? ma.dates : weekly.dates;

  state.charts.strategyComparison = new Chart(els.strategyComparisonChart.getContext("2d"), {
    type: "line",
    data: {
      labels: comparisonLabels,
      datasets: [
        {
          label: `MA Crossover (${ma.symbol})`,
          data: ma.portfolio_values.slice(0, comparisonLabels.length),
          borderColor: "#6f7dff",
          backgroundColor: "rgba(111,125,255,0.16)",
          borderWidth: 2,
          tension: 0.35,
          pointRadius: 0,
        },
        {
          label: "Weekly Mean Reversion",
          data: weekly.portfolio_values.slice(0, comparisonLabels.length),
          borderColor: "#35d7a8",
          backgroundColor: "rgba(53,215,168,0.16)",
          borderWidth: 2,
          tension: 0.35,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: muted() } } },
      scales: {
        x: { ticks: { color: muted(), maxTicksLimit: 8 } },
        y: { ticks: { color: muted() } },
      },
    },
  });
}

function renderLeaderboard(performance) {
  const ma = performance.ma_crossover;
  const weekly = performance.weekly_mean_reversion;
  const tiktok = performance.tiktok_strategy;
  const best = performance.best_strategy;

  els.leaderboardEmptyState.hidden = true;
  els.leaderboardContent.hidden = false;

  const rows = [
    { name: `MA Crossover (${ma.symbol})`, final: ma.final_value, ret: ma.return_percent, dd: ma.max_drawdown_percent, sharpe: ma.sharpe },
    { name: "Weekly Mean Reversion", final: weekly.final_value, ret: weekly.return_percent, dd: weekly.max_drawdown_percent, sharpe: weekly.sharpe },
    { name: "TikTok Guru Strategy", final: tiktok.final_value, ret: tiktok.return_percent, dd: tiktok.max_drawdown_percent, sharpe: tiktok.sharpe },
  ];

  if (best) {
    (best.comparison_table || []).forEach((row) => {
      const label = row.Strategy === "Benchmark (equal-weight)" ? "Benchmark (full universe)" : `${row.Strategy} (baseline)`;
      rows.push({ name: label, final: row["Final Value"], ret: row["Return %"], dd: row["Max Drawdown %"], sharpe: row.Sharpe });
    });
    const m = best.best_strategy_metrics;
    rows.push({ name: `${best.name} (tuned)`, final: m.final_value, ret: m.return_pct, dd: m.max_drawdown_pct, sharpe: m.sharpe });
  }

  els.leaderboardTableBody.innerHTML = rows
    .map((r) => `<tr><td>${r.name}</td><td>${fmtCurrency(r.final)}</td><td>${fmtPercent(r.ret)}</td><td>${fmtPercent(r.dd)}</td><td>${Number(r.sharpe || 0).toFixed(2)}</td></tr>`)
    .join("");

  state.charts.leaderboardMetrics = new Chart(els.leaderboardMetricsChart.getContext("2d"), {
    type: "bar",
    data: {
      labels: rows.map((r) => r.name),
      datasets: [
        { label: "Return %", data: rows.map((r) => r.ret), backgroundColor: "rgba(111,125,255,0.75)" },
        { label: "Max Drawdown %", data: rows.map((r) => r.dd), backgroundColor: "rgba(255,100,116,0.7)" },
        { label: "Sharpe", data: rows.map((r) => r.sharpe), backgroundColor: "rgba(53,215,168,0.75)" },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: muted() } } },
      scales: {
        x: { ticks: { color: muted(), maxRotation: 30, minRotation: 30 } },
        y: { ticks: { color: muted() } },
      },
    },
  });
}

function renderBestStrategy(best) {
  if (!best) return;
  const m = best.best_strategy_metrics;
  const seeds = best.seed_stability;

  els.bestTitle.textContent = best.name;

  els.bestSummary.innerHTML = [
    `Model: ${best.model_type} · Weighting: ${best.weighting_method}`,
    `Universe: ${best.universe.length} EGX stocks · Initial capital: ${fmtCurrency(m.initial_value)}`,
    `Final value: ${fmtCurrency(m.final_value)} · P/L: ${fmtCurrency(m.pnl)} · Return: ${fmtPercent(m.return_pct)}`,
    `Max drawdown: ${fmtCurrency(m.max_drawdown_egp)} (${fmtPercent(m.max_drawdown_pct)}) · Sharpe: ${m.sharpe.toFixed(2)} · Rebalances: ${m.n_rebalances}`,
    `Seed stability (seeds ${seeds.seeds.join(", ")}): mean ${fmtPercent(seeds.mean_return_pct)}, std ${seeds.std_return_pct.toFixed(2)} pts, profitable in ${Math.round(seeds.profitable_seed_fraction * 100)}% of seeds — ${seeds.verdict}`,
  ].map((line) => `<div>${line}</div>`).join("");

  els.bestBadges.innerHTML = `
    <span class="pill">Return ${fmtPercent(m.return_pct)}</span>
    <span class="pill">Drawdown ${fmtPercent(m.max_drawdown_pct)}</span>
    <span class="pill">Sharpe ${m.sharpe.toFixed(2)}</span>
    <span class="pill">${best.model_type}</span>
  `;

  state.charts.best = new Chart(els.bestChart.getContext("2d"), {
    type: "line",
    data: {
      labels: best.dates,
      datasets: [
        { label: "Benchmark", data: best.benchmark_curve, borderColor: "#84a0c0", borderDash: [5, 4], borderWidth: 1.6, pointRadius: 0, tension: 0.25 },
        { label: "MLP Portfolio", data: best.mlp_curve, borderColor: "#6f7dff", borderWidth: 1.8, pointRadius: 0, tension: 0.25 },
        { label: "LSTM Portfolio", data: best.lstm_curve, borderColor: "#35d7a8", borderWidth: 1.8, pointRadius: 0, tension: 0.25 },
        { label: `${best.name} (best)`, data: best.best_curve, borderColor: "#ffc36b", borderWidth: 2.4, pointRadius: 0, tension: 0.25 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: muted() } } },
      scales: {
        x: { ticks: { color: muted(), maxTicksLimit: 8 } },
        y: { ticks: { color: muted() } },
      },
    },
  });

  state.charts.bestDrawdown = new Chart(els.bestDrawdownChart.getContext("2d"), {
    type: "line",
    data: {
      labels: best.dates,
      datasets: [
        { label: "Benchmark", data: best.benchmark_drawdown_pct, borderColor: "#84a0c0", borderDash: [5, 4], borderWidth: 1.4, pointRadius: 0, fill: false, tension: 0.2 },
        { label: "MLP Portfolio", data: best.mlp_drawdown_pct, borderColor: "#6f7dff", borderWidth: 1.6, pointRadius: 0, fill: false, tension: 0.2 },
        { label: "LSTM Portfolio", data: best.lstm_drawdown_pct, borderColor: "#35d7a8", borderWidth: 1.6, pointRadius: 0, fill: false, tension: 0.2 },
        { label: `${best.name} (best)`, data: best.best_drawdown_pct, borderColor: "#ffc36b", borderWidth: 2, pointRadius: 0, fill: false, tension: 0.2 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: muted() } } },
      scales: {
        x: { ticks: { color: muted(), maxTicksLimit: 8 } },
        y: { reverse: true, ticks: { color: muted() } },
      },
    },
  });
}

function renderTiktokChart(tiktok) {
  if (!tiktok) return;
  state.charts.tiktok = new Chart(els.tiktokChart.getContext("2d"), {
    type: "line",
    data: {
      labels: tiktok.dates,
      datasets: [
        { label: "TikTok Guru Strategy", data: tiktok.portfolio_values, borderColor: "#ffc36b", borderWidth: 2, pointRadius: 0, tension: 0.25 },
        { label: "Equal-Weight Benchmark", data: tiktok.benchmark_values, borderColor: "#84a0c0", borderDash: [5, 4], borderWidth: 1.6, pointRadius: 0, tension: 0.25 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: muted() } } },
      scales: {
        x: { ticks: { color: muted(), maxTicksLimit: 8 } },
        y: { ticks: { color: muted() } },
      },
    },
  });
}

function renderReferenceComparison(reference, best) {
  if (!reference) {
    els.referenceEmptyState.hidden = false;
    els.referenceContent.hidden = true;
    return;
  }
  els.referenceEmptyState.hidden = true;
  els.referenceContent.hidden = false;
  els.referenceSource.textContent = `Source: ${reference.source}`;

  const mineMlp = best?.comparison_table?.find((r) => r.Strategy === "MLP Portfolio");
  const mineLstm = best?.comparison_table?.find((r) => r.Strategy === "LSTM Portfolio");
  const refMlp = reference.mlp;
  const refLstm = reference.lstm;

  els.referenceSummary.innerHTML = [
    `My MLP and LSTM train on the full 34-stock EGX universe with proportional full-universe weights; the reference notebooks train a single stock with a top-k equal-weight strategy — different setups, so treat this as "does the same idea hold up elsewhere", not an apples-to-apples score.`,
    refMlp ? `Reference MLP: ${fmtPercent(refMlp.return_percent)} return, ${fmtPercent(refMlp.max_drawdown_percent)} drawdown, Sharpe ${refMlp.sharpe.toFixed(2)}.` : "",
    refLstm ? `Reference LSTM: ${fmtPercent(refLstm.return_percent)} return, ${fmtPercent(refLstm.max_drawdown_percent)} drawdown, Sharpe ${refLstm.sharpe.toFixed(2)}.` : "",
  ].filter(Boolean).map((line) => `<div>${line}</div>`).join("");

  const tableRows = [];
  if (mineMlp) tableRows.push({ model: "MLP", source: "Mine (full universe)", final: mineMlp["Final Value"], ret: mineMlp["Return %"], dd: mineMlp["Max Drawdown %"], sharpe: mineMlp.Sharpe });
  if (refMlp) tableRows.push({ model: "MLP", source: "Reference notebook", final: refMlp.final_value, ret: refMlp.return_percent, dd: refMlp.max_drawdown_percent, sharpe: refMlp.sharpe });
  if (mineLstm) tableRows.push({ model: "LSTM", source: "Mine (full universe)", final: mineLstm["Final Value"], ret: mineLstm["Return %"], dd: mineLstm["Max Drawdown %"], sharpe: mineLstm.Sharpe });
  if (refLstm) tableRows.push({ model: "LSTM", source: "Reference notebook", final: refLstm.final_value, ret: refLstm.return_percent, dd: refLstm.max_drawdown_percent, sharpe: refLstm.sharpe });

  els.referenceTableBody.innerHTML = tableRows
    .map((r) => `<tr><td>${r.model}</td><td>${r.source}</td><td>${fmtCurrency(r.final)}</td><td>${fmtPercent(r.ret)}</td><td>${fmtPercent(r.dd)}</td><td>${Number(r.sharpe || 0).toFixed(2)}</td></tr>`)
    .join("");

  const pivotSeeds = reference.pivot_seed_table || [];
  const pivotWinRate = pivotSeeds.length ? pivotSeeds.filter((s) => s.beat_benchmark).length / pivotSeeds.length : null;
  const mySeeds = best?.seed_stability;

  els.referenceSeedSummary.innerHTML = [
    mySeeds ? `Mine: ${mySeeds.seeds.length} seeds (${mySeeds.seeds.join(", ")}), profitable in ${Math.round(mySeeds.profitable_seed_fraction * 100)}% of seeds, mean return ${fmtPercent(mySeeds.mean_return_pct)}, std ${mySeeds.std_return_pct.toFixed(2)} pts.` : "",
    pivotWinRate !== null ? `Reference (pivot.ipynb): ${pivotSeeds.length} seeds, beat the benchmark in ${Math.round(pivotWinRate * 100)}% of seeds — the reference notebook's own point is that this is close to a coin flip for a top-k single-stock strategy.` : "",
  ].filter(Boolean).map((line) => `<div>${line}</div>`).join("");
}

function toggleChat(open) {
  state.chatOpen = open ?? !state.chatOpen;
  els.chatPanel.hidden = !state.chatOpen;
  els.chatFab.textContent = state.chatOpen ? "▾" : "🐂";
  els.chatFab.title = state.chatOpen ? "Minimize chat" : "Chat with Bull";
  els.chatFab.setAttribute("aria-label", state.chatOpen ? "Minimize chat with Bull" : "Open chat with Bull");
  els.chatFab.classList.toggle("chat-fab--open", state.chatOpen);
  if (state.chatOpen) els.chatInput.focus();
}

function appendChatMessage(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `chat-msg chat-msg--${role === "user" ? "user" : "bot"}`;
  bubble.textContent = text;
  els.chatMessages.appendChild(bubble);
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
  return bubble;
}

function buildChatContext() {
  const perf = state.strategyPerformance;
  const context = { selected_symbol: els.assetSelect?.value || null };
  if (state.results) {
    context.selected_stock_backtest = {
      symbol: state.results.symbol,
      return_percent: state.results.return_percent,
      max_drawdown_percent: state.results.max_drawdown_percent,
      final_value: state.results.final_value,
    };
  }
  if (state.newsSentiment) context.news_sentiment = state.newsSentiment;
  if (perf) {
    const pick = (r) => r && { return_percent: r.return_percent, max_drawdown_percent: r.max_drawdown_percent, sharpe: r.sharpe, final_value: r.final_value };
    context.ma_crossover = pick(perf.ma_crossover);
    context.weekly_mean_reversion = pick(perf.weekly_mean_reversion);
    context.tiktok_strategy = pick(perf.tiktok_strategy);
    if (perf.best_strategy) {
      context.best_strategy = {
        name: perf.best_strategy.name,
        model_type: perf.best_strategy.model_type,
        weighting_method: perf.best_strategy.weighting_method,
        universe_size: perf.best_strategy.universe?.length,
        metrics: perf.best_strategy.best_strategy_metrics,
        seed_stability: perf.best_strategy.seed_stability,
        comparison_table: perf.best_strategy.comparison_table,
      };
    }
  }
  return context;
}

async function sendChatMessage(event) {
  event.preventDefault();
  const message = els.chatInput.value.trim();
  if (!message) return;
  els.chatInput.value = "";
  els.chatSendBtn.disabled = true;
  appendChatMessage("user", message);
  const pending = appendChatMessage("bot", "🐂 hyping up an answer…");
  pending.classList.add("chat-msg--pending");

  try {
    const r = await fetch(`${API}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history: state.chatHistory, context: buildChatContext() }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Chat failed");
    pending.classList.remove("chat-msg--pending");
    pending.textContent = data.reply;
    state.chatHistory.push({ role: "user", content: message }, { role: "assistant", content: data.reply });
    if (state.chatHistory.length > 20) state.chatHistory = state.chatHistory.slice(-20);
  } catch (e) {
    pending.classList.remove("chat-msg--pending");
    pending.textContent = "🐂 Even I can't hype my way past a backend error right now. Try again in a sec.";
  } finally {
    els.chatSendBtn.disabled = false;
  }
}

function resetForm() {
  els.assetSelect.value = state.assets[0] || "";
  els.newsAssetSelect.value = state.assets[0] || "";
  els.initialCash.value = "1000";
  els.fastWindow.value = "9";
  els.slowWindow.value = "20";
  els.tradeSearch.value = "";
  els.tradeFilter.value = "ALL";
  els.tradeSort.value = "newest";
  state.results = null;
  state.strategyPerformance = null;
  els.resultsSection.hidden = true;
  els.emptyState.hidden = false;
  els.leaderboardEmptyState.hidden = false;
  els.leaderboardContent.hidden = true;
  els.referenceEmptyState.hidden = false;
  els.referenceContent.hidden = true;
  els.kpiRow.innerHTML = "";
  els.newsEmptyState.hidden = false;
  els.newsContent.hidden = true;
  els.newsStatusBanner.textContent = "";
  els.newsStatusBanner.className = "status-banner";
  els.newsSentimentBadge.textContent = "—";
  els.newsSentimentBadge.className = "pill pill--neutral";
  els.newsHeadlineList.innerHTML = "";
  els.newsSummary.textContent = "";
  state.newsSentiment = null;
  destroyCharts();
}

function bindEvents() {
  els.runBtn.addEventListener("click", runBacktest);
  els.resetBtn.addEventListener("click", resetForm);
  els.newsFetchBtn.addEventListener("click", () => loadNewsSentiment(els.newsAssetSelect.value));
  els.refreshBtn.addEventListener("click", async () => {
    await checkHealth();
    await loadAssets();
  });
  els.themeToggle.addEventListener("click", () => {
    setTheme(state.theme === "dark" ? "light" : "dark");
  });
  els.tradeSearch.addEventListener("input", () => {
    if (state.results) renderTrades(state.results);
  });
  els.tradeFilter.addEventListener("change", () => {
    if (state.results) renderTrades(state.results);
  });
  els.tradeSort.addEventListener("change", () => {
    if (state.results) renderTrades(state.results);
  });
  els.downloadBtn.addEventListener("click", () => {
    if (!state.results) return;
    const link = document.createElement("a");
    link.download = `${state.results.symbol}-chart.png`;
    link.href = document.getElementById("priceChart").toDataURL("image/png");
    link.click();
  });
  els.fullscreenBtn.addEventListener("click", () => {
    const chart = document.getElementById("priceChart");
    if (chart.requestFullscreen) chart.requestFullscreen();
  });
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      runBacktest();
    }
    if (event.key === "Escape" && state.chatOpen) toggleChat(false);
  });
  els.chatFab.addEventListener("click", () => toggleChat());
  els.chatCloseBtn.addEventListener("click", () => toggleChat(false));
  els.chatForm.addEventListener("submit", sendChatMessage);
}

async function init() {
  setTheme("dark");
  bindEvents();
  initSectionSwitcher();
  await checkHealth();
  await loadAssets();
  setLoading(false);
  resetForm();
  if (state.assets.length) {
    els.assetSelect.value = state.assets[0];
    await runBacktest();   // pre-load the Leaderboard / Reference tabs so they aren't empty
  }
}

init();
