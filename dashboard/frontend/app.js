// Dashboard frontend for the EGX Strategy Lab.
const API = "http://localhost:8000";
const state = {
  assets: [],
  results: null,
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
    setBanner("Fast MA must be smaller than Fast MA.", "error");
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
    const r = await fetch(`${API}/backtest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await r.json();
    if (!r.ok) throw new Error(result.detail || "Backtest failed");
    state.results = result;
    renderResults(result);
    setBanner(`Backtest complete for ${result.symbol}.`, "success");
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

function resetForm() {
  els.assetSelect.value = state.assets[0] || "";
  els.initialCash.value = "1000";
  els.fastWindow.value = "9";
  els.slowWindow.value = "20";
  els.tradeSearch.value = "";
  els.tradeFilter.value = "ALL";
  els.tradeSort.value = "newest";
  state.results = null;
  els.resultsSection.hidden = true;
  els.emptyState.hidden = false;
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
