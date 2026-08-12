<<<<<<< HEAD
const API_BASE = "http://127.0.0.1:8000";

const statusPanel = document.getElementById("status");
const strategySelect = document.getElementById("strategy-select");
const assetSelect = document.getElementById("asset-select");
const assetControl = document.getElementById("asset-control");
const assetDescription = document.getElementById("asset-description");
const insightBanner = document.getElementById("insight-banner");

let priceChart = null;
let equityChart = null;
let drawdownChart = null;


function formatEGP(value) {
  return new Intl.NumberFormat("en-EG", {
    style: "currency",
    currency: "EGP",
    minimumFractionDigits: 2,
  }).format(value);
}


function formatPercent(value) {
  return `${Number(value).toFixed(2)}%`;
}


function setStatus(message, state = "") {
  statusPanel.textContent = message;
  statusPanel.className = `status ${state}`;
}


function setReturnColor(element, value) {
  element.classList.remove("positive", "negative");
  element.classList.add(value >= 0 ? "positive" : "negative");
}


function destroyCharts() {
  for (const chart of [priceChart, equityChart, drawdownChart]) {
    if (chart) chart.destroy();
  }
  priceChart = null;
  equityChart = null;
  drawdownChart = null;
}


function attachZoomReset(canvas, getChart) {
  canvas.ondblclick = () => {
    const chart = getChart();
    if (chart && typeof chart.resetZoom === "function") {
      chart.resetZoom();
    }
  };
}


function chartOptions(yTitle, indexMode = true) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: indexMode ? "index" : "nearest",
      intersect: false,
    },
    plugins: {
      legend: {
        labels: { color: "#e8eef7" },
      },
      zoom: {
        limits: { x: { minRange: 10 } },
        pan: {
          enabled: true,
          mode: "x",
          modifierKey: "shift",
        },
        zoom: {
          wheel: { enabled: true, speed: 0.1 },
          pinch: { enabled: true },
          drag: {
            enabled: true,
            backgroundColor: "rgba(96, 165, 250, 0.15)",
            borderColor: "#60a5fa",
            borderWidth: 1,
          },
          mode: "x",
        },
      },
    },
    scales: {
      x: {
        ticks: { color: "#91a3ba", maxTicksLimit: 12 },
        grid: { color: "rgba(145, 163, 186, 0.08)" },
      },
      y: {
        title: { display: true, text: yTitle, color: "#91a3ba" },
        ticks: { color: "#91a3ba" },
        grid: { color: "rgba(145, 163, 186, 0.08)" },
      },
    },
  };
}


function setCard(id, value, label, note = "") {
  if (label) document.getElementById(`${id}-label`).textContent = label;
  document.getElementById(`${id}-value`).textContent = value;
  const noteElement = document.getElementById(`${id}-note`);
  if (noteElement) noteElement.textContent = note;
}


function displaySmaMetrics(backtest) {
  document.getElementById("final-value").textContent =
    formatEGP(backtest.final_portfolio_value_egp);

  const returnElement = document.getElementById("total-return");
  returnElement.textContent = formatPercent(backtest.total_return_percent);
  setReturnColor(returnElement, backtest.total_return_percent);

  document.getElementById("max-drawdown").textContent =
    `${formatEGP(backtest.max_drawdown_egp)} ` +
    `(${formatPercent(backtest.max_drawdown_percent)})`;

  document.getElementById("operations-label").textContent =
    "Buy / sell operations";
  document.getElementById("operations").textContent =
    `${backtest.buy_operations} / ${backtest.sell_operations}`;
  document.getElementById("operations-note").textContent =
    `${backtest.total_operations} total operations`;

  setCard(
    "comparison",
    backtest.open_position ? "Invested" : "Cash",
    "Current position",
    "Position at the final historical date",
  );
  setCard(
    "cost",
    formatEGP(0),
    "Commission impact",
    "Single-asset test assumes zero commission",
  );
}


function displayMeanReversionMetrics(data) {
  document.getElementById("final-value").textContent =
    formatEGP(data.final_portfolio_value_egp);

  const returnElement = document.getElementById("total-return");
  returnElement.textContent = formatPercent(data.total_return_percent);
  setReturnColor(returnElement, data.total_return_percent);

  document.getElementById("max-drawdown").textContent =
    `${formatEGP(data.max_drawdown_egp)} ` +
    `(${formatPercent(data.max_drawdown_percent)})`;

  document.getElementById("operations-label").textContent = "Weight changes";
  document.getElementById("operations").textContent =
    data.total_trades.toLocaleString();
  document.getElementById("operations-note").textContent =
    `${data.average_assets_held.toFixed(1)} assets held on average`;

  setCard(
    "comparison",
    formatEGP(data.benchmark_final_value_egp),
    "Equal-weight benchmark",
    `Strategy Sharpe: ${data.sharpe.toFixed(3)}`,
  );
  setCard(
    "cost",
    formatEGP(data.commission_drag_egp),
    "Commission drag",
    `No-cost result: ${formatEGP(data.no_cost_final_value_egp)}`,
  );
}


function renderSmaPriceChart(indicators, trades) {
  const canvas = document.getElementById("price-chart");
  const labels = indicators.data.map((row) => row.date);
  const buys = new Map(
    trades
      .filter((trade) => trade.operation === "BUY")
      .map((trade) => [trade.execution_date, trade.execution_price]),
  );
  const sells = new Map(
    trades
      .filter((trade) => trade.operation === "SELL")
      .map((trade) => [trade.execution_date, trade.execution_price]),
  );

  priceChart = new Chart(canvas, {
=======
<<<<<<< HEAD
// Dashboard frontend for the EGX Strategy Lab.
const API = "http://localhost:8000";
const state = {
  assets: [],
  results: null,
  strategyPerformance: null,
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
  strategyPerformancePanel: document.getElementById("strategyPerformancePanel"),
  strategyPerformanceSummary: document.getElementById("strategyPerformanceSummary"),
  strategyPerformanceBadges: document.getElementById("strategyPerformanceBadges"),
  strategyComparisonChartPanel: document.getElementById("strategyComparisonChartPanel"),
  strategyMetricsChartPanel: document.getElementById("strategyMetricsChartPanel"),
  strategyComparisonChart: document.getElementById("strategyComparisonChart"),
  strategyMetricsChart: document.getElementById("strategyMetricsChart"),
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
=======
// Dashboard frontend. Grows via dashboard/tasks/.
const API = "http://localhost:8000";
>>>>>>> origin/main

async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const j = await r.json();
<<<<<<< HEAD
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
    els.assetSelect.innerHTML = state.assets
      .map((asset) => `<option value="${asset}">${asset}</option>`)
      .join("");
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
  ["strategyComparison", "strategyMetrics"].forEach((key) => {
    if (state.charts[key]) {
      state.charts[key].destroy();
      delete state.charts[key];
    }
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
>>>>>>> origin/Kanzy_Kabesh
    type: "line",
    data: {
      labels,
      datasets: [
        {
<<<<<<< HEAD
          label: "Closing price",
          data: indicators.data.map((row) => row.close),
          borderColor: "#e8eef7",
          borderWidth: 1.2,
          pointRadius: 0,
        },
        {
          label: "SMA 9",
          data: indicators.data.map((row) => row.ma9),
          borderColor: "#32d583",
          borderWidth: 1.5,
          pointRadius: 0,
        },
        {
          label: "SMA 20",
          data: indicators.data.map((row) => row.ma20),
          borderColor: "#f59e0b",
          borderWidth: 1.5,
          pointRadius: 0,
        },
        {
          label: "Buy",
          data: labels.map((date) => buys.get(date) ?? null),
          borderColor: "#32d583",
          backgroundColor: "#32d583",
          pointStyle: "triangle",
          pointRadius: labels.map((date) => (buys.has(date) ? 7 : 0)),
          showLine: false,
        },
        {
          label: "Sell",
          data: labels.map((date) => sells.get(date) ?? null),
          borderColor: "#ff6b6b",
          backgroundColor: "#ff6b6b",
          pointStyle: "triangle",
          pointRotation: 180,
          pointRadius: labels.map((date) => (sells.has(date) ? 7 : 0)),
          showLine: false,
        },
      ],
    },
    options: chartOptions("Price"),
  });
  attachZoomReset(canvas, () => priceChart);
}


function renderSmaEquityChart(backtest) {
  const canvas = document.getElementById("equity-chart");
  const equity = backtest.equity_curve;
  equityChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: equity.map((row) => row.date),
      datasets: [
        {
          label: "Portfolio value",
          data: equity.map((row) => row.portfolio_value),
          borderColor: "#60a5fa",
          backgroundColor: "rgba(96, 165, 250, 0.12)",
          fill: true,
          borderWidth: 2,
          pointRadius: 0,
        },
        {
          label: "Running peak",
          data: equity.map((row) => row.running_peak),
          borderColor: "#91a3ba",
          borderDash: [6, 6],
          borderWidth: 1,
=======
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

function renderStrategyPerformance(performance, baseResult) {
  const ma = performance.ma_crossover;
  const weekly = performance.weekly_mean_reversion;
  const comparisonLabels = ma.dates.length <= weekly.dates.length ? ma.dates : weekly.dates;

  els.strategyPerformancePanel.hidden = false;
  els.strategyComparisonChartPanel.hidden = false;
  els.strategyMetricsChartPanel.hidden = false;

  els.strategyPerformanceSummary.innerHTML = [
    `MA crossover strategy run on ${ma.symbol} with fast=${ma.fast_window} and slow=${ma.slow_window}.`,
    `Weekly mean reversion strategy run across the full EGX universe.`,
    `Selected cash base: ${fmtCurrency(ma.initial_cash)}.`,
    `MA crossover return: ${fmtPercent(ma.return_percent)} vs weekly return: ${fmtPercent(weekly.return_percent)}.`,
  ].map((line) => `<div>${line}</div>`).join("");

  els.strategyPerformanceBadges.innerHTML = `
    <span class="pill">MA return ${fmtPercent(ma.return_percent)}</span>
    <span class="pill">Weekly return ${fmtPercent(weekly.return_percent)}</span>
    <span class="pill">MA drawdown ${fmtPercent(ma.max_drawdown_percent)}</span>
    <span class="pill">Weekly drawdown ${fmtPercent(weekly.max_drawdown_percent)}</span>
  `;

  destroyStrategyCharts();

  state.charts.strategyComparison = new Chart(els.strategyComparisonChart.getContext("2d"), {
    type: "line",
    data: {
      labels: comparisonLabels,
      datasets: [
        {
          label: "MA Crossover",
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
>>>>>>> origin/Kanzy_Kabesh
          pointRadius: 0,
        },
      ],
    },
<<<<<<< HEAD
    options: chartOptions("Portfolio value (EGP)"),
  });
  attachZoomReset(canvas, () => equityChart);
}


function renderSmaDrawdownChart(backtest) {
  const canvas = document.getElementById("drawdown-chart");
  const equity = backtest.equity_curve;
  drawdownChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: equity.map((row) => row.date),
      datasets: [{
        label: "Drawdown",
        data: equity.map((row) => row.drawdown_percent),
        borderColor: "#ff6b6b",
        backgroundColor: "rgba(255, 107, 107, 0.3)",
        fill: true,
        borderWidth: 1.5,
        pointRadius: 0,
      }],
    },
    options: chartOptions("Drawdown (%)"),
  });
  attachZoomReset(canvas, () => drawdownChart);
}


function renderMeanAllocationChart(data) {
  const canvas = document.getElementById("price-chart");
  const allocations = data.latest_allocations;
  priceChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: allocations.map((row) => row.symbol),
      datasets: [{
        label: "Portfolio weight (%)",
        data: allocations.map((row) => row.weight_percent),
        backgroundColor: allocations.map((_, index) =>
          index < 3 ? "#32d583" : "rgba(96, 165, 250, 0.72)"
        ),
        borderRadius: 5,
      }],
    },
    options: {
      ...chartOptions("Weight (%)", false),
      plugins: {
        ...chartOptions("Weight (%)", false).plugins,
        tooltip: {
          callbacks: {
            afterLabel(context) {
              const row = allocations[context.dataIndex];
              return [
                `5-day return: ${formatPercent(row.five_day_return_percent)}`,
                `Allocation: ${formatEGP(row.amount_egp)}`,
              ];
            },
          },
        },
      },
    },
  });
  attachZoomReset(canvas, () => priceChart);
}


function renderMeanEquityChart(data) {
  const canvas = document.getElementById("equity-chart");
  const equity = data.equity_curve;
  equityChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: equity.map((row) => row.date),
      datasets: [
        {
          label: `Strategy after ${formatPercent(data.commission_percent)} commission`,
          data: equity.map((row) => row.portfolio_value),
          borderColor: "#60a5fa",
          borderWidth: 2,
          pointRadius: 0,
        },
        {
          label: "Strategy without commission",
          data: equity.map((row) => row.no_cost_value),
          borderColor: "#32d583",
          borderWidth: 1.5,
          pointRadius: 0,
        },
        {
          label: "Equal-weight benchmark",
          data: equity.map((row) => row.benchmark_value),
          borderColor: "#f59e0b",
          borderDash: [6, 6],
          borderWidth: 1.5,
          pointRadius: 0,
        },
      ],
    },
    options: chartOptions("Portfolio value (EGP)"),
  });
  attachZoomReset(canvas, () => equityChart);
}


function renderMeanDrawdownChart(data) {
  const canvas = document.getElementById("drawdown-chart");
  const equity = data.equity_curve;
  drawdownChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: equity.map((row) => row.date),
      datasets: [{
        label: "Strategy drawdown",
        data: equity.map((row) => row.drawdown_percent),
        borderColor: "#ff6b6b",
        backgroundColor: "rgba(255, 107, 107, 0.3)",
        fill: true,
        borderWidth: 1.5,
        pointRadius: 0,
      }],
    },
    options: chartOptions("Drawdown (%)"),
  });
  attachZoomReset(canvas, () => drawdownChart);
}


function renderSmaTrades(trades) {
  document.getElementById("table-head").innerHTML = `
    <tr>
      <th>Operation</th><th>Signal date</th><th>Execution date</th>
      <th>Price</th><th>Shares</th><th>Amount</th>
    </tr>`;
  const table = document.getElementById("trade-table");
  table.innerHTML = "";
  if (trades.length === 0) {
    table.innerHTML = '<tr><td colspan="6">No operations were generated.</td></tr>';
    return;
  }
  for (const trade of trades) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td class="${trade.operation.toLowerCase()}">${trade.operation}</td>
      <td>${trade.signal_date}</td><td>${trade.execution_date}</td>
      <td>${trade.execution_price.toFixed(4)}</td>
      <td>${trade.shares.toFixed(6)}</td><td>${formatEGP(trade.amount_egp)}</td>`;
    table.appendChild(row);
  }
}


function renderAllocations(data) {
  document.getElementById("table-head").innerHTML = `
    <tr><th>Asset</th><th>Five-day return</th><th>Weight</th><th>EGP allocation</th></tr>`;
  const table = document.getElementById("trade-table");
  table.innerHTML = "";
  if (data.latest_allocations.length === 0) {
    table.innerHTML = '<tr><td colspan="4">No recent losers; portfolio is in cash.</td></tr>';
    return;
  }
  for (const allocation of data.latest_allocations) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td class="buy">${allocation.symbol}</td>
      <td class="negative">${formatPercent(allocation.five_day_return_percent)}</td>
      <td>${formatPercent(allocation.weight_percent)}</td>
      <td>${formatEGP(allocation.amount_egp)}</td>`;
    table.appendChild(row);
  }
}


async function loadSmaAsset(symbol) {
  try {
    setStatus(`Loading ${symbol}…`);
    assetSelect.disabled = true;
    destroyCharts();
    const safeSymbol = encodeURIComponent(symbol);
    const [indicatorsResponse, backtestResponse] = await Promise.all([
      fetch(`${API_BASE}/indicators/${safeSymbol}`),
      fetch(`${API_BASE}/backtest/${safeSymbol}`),
    ]);
    if (!indicatorsResponse.ok || !backtestResponse.ok) {
      throw new Error(`Could not load ${symbol}.`);
    }
    const indicators = await indicatorsResponse.json();
    const backtest = await backtestResponse.json();

    displaySmaMetrics(backtest);
    renderSmaPriceChart(indicators, backtest.trades);
    renderSmaEquityChart(backtest);
    renderSmaDrawdownChart(backtest);
    renderSmaTrades(backtest.trades);

    document.getElementById("primary-chart-title").textContent =
      `${symbol} price, SMA 9/20, and executions`;
    document.getElementById("equity-chart-title").textContent = "Portfolio equity curve";
    document.getElementById("drawdown-chart-title").textContent = "Portfolio drawdown";
    document.getElementById("table-title").textContent = "Trade history";
    assetDescription.textContent =
      `${symbol} · SMA 9/20 crossover · Starting capital: 1,000 EGP`;
    insightBanner.textContent =
      `The strategy buys ${symbol} after SMA 9 crosses above SMA 20 and sells after the reverse crossover. Signals execute at the next available close.`;
    setStatus(`${symbol}: ready`, "ok");
  } catch (error) {
    console.error(error);
    setStatus(`${symbol}: failed to load`, "error");
  } finally {
    assetSelect.disabled = false;
    strategySelect.disabled = false;
  }
}


async function loadMeanReversion() {
  try {
    setStatus("Running 34-asset strategy…");
    strategySelect.disabled = true;
    destroyCharts();
    const response = await fetch(`${API_BASE}/portfolio/mean-reversion`);
    if (!response.ok) throw new Error("Could not run mean reversion.");
    const data = await response.json();

    displayMeanReversionMetrics(data);
    renderMeanAllocationChart(data);
    renderMeanEquityChart(data);
    renderMeanDrawdownChart(data);
    renderAllocations(data);

    document.getElementById("primary-chart-title").textContent =
      `Latest allocations · ${data.latest_decision_date}`;
    document.getElementById("equity-chart-title").textContent =
      "Strategy vs no-cost scenario vs benchmark";
    document.getElementById("drawdown-chart-title").textContent =
      "Cost-adjusted portfolio drawdown";
    document.getElementById("table-title").textContent = "Latest portfolio allocation";
    assetDescription.textContent =
      `${data.universe_size} assets · ${data.signal_days}-day loser signal · ` +
      `${formatPercent(data.commission_percent)} commission · Starting capital: 1,000 EGP`;
    insightBanner.textContent =
      `Without commission, the portfolio finished at ${formatEGP(data.no_cost_final_value_egp)}. ` +
      `After trading costs it finished at ${formatEGP(data.final_portfolio_value_egp)}, ` +
      `a ${formatEGP(data.commission_drag_egp)} drag. High turnover—not just the signal—is the central insight.`;
    setStatus("Mean reversion: ready", "ok");
  } catch (error) {
    console.error(error);
    setStatus("Mean reversion failed", "error");
  } finally {
    strategySelect.disabled = false;
  }
}


async function switchStrategy() {
  const mode = strategySelect.value;
  if (mode === "mean-reversion") {
    assetControl.style.display = "none";
    await loadMeanReversion();
  } else {
    assetControl.style.display = "flex";
    await loadSmaAsset(assetSelect.value);
  }
}


async function initializeDashboard() {
  try {
    setStatus("Loading assets…");
    strategySelect.disabled = true;
    assetSelect.disabled = true;
    const [healthResponse, universeResponse] = await Promise.all([
      fetch(`${API_BASE}/health`),
      fetch(`${API_BASE}/universe`),
    ]);
    if (!healthResponse.ok || !universeResponse.ok) {
      throw new Error("Could not connect to the backend.");
    }
    const health = await healthResponse.json();
    const universe = await universeResponse.json();
    if (health.status !== "ok" || !universe.assets?.length) {
      throw new Error("No assets are available.");
    }

    assetSelect.innerHTML = "";
    for (const symbol of universe.assets) {
      const option = document.createElement("option");
      option.value = symbol;
      option.textContent = symbol;
      assetSelect.appendChild(option);
    }
    assetSelect.value = universe.assets.includes("SAUD")
      ? "SAUD"
      : universe.assets[0];
    assetSelect.disabled = false;
    strategySelect.disabled = false;
    await switchStrategy();
  } catch (error) {
    console.error(error);
    setStatus("Backend not reachable", "error");
    insightBanner.textContent = "Start the backend on port 8000, then refresh this page.";
  }
}


strategySelect.addEventListener("change", switchStrategy);
assetSelect.addEventListener("change", () => {
  if (strategySelect.value === "sma") loadSmaAsset(assetSelect.value);
});

initializeDashboard();
=======
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: getComputedStyle(document.documentElement).getPropertyValue("--muted").trim() } },
      },
      scales: {
        x: { ticks: { color: getComputedStyle(document.documentElement).getPropertyValue("--muted").trim() } },
        y: { ticks: { color: getComputedStyle(document.documentElement).getPropertyValue("--muted").trim() } },
      },
    },
  });

  state.charts.strategyMetrics = new Chart(els.strategyMetricsChart.getContext("2d"), {
    type: "bar",
    data: {
      labels: ["Return %", "Max Drawdown %", "Trades"],
      datasets: [
        {
          label: "MA Crossover",
          data: [ma.return_percent, ma.max_drawdown_percent, ma.total_operations],
          backgroundColor: "rgba(111,125,255,0.7)",
        },
        {
          label: "Weekly Mean Reversion",
          data: [weekly.return_percent, weekly.max_drawdown_percent, weekly.trade_count],
          backgroundColor: "rgba(53,215,168,0.7)",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: getComputedStyle(document.documentElement).getPropertyValue("--muted").trim() } },
        y: { ticks: { color: getComputedStyle(document.documentElement).getPropertyValue("--muted").trim() } },
      },
    },
  });
}

function resetForm() {
  els.assetSelect.value = state.assets[0] || "";
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
  els.strategyPerformancePanel.hidden = true;
  els.strategyComparisonChartPanel.hidden = true;
  els.strategyMetricsChartPanel.hidden = true;
  els.kpiRow.innerHTML = "";
  destroyCharts();
}

function bindEvents() {
  els.runBtn.addEventListener("click", runBacktest);
  els.resetBtn.addEventListener("click", resetForm);
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
  });
}

async function init() {
  setTheme("dark");
  bindEvents();
  await checkHealth();
  await loadAssets();
  setLoading(false);
  resetForm();
}

init();
=======
    document.getElementById("status").textContent = "backend: " + j.status;
  } catch (e) {
    document.getElementById("status").textContent = "backend not reachable — start uvicorn";
  }
}
checkHealth();
// TASK_02+ : fetch /prices and render a chart, etc.
>>>>>>> origin/main
>>>>>>> origin/Kanzy_Kabesh
