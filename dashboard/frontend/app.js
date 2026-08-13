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
  runHistory: [],
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

  await runSimulation();
  await runBaselineEquity();
  await runStrategyComparison();
  await runComparison();

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

  state.latestBacktest = backtest;
  state.latestIndicators = indicators;
  state.latestSymbol = symbol;

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

init();
