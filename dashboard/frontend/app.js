// Dashboard frontend. Grows via dashboard/tasks/.
const API = "http://localhost:8000";

// Both columns are the validated dataviz palette's categorical hues, light
// and dark steps of the SAME eight — not two different palettes. Status
// colors (good/critical/warning) are mode-invariant, so only one set.
const THEME_COLORS = {
  dark: { blue: "#3987e5", orange: "#d95926", aqua: "#199e70", yellow: "#c98500", magenta: "#d55181", green: "#008300", violet: "#9085e9", red: "#e66767", text: "#c3c2b7", grid: "#2c2c2a" },
  light: { blue: "#2a78d6", orange: "#eb6834", aqua: "#1baf7a", yellow: "#eda100", magenta: "#e87ba4", green: "#008300", violet: "#4a3aa7", red: "#e34948", text: "#52514e", grid: "#e1e0d9" },
};
const STATUS = { good: "#0ca30c", critical: "#d03b3b", warning: "#fab219" };

let COLOR = {};

function applyTheme(theme, { rerender = true } = {}) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("dashboard-theme", theme);
  COLOR = { ...THEME_COLORS[theme], ...STATUS };
  document.getElementById("themeIcon").textContent = theme === "dark" ? "🌙" : "☀️";
  document.getElementById("themeLabel").textContent = theme === "dark" ? "Dark" : "Light";
  if (rerender) rerenderAll();
}

// Drives both the single-select "Chart indicator" dropdown and what gets
// fetched/plotted. kind "overlay" draws on the price chart; kind
// "oscillator" gets the dedicated indicator panel (synced zoom with price).
const INDICATORS = [
  { key: "sma", label: "SMA", kind: "overlay",
    params: [{ name: "sma_window", label: "Period", default: 20, step: 1 }] },
  { key: "ema", label: "EMA", kind: "overlay",
    params: [{ name: "ema_window", label: "Period", default: 20, step: 1 }] },
  { key: "bb", label: "Bollinger Bands", kind: "overlay",
    params: [{ name: "bb_window", label: "Period", default: 20, step: 1 }, { name: "bb_std", label: "Std dev", default: 2, step: 0.1 }] },
  { key: "vwap", label: "VWAP", kind: "overlay",
    params: [{ name: "vwap_window", label: "Window", default: 20, step: 1 }] },
  { key: "ichimoku", label: "Ichimoku Cloud", kind: "overlay",
    params: [{ name: "ichimoku_tenkan", label: "Tenkan", default: 9, step: 1 }, { name: "ichimoku_kijun", label: "Kijun", default: 26, step: 1 }, { name: "ichimoku_senkou_b", label: "Senkou B", default: 52, step: 1 }] },
  { key: "psar", label: "Parabolic SAR", kind: "overlay",
    params: [{ name: "psar_step", label: "Step", default: 0.02, step: 0.01 }, { name: "psar_max", label: "Max step", default: 0.2, step: 0.01 }] },

  { key: "rsi", label: "RSI", kind: "oscillator",
    params: [{ name: "rsi_window", label: "Period", default: 14, step: 1 }] },
  { key: "macd", label: "MACD", kind: "oscillator",
    params: [{ name: "macd_fast", label: "Fast", default: 12, step: 1 }, { name: "macd_slow", label: "Slow", default: 26, step: 1 }, { name: "macd_signal", label: "Signal", default: 9, step: 1 }] },
  { key: "stoch", label: "Stochastic", kind: "oscillator",
    params: [{ name: "stoch_k", label: "%K", default: 14, step: 1 }, { name: "stoch_d", label: "%D", default: 3, step: 1 }] },
  { key: "atr", label: "ATR", kind: "oscillator",
    params: [{ name: "atr_window", label: "Period", default: 14, step: 1 }] },
  { key: "adx", label: "ADX", kind: "oscillator",
    params: [{ name: "adx_window", label: "Period", default: 14, step: 1 }] },
  { key: "obv", label: "OBV", kind: "oscillator", params: [] },
];
const DEFAULT_INDICATOR_KEY = "rsi";

const charts = {};        // name -> Chart instance, so we can destroy() before redraw
const state = {
  universe: "small", // TASK_05: "small" (6-stock teaching set) or "full" (all of data/egx)
  symbols: [], latestBacktest: null, latestIndicators: null, latestSymbol: null,
  latestForecast: null, latestCompareSymbols: null, latestComparePrices: null, latestCompareRiskReward: null,
  latestBaseline: null, latestStrategyComparison: null,
  runHistory: [], chatHistory: [],
};

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

async function checkHealth() {
  try {
    const j = await fetchJSON(`${API}/health`);
    document.getElementById("status").textContent = "backend: " + j.status;
  } catch (e) {
    document.getElementById("status").textContent = "backend not reachable — start uvicorn";
  }
}

function destroy(name) {
  if (charts[name]) { charts[name].destroy(); delete charts[name]; }
}

// `syncWith` names another entry in `charts` (by key) whose x-scale should
// track this chart's zoom/pan, and vice versa — used to keep the price
// chart and the indicator subplot moving together. The callback is baked
// into the options at chart-CREATION time and resolves its target from the
// live `charts` registry on every call, rather than being mutated onto
// `chart.options` after construction — chartjs-plugin-zoom resolves these
// handlers once at setup, so a post-hoc mutation is silently ignored.
function zoomSyncHandler(syncWith) {
  if (!syncWith) return undefined;
  return ({ chart }) => {
    const target = charts[syncWith];
    if (!target || chart._zoomSyncGuard) return;
    target._zoomSyncGuard = true;
    target.zoomScale("x", { min: chart.scales.x.min, max: chart.scales.x.max }, "none");
    target._zoomSyncGuard = false;
  };
}

function gridOptions({ syncWith } = {}) {
  const onComplete = zoomSyncHandler(syncWith);
  return {
    scales: {
      x: { ticks: { color: COLOR.text, maxTicksLimit: 10 }, grid: { color: COLOR.grid } },
      y: { ticks: { color: COLOR.text }, grid: { color: COLOR.grid } },
    },
    plugins: {
      legend: { labels: { color: COLOR.text } },
      tooltip: { mode: "index", intersect: false },
      zoom: {
        pan: { enabled: true, mode: "x", onPanComplete: onComplete },
        zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: "x", onZoomComplete: onComplete },
      },
    },
    interaction: { mode: "index", intersect: false },
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
  };
}

function resetAllZoom() {
  Object.values(charts).forEach((c) => { if (c.resetZoom) c.resetZoom(); });
}

function fieldLabel(f) {
  return { close: "Close", open: "Open", high: "High", low: "Low" }[f] || f;
}
function pct(v, digits = 2) { return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`; }
function egp(v) { return v.toLocaleString(undefined, { maximumFractionDigits: 2 }); }

// -------------------------------------------------------- indicator UI ----

function currentIndicator() {
  const key = document.getElementById("indicatorSelect").value;
  return INDICATORS.find((i) => i.key === key);
}

function paramValue(name) {
  const el = document.getElementById(`param_${name}`);
  return el ? el.value : undefined;
}

function indicatorParamValues() {
  const values = {};
  currentIndicator().params.forEach((p) => { values[p.name] = paramValue(p.name); });
  return values;
}

function buildIndicatorSelect() {
  const select = document.getElementById("indicatorSelect");
  select.innerHTML = INDICATORS.map((i) => `<option value="${i.key}">${i.label} (${i.kind})</option>`).join("");
  select.value = DEFAULT_INDICATOR_KEY;
  select.addEventListener("change", () => { renderIndicatorParamInputs(); runSimulation(); });
  renderIndicatorParamInputs();
}

function renderIndicatorParamInputs() {
  const ind = currentIndicator();
  const container = document.getElementById("indicatorParams");
  container.innerHTML = ind.params
    .map((p) => `
      <div class="param">
        <label for="param_${p.name}">${p.label}</label>
        <input type="number" id="param_${p.name}" value="${p.default}" step="${p.step}"/>
      </div>`)
    .join("");
  container.querySelectorAll("input").forEach((el) => el.addEventListener("change", runSimulation));
}

// ---------------------------------------------------------------- init ----

async function init() {
  applyTheme(document.documentElement.getAttribute("data-theme") || "dark", { rerender: false });
  document.getElementById("themeToggle").addEventListener("click", () => {
    applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
  });

  loadRunHistory();
  await checkHealth();
  buildIndicatorSelect();

  state.symbols = await fetchJSON(`${API}/universe?${new URLSearchParams({ universe: state.universe })}`);

  const select = document.getElementById("symbolSelect");
  select.innerHTML = state.symbols.map((s) => `<option value="${s}">${s}</option>`).join("");
  select.value = state.symbols.includes("COMI") ? "COMI" : state.symbols[0];

  document.getElementById("compareInput").value = state.symbols.slice(0, 3).join(",");

  const priceInfo = await fetchJSON(`${API}/prices/${select.value}?${new URLSearchParams({ universe: state.universe })}`);
  document.getElementById("startDate").value = priceInfo.dates[0];
  document.getElementById("endDate").value = priceInfo.dates[priceInfo.dates.length - 1];

  document.getElementById("runButton").addEventListener("click", runSimulation);
  document.getElementById("exportButton").addEventListener("click", exportCSV);
  document.getElementById("compareButton").addEventListener("click", runComparison);
  document.getElementById("fieldSelect").addEventListener("change", runSimulation);
  document.getElementById("resetZoomButton").addEventListener("click", resetAllZoom);
  document.getElementById("clearHistoryButton").addEventListener("click", clearRunHistory);
  document.getElementById("runHistoryBody").addEventListener("click", (e) => {
    if (e.target.matches(".delete-run")) deleteRun(Number(e.target.dataset.id));
  });
  document.getElementById("universeToggle").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-universe]");
    if (!btn || btn.classList.contains("active")) return;
    applyUniverse(btn.dataset.universe);
  });
  ["toggleMaFast", "toggleMaSlow"].forEach((id) =>
    document.getElementById(id).addEventListener("change", () => {
      renderPriceChart(state.latestBacktest, state.latestIndicators);
    })
  );

  document.getElementById("newsRefreshButton").addEventListener("click", () => {
    loadNews(document.getElementById("symbolSelect").value, true);
  });
  initChatWidget();

  // Each panel's startup fetch is independent — one backend failure (e.g. a
  // strategy checkpoint mismatch) shouldn't take the rest of the page down
  // with it, and MUST NOT prevent initTabs() from running below, or every
  // tab (including ones with no connection to the failure) becomes
  // permanently unclickable for the rest of the session.
  for (const fn of [runSimulation, runBaselineEquity, runStrategyComparison, runComparison]) {
    try {
      await fn();
    } catch (e) {
      console.error(`${fn.name} failed during init:`, e);
    }
  }

  initTabs();
}

// ----------------------------------------------------------------- tabs ----
// Simulator's data loads eagerly above (it's the default tab); the other
// three tabs load lazily, the first time you switch to them, so opening the
// dashboard doesn't pay for four tabs' worth of fetches up front.
function initTabs() {
  document.getElementById("tabBar").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-tab]");
    if (!btn) return;
    const tab = btn.dataset.tab;
    document.querySelectorAll("#tabBar button").forEach((b) => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));

    if (tab === "models" && !state.modelsInitialized) { state.modelsInitialized = true; initModelComparison(); }
    if (tab === "strategies" && !state.strategiesInitialized) { state.strategiesInitialized = true; initStrategiesTab(); }
    if (tab === "performance" && !state.performanceInitialized) { state.performanceInitialized = true; loadPerformanceResults(); }
    if (tab === "game" && !state.gameInitialized) { state.gameInitialized = true; initGame(); }
  });
}

// TASK_05 universe toggle: switching re-fetches /universe (so the symbol
// dropdown reflects the new list), then re-runs every panel that depends on
// a universe-scoped endpoint — the single-asset simulator (whose valid
// symbols come from the selected universe), the Notebook 4 baseline equity
// curve, the strategy comparison, and the asset-comparison panel.
async function applyUniverse(newUniverse) {
  state.universe = newUniverse;
  document.querySelectorAll("#universeToggle button").forEach((b) => {
    b.classList.toggle("active", b.dataset.universe === newUniverse);
  });

  const previousSymbol = document.getElementById("symbolSelect").value;
  state.symbols = await fetchJSON(`${API}/universe?${new URLSearchParams({ universe: newUniverse })}`);

  const select = document.getElementById("symbolSelect");
  select.innerHTML = state.symbols.map((s) => `<option value="${s}">${s}</option>`).join("");
  select.value = state.symbols.includes(previousSymbol)
    ? previousSymbol
    : (state.symbols.includes("COMI") ? "COMI" : state.symbols[0]);

  document.getElementById("compareInput").value = state.symbols.slice(0, 3).join(",");

  await runSimulation();
  await runBaselineEquity();
  await runStrategyComparison();
  await runComparison();
}

function rerenderAll() {
  if (state.latestBacktest) {
    renderKPIs(state.latestBacktest.kpis);
    renderAlert(state.latestBacktest.alert, document.getElementById("fastInput").value, document.getElementById("slowInput").value);
    renderPriceChart(state.latestBacktest, state.latestIndicators);
    renderIndicatorPanel(state.latestIndicators);
    renderSingleAssetEquityChart(state.latestBacktest);
    renderTradeFeed(state.latestBacktest.buy_signals, state.latestBacktest.sell_signals);
  }
  if (state.latestBaseline) drawBaselineEquityChart(state.latestBaseline);
  if (state.latestStrategyComparison) {
    drawStrategyComparisonChart(state.latestStrategyComparison);
    renderStrategyMetrics(state.latestStrategyComparison);
  }
  if (state.latestForecast) drawForecastChart(state.latestForecast);
  if (state.latestCompareSymbols) drawCompareCharts();
  renderRunHistory();
}

// ------------------------------------------------------------ simulator ----

async function runSimulation() {
  const symbol = document.getElementById("symbolSelect").value;
  const field = document.getElementById("fieldSelect").value;
  const start = document.getElementById("startDate").value;
  const end = document.getElementById("endDate").value;
  const fast = document.getElementById("fastInput").value;
  const slow = document.getElementById("slowInput").value;
  const capital = document.getElementById("capitalInput").value;
  const indicator = currentIndicator();
  const indicatorParams = indicatorParamValues();

  const btParams = new URLSearchParams({ symbol, universe: state.universe, field, fast, slow, capital, start, end });
  const indParams = new URLSearchParams({ universe: state.universe, field, start, end, ...indicatorParams });
  const [backtest, indicators] = await Promise.all([
    fetchJSON(`${API}/backtest/single?${btParams}`),
    fetchJSON(`${API}/indicators/${symbol}?${indParams}`),
  ]);

  const symbolChanged = state.latestSymbol !== symbol;
  state.latestBacktest = backtest;
  state.latestIndicators = indicators;
  state.latestSymbol = symbol;
  if (symbolChanged) loadNews(symbol); // cached server-side, cheap to skip when unchanged

  renderFieldNote(field, backtest.field);
  renderKPIs(backtest.kpis);
  renderAlert(backtest.alert, fast, slow);
  renderPriceChart(backtest, indicators);
  renderIndicatorPanel(indicators);
  renderSingleAssetEquityChart(backtest);
  renderTradeFeed(backtest.buy_signals, backtest.sell_signals);
  await renderForecast(symbol, field);

  recordRun({ symbol, field: backtest.field, fast, slow, indicator, indicatorParams, kpis: backtest.kpis });
}

function renderFieldNote(requestedField, resolvedField) {
  const note = document.getElementById("fieldNote");
  if (requestedField === "adj_close" && resolvedField === "close") {
    note.textContent = "No adjusted-close data available for this asset — using Close instead.";
    note.style.display = "block";
  } else {
    note.style.display = "none";
  }
}

function renderKPIs(k) {
  const cards = [
    { label: "Current price", value: `${k.current_price.toFixed(2)} EGP`, sub: pct(k.daily_change_pct) + " today", cls: k.daily_change_pct >= 0 ? "good" : "critical" },
    { label: "Portfolio value", value: `${egp(k.final_value)} EGP`, sub: `Buy & hold: ${egp(k.buy_and_hold_final_value)} EGP` },
    { label: "Total return", value: pct(k.total_return_pct), cls: k.total_return_pct >= 0 ? "good" : "critical" },
    { label: "Max drawdown", value: `-${k.max_drawdown_pct.toFixed(2)}%`, cls: "critical" },
    { label: "Win rate", value: `${k.win_rate_pct.toFixed(1)}%`, sub: `${k.num_sells} closed trades` },
    { label: "Buy / sell ops", value: `${k.num_buys} / ${k.num_sells}` },
    { label: "Sharpe ratio", value: k.sharpe.toFixed(2) },
    { label: "Avg holding period", value: `${k.avg_holding_days.toFixed(1)} days` },
    { label: "Volatility (ann.)", value: `${k.volatility_pct.toFixed(1)}%` },
    { label: "Expected return (ann.)", value: pct(k.expected_return_pct), cls: k.expected_return_pct >= 0 ? "good" : "critical" },
  ];

  document.getElementById("kpiGrid").innerHTML = cards
    .map((c) => `
      <div class="kpi-card">
        <div class="label">${c.label}</div>
        <div class="value ${c.cls || ""}">${c.value}</div>
        ${c.sub ? `<div class="sub">${c.sub}</div>` : ""}
      </div>`)
    .join("");
}

function renderAlert(alert, fast, slow) {
  const banner = document.getElementById("alertBanner");
  if (!alert || !alert.active) { banner.style.display = "none"; return; }
  const word = alert.direction === "golden" ? "golden cross (buy)" : "death cross (sell)";
  document.getElementById("alertText").textContent =
    `MA${fast} and MA${slow} are converging — a ${word} may be imminent (~${alert.distance_pct.toFixed(2)}% apart).`;
  banner.style.display = "flex";
}

function overlayDatasetsFor(indicator, ind) {
  switch (indicator.key) {
    case "sma":
      return [{ label: `SMA(${paramValue("sma_window")})`, data: ind.sma, borderColor: COLOR.yellow, borderWidth: 1.5, pointRadius: 0, order: 3 }];
    case "ema":
      return [{ label: `EMA(${paramValue("ema_window")})`, data: ind.ema, borderColor: COLOR.magenta, borderWidth: 1.5, pointRadius: 0, order: 3 }];
    case "bb":
      return [
        { label: "BB upper", data: ind.bb_upper, borderColor: COLOR.violet, borderWidth: 1, borderDash: [4, 3], pointRadius: 0, fill: false, order: 2 },
        { label: "BB lower", data: ind.bb_lower, borderColor: COLOR.violet, borderWidth: 1, borderDash: [4, 3], pointRadius: 0, fill: "-1", backgroundColor: "rgba(144,133,233,0.10)", order: 2 },
      ];
    case "vwap":
      return [{ label: `VWAP(${paramValue("vwap_window")})`, data: ind.vwap, borderColor: COLOR.green, borderWidth: 1.5, borderDash: [2, 2], pointRadius: 0, order: 3 }];
    case "ichimoku":
      return [
        { label: "Tenkan-sen", data: ind.ichimoku_tenkan, borderColor: COLOR.red, borderWidth: 1, pointRadius: 0, order: 3 },
        { label: "Kijun-sen", data: ind.ichimoku_kijun, borderColor: COLOR.green, borderWidth: 1, pointRadius: 0, order: 3 },
        { label: "Senkou A", data: ind.ichimoku_senkou_a, borderColor: "rgba(144,133,233,0.5)", borderWidth: 1, pointRadius: 0, fill: false, order: 2 },
        { label: "Senkou B (cloud)", data: ind.ichimoku_senkou_b, borderColor: "rgba(144,133,233,0.5)", borderWidth: 1, pointRadius: 0, fill: "-1", backgroundColor: "rgba(144,133,233,0.12)", order: 2 },
      ];
    case "psar":
      return [{ label: "Parabolic SAR", data: ind.psar, showLine: false, pointStyle: "circle", pointRadius: 2.5, pointBackgroundColor: COLOR.magenta, pointBorderColor: COLOR.magenta, order: 1 }];
    default:
      return [];
  }
}

function renderPriceChart(bt, ind) {
  if (!bt) return;
  destroy("price");

  const datasets = [
    { label: `Price (${fieldLabel(bt.field)})`, data: bt.close, borderColor: COLOR.blue, borderWidth: 2, pointRadius: 0, order: 5 },
  ];

  if (document.getElementById("toggleMaFast").checked) {
    datasets.push({ label: "MA fast (strategy)", data: bt.ma_fast, borderColor: COLOR.orange, borderWidth: 1.5, pointRadius: 0, order: 4 });
  }
  if (document.getElementById("toggleMaSlow").checked) {
    datasets.push({ label: "MA slow (strategy)", data: bt.ma_slow, borderColor: COLOR.aqua, borderWidth: 1.5, pointRadius: 0, order: 4 });
  }

  const active = currentIndicator();
  if (ind && active && active.kind === "overlay") {
    datasets.push(...overlayDatasetsFor(active, ind));
  }

  const buyDates = new Set(bt.buy_signals.map((s) => s.date));
  const sellDates = new Set(bt.sell_signals.map((s) => s.date));
  const buyData = bt.dates.map((d, i) => (buyDates.has(d) ? bt.close[i] : null));
  const sellData = bt.dates.map((d, i) => (sellDates.has(d) ? bt.close[i] : null));
  datasets.push({ label: "Buy", data: buyData, showLine: false, pointStyle: "triangle", pointRadius: 7, pointBackgroundColor: COLOR.good, pointBorderColor: COLOR.good, order: 1 });
  datasets.push({ label: "Sell", data: sellData, showLine: false, pointStyle: "triangle", pointRotation: 180, pointRadius: 7, pointBackgroundColor: COLOR.critical, pointBorderColor: COLOR.critical, order: 1 });

  charts.price = new Chart(document.getElementById("priceChart"), {
    type: "line",
    data: { labels: bt.dates, datasets },
    options: gridOptions({ syncWith: "indicatorPanel" }),
  });
}

function renderSingleAssetEquityChart(bt) {
  if (!bt) return;
  destroy("singleAssetEquity");
  charts.singleAssetEquity = new Chart(document.getElementById("singleAssetEquityChart"), {
    type: "line",
    data: {
      labels: bt.dates,
      datasets: [
        { label: "MA crossover strategy", data: bt.portfolio_value, borderColor: COLOR.blue, borderWidth: 2, pointRadius: 0 },
        { label: "Buy & hold", data: bt.buy_and_hold_value, borderColor: COLOR.orange, borderWidth: 2, pointRadius: 0 },
      ],
    },
    options: gridOptions(),
  });
}

// ----------------------------------------------- Notebook 4 baseline (TASK_05) ----

async function runBaselineEquity() {
  const bt = await fetchJSON(`${API}/backtest?${new URLSearchParams({ universe: state.universe, strategy: "sma" })}`);
  state.latestBaseline = bt;
  drawBaselineEquityChart(bt);
}

function drawBaselineEquityChart(bt) {
  destroy("equity");
  charts.equity = new Chart(document.getElementById("equityChart"), {
    type: "line",
    data: {
      labels: bt.dates,
      datasets: [
        { label: bt.strategy_label, data: bt.portfolio, borderColor: COLOR.blue, borderWidth: 2, pointRadius: 0 },
        { label: "Benchmark (equal-weight)", data: bt.benchmark, borderColor: COLOR.orange, borderWidth: 2, pointRadius: 0 },
      ],
    },
    options: gridOptions(),
  });
  document.getElementById("baselineUniverseNote").textContent =
    `Universe: ${state.universe === "small" ? "Small (6 stocks)" : `Full (${state.symbols.length} stocks)`}. Both lines start at 1.0.`;
}

// ------------------------------------------- strategy comparison (TASK_05) ----

// Notebook 4 baseline (SMA), MPT, HFT mean-reversion, and LSTM (trained in
// lstm.ipynb, loaded by main.py if models/lstm_dashboard.pt exists) — all
// four share the same /backtest + /metrics shape (see main.py), so the
// comparison section iterates this list instead of hardcoding entries.
// Colors are looked up from COLOR (a color KEY, not a resolved hex) at draw
// time, not baked in here — this array is built once at module-load, before
// applyTheme() has run, when COLOR is still {}.
const COMPARISON_STRATEGIES = [
  { key: "sma", colorKey: "blue" },
  { key: "mpt", colorKey: "violet" },
  { key: "hft_mean_reversion", colorKey: "magenta" },
  { key: "lstm", colorKey: "aqua" },
];

async function runStrategyComparison() {
  const common = { universe: state.universe };
  const results = await Promise.all(
    COMPARISON_STRATEGIES.map(({ key }) =>
      Promise.all([
        fetchJSON(`${API}/backtest?${new URLSearchParams({ ...common, strategy: key })}`),
        fetchJSON(`${API}/metrics?${new URLSearchParams({ ...common, strategy: key })}`),
      ])
    )
  );
  state.latestStrategyComparison = COMPARISON_STRATEGIES.map(({ key, colorKey }, i) => ({
    key, colorKey, bt: results[i][0], metrics: results[i][1],
  }));
  drawStrategyComparisonChart(state.latestStrategyComparison);
  renderStrategyMetrics(state.latestStrategyComparison);
}

function drawStrategyComparisonChart(strategies) {
  destroy("strategyComparison");
  const datasets = strategies.map((s) => ({
    label: s.bt.strategy_label, data: s.bt.portfolio, borderColor: COLOR[s.colorKey], borderWidth: 2, pointRadius: 0,
  }));
  datasets.push({
    label: "Benchmark (equal-weight)", data: strategies[0].bt.benchmark,
    borderColor: COLOR.orange, borderWidth: 2, borderDash: [4, 3], pointRadius: 0,
  });
  // Log scale: HFT's tiny fixed-notional trades keep it near 1.0x while SMA/MPT
  // can run into the tens-of-x — on a linear axis HFT and the benchmark
  // flatten into an indistinguishable line at the bottom. Still one axis
  // (not a dual-axis chart), just log-scaled so all three stay readable.
  const options = gridOptions();
  charts.strategyComparison = new Chart(document.getElementById("strategyComparisonChart"), {
    type: "line",
    data: { labels: strategies[0].bt.dates, datasets },
    options: { ...options, scales: { ...options.scales, y: { ...options.scales.y, type: "logarithmic" } } },
  });
}

function renderStrategyMetrics(strategies) {
  document.getElementById("strategyMetricsGrid").innerHTML = strategies
    .map(({ metrics: m }) => {
      // Only the HFT strategy has discrete trades to win/lose — SMA and MPT
      // rebalance continuous weights daily and never "close a trade". And by
      // construction HFT's exit only fires at/above the pre-drop reference
      // price, so every CLOSED trade wins; the real risk is entirely in
      // positions still open (see the disclaimer above the chart).
      const tradeInfo = m.win_rate_pct === undefined ? "" :
        `<div class="sub">${m.win_rate_pct.toFixed(0)}% of ${m.num_trades_closed} closed trades won · ${m.num_positions_open_at_end} still open, unrecovered</div>`;
      return `
      <div class="kpi-card">
        <div class="label">${m.strategy_label}</div>
        <div class="value ${m.total_return >= 0 ? "good" : "critical"}">${pct(m.total_return * 100)}</div>
        <div class="sub">Sharpe ${m.sharpe.toFixed(2)} · Max drawdown -${(m.max_drawdown * 100).toFixed(1)}%</div>
        ${tradeInfo}
      </div>`;
    })
    .join("");
}

// ------------------------------------------------------- indicator panel ----

function oscillatorChartConfig(key, ind) {
  const options = gridOptions({ syncWith: "price" });
  const flat = (value) => ind.dates.map(() => value);
  switch (key) {
    case "rsi":
      return {
        datasets: [
          { label: `RSI(${paramValue("rsi_window")})`, data: ind.rsi, borderColor: COLOR.yellow, borderWidth: 1.5, pointRadius: 0 },
          { label: "Overbought", data: flat(70), borderColor: COLOR.critical, borderWidth: 1, borderDash: [3, 3], pointRadius: 0 },
          { label: "Oversold", data: flat(30), borderColor: COLOR.good, borderWidth: 1, borderDash: [3, 3], pointRadius: 0 },
        ],
        options: { ...options, scales: { ...options.scales, y: { ...options.scales.y, min: 0, max: 100 } } },
      };
    case "macd":
      return {
        datasets: [
          { label: "MACD", data: ind.macd_line, borderColor: COLOR.blue, borderWidth: 1.5, pointRadius: 0 },
          { label: "Signal", data: ind.macd_signal, borderColor: COLOR.orange, borderWidth: 1.5, pointRadius: 0 },
        ],
        options,
      };
    case "stoch":
      return {
        datasets: [
          { label: "%K", data: ind.stoch_k, borderColor: COLOR.aqua, borderWidth: 1.5, pointRadius: 0 },
          { label: "%D", data: ind.stoch_d, borderColor: COLOR.orange, borderWidth: 1.5, pointRadius: 0 },
          { label: "Overbought", data: flat(80), borderColor: COLOR.critical, borderWidth: 1, borderDash: [3, 3], pointRadius: 0 },
          { label: "Oversold", data: flat(20), borderColor: COLOR.good, borderWidth: 1, borderDash: [3, 3], pointRadius: 0 },
        ],
        options: { ...options, scales: { ...options.scales, y: { ...options.scales.y, min: 0, max: 100 } } },
      };
    case "atr":
      return { datasets: [{ label: `ATR(${paramValue("atr_window")})`, data: ind.atr, borderColor: COLOR.orange, borderWidth: 1.5, pointRadius: 0 }], options };
    case "adx":
      return {
        datasets: [
          { label: "ADX", data: ind.adx, borderColor: COLOR.violet, borderWidth: 1.5, pointRadius: 0 },
          { label: "+DI", data: ind.plus_di, borderColor: COLOR.good, borderWidth: 1, pointRadius: 0 },
          { label: "-DI", data: ind.minus_di, borderColor: COLOR.critical, borderWidth: 1, pointRadius: 0 },
        ],
        options,
      };
    case "obv":
      return { datasets: [{ label: "OBV", data: ind.obv, borderColor: COLOR.green, borderWidth: 1.5, pointRadius: 0 }], options };
    default:
      return null;
  }
}

function renderIndicatorPanel(ind) {
  const wrap = document.getElementById("indicatorPanelWrap");
  destroy("indicatorPanel");

  const active = currentIndicator();
  if (!ind || !active || active.kind !== "oscillator") {
    wrap.style.display = "none";
    return;
  }
  wrap.style.display = "block";
  document.getElementById("indicatorPanelTitle").textContent = active.label;

  const cfg = oscillatorChartConfig(active.key, ind);
  charts.indicatorPanel = new Chart(document.getElementById("indicatorPanelChart"), {
    type: "line",
    data: { labels: ind.dates, datasets: cfg.datasets },
    options: cfg.options,
  });
}

function renderTradeFeed(buySignals, sellSignals) {
  const rows = [
    ...buySignals.map((s) => ({ ...s, action: "buy" })),
    ...sellSignals.map((s) => ({ ...s, action: "sell" })),
  ].sort((a, b) => (a.date < b.date ? 1 : -1)); // most recent first

  document.getElementById("tradeFeedBody").innerHTML = rows
    .map((r) => `
      <tr>
        <td>${r.date}</td>
        <td class="action-${r.action}">${r.action.toUpperCase()}</td>
        <td>${r.price.toFixed(2)}</td>
        <td>${egp(r.portfolio_value)}</td>
      </tr>`)
    .join("") || `<tr><td colspan="4" class="empty-note">No trades in this window.</td></tr>`;
}

function exportCSV() {
  const bt = state.latestBacktest;
  if (!bt) return;

  const lines = ["metric,value"];
  Object.entries(bt.kpis).forEach(([k, v]) => lines.push(`${k},${v}`));
  lines.push("");
  lines.push("buy_date,buy_price,sell_date,sell_price,holding_days,return_pct,win,open");
  bt.trades.forEach((t) =>
    lines.push([t.buy_date, t.buy_price, t.sell_date ?? "", t.sell_price ?? "", t.holding_days, t.return_pct, t.win, t.open].join(","))
  );

  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `backtest_${state.latestSymbol}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ----------------------------------------------------------- run history ----

const RUN_HISTORY_KEY = "dashboard-run-history";

function loadRunHistory() {
  try {
    state.runHistory = JSON.parse(localStorage.getItem(RUN_HISTORY_KEY) || "[]");
  } catch (e) {
    state.runHistory = [];
  }
  renderRunHistory();
}

function saveRunHistory() {
  localStorage.setItem(RUN_HISTORY_KEY, JSON.stringify(state.runHistory.slice(0, 100)));
}

function recordRun({ symbol, field, fast, slow, indicator, indicatorParams, kpis }) {
  const paramsSummary = indicator.params.map((p) => `${p.label}=${indicatorParams[p.name]}`).join(", ") || "—";
  state.runHistory.unshift({
    id: Date.now(),
    time: new Date().toLocaleString(),
    symbol, field, fast, slow,
    indicatorLabel: indicator.label,
    paramsSummary,
    final_value: kpis.final_value,
    total_return_pct: kpis.total_return_pct,
    max_drawdown_pct: kpis.max_drawdown_pct,
    win_rate_pct: kpis.win_rate_pct,
    sharpe: kpis.sharpe,
  });
  saveRunHistory();
  renderRunHistory();
}

function deleteRun(id) {
  state.runHistory = state.runHistory.filter((r) => r.id !== id);
  saveRunHistory();
  renderRunHistory();
}

function clearRunHistory() {
  state.runHistory = [];
  saveRunHistory();
  renderRunHistory();
}

function renderRunHistory() {
  const body = document.getElementById("runHistoryBody");
  if (!body) return;
  body.innerHTML = state.runHistory
    .map((r) => `
      <tr>
        <td>${r.time}</td>
        <td>${r.symbol}</td>
        <td>${fieldLabel(r.field)}</td>
        <td>${r.indicatorLabel}<br/><span style="color:var(--text-muted);font-size:0.75rem">${r.paramsSummary}</span></td>
        <td>${r.fast}/${r.slow}</td>
        <td>${egp(r.final_value)} EGP</td>
        <td class="${r.total_return_pct >= 0 ? "action-buy" : "action-sell"}">${pct(r.total_return_pct)}</td>
        <td>-${r.max_drawdown_pct.toFixed(2)}%</td>
        <td>${r.win_rate_pct.toFixed(1)}%</td>
        <td>${r.sharpe.toFixed(2)}</td>
        <td><button class="delete-run" data-id="${r.id}" title="Delete this run">✕</button></td>
      </tr>`)
    .join("") || `<tr><td colspan="11" class="empty-note">No runs yet — click "Run simulator" above.</td></tr>`;
}

// -------------------------------------------------------------- forecast ----

async function renderForecast(symbol, field) {
  const fc = await fetchJSON(`${API}/forecast/${symbol}?${new URLSearchParams({ universe: state.universe, field, years: 3 })}`);
  state.latestForecast = fc;
  drawForecastChart(fc);
}

function drawForecastChart(fc) {
  destroy("forecast");

  const histDates = fc.history.dates.slice(-500);
  const histClose = fc.history.close.slice(-500);
  const labels = [...histDates, ...fc.forecast.dates];
  const pad = (arr) => new Array(histDates.length - 1).fill(null).concat(arr);

  charts.forecast = new Chart(document.getElementById("forecastChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: `History (${fieldLabel(fc.field)})`, data: [...histClose, ...new Array(fc.forecast.dates.length).fill(null)], borderColor: COLOR.blue, borderWidth: 2, pointRadius: 0 },
        { label: "Projected (median)", data: pad([histClose[histClose.length - 1], ...fc.forecast.median]), borderColor: COLOR.orange, borderDash: [6, 4], borderWidth: 2, pointRadius: 0 },
        { label: "Upper (80% band)", data: pad([histClose[histClose.length - 1], ...fc.forecast.upper]), borderColor: "rgba(144,133,233,0.4)", borderWidth: 1, pointRadius: 0, fill: false },
        { label: "Lower (80% band)", data: pad([histClose[histClose.length - 1], ...fc.forecast.lower]), borderColor: "rgba(144,133,233,0.4)", borderWidth: 1, pointRadius: 0, fill: "-1", backgroundColor: "rgba(144,133,233,0.12)" },
      ],
    },
    options: gridOptions(),
  });

  document.getElementById("forecastDisclaimer").textContent =
    `${fc.disclaimer} Fitted drift ${pct(fc.annualized_drift_pct)}/yr, volatility ${fc.annualized_volatility_pct.toFixed(1)}%/yr, ${(fc.confidence * 100).toFixed(0)}% band shown.`;
}

// --------------------------------------------------------- comparison ----

async function runComparison() {
  const symbols = document
    .getElementById("compareInput")
    .value.split(",")
    .map((s) => s.trim().toUpperCase())
    .filter((s) => state.symbols.includes(s))
    .slice(0, 3);
  if (symbols.length === 0) return;

  const priceSeries = await Promise.all(
    symbols.map((s) => fetchJSON(`${API}/prices/${s}?${new URLSearchParams({ universe: state.universe })}`))
  );
  const riskReward = await Promise.all(
    symbols.map((s) =>
      fetchJSON(`${API}/backtest/single?${new URLSearchParams({ symbol: s, universe: state.universe, fast: 9, slow: 20, capital: 1000 })}`)
    )
  );

  state.latestCompareSymbols = symbols;
  state.latestComparePrices = priceSeries;
  state.latestCompareRiskReward = riskReward;
  drawCompareCharts();
}

function drawCompareCharts() {
  const symbols = state.latestCompareSymbols;
  const priceSeries = state.latestComparePrices;
  const riskReward = state.latestCompareRiskReward;
  const colors = [COLOR.blue, COLOR.orange, COLOR.aqua];

  // Symbols can have different trading calendars (different listing dates,
  // holidays) — plotting each against a shared label array by index would
  // silently misalign dates. Intersect the calendars first, same approach
  // DataFeed.from_dir uses server-side for the multi-asset universe.
  const dateSets = priceSeries.map((p) => new Set(p.dates));
  const commonDates = priceSeries[0].dates.filter((d) => dateSets.every((s) => s.has(d))).sort();

  destroy("compare");
  charts.compare = new Chart(document.getElementById("compareChart"), {
    type: "line",
    data: {
      labels: commonDates,
      datasets: priceSeries.map((p, i) => {
        const closeByDate = new Map(p.dates.map((d, idx) => [d, p.close[idx]]));
        const base = closeByDate.get(commonDates[0]);
        return {
          label: symbols[i],
          data: commonDates.map((d) => (closeByDate.get(d) / base - 1) * 100),
          borderColor: colors[i],
          borderWidth: 2,
          pointRadius: 0,
        };
      }),
    },
    options: gridOptions(),
  });

  destroy("riskReward");
  const options = gridOptions();
  charts.riskReward = new Chart(document.getElementById("riskRewardChart"), {
    type: "scatter",
    data: {
      datasets: riskReward.map((r, i) => ({
        label: symbols[i],
        data: [{ x: r.kpis.volatility_pct, y: r.kpis.expected_return_pct }],
        backgroundColor: colors[i],
        pointRadius: 8,
      })),
    },
    options: {
      ...options,
      scales: {
        x: { ...options.scales.x, type: "linear", title: { display: true, text: "Volatility % (annualized)", color: COLOR.text } },
        y: { ...options.scales.y, type: "linear", title: { display: true, text: "Expected return % (annualized)", color: COLOR.text } },
      },
      interaction: { mode: "point" },
    },
  });
}

// ======================================================= model comparison ==

async function initModelComparison() {
  state.models = await fetchJSON(`${API}/models`);

  const modelSelect = document.getElementById("modelSelect");
  modelSelect.innerHTML = state.models.map((m) => `<option value="${m.key}">${m.label}</option>`).join("");
  modelSelect.addEventListener("change", () => { populateModelSymbols(); runModelComparison(); });

  document.getElementById("modelSymbolSelect").addEventListener("change", runModelComparison);
  document.getElementById("runModelButton").addEventListener("click", runModelComparison);

  populateModelSymbols();
  await runModelComparison();
}

function populateModelSymbols() {
  const modelKey = document.getElementById("modelSelect").value;
  const model = state.models.find((m) => m.key === modelKey);
  const select = document.getElementById("modelSymbolSelect");
  const previous = select.value;
  select.innerHTML = model.symbols.map((s) => `<option value="${s}">${s}</option>`).join("");
  select.value = model.symbols.includes(previous) ? previous : (model.symbols.includes("COMI") ? "COMI" : model.symbols[0]);
}

async function runModelComparison() {
  const modelKey = document.getElementById("modelSelect").value;
  const symbol = document.getElementById("modelSymbolSelect").value;
  const capital = document.getElementById("modelCapitalInput").value;

  const data = await fetchJSON(`${API}/models/${modelKey}/${symbol}?${new URLSearchParams({ capital })}`);
  state.latestModelComparison = data;

  document.getElementById("modelNote").textContent =
    `${data.model_label} on ${symbol} — trained/validated on this stock's own full history. ` +
    `Train: ${data.dates_train[0]} to ${data.dates_train[data.dates_train.length - 1]}. ` +
    `Test (held out, out-of-sample): ${data.dates_test[0]} to ${data.dates_test[data.dates_test.length - 1]}.`;
  document.getElementById("modelLowLiquidityBanner").style.display = data.metrics.low_liquidity ? "flex" : "none";

  renderModelMetrics(data);
  renderModelLossChart(data);
  renderModelPredVsActual(data);
  renderModelImpact(data);
}

function renderModelMetrics(data) {
  const m = data.metrics;
  const cards = [
    { label: "RMSE", value: m.rmse.toFixed(6) },
    { label: "MAE", value: m.mae.toFixed(6) },
    { label: "MAPE", value: m.mape === null ? "n/a" : `${m.mape.toFixed(1)}%`, sub: "unstable near-zero returns -- see note" },
    { label: "Directional accuracy", value: `${m.directional_accuracy_pct.toFixed(1)}%`, cls: m.directional_accuracy_pct >= 50 ? "good" : "critical", sub: "coin flip = 50.0%" },
  ];
  document.getElementById("modelMetricsGrid").innerHTML = cards
    .map((c) => `
      <div class="kpi-card">
        <div class="label">${c.label}</div>
        <div class="value ${c.cls || ""}">${c.value}</div>
        ${c.sub ? `<div class="sub">${c.sub}</div>` : ""}
      </div>`)
    .join("");
}

function renderModelLossChart(data) {
  destroy("modelLoss");
  const opts = gridOptions();
  charts.modelLoss = new Chart(document.getElementById("modelLossChart"), {
    type: "line",
    data: {
      labels: (data.train_loss_history || []).map((_, i) => i),
      datasets: [
        { label: "train", data: data.train_loss_history, borderColor: COLOR.blue, borderWidth: 1.5, pointRadius: 0 },
        { label: "test", data: data.test_loss_history, borderColor: COLOR.orange, borderWidth: 1.5, pointRadius: 0 },
      ],
    },
    options: {
      ...opts,
      scales: {
        x: { ...opts.scales.x, title: { display: true, text: "epoch", color: COLOR.text } },
        y: { ...opts.scales.y, type: "logarithmic", title: { display: true, text: "MSE loss", color: COLOR.text } },
      },
    },
  });
}

function renderModelPredVsActual(data) {
  const opts = gridOptions();
  const window_ = 150;

  destroy("modelTrain");
  charts.modelTrain = new Chart(document.getElementById("modelTrainChart"), {
    type: "line",
    data: {
      labels: data.dates_train.slice(0, window_),
      datasets: [
        { label: "actual", data: data.y_train.slice(0, window_), borderColor: COLOR.blue, borderWidth: 1.5, pointRadius: 0 },
        { label: "predicted", data: data.train_preds.slice(0, window_), borderColor: COLOR.orange, borderWidth: 1.5, pointRadius: 0 },
      ],
    },
    options: { ...opts, plugins: { ...opts.plugins, title: { display: true, text: "Train period", color: COLOR.text } } },
  });

  destroy("modelTest");
  charts.modelTest = new Chart(document.getElementById("modelTestChart"), {
    type: "line",
    data: {
      labels: data.dates_test.slice(0, window_),
      datasets: [
        { label: "actual", data: data.y_test.slice(0, window_), borderColor: COLOR.blue, borderWidth: 1.5, pointRadius: 0 },
        { label: "predicted", data: data.test_preds.slice(0, window_), borderColor: COLOR.orange, borderWidth: 1.5, pointRadius: 0 },
      ],
    },
    options: { ...opts, plugins: { ...opts.plugins, title: { display: true, text: "Test period (out-of-sample)", color: COLOR.text } } },
  });
}

function renderModelImpact(data) {
  destroy("modelImpact");
  charts.modelImpact = new Chart(document.getElementById("modelImpactChart"), {
    type: "line",
    data: {
      labels: data.dates_test,
      datasets: [
        { label: `Following ${data.model_label}'s calls`, data: data.portfolio_value, borderColor: COLOR.blue, borderWidth: 2, pointRadius: 0 },
        { label: "Buy & hold", data: data.buy_and_hold_value, borderColor: COLOR.orange, borderWidth: 2, pointRadius: 0 },
      ],
    },
    options: gridOptions(),
  });

  const capital = Number(document.getElementById("modelCapitalInput").value);
  const k = data.kpis;
  const cards = [
    { label: "Starting balance", value: `${egp(capital)} EGP` },
    { label: "Ending balance", value: `${egp(k.final_value)} EGP`, sub: `Buy & hold: ${egp(k.buy_and_hold_final_value)} EGP` },
    { label: "Total return", value: pct(k.total_return_pct), cls: k.total_return_pct >= 0 ? "good" : "critical" },
    { label: "Max drawdown", value: `-${k.max_drawdown_pct.toFixed(2)}%`, cls: "critical" },
    { label: "Buy / sell ops", value: `${k.num_buys} / ${k.num_sells}` },
    { label: "Win rate", value: `${k.win_rate_pct.toFixed(1)}%` },
    { label: "Sharpe ratio", value: k.sharpe.toFixed(2) },
    { label: "Avg holding period", value: `${k.avg_holding_days.toFixed(1)} days` },
  ];
  document.getElementById("modelImpactGrid").innerHTML = cards
    .map((c) => `
      <div class="kpi-card">
        <div class="label">${c.label}</div>
        <div class="value ${c.cls || ""}">${c.value}</div>
        ${c.sub ? `<div class="sub">${c.sub}</div>` : ""}
      </div>`)
    .join("");

  document.getElementById("modelImpactNote").textContent =
    `Long-only, long/flat: go long whenever ${data.model_label} predicts a positive next-day return, hold cash otherwise. ` +
    `Test period only (${data.dates_test[0]} to ${data.dates_test[data.dates_test.length - 1]}) -- out-of-sample, exactly the ` +
    `days this model never trained on.`;
}

// ============================================================ strategies ==

async function initStrategiesTab() {
  const strategies = await fetchJSON(`${API}/strategies`);
  state.strategies = strategies;

  const select = document.getElementById("strategySelect");
  select.innerHTML = strategies.map((s) => `<option value="${s.key}">${s.label}</option>`).join("");

  document.getElementById("runStrategyButton").addEventListener("click", runStrategyOnDemand);
  document.getElementById("clearStrategyRunsButton").addEventListener("click", () => {
    state.strategyRuns = [];
    renderStrategyRuns();
  });
  state.strategyRuns = [];

  await runStrategyOnDemand();
}

async function runStrategyOnDemand() {
  const strategyKey = document.getElementById("strategySelect").value;
  const universe = document.getElementById("strategyUniverseSelect").value;
  const common = { universe, strategy: strategyKey };

  let bt, m;
  try {
    [bt, m] = await Promise.all([
      fetchJSON(`${API}/backtest?${new URLSearchParams(common)}`),
      fetchJSON(`${API}/metrics?${new URLSearchParams(common)}`),
    ]);
  } catch (e) {
    document.getElementById("strategyNote").textContent = `${strategyKey} isn't available on the ${universe} universe: ${e.message}`;
    return;
  }

  document.getElementById("strategyNote").textContent =
    `${bt.strategy_label} on the ${universe === "small" ? "small (6-stock)" : "full (34-stock)"} universe. ` +
    `${bt.dates[0]} to ${bt.dates[bt.dates.length - 1]}. Portfolio and benchmark both start at 1.0.`;

  const cards = [
    { label: "Total return", value: pct(m.total_return * 100), cls: m.total_return >= 0 ? "good" : "critical" },
    { label: "Sharpe ratio", value: m.sharpe.toFixed(2) },
    { label: "Max drawdown", value: `-${(m.max_drawdown * 100).toFixed(2)}%`, cls: "critical" },
  ];
  if (m.win_rate_pct !== undefined) {
    cards.push(
      { label: "Win rate", value: `${m.win_rate_pct.toFixed(1)}%` },
      { label: "Trades closed", value: `${m.num_trades_closed}`, sub: `${m.num_positions_open_at_end} still open` },
      { label: "Avg holding period", value: `${m.avg_holding_days.toFixed(1)} days` },
    );
  }
  document.getElementById("strategyRunMetricsGrid").innerHTML = cards
    .map((c) => `
      <div class="kpi-card">
        <div class="label">${c.label}</div>
        <div class="value ${c.cls || ""}">${c.value}</div>
        ${c.sub ? `<div class="sub">${c.sub}</div>` : ""}
      </div>`)
    .join("");

  destroy("strategyRun");
  charts.strategyRun = new Chart(document.getElementById("strategyRunChart"), {
    type: "line",
    data: {
      labels: bt.dates,
      datasets: [
        { label: bt.strategy_label, data: bt.portfolio, borderColor: COLOR.blue, borderWidth: 2, pointRadius: 0 },
        { label: "Benchmark (equal-weight)", data: bt.benchmark, borderColor: COLOR.orange, borderWidth: 2, borderDash: [4, 3], pointRadius: 0 },
      ],
    },
    options: gridOptions(),
  });

  state.strategyRuns.unshift({
    time: new Date().toLocaleString(), strategy: bt.strategy_label, universe,
    total_return_pct: m.total_return * 100, sharpe: m.sharpe, max_drawdown_pct: m.max_drawdown * 100,
  });
  renderStrategyRuns();
}

function renderStrategyRuns() {
  document.getElementById("strategyRunsBody").innerHTML = state.strategyRuns
    .map((r) => `
      <tr>
        <td>${r.time}</td>
        <td>${r.strategy}</td>
        <td>${r.universe}</td>
        <td class="${r.total_return_pct >= 0 ? "action-buy" : "action-sell"}">${pct(r.total_return_pct)}</td>
        <td>${r.sharpe.toFixed(2)}</td>
        <td>-${r.max_drawdown_pct.toFixed(2)}%</td>
      </tr>`)
    .join("") || `<tr><td colspan="6" class="empty-note">No runs yet — click "Run strategy" above.</td></tr>`;
}

// =================================================== performance results ==

async function loadPerformanceResults() {
  state.performanceData = await fetchJSON(`${API}/performance-results`);
  state.performanceSelected = new Set();

  const stocks = [...new Set(state.performanceData.models.map((r) => r.symbol))].sort();
  const stockFilter = document.getElementById("perfStockFilter");
  stockFilter.innerHTML = `<option value="">All</option>` + stocks.map((s) => `<option value="${s}">${s}</option>`).join("");

  document.getElementById("refreshPerformanceButton").addEventListener("click", async () => {
    // Force a fresh pull (bypassing nothing server-side -- the backend caches
    // per-checkpoint results since they never change without retraining, but
    // this refetches this endpoint's own aggregation).
    state.performanceData = await fetchJSON(`${API}/performance-results`);
    renderPerformanceTable();
    renderPerformanceGraphs();
  });
  ["perfKindFilter", "perfStockFilter", "perfSortSelect"].forEach((id) =>
    document.getElementById(id).addEventListener("change", renderPerformanceTable)
  );
  document.getElementById("perfGraphGroupBy").addEventListener("change", renderPerformanceGraphs);
  document.getElementById("performanceTableBody").addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-row-key]");
    if (!row) return;
    const key = row.dataset.rowKey;
    if (state.performanceSelected.has(key)) state.performanceSelected.delete(key);
    else state.performanceSelected.add(key);
    renderPerformanceTable();
    renderPerformanceCompareChart();
  });

  renderPerformanceTable();
  renderPerformanceGraphs();
}

function _perfRows() {
  const kind = document.getElementById("perfKindFilter").value;
  const stock = document.getElementById("perfStockFilter").value;
  const sortKey = document.getElementById("perfSortSelect").value;
  const { models, strategies } = state.performanceData;

  let rows = [];
  if (kind !== "strategy") rows = rows.concat(models);
  if (kind !== "model") rows = rows.concat(strategies);
  if (stock) rows = rows.filter((r) => r.kind !== "model" || r.symbol === stock);

  return rows.sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (av === undefined || av === null) return 1;
    if (bv === undefined || bv === null) return -1;
    return bv - av;
  });
}

function renderPerformanceTable() {
  const rows = _perfRows();
  const best = state.performanceData.best_per_stock;

  document.getElementById("performanceTableBody").innerHTML = rows
    .map((r) => {
      const rowKey = r.kind === "model" ? `model:${r.key}:${r.symbol}` : `strategy:${r.key}:${r.universe}`;
      const isBest = r.kind === "model" && best[r.symbol] && best[r.symbol].key === r.key;
      const selected = state.performanceSelected.has(rowKey);
      return `
      <tr data-row-key="${rowKey}" style="cursor:pointer;${selected ? "background:var(--row-highlight)" : ""}">
        <td>${r.kind}</td>
        <td>${r.label}${isBest ? ' <span class="badge best">Best</span>' : ""}${r.low_liquidity ? ' <span class="badge warn">Low liquidity</span>' : ""}</td>
        <td>${r.kind === "model" ? r.symbol : r.universe}</td>
        <td>${r.directional_accuracy_pct !== undefined ? r.directional_accuracy_pct.toFixed(1) + "%" : "—"}</td>
        <td>${r.rmse !== undefined ? r.rmse.toFixed(6) : "—"}</td>
        <td class="${r.total_return_pct >= 0 ? "action-buy" : "action-sell"}">${pct(r.total_return_pct)}</td>
        <td>${r.sharpe !== undefined ? r.sharpe.toFixed(2) : "—"}</td>
        <td>-${(r.max_drawdown_pct || 0).toFixed(2)}%</td>
        <td>${r.win_rate_pct !== undefined ? r.win_rate_pct.toFixed(1) + "%" : "—"}</td>
      </tr>`;
    })
    .join("") || `<tr><td colspan="9" class="empty-note">No results.</td></tr>`;
}

async function renderPerformanceCompareChart() {
  const keys = [...state.performanceSelected];
  document.getElementById("performanceCompareList").textContent = keys.length
    ? `${keys.length} selected: ${keys.map((k) => k.split(":").slice(1).join(" / ")).join(", ")}`
    : "No rows selected yet — click table rows above to select them.";

  destroy("performanceCompare");
  if (keys.length === 0) return;

  // Selected rows can be a universe-wide strategy backtest and a single
  // stock's model backtest at once -- genuinely different date ranges and
  // lengths, not just different calendars. Rather than force them onto one
  // shared date axis (the same misalignment bug the asset-comparison chart
  // had to avoid earlier), plot by trading-day INDEX instead of calendar
  // date -- honest about comparing shape/magnitude, not claiming the two
  // curves are aligned in time.
  const colors = [COLOR.blue, COLOR.orange, COLOR.aqua, COLOR.magenta, COLOR.violet, COLOR.yellow];
  const series = [];
  for (let i = 0; i < keys.length; i++) {
    const [kind, key, third] = keys[i].split(":");
    if (kind === "strategy") {
      const bt = await fetchJSON(`${API}/backtest?${new URLSearchParams({ universe: third, strategy: key })}`);
      series.push({ label: `${bt.strategy_label} (${third})`, data: bt.portfolio, color: colors[i % colors.length] });
    } else {
      const m = await fetchJSON(`${API}/models/${key}/${third}?capital=1000`);
      series.push({ label: `${m.model_label} (${third})`, data: m.portfolio_value.map((v) => v / 1000), color: colors[i % colors.length] });
    }
  }

  const maxLen = Math.max(...series.map((s) => s.data.length));
  const opts = gridOptions();
  charts.performanceCompare = new Chart(document.getElementById("performanceCompareChart"), {
    type: "line",
    data: {
      labels: Array.from({ length: maxLen }, (_, i) => i),
      datasets: series.map((s) => ({ label: s.label, data: s.data, borderColor: s.color, borderWidth: 2, pointRadius: 0 })),
    },
    options: {
      ...opts,
      scales: {
        x: { ...opts.scales.x, title: { display: true, text: "trading days into each run", color: COLOR.text } },
        y: { ...opts.scales.y, title: { display: true, text: "growth of 1.0", color: COLOR.text } },
      },
    },
  });
}

async function renderPerformanceGraphs() {
  const groupBy = document.getElementById("perfGraphGroupBy").value;
  const grid = document.getElementById("performanceGraphsGrid");
  grid.innerHTML = "";

  const { models } = state.performanceData;
  const groups = new Map();
  for (const r of models) {
    const key = groupBy === "stock" ? r.symbol : r.key;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }

  let cardIndex = 0;
  for (const [groupKey, rows] of groups) {
    const card = document.createElement("div");
    card.className = "graph-card";
    const title = document.createElement("h3");
    title.textContent = groupBy === "stock" ? groupKey : MODEL_GRAPH_LABELS[groupKey] || groupKey;
    const canvas = document.createElement("canvas");
    canvas.id = `perfGraphCanvas${cardIndex++}`;
    card.appendChild(title);
    const wrap = document.createElement("div");
    wrap.className = "chart-wrap short";
    wrap.appendChild(canvas);
    card.appendChild(wrap);
    grid.appendChild(card);

    const opts = gridOptions();
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: rows.map((r) => (groupBy === "stock" ? (MODEL_GRAPH_LABELS[r.key] || r.key) : r.symbol)),
        datasets: [{
          label: "Directional accuracy %",
          data: rows.map((r) => r.directional_accuracy_pct),
          backgroundColor: rows.map((r) => (r.low_liquidity ? COLOR.text : r.directional_accuracy_pct >= 50 ? COLOR.good ?? "#0ca30c" : COLOR.critical ?? "#d03b3b")),
        }],
      },
      options: { ...opts, plugins: { ...opts.plugins, legend: { display: false } }, scales: { ...opts.scales, y: { ...opts.scales.y, min: 0, max: 100 } } },
    });
  }
}

const MODEL_GRAPH_LABELS = { nn: "NN", lstm: "LSTM" };

// -------------------------------------------------------------- news panel ----
// News titles/publishers come from an external source and chat replies come
// from the LLM — unlike the rest of this file's innerHTML use (all internal,
// known-shape data), that's untrusted text, so it gets escaped before going
// into the DOM.
function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s ?? "";
  return div.innerHTML;
}

async function loadNews(symbol, refresh = false) {
  const container = document.getElementById("newsContent");
  document.getElementById("newsHeading").textContent = `News & sentiment — ${symbol}`;
  container.innerHTML = `<p class="disclaimer">Loading news…</p>`;
  try {
    const params = refresh ? "?refresh=true" : "";
    const data = await fetchJSON(`${API}/news/${symbol}${params}`);
    renderNews(data);
  } catch (e) {
    container.innerHTML = `<p class="disclaimer">Couldn't load news right now (${escapeHtml(e.message)}).</p>`;
  }
}

function renderNews(data) {
  const container = document.getElementById("newsContent");

  if (data.message && (!data.headlines || data.headlines.length === 0)) {
    container.innerHTML = `<p class="disclaimer">${escapeHtml(data.message)}</p>`;
    return;
  }

  let html = "";
  if (data.summary) {
    const label = (data.sentiment?.label || "Neutral").toLowerCase();
    html += `<div class="news-summary">
      <span class="news-sentiment ${label}">${escapeHtml(data.sentiment?.label || "Neutral")}${data.sentiment?.score != null ? ` (${data.sentiment.score.toFixed(2)})` : ""}</span>
      <p style="margin:6px 0 0">${escapeHtml(data.summary)}</p>
      ${data.sentiment?.reason ? `<p class="disclaimer" style="margin:6px 0 0">${escapeHtml(data.sentiment.reason)}</p>` : ""}
    </div>`;
  } else if (data.message) {
    html += `<p class="disclaimer">${escapeHtml(data.message)}</p>`;
  }

  if (data.headlines && data.headlines.length) {
    html += `<ul class="news-list">${data.headlines.map((h) => `
      <li>
        <a href="${escapeHtml(h.url || "#")}" target="_blank" rel="noopener noreferrer">${escapeHtml(h.title)}</a>
        <div class="news-meta">${escapeHtml(h.publisher || "")}${h.published_at ? " · " + escapeHtml(h.published_at) : ""}</div>
      </li>`).join("")}</ul>`;
  }

  container.innerHTML = html || `<p class="disclaimer">No recent news found for this symbol.</p>`;
}

// ------------------------------------------------------------ chat widget ----
// Grounds every answer in what's ACTUALLY on screen: this context is read
// fresh from the DOM/state at send-time, not cached, so it can't go stale
// mid-conversation. state.backtest is only included once a backtest has
// actually run (state.latestBacktest set) — otherwise the backend correctly
// reports "no backtest currently displayed" instead of guessing.
function buildDashboardContext() {
  return {
    symbol: document.getElementById("symbolSelect").value,
    universe: state.universe,
    field: document.getElementById("fieldSelect").value,
    start: document.getElementById("startDate").value || null,
    end: document.getElementById("endDate").value || null,
    backtest: state.latestBacktest
      ? {
          fast: Number(document.getElementById("fastInput").value),
          slow: Number(document.getElementById("slowInput").value),
          capital: Number(document.getElementById("capitalInput").value),
        }
      : null,
  };
}

function appendChatMessage(role, text, extraClass = "") {
  const messages = document.getElementById("chatMessages");
  const div = document.createElement("div");
  div.className = `chat-msg ${role} ${extraClass}`.trim();
  div.textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

async function sendChatMessage() {
  const input = document.getElementById("chatInput");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";

  appendChatMessage("user", text);
  const pending = appendChatMessage("model", "Thinking…", "pending");

  try {
    const body = {
      message: text,
      history: state.chatHistory,
      context: buildDashboardContext(),
    };
    const res = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `request failed (${res.status})`);

    pending.remove();
    appendChatMessage("model", data.reply);
    state.chatHistory.push({ role: "user", text });
    state.chatHistory.push({ role: "model", text: data.reply });
    // Keep only the most recent turns so the request body doesn't grow
    // unbounded over a long session.
    if (state.chatHistory.length > 20) state.chatHistory = state.chatHistory.slice(-20);
  } catch (e) {
    pending.remove();
    appendChatMessage("model", `Sorry, something went wrong: ${e.message}`, "error");
  }
}

// ---------------------------------------------- asset management game ----
// The rules run entirely client-side against price data fetched once, same
// pattern as everything else in this file (main.py is stateless REST; app.js
// state drives all interaction). dayIndex is the last APPLIED day (-1 = the
// player hasn't picked an opening pair yet). Each "apply" recomputes shares
// from `pendingSelection` at the prior close (fee only charged when the
// selection actually differs from current holdings), then marks to market
// at the next day's close — see PR notes for the exact accounting.
const game = {
  config: null, prices: null, benchmarks: null,
  dayIndex: -1, holdings: [], shares: {}, pendingSelection: [],
  valueHistory: [],
  snapshots: [], // snapshots[i] = full state right after day i was applied (i = 0..num_days-1) — random-access, non-destructive, so "jump to day N" and Prev are the same operation
  finished: false, playTimer: null,
  hasCompletedOnce: false, // true from the first time day num_days-1 is reached, for the rest of the session
  isReplay: false,         // true once the player jumps back to an earlier day AFTER hasCompletedOnce — gates auto-save vs explicit "save replay"
  feeEnabled: true, custodyFeeEnabled: false, feesPaidTotal: 0,
};

// Setup screen fetches only the date bounds up front — config/prices/
// benchmarks are fetched with the PLAYER'S chosen cash/date-range/fee
// settings only once they press "Start game" (gameStartWithSetup), which is
// the actual fix for the setup inputs previously being collected and then
// silently ignored: nothing downstream read them.
async function initGame() {
  try {
    const bounds = await fetchJSON(`${API}/game/date-bounds`);
    document.getElementById("gameSetupStart").min = bounds.min_date;
    document.getElementById("gameSetupStart").max = bounds.max_date;
    document.getElementById("gameSetupEnd").min = bounds.min_date;
    document.getElementById("gameSetupEnd").max = bounds.max_date;
  } catch (e) {
    document.getElementById("gameSetupHint").textContent = `Couldn't load valid date range: ${e.message}`;
  }

  document.getElementById("gameSetupStartButton").addEventListener("click", gameStartWithSetup);
  document.getElementById("gameChangeSetupButton").addEventListener("click", () => {
    if (game.playTimer) gameTogglePlay();
    document.getElementById("gamePlayArea").style.display = "none";
    document.getElementById("gameSetupPanel").style.display = "block";
  });
  document.getElementById("gamePrevButton").addEventListener("click", () => gameJumpToDay(game.dayIndex - 1));
  document.getElementById("gameNextButton").addEventListener("click", gameApplyDay);
  document.getElementById("gamePlayButton").addEventListener("click", gameTogglePlay);
  document.getElementById("gameResetButton").addEventListener("click", gameReset);
  document.getElementById("gameJumpButton").addEventListener("click", () => {
    gameJumpToDay(Number(document.getElementById("gameJumpInput").value));
  });
  document.getElementById("gameSaveReplayButton").addEventListener("click", gameSaveAttempt);
  document.getElementById("gameLeaderboardRefresh").addEventListener("click", loadGameLeaderboard);

  loadGameLeaderboard();
}

async function gameStartWithSetup() {
  const hint = document.getElementById("gameSetupHint");
  const startCash = Number(document.getElementById("gameSetupCash").value);
  const startDate = document.getElementById("gameSetupStart").value;
  const endDate = document.getElementById("gameSetupEnd").value;
  const feeEnabled = document.getElementById("gameSetupFeeEnabled").checked;
  const custodyFeeEnabled = document.getElementById("gameSetupCustodyEnabled").checked;

  if (!startCash || startCash <= 0) { hint.textContent = "Starting cash must be a positive number."; return; }
  if (!startDate || !endDate) { hint.textContent = "Pick both a start and end date."; return; }
  if (startDate >= endDate) { hint.textContent = "Start date must be before end date."; return; }

  hint.textContent = "Loading…";
  const startButton = document.getElementById("gameSetupStartButton");
  startButton.disabled = true;
  try {
    const params = new URLSearchParams({ start_date: startDate, end_date: endDate, start_cash: startCash });
    const benchParams = new URLSearchParams({
      start_date: startDate, end_date: endDate, start_cash: startCash,
      fee_enabled: feeEnabled, custody_fee_enabled: custodyFeeEnabled,
    });
    const [config, prices, benchmarks] = await Promise.all([
      fetchJSON(`${API}/game/config?${params}`),
      fetchJSON(`${API}/game/prices?${params}`),
      fetchJSON(`${API}/game/benchmarks?${benchParams}`),
    ]);

    game.config = config;
    game.prices = prices;
    game.benchmarks = benchmarks;
    game.feeEnabled = feeEnabled;
    game.custodyFeeEnabled = custodyFeeEnabled;
    // A genuinely new setup starts a fresh session — a prior run's replay
    // bookkeeping shouldn't leak into a different starting-cash/date-range game.
    game.hasCompletedOnce = false;
    game.isReplay = false;
    game.snapshots = [];

    document.getElementById("gameJumpMax").textContent = config.num_days - 1;
    document.getElementById("gameJumpInput").max = config.num_days - 1;
    document.getElementById("gameRulesText").textContent =
      `Start with ${startCash.toLocaleString()} EGP, always invested exactly 50/50 across 2 of the 8 stocks below — `
      + `never in cash, never 1 or 3+. Each simulated day, decide to KEEP your pair or SWITCH, using only what's shown up `
      + `to that point (no peeking ahead). Step through ${config.start_date} → ${config.end_date}.`
      + (feeEnabled ? ` Trading fees are ON (EFG Hermes schedule, ~${config.fee.effective_pct.toFixed(2)}% + EGP ${config.fee.min_egp} min per trade).` : " Trading fees are OFF.");
    document.getElementById("gameChartNote").textContent =
      `All lines start at ${startCash.toLocaleString()} EGP and reveal day by day alongside your play — no benchmark shows you the future either.`;

    buildGameTiles();
    gameReset();
    document.getElementById("gameSetupPanel").style.display = "none";
    document.getElementById("gamePlayArea").style.display = "block";
  } catch (e) {
    hint.textContent = `Couldn't start the game: ${e.message}`;
  } finally {
    startButton.disabled = false;
  }
}

function buildGameTiles() {
  const grid = document.getElementById("gameTileGrid");
  grid.innerHTML = game.config.symbols.map((sym) => `
    <div class="graph-card game-tile" data-symbol="${sym}">
      <h3>${sym} <span class="held-badge" style="display:none">Held</span></h3>
      <div class="chart-wrap game-tile-chart"><canvas id="gameTile-${sym}"></canvas></div>
    </div>
  `).join("");
  grid.querySelectorAll(".game-tile").forEach((tile) => {
    tile.addEventListener("click", () => gameToggleSelection(tile.dataset.symbol));
  });
}

function gameToggleSelection(symbol) {
  if (game.finished) return;
  const i = game.pendingSelection.indexOf(symbol);
  if (i >= 0) {
    game.pendingSelection.splice(i, 1);
  } else if (game.pendingSelection.length < 2) {
    game.pendingSelection.push(symbol);
  } else {
    document.getElementById("gameHint").textContent = "Only 2 holdings allowed — deselect one first.";
    return;
  }
  renderGameTiles();
}

function renderGameTiles() {
  const revealCount = game.dayIndex + 1; // how many played days are visible so far
  game.config.symbols.forEach((sym) => {
    const tile = document.querySelector(`.game-tile[data-symbol="${sym}"]`);
    const held = game.pendingSelection.includes(sym);
    tile.classList.toggle("held", held);
    tile.querySelector(".held-badge").style.display = held ? "inline-block" : "none";

    const dates = game.prices[sym].dates.slice(0, revealCount);
    const close = game.prices[sym].close.slice(0, revealCount);
    destroy(`gameTile-${sym}`);
    const canvas = document.getElementById(`gameTile-${sym}`);
    const up = close.length > 1 && close[close.length - 1] >= close[0];
    charts[`gameTile-${sym}`] = new Chart(canvas, {
      type: "line",
      data: { labels: dates, datasets: [{
        data: close, borderColor: up ? COLOR.good : COLOR.critical, borderWidth: 1.5,
        pointRadius: 0, tension: 0.15, fill: false,
      }] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: { x: { display: false }, y: { display: false } },
      },
    });
  });

  const label = game.dayIndex === -1
    ? "Day 0 — pick your opening pair (no chart data yet, no lookahead)"
    : `Day ${game.dayIndex + 1} of ${game.config.num_days} — ${game.config.trading_days[game.dayIndex]}`;
  document.getElementById("gameDayLabel").textContent = label;

  const canAdvance = game.pendingSelection.length === 2 && !game.finished;
  document.getElementById("gameNextButton").disabled = !canAdvance;
  // Play must be just as gated as Next — otherwise clicking Play before a
  // pair is selected starts the auto-advance interval, which immediately
  // no-ops and cancels itself on its first tick (looks like "Play does
  // nothing" from the user's side, since it flips back within ~1 second).
  document.getElementById("gamePlayButton").disabled = !canAdvance && !game.playTimer;
  document.getElementById("gameHint").textContent = game.finished
    ? "Game finished — press Reset to play again."
    : (canAdvance ? "" : "Select exactly 2 tiles to hold before advancing or pressing Play.");
}

function gameGetSharesValue(shares, dayIdx) {
  return Object.entries(shares).reduce((sum, [sym, n]) => sum + n * game.prices[sym].close[dayIdx], 0);
}

// Mirrors dashboard/backend/game_service.py's compute_trade_fee exactly —
// EFG Hermes schedule, summed to one effective rate (~0.55%) with a
// combined EGP 15 practical minimum per trade. game.config.fee comes from
// /game/config so a rate change on the backend doesn't need a frontend edit.
function computeTradeFee(tradeValue) {
  if (!game.feeEnabled || tradeValue <= 0) return 0;
  return Math.max(tradeValue * game.config.fee.effective_pct / 100, game.config.fee.min_egp);
}

function isYearEnd(dateStr) {
  const d = new Date(dateStr + "T00:00:00Z");
  return d.getUTCMonth() === 11 && d.getUTCDate() === 31; // Dec 31
}

function gameApplyDay() {
  if (game.finished || game.pendingSelection.length !== 2) return;
  const [a, b] = game.pendingSelection;
  const sameHoldings = game.holdings.length === 2 && game.holdings.includes(a) && game.holdings.includes(b);
  let feesThisStep = 0;

  if (game.dayIndex === -1) {
    // Opening buy: no prior game history, so this is 2 buy trades (buy A,
    // buy B) against the starting cash — day 0's value is start_cash minus
    // those two trades' fees, not exactly start_cash when fees are on.
    const cash = game.config.start_cash;
    const half = cash / 2;
    const feeA = computeTradeFee(half);
    const feeB = computeTradeFee(half);
    game.shares = { [a]: (half - feeA) / game.prices[a].close[0], [b]: (half - feeB) / game.prices[b].close[0] };
    game.holdings = [a, b];
    feesThisStep = feeA + feeB;
    game.valueHistory = [cash - feesThisStep];
    game.dayIndex = 0;
  } else {
    const priorClose = game.dayIndex; // "prior close" for the day we're advancing INTO
    const nextIdx = game.dayIndex + 1;
    const currentValue = game.valueHistory[game.valueHistory.length - 1];
    let newShares;

    if (sameHoldings) {
      newShares = game.shares; // KEEP: no trades, no fees
    } else {
      // SWITCH = 4 trades: sell A, sell B (at the prior close, against the
      // CURRENT 50/50 split), then buy C, buy D with whatever cash remains
      // after the sell fees. Each trade's fee is computed on its own value.
      const sellHalf = currentValue / 2;
      const sellFeeA = computeTradeFee(sellHalf);
      const sellFeeB = computeTradeFee(sellHalf);
      const cashAfterSells = currentValue - sellFeeA - sellFeeB;

      const buyHalf = cashAfterSells / 2;
      const buyFeeC = computeTradeFee(buyHalf);
      const buyFeeD = computeTradeFee(buyHalf);
      newShares = {
        [a]: (buyHalf - buyFeeC) / game.prices[a].close[priorClose],
        [b]: (buyHalf - buyFeeD) / game.prices[b].close[priorClose],
      };
      feesThisStep = sellFeeA + sellFeeB + buyFeeC + buyFeeD;
    }

    let newValue = gameGetSharesValue(newShares, nextIdx);

    // Annual custody fee — a level markdown applied once per Dec-31 inside
    // the played range, off by default (most playthroughs are weeks long).
    if (game.custodyFeeEnabled && isYearEnd(game.config.trading_days[nextIdx])) {
      const custodyFee = newValue * game.config.fee.annual_custody_pct / 100;
      const factor = (newValue - custodyFee) / newValue;
      for (const sym of Object.keys(newShares)) newShares[sym] *= factor;
      newValue -= custodyFee;
      feesThisStep += custodyFee;
    }

    game.shares = newShares;
    game.holdings = [a, b];
    game.valueHistory.push(newValue);
    game.dayIndex = nextIdx;

    showGameFlourish((newValue - currentValue) / currentValue * 100);
  }

  game.feesPaidTotal += feesThisStep;

  // Random-access snapshot for this day — enables both Prev (jump to
  // dayIndex-1) and jump-to-any-day replay as the exact same operation,
  // non-destructively (unlike the old pop()-based undo, revisiting a day
  // doesn't erase it, so re-diverging from it works more than once).
  game.snapshots[game.dayIndex] = {
    holdings: [...game.holdings], shares: { ...game.shares }, valueHistory: [...game.valueHistory],
    feesPaidTotal: game.feesPaidTotal,
  };

  game.pendingSelection = [...game.holdings];
  game.finished = game.dayIndex === game.config.num_days - 1;
  renderGameTiles();
  renderGameKpis();
  renderGameEquityChart();
  if (game.finished) {
    if (game.playTimer) gameTogglePlay();
    renderGameSummary();
  }
}

function gameJumpToDay(n) {
  n = Math.max(-1, Math.min(n, game.snapshots.length - 1));
  if (game.playTimer) gameTogglePlay();

  // "Replay mode" per spec is specifically post-completion exploration —
  // jumping around before ever finishing is just ordinary undo, no
  // leaderboard implications.
  if (game.hasCompletedOnce) game.isReplay = true;

  if (n === -1) {
    game.dayIndex = -1; game.holdings = []; game.shares = {}; game.valueHistory = []; game.feesPaidTotal = 0;
  } else {
    const snap = game.snapshots[n];
    if (!snap) return; // that day was never actually reached this session
    game.dayIndex = n;
    game.holdings = snap.holdings;
    game.shares = snap.shares;
    game.valueHistory = snap.valueHistory;
    game.feesPaidTotal = snap.feesPaidTotal; // fees paid AS OF that day, not the session's running total
  }
  game.pendingSelection = [...game.holdings];
  game.finished = false;
  document.getElementById("gameSummaryPanel").style.display = "none";
  document.getElementById("gameFlourishSlot").innerHTML = "";
  renderGameTiles();
  renderGameKpis();
  renderGameEquityChart();
}

function gameTogglePlay() {
  const btn = document.getElementById("gamePlayButton");
  if (game.playTimer) {
    clearInterval(game.playTimer);
    game.playTimer = null;
    btn.textContent = "▶ Play";
    renderGameTiles(); // re-enable Next/Play button states now that autoplay stopped
  } else {
    if (game.finished || game.pendingSelection.length !== 2) return; // button should be disabled anyway; belt and suspenders
    btn.textContent = "⏸ Pause";
    game.playTimer = setInterval(() => {
      // Keeping the same pair is the only automatic move Play makes — it
      // never switches on your behalf. Stops on its own once the game ends.
      if (game.finished || game.pendingSelection.length !== 2) { gameTogglePlay(); return; }
      gameApplyDay();
    }, 1100);
  }
}

function gameReset() {
  if (game.playTimer) { clearInterval(game.playTimer); game.playTimer = null; }
  document.getElementById("gamePlayButton").textContent = "▶ Play";
  // hasCompletedOnce/isReplay/snapshots intentionally survive a Reset within
  // the same tab session — Reset starts a fresh attempt, it doesn't erase
  // "have I already saved an original run this session" bookkeeping.
  Object.assign(game, { dayIndex: -1, holdings: [], shares: {}, pendingSelection: [], valueHistory: [], finished: false, feesPaidTotal: 0 });
  document.getElementById("gameSummaryPanel").style.display = "none";
  document.getElementById("gameFlourishSlot").innerHTML = "";
  document.getElementById("gameReplayControls").style.display = game.hasCompletedOnce ? "flex" : "none";
  renderGameTiles();
  renderGameKpis();
  renderGameEquityChart();
}

function showGameFlourish(pct) {
  const slot = document.getElementById("gameFlourishSlot");
  const up = pct >= 0;
  slot.innerHTML = `<span class="game-flourish ${up ? "up" : "down"}">${up ? "▲" : "▼"} ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}% ${up ? "📈" : "📉"}</span>`;
}

// Mirrors dashboard/backend/game_service.py's _risk_stats exactly (0%
// risk-free rate, 252-day annualization) so the player's own numbers are
// computed the same way as the server-side benchmark numbers they're
// compared against.
const TRADING_DAYS = 252;
function computeRiskStats(values) {
  if (values.length < 2) return { volatility_pct: 0, sharpe: 0, max_drawdown_pct: 0 };
  const returns = values.slice(1).map((v, i) => v / values[i] - 1);
  const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
  const variance = returns.reduce((a, b) => a + (b - mean) ** 2, 0) / returns.length;
  const std = Math.sqrt(variance);
  let peak = -Infinity, maxDrawdown = 0;
  for (const v of values) { peak = Math.max(peak, v); maxDrawdown = Math.max(maxDrawdown, (peak - v) / peak); }
  return {
    volatility_pct: std * Math.sqrt(TRADING_DAYS) * 100,
    sharpe: std > 0 ? (mean / std) * Math.sqrt(TRADING_DAYS) : 0,
    max_drawdown_pct: maxDrawdown * 100,
  };
}

function renderGameKpis() {
  const value = game.valueHistory.length ? game.valueHistory[game.valueHistory.length - 1] : game.config.start_cash;
  const profit = value - game.config.start_cash;
  const profitPct = profit / game.config.start_cash * 100;
  const cards = [
    { label: "Portfolio value", value: `${value.toLocaleString(undefined, { maximumFractionDigits: 0 })} EGP` },
    { label: "Profit / loss", value: `${profit >= 0 ? "+" : ""}${profit.toLocaleString(undefined, { maximumFractionDigits: 0 })} EGP`, cls: profit >= 0 ? "good" : "critical" },
    { label: "Profit %", value: `${profitPct >= 0 ? "+" : ""}${profitPct.toFixed(2)}%`, cls: profitPct >= 0 ? "good" : "critical" },
    { label: "Current holdings", value: game.holdings.length ? game.holdings.join(" + ") : "—" },
    { label: "Fees paid so far", value: `${game.feesPaidTotal.toLocaleString(undefined, { maximumFractionDigits: 0 })} EGP`, cls: game.feesPaidTotal > 0 ? "critical" : "" },
  ];
  document.getElementById("gameKpiGrid").innerHTML = cards.map((c) => `
    <div class="kpi-card"><div class="label">${c.label}</div><div class="value ${c.cls || ""}">${c.value}</div></div>
  `).join("");

  const risk = computeRiskStats(game.valueHistory);
  const riskCards = [
    { label: "Volatility (annualized)", value: `${risk.volatility_pct.toFixed(2)}%` },
    { label: "Sharpe (rf = 0%)", value: risk.sharpe.toFixed(2) },
    { label: "Max drawdown", value: `${risk.max_drawdown_pct.toFixed(2)}%` },
  ];
  document.getElementById("gameRiskGrid").innerHTML = riskCards.map((c) => `
    <div class="kpi-card"><div class="label">${c.label}</div><div class="value">${c.value}</div></div>
  `).join("");

  renderGameDeltaRow(profitPct);
}

// "+3.2% vs. buy-and-hold" — player's profit % so far compared against each
// benchmark's profit % AS OF THE SAME DAY (not the benchmark's final value),
// so the comparison is fair while the game is still in progress.
function renderGameDeltaRow(playerProfitPct) {
  const row = document.getElementById("gameDeltaRow");
  if (game.dayIndex < 0) { row.textContent = ""; return; }
  const idx = game.dayIndex;
  const entries = [
    ["Equal-weight (all 8)", game.benchmarks.equal_weight],
    ["Best pair in hindsight", game.benchmarks.best_hindsight_pair],
    ...(game.benchmarks.egx_index ? [["EGX30 index", game.benchmarks.egx_index]] : []),
  ];
  const parts = entries.map(([label, b]) => {
    const benchProfitPctToDate = (b.values[idx] / game.config.start_cash - 1) * 100;
    const delta = playerProfitPct - benchProfitPctToDate;
    return `${delta >= 0 ? "+" : ""}${delta.toFixed(2)}% vs. ${label}`;
  });
  row.textContent = parts.join("  ·  ");
}

function renderGameEquityChart() {
  destroy("gameEquityChart");
  const canvas = document.getElementById("gameEquityChart");
  const n = game.dayIndex + 1; // days actually revealed so far — benchmarks are sliced the same way, no lookahead on this chart either
  const dates = n > 0 ? game.config.trading_days.slice(0, n) : [];
  const opts = gridOptions();

  const datasets = [{
    label: "Your portfolio", data: game.valueHistory, borderColor: COLOR.blue, backgroundColor: COLOR.blue,
    pointRadius: 0, borderWidth: 2.5, tension: 0.1,
  }];
  if (n > 0 && game.benchmarks) {
    const benchLines = [
      ["Equal-weight (all 8)", game.benchmarks.equal_weight, COLOR.aqua],
      ["Best pair in hindsight", game.benchmarks.best_hindsight_pair, COLOR.orange],
      ...(game.benchmarks.egx_index ? [["EGX30 index", game.benchmarks.egx_index, COLOR.violet]] : []),
    ];
    for (const [label, b, color] of benchLines) {
      datasets.push({
        label, data: b.values.slice(0, n), borderColor: color, backgroundColor: color,
        pointRadius: 0, borderWidth: 1.5, borderDash: [5, 3], tension: 0.1,
      });
    }
  }

  charts.gameEquityChart = new Chart(canvas, {
    type: "line",
    data: { labels: dates, datasets },
    options: { ...opts, plugins: { ...opts.plugins, legend: { display: true } } },
  });
}

function renderGameSummary() {
  const value = game.valueHistory[game.valueHistory.length - 1];
  const profit = value - game.config.start_cash;
  const profitPct = profit / game.config.start_cash * 100;
  const playerRisk = computeRiskStats(game.valueHistory);
  const ew = game.benchmarks.equal_weight;
  const bp = game.benchmarks.best_hindsight_pair;
  const idx = game.benchmarks.egx_index;

  const row = (label, val, pct, risk, sub) => `
    <div class="kpi-card">
      <div class="label">${label}</div>
      <div class="value ${pct >= 0 ? "good" : "critical"}">${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%</div>
      <div class="sub">${val.toLocaleString(undefined, { maximumFractionDigits: 0 })} EGP${sub ? " · " + sub : ""}</div>
      <div class="sub">Vol ${risk.volatility_pct.toFixed(1)}% · Sharpe ${risk.sharpe.toFixed(2)} · MaxDD ${risk.max_drawdown_pct.toFixed(1)}%</div>
    </div>`;

  const rows = [
    row("You" + (game.isReplay ? " (replay)" : ""), value, profitPct, playerRisk,
      `Fees paid: ${game.feesPaidTotal.toLocaleString(undefined, { maximumFractionDigits: 0 })} EGP`),
    row("Equal-weight, all 8", ew.final_value, ew.profit_pct, ew, game.feeEnabled ? "1 initial buy-in fee, never traded again" : "fees off"),
    row("Best 2-stock pair in hindsight", bp.final_value, bp.profit_pct, bp,
      bp.symbols.join(" + ") + (game.feeEnabled ? " · 1 initial buy-in fee" : "")),
  ];
  if (idx) rows.push(row("EGX30 index", idx.final_value, idx.profit_pct, idx));
  document.getElementById("gameSummaryGrid").innerHTML = rows.join("");

  const beatEw = profitPct > ew.profit_pct;
  const beatBp = profitPct > bp.profit_pct;
  document.getElementById("gameSummaryNote").textContent =
    `You ${beatEw ? "beat" : "trailed"} the equal-weight benchmark and ${beatBp ? "beat" : "trailed"} the best-possible fixed pair chosen with hindsight. `
    + "The hindsight pair is the single best-performing static 50/50 pair held the whole period — a ceiling reference, not something you could have known in advance.";
  document.getElementById("gameSummaryPanel").style.display = "block";
  document.getElementById("gameReplayControls").style.display = "flex";

  const saveBtn = document.getElementById("gameSaveReplayButton");
  const saveNote = document.getElementById("gameSaveNote");
  if (!game.hasCompletedOnce) {
    // First-ever completion this session: auto-save, no button needed.
    game.hasCompletedOnce = true;
    saveBtn.style.display = "none";
    gameSaveAttempt(/* silent */ true);
  } else if (game.isReplay) {
    // A completed replay branch — never overwrites the original automatically.
    saveBtn.style.display = "inline-block";
    saveNote.textContent = "This is a replay of an earlier decision point — it won't be added to the leaderboard unless you save it.";
  } else {
    saveBtn.style.display = "none";
  }
}

async function gameSaveAttempt(silent = false) {
  const value = game.valueHistory[game.valueHistory.length - 1];
  const profitPct = (value - game.config.start_cash) / game.config.start_cash * 100;
  const risk = computeRiskStats(game.valueHistory);
  const body = {
    profit_pct: profitPct,
    final_value: value,
    volatility_pct: risk.volatility_pct,
    sharpe: risk.sharpe,
    max_drawdown_pct: risk.max_drawdown_pct,
    fees_paid: game.feesPaidTotal,
    fee_enabled: game.feeEnabled,
    start_cash: game.config.start_cash,
    start_date: game.config.start_date,
    end_date: game.config.end_date,
    is_replay: game.isReplay,
    holdings_path: game.snapshots.filter(Boolean).map((s) => s.holdings),
  };
  const saveNote = document.getElementById("gameSaveNote");
  try {
    const res = await fetch(`${API}/game/leaderboard`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`save failed (${res.status})`);
    saveNote.textContent = silent ? "✓ Saved to leaderboard." : "✓ Replay saved as a new attempt.";
    document.getElementById("gameSaveReplayButton").style.display = "none";
    await loadGameLeaderboard();
  } catch (e) {
    saveNote.textContent = `Couldn't save to the leaderboard: ${e.message}`;
  }
}

async function loadGameLeaderboard() {
  const body = document.getElementById("gameLeaderboardBody");
  try {
    const attempts = await fetchJSON(`${API}/game/leaderboard`);
    if (!attempts.length) {
      body.innerHTML = `<tr><td colspan="10" class="empty-note">No attempts saved yet — finish a playthrough to appear here.</td></tr>`;
      return;
    }
    body.innerHTML = attempts.map((a, i) => `
      <tr>
        <td>${i + 1}</td>
        <td>${new Date(a.played_at).toLocaleString()}</td>
        <td>${(a.start_cash ?? 100000).toLocaleString()} EGP · ${a.start_date ?? "?"}–${a.end_date ?? "?"}</td>
        <td class="${a.profit_pct >= 0 ? "action-buy" : "action-sell"}">${a.profit_pct >= 0 ? "+" : ""}${a.profit_pct.toFixed(2)}%</td>
        <td>${a.final_value.toLocaleString(undefined, { maximumFractionDigits: 0 })} EGP</td>
        <td>${(a.fees_paid ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} EGP</td>
        <td>${a.volatility_pct.toFixed(2)}%</td>
        <td>${a.sharpe.toFixed(2)}</td>
        <td>${a.max_drawdown_pct.toFixed(2)}%</td>
        <td>${a.is_replay ? "Replay" : "Original"}</td>
      </tr>
    `).join("");
  } catch (e) {
    body.innerHTML = `<tr><td colspan="10" class="empty-note">Couldn't load the leaderboard: ${e.message}</td></tr>`;
  }
}

function initChatWidget() {
  const toggle = document.getElementById("chatToggle");
  const win = document.getElementById("chatWindow");
  toggle.addEventListener("click", () => win.classList.toggle("open"));
  document.getElementById("chatClose").addEventListener("click", () => win.classList.remove("open"));
  document.getElementById("chatSend").addEventListener("click", sendChatMessage);
  document.getElementById("chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendChatMessage();
  });
}

init();
