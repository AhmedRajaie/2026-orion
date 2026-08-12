const API = "http://localhost:8000";
const EMPTY_VALUE = "--";
const STRATEGY_KEYS = ["mlp", "lstm", "sma", "video"];

const STRATEGIES = {
  mlp: {
    shortLabel: "MLP",
    label: "MLP Portfolio",
    tabId: "strategyTabMLP",
    panelId: "strategyPanelMLP",
    color: "#5ca2ff",
    note: "Week 2 Day 3 best MLP portfolio with honest out-of-sample predictions.",
  },
  lstm: {
    shortLabel: "LSTM",
    label: "LSTM Portfolio",
    tabId: "strategyTabLSTM",
    panelId: "strategyPanelLSTM",
    color: "#2dd4bf",
    note: "Week 2 Day 3 strongest LSTM portfolio variant, kept out of sample.",
  },
  sma: {
    shortLabel: "SMA",
    label: "SMA Portfolio",
    tabId: "strategyTabSMA",
    panelId: "strategyPanelSMA",
    color: "#60a5fa",
    note: "The final multi-asset SMA crossover strategy from Week 1.",
  },
  video: {
    shortLabel: "Video Strategy",
    label: "Video Strategy",
    tabId: "strategyTabVideo",
    panelId: "strategyPanelVideo",
    color: "#f472b6",
    note: "The final Week 1 TikTok contrarian strategy with fixed EGP trade sizes.",
  },
};

const KPI_DEFINITIONS = [
  { key: "initial_portfolio_value", label: "Initial portfolio value", primary: false, formatter: formatCurrency },
  { key: "final_portfolio_value", label: "Final portfolio value", primary: true, formatter: formatCurrency },
  { key: "profit_loss_egp", label: "Profit / loss", primary: false, formatter: formatCurrency },
  { key: "total_return_pct", label: "Total return", primary: true, formatter: formatPercent },
  { key: "benchmark_return_pct", label: "Benchmark return", primary: false, formatter: formatPercent },
  { key: "excess_return_pct", label: "Excess return vs benchmark", primary: false, formatter: formatPercent },
  { key: "sharpe_ratio", label: "Sharpe ratio", primary: true, formatter: (value) => formatNumber(value, 3) },
  { key: "maximum_drawdown_pct", label: "Maximum drawdown", primary: true, formatter: formatPercent },
  { key: "maximum_drawdown_egp", label: "Maximum drawdown (EGP)", primary: false, formatter: formatCurrency },
  { key: "current_drawdown_pct", label: "Current drawdown", primary: false, formatter: formatPercent },
  { key: "total_buy_operations", label: "Total buy operations", primary: false, formatter: formatInteger },
  { key: "total_sell_operations", label: "Total sell operations", primary: false, formatter: formatInteger },
  { key: "total_operations", label: "Total operations", primary: false, formatter: formatInteger },
  { key: "market_exposure_pct", label: "Market exposure", primary: false, formatter: formatPercent },
  { key: "current_portfolio_state", label: "Current portfolio state", primary: false, formatter: formatText },
  { key: "positions_currently_held", label: "Positions currently held", primary: false, formatter: formatInteger },
];

let activeStrategy = "mlp";
let selectedDateRange = "ALL";
let initializationStarted = false;
let activeRequestToken = 0;
let strategyData = createStrategyState(null);
let strategyErrors = createStrategyState(null);
let strategyMeta = null;
let chartInstances = createChartState();

function createStrategyState(initialValue) {
  return Object.fromEntries(STRATEGY_KEYS.map((strategy) => [strategy, initialValue]));
}

function createChartState() {
  return Object.fromEntries(
    STRATEGY_KEYS.map((strategy) => [
      strategy,
      {
        portfolio: null,
        equity: null,
        drawdown: null,
      },
    ])
  );
}

function setStatusMessage(message) {
  const element = document.getElementById("status");
  if (element) {
    element.textContent = message;
  }
}

function setDashboardStatus(message) {
  const element = document.getElementById("dashboardStatus");
  if (element) {
    element.textContent = message;
  }
}

function getPanel(strategy) {
  return document.getElementById(STRATEGIES[strategy].panelId);
}

function getPanelRole(strategy, role) {
  const panel = getPanel(strategy);
  return panel ? panel.querySelector(`[data-role="${role}"]`) : null;
}

function getKpiValueElement(strategy, key) {
  const panel = getPanel(strategy);
  return panel ? panel.querySelector(`[data-kpi="${key}"]`) : null;
}

function buildStrategyPanels() {
  const host = document.getElementById("strategyPanels");
  const template = document.getElementById("strategyPanelTemplate");
  if (!host || !template) {
    return;
  }

  host.replaceChildren();

  STRATEGY_KEYS.forEach((strategy) => {
    const fragment = template.content.cloneNode(true);
    const panel = fragment.querySelector("[data-role='strategyPanel']");
    const kpiGrid = fragment.querySelector("[data-role='kpiGrid']");
    const title = fragment.querySelector("[data-role='strategyTitle']");
    const note = fragment.querySelector("[data-role='strategyNote']");

    panel.id = STRATEGIES[strategy].panelId;
    panel.dataset.strategy = strategy;
    panel.hidden = strategy !== activeStrategy;
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", STRATEGIES[strategy].tabId);

    if (title) {
      title.textContent = STRATEGIES[strategy].label;
    }
    if (note) {
      note.textContent = STRATEGIES[strategy].note;
    }

    buildKpiGrid(kpiGrid);
    host.appendChild(fragment);
  });
}

function buildKpiGrid(container) {
  if (!container) {
    return;
  }

  container.replaceChildren();
  KPI_DEFINITIONS.forEach((definition) => {
    const card = document.createElement("div");
    card.className = definition.primary ? "kpi-card primary" : "kpi-card";

    const label = document.createElement("div");
    label.className = "label";
    label.textContent = definition.label;

    const value = document.createElement("div");
    value.className = "value";
    value.dataset.kpi = definition.key;
    value.textContent = EMPTY_VALUE;

    card.appendChild(label);
    card.appendChild(value);
    container.appendChild(card);
  });
}

function destroyChart(chart) {
  if (chart) {
    chart.destroy();
  }
}

function destroyStrategyCharts(strategy) {
  const bucket = chartInstances[strategy];
  if (!bucket) {
    return;
  }
  destroyChart(bucket.portfolio);
  destroyChart(bucket.equity);
  destroyChart(bucket.drawdown);
  bucket.portfolio = null;
  bucket.equity = null;
  bucket.drawdown = null;
}

function destroyAllCharts() {
  STRATEGY_KEYS.forEach((strategy) => destroyStrategyCharts(strategy));
}

function clearDetailList(container, message) {
  if (!container) {
    return;
  }

  container.replaceChildren();
  const row = document.createElement("div");
  row.className = "detail-row";

  const label = document.createElement("span");
  label.className = "label";
  label.textContent = "Status";

  const value = document.createElement("span");
  value.className = "value";
  value.textContent = message || EMPTY_VALUE;

  row.appendChild(label);
  row.appendChild(value);
  container.appendChild(row);
}

function showEmptyTradeTable(strategy, message) {
  const tbody = getPanelRole(strategy, "tradeTableBody");
  if (!tbody) {
    return;
  }

  tbody.replaceChildren();
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 7;
  cell.className = "empty-state";
  cell.textContent = message;
  row.appendChild(cell);
  tbody.appendChild(row);
}

function clearStrategyPanel(strategy, message) {
  const panel = getPanel(strategy);
  if (!panel) {
    return;
  }

  panel.dataset.loading = "false";
  setPanelStatus(strategy, message || "Run strategies to load this tab.", false);

  KPI_DEFINITIONS.forEach((definition) => {
    const value = getKpiValueElement(strategy, definition.key);
    if (!value) {
      return;
    }
    value.textContent = EMPTY_VALUE;
    value.classList.remove("positive", "negative");
  });

  clearDetailList(getPanelRole(strategy, "parameterSummary"), "No run loaded");
  clearDetailList(getPanelRole(strategy, "strategyDetails"), "No run loaded");
  showEmptyTradeTable(strategy, message || "Run strategies to load trade history.");
  destroyStrategyCharts(strategy);
}

function setPanelStatus(strategy, message, isError) {
  const status = getPanelRole(strategy, "panelStatus");
  if (!status) {
    return;
  }
  status.textContent = message;
  status.classList.toggle("error", Boolean(isError));
}

function setStrategyLoading(strategy, message) {
  const panel = getPanel(strategy);
  if (!panel) {
    return;
  }
  panel.dataset.loading = "true";
  setPanelStatus(strategy, message, false);
  KPI_DEFINITIONS.forEach((definition) => {
    const value = getKpiValueElement(strategy, definition.key);
    if (!value) {
      return;
    }
    value.textContent = EMPTY_VALUE;
    value.classList.remove("positive", "negative");
  });
  clearDetailList(getPanelRole(strategy, "parameterSummary"), "Loading...");
  clearDetailList(getPanelRole(strategy, "strategyDetails"), "Loading...");
  showEmptyTradeTable(strategy, "Loading trades...");
  destroyStrategyCharts(strategy);
}

function setActiveStrategy(strategy) {
  activeStrategy = strategy;

  STRATEGY_KEYS.forEach((key) => {
    const tab = document.getElementById(STRATEGIES[key].tabId);
    const panel = getPanel(key);
    const isActive = key === strategy;

    if (tab) {
      tab.classList.toggle("active", isActive);
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
    }
    if (panel) {
      panel.hidden = !isActive;
    }
  });

  renderStrategyPanel(strategy);
  updateVisibleDateRangeLabel();
}

function setDateRangeSelection(range) {
  selectedDateRange = range;
  document.querySelectorAll(".date-range-button").forEach((button) => {
    const isActive = button.getAttribute("data-range") === range;
    button.classList.toggle("active", isActive);
  });
  renderStrategyPanel(activeStrategy);
  updateVisibleDateRangeLabel();
}

function attachEventListeners() {
  const runButton = document.getElementById("runDashboardButton");
  const universeSelect = document.getElementById("universeSelect");

  if (runButton) {
    runButton.addEventListener("click", runStrategies);
  }

  if (universeSelect) {
    universeSelect.addEventListener("change", async () => {
      await loadStrategyMetadata();
      setDashboardStatus("Universe changed. Click Run strategies to apply the new settings.");
    });
  }

  document.querySelectorAll(".strategy-tab").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveStrategy(button.getAttribute("data-strategy") || "mlp");
    });
  });

  document.querySelectorAll(".date-range-button").forEach((button) => {
    button.addEventListener("click", () => {
      setDateRangeSelection(button.getAttribute("data-range") || "ALL");
    });
  });

  const startDateInput = document.getElementById("portfolioStartDate");
  const capitalInput = document.getElementById("initialCapital");
  [startDateInput, capitalInput].forEach((input) => {
    if (!input) {
      return;
    }
    input.addEventListener("change", () => {
      setDashboardStatus("Parameters changed. Click Run strategies to refresh all four tabs.");
    });
  });
}

function getSelectedUniverse() {
  const select = document.getElementById("universeSelect");
  return select ? select.value : "full";
}

function getSelectedStartDate() {
  const input = document.getElementById("portfolioStartDate");
  return input ? input.value : "";
}

function getSelectedInitialCapital() {
  const input = document.getElementById("initialCapital");
  return input ? Number.parseFloat(input.value) : NaN;
}

function formatNumber(value, digits = 2) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return EMPTY_VALUE;
  }
  return numeric.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatCurrency(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return EMPTY_VALUE;
  }
  return `${numeric.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} EGP`;
}

function formatPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return EMPTY_VALUE;
  }
  return `${numeric.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}%`;
}

function formatInteger(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return EMPTY_VALUE;
  }
  return Math.round(numeric).toLocaleString();
}

function formatText(value) {
  if (value === null || value === undefined || value === "") {
    return EMPTY_VALUE;
  }
  return String(value);
}

function formatBoolean(value) {
  if (value === null || value === undefined) {
    return EMPTY_VALUE;
  }
  return value ? "Yes" : "No";
}

function parseIsoDate(value) {
  if (!value || typeof value !== "string") {
    return null;
  }
  const parts = value.split("-").map((part) => Number.parseInt(part, 10));
  if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) {
    return null;
  }
  const parsed = new Date(parts[0], parts[1] - 1, parts[2]);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatDateDisplay(value) {
  if (!value) {
    return EMPTY_VALUE;
  }
  const parsed = parseIsoDate(value);
  if (!parsed) {
    return String(value);
  }
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(parsed);
}

function universeLabel(universe) {
  if (universe === "small") {
    return "Small universe";
  }
  if (universe === "full") {
    return "Full universe";
  }
  return formatText(universe);
}

function getVisibleRange(data) {
  if (!data || !Array.isArray(data.dates) || data.dates.length === 0) {
    return {
      startIndex: 0,
      endIndex: 0,
      text: "Visible chart window: waiting for strategy data.",
    };
  }

  const labels = data.dates;
  const endIndex = labels.length - 1;
  let startIndex = 0;

  if (selectedDateRange !== "ALL") {
    const latestDate = parseIsoDate(labels[endIndex]);
    if (latestDate) {
      const cutoff = new Date(latestDate);
      if (selectedDateRange === "1M") {
        cutoff.setMonth(cutoff.getMonth() - 1);
      } else if (selectedDateRange === "3M") {
        cutoff.setMonth(cutoff.getMonth() - 3);
      } else if (selectedDateRange === "6M") {
        cutoff.setMonth(cutoff.getMonth() - 6);
      } else if (selectedDateRange === "1Y") {
        cutoff.setFullYear(cutoff.getFullYear() - 1);
      } else if (selectedDateRange === "3Y") {
        cutoff.setFullYear(cutoff.getFullYear() - 3);
      }

      for (let index = 0; index < labels.length; index += 1) {
        const currentDate = parseIsoDate(labels[index]);
        if (currentDate && currentDate >= cutoff) {
          startIndex = index;
          break;
        }
      }
    }
  }

  return {
    startIndex,
    endIndex,
    text: `Visible chart window: ${formatDateDisplay(labels[startIndex])} to ${formatDateDisplay(labels[endIndex])}`,
  };
}

function updateVisibleDateRangeLabel() {
  const label = document.getElementById("visibleDateRange");
  if (!label) {
    return;
  }

  const data = strategyData[activeStrategy];
  const error = strategyErrors[activeStrategy];
  if (error) {
    label.textContent = "Visible chart window: no chart available in the active tab.";
    return;
  }
  label.textContent = getVisibleRange(data).text;
}

function sliceSeries(values, startIndex, endIndex) {
  return Array.isArray(values) ? values.slice(startIndex, endIndex + 1) : [];
}

function getVisibleSeries(data) {
  const range = getVisibleRange(data);
  return {
    range,
    dates: sliceSeries(data.dates, range.startIndex, range.endIndex),
    portfolioValues: sliceSeries(data.portfolio_values, range.startIndex, range.endIndex),
    benchmarkValues: sliceSeries(data.benchmark_values, range.startIndex, range.endIndex),
    equity: sliceSeries(data.equity, range.startIndex, range.endIndex),
    benchmarkEquity: sliceSeries(data.benchmark_equity, range.startIndex, range.endIndex),
    drawdown: sliceSeries(data.drawdown, range.startIndex, range.endIndex),
  };
}

function getDetailRowsForStrategy(strategy, data) {
  const parameters = data.parameters || {};
  const extra = data.extra || {};

  if (strategy === "mlp") {
    return [
      { label: "Model", value: parameters.model || "MLP" },
      { label: "Hidden size", value: formatInteger(extra.architecture_hidden) },
      { label: "Hidden layers", value: formatInteger(extra.hidden_layers) },
      { label: "Epochs", value: formatInteger(extra.epochs) },
      { label: "Learning rate", value: formatNumber(extra.learning_rate, 4) },
      { label: "Seed", value: formatInteger(extra.seed) },
      { label: "Selection rule", value: extra.selection_rule },
      {
        label: "Valid OOS period",
        value: `${formatDateDisplay(extra.oos_valid_start_date)} to ${formatDateDisplay(extra.oos_valid_end_date)}`,
      },
      { label: "Average stocks held", value: formatNumber(extra.average_stocks_held_full_period, 2) },
      { label: "Features", value: Array.isArray(extra.feature_names) ? extra.feature_names.join(", ") : EMPTY_VALUE },
    ];
  }

  if (strategy === "lstm") {
    return [
      { label: "Model", value: parameters.model || "LSTM" },
      { label: "Hidden size", value: formatInteger(extra.architecture_hidden) },
      { label: "Sequence length", value: formatInteger(extra.sequence_length) },
      { label: "Epochs", value: formatInteger(extra.epochs) },
      { label: "Learning rate", value: formatNumber(extra.learning_rate, 4) },
      { label: "Seed", value: formatInteger(extra.seed) },
      { label: "Selection rule", value: extra.selection_rule },
      {
        label: "Valid OOS period",
        value: `${formatDateDisplay(extra.oos_valid_start_date)} to ${formatDateDisplay(extra.oos_valid_end_date)}`,
      },
      { label: "Average stocks held", value: formatNumber(extra.average_stocks_held_full_period, 2) },
      { label: "Features", value: Array.isArray(extra.feature_names) ? extra.feature_names.join(", ") : EMPTY_VALUE },
    ];
  }

  if (strategy === "sma") {
    return [
      { label: "Fast MA", value: formatInteger(parameters.fast_window) },
      { label: "Slow MA", value: formatInteger(parameters.slow_window) },
      { label: "Observation lookback", value: `${formatInteger(extra.lookback_window_days)} days` },
      { label: "Signal rule", value: extra.signal_definition },
      { label: "Average stocks held", value: formatNumber(extra.average_stocks_held, 2) },
    ];
  }

  return [
    { label: "Lookback", value: `${formatInteger(parameters.lookback_days)} trading days` },
    { label: "Buy threshold", value: formatPercent(parameters.buy_threshold_pct) },
    { label: "Sell threshold", value: formatPercent(parameters.sell_threshold_pct) },
    { label: "Buy notional", value: formatCurrency(parameters.buy_notional) },
    { label: "Sell notional", value: formatCurrency(parameters.sell_notional) },
    { label: "Execution order", value: extra.execution_order },
    { label: "Fractional shares", value: formatBoolean(extra.fractional_shares) },
    { label: "Short selling", value: formatBoolean(extra.short_selling) },
    { label: "Signal rule", value: extra.signal_definition },
  ];
}

function renderDetailList(container, rows) {
  if (!container) {
    return;
  }

  container.replaceChildren();
  rows.forEach((rowData) => {
    const row = document.createElement("div");
    row.className = "detail-row";

    const label = document.createElement("span");
    label.className = "label";
    label.textContent = rowData.label;

    const value = document.createElement("span");
    value.className = "value";
    value.textContent = formatText(rowData.value);

    row.appendChild(label);
    row.appendChild(value);
    container.appendChild(row);
  });
}

function getConfigRows(data) {
  return [
    { label: "Universe", value: universeLabel(data.universe) },
    { label: "Requested start", value: formatDateDisplay(data.requested_start_date) },
    { label: "Actual start", value: formatDateDisplay(data.actual_start_date) },
    { label: "End date", value: formatDateDisplay(data.end_date) },
    { label: "Initial capital", value: formatCurrency(data.initial_cash) },
    { label: "Benchmark", value: data.benchmark_label },
  ];
}

function applyKpiClass(element, key, value, metrics) {
  if (!element) {
    return;
  }

  element.classList.remove("positive", "negative");
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return;
  }

  if (["profit_loss_egp", "total_return_pct", "benchmark_return_pct", "excess_return_pct", "sharpe_ratio"].includes(key)) {
    if (numeric > 0) {
      element.classList.add("positive");
    } else if (numeric < 0) {
      element.classList.add("negative");
    }
    return;
  }

  if (key === "final_portfolio_value") {
    const initial = Number(metrics.initial_portfolio_value);
    if (Number.isFinite(initial)) {
      if (numeric > initial) {
        element.classList.add("positive");
      } else if (numeric < initial) {
        element.classList.add("negative");
      }
    }
    return;
  }

  if (["maximum_drawdown_pct", "current_drawdown_pct"].includes(key) && numeric < 0) {
    element.classList.add("negative");
  }
}

function renderKpis(strategy, data) {
  const metrics = data.kpis || {};

  KPI_DEFINITIONS.forEach((definition) => {
    const element = getKpiValueElement(strategy, definition.key);
    if (!element) {
      return;
    }
    const value = metrics[definition.key];
    element.textContent = definition.formatter(value);
    applyKpiClass(element, definition.key, value, metrics);
  });
}

function formatTradeValue(key, value) {
  if (value === null || value === undefined || value === "") {
    return EMPTY_VALUE;
  }

  if (["price", "notional", "portfolio_value_after"].includes(key)) {
    return formatCurrency(value);
  }
  if (key === "shares") {
    return formatNumber(value, 6);
  }
  return formatText(value);
}

function renderTradeTable(strategy, trades) {
  const tbody = getPanelRole(strategy, "tradeTableBody");
  if (!tbody) {
    return;
  }

  tbody.replaceChildren();
  if (!Array.isArray(trades) || trades.length === 0) {
    showEmptyTradeTable(strategy, "No executed trades occurred for this backtest window.");
    return;
  }

  trades.forEach((trade) => {
    const row = document.createElement("tr");
    ["date", "operation", "symbol", "price", "shares", "notional", "portfolio_value_after"].forEach((key) => {
      const cell = document.createElement("td");
      cell.textContent = formatTradeValue(key, trade[key]);
      row.appendChild(cell);
    });
    tbody.appendChild(row);
  });
}

function axisNumber(value, digits = 2) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return EMPTY_VALUE;
  }
  return numeric.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function axisCurrency(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return EMPTY_VALUE;
  }
  return numeric.toLocaleString(undefined, {
    maximumFractionDigits: 0,
  });
}

function commonChartOptions({ yTitle, tickFormatter, labelFormatter, title, extraTooltipLine }) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    normalized: true,
    interaction: {
      mode: "index",
      axis: "x",
      intersect: false,
    },
    plugins: {
      legend: { display: true },
      title: {
        display: true,
        text: title,
      },
      tooltip: {
        callbacks: {
          title(items) {
            const first = items && items[0];
            return first ? `Date: ${formatDateDisplay(first.label)}` : "";
          },
          label(context) {
            return `${context.dataset.label}: ${labelFormatter(context.parsed.y)}`;
          },
          afterBody(items) {
            if (typeof extraTooltipLine !== "function") {
              return [];
            }
            const line = extraTooltipLine(items);
            return line ? [line] : [];
          },
        },
      },
    },
    scales: {
      x: {
        ticks: {
          autoSkip: true,
          maxTicksLimit: 12,
          minRotation: 0,
          maxRotation: 40,
        },
        grid: {
          color: "rgba(49, 72, 102, 0.3)",
        },
      },
      y: {
        title: {
          display: true,
          text: yTitle,
        },
        ticks: {
          callback: tickFormatter,
        },
        grid: {
          color: "rgba(49, 72, 102, 0.3)",
        },
      },
    },
  };
}

function renderPortfolioChart(strategy, data) {
  const panel = getPanel(strategy);
  if (!panel) {
    return;
  }

  const canvas = panel.querySelector("[data-chart='portfolio']");
  if (!canvas) {
    return;
  }

  destroyChart(chartInstances[strategy].portfolio);

  const visible = getVisibleSeries(data);
  const strategyColor = STRATEGIES[strategy].color;

  chartInstances[strategy].portfolio = new Chart(canvas, {
    type: "line",
    data: {
      labels: visible.dates,
      datasets: [
        {
          label: STRATEGIES[strategy].label,
          data: visible.portfolioValues,
          borderColor: strategyColor,
          backgroundColor: `${strategyColor}22`,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.18,
        },
        {
          label: data.benchmark_label || "Benchmark",
          data: visible.benchmarkValues,
          borderColor: "#fbbf24",
          backgroundColor: "rgba(251, 191, 36, 0.15)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.18,
        },
        {
          label: "Initial capital",
          data: visible.dates.map(() => data.initial_cash),
          borderColor: "#94a3b8",
          borderDash: [6, 6],
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0,
        },
      ],
    },
    options: commonChartOptions({
      yTitle: "Portfolio Value (EGP)",
      tickFormatter: axisCurrency,
      labelFormatter: formatCurrency,
      title: `${STRATEGIES[strategy].shortLabel} - Portfolio Value`,
    }),
  });
}

function renderEquityChart(strategy, data) {
  const panel = getPanel(strategy);
  if (!panel) {
    return;
  }

  const canvas = panel.querySelector("[data-chart='equity']");
  if (!canvas) {
    return;
  }

  destroyChart(chartInstances[strategy].equity);

  const visible = getVisibleSeries(data);
  const strategyColor = STRATEGIES[strategy].color;

  chartInstances[strategy].equity = new Chart(canvas, {
    type: "line",
    data: {
      labels: visible.dates,
      datasets: [
        {
          label: STRATEGIES[strategy].label,
          data: visible.equity,
          borderColor: strategyColor,
          backgroundColor: `${strategyColor}22`,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.18,
        },
        {
          label: data.benchmark_label || "Benchmark",
          data: visible.benchmarkEquity,
          borderColor: "#fbbf24",
          backgroundColor: "rgba(251, 191, 36, 0.15)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.18,
        },
      ],
    },
    options: commonChartOptions({
      yTitle: "Growth of Initial Capital",
      tickFormatter: (value) => axisNumber(value, 2),
      labelFormatter: (value) => axisNumber(value, 2),
      title: "Equity Growth",
      extraTooltipLine(items) {
        const first = items && items[0];
        if (!first || first.datasetIndex !== 0) {
          return "";
        }
        const numeric = Number(first.parsed.y);
        return Number.isFinite(numeric) ? `Strategy return since start: ${formatPercent((numeric - 1) * 100)}` : "";
      },
    }),
  });
}

function renderDrawdownChart(strategy, data) {
  const panel = getPanel(strategy);
  if (!panel) {
    return;
  }

  const canvas = panel.querySelector("[data-chart='drawdown']");
  if (!canvas) {
    return;
  }

  destroyChart(chartInstances[strategy].drawdown);

  const visible = getVisibleSeries(data);

  chartInstances[strategy].drawdown = new Chart(canvas, {
    type: "line",
    data: {
      labels: visible.dates,
      datasets: [
        {
          label: "Drawdown",
          data: visible.drawdown,
          borderColor: "#fb7185",
          backgroundColor: "rgba(251, 113, 133, 0.14)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.12,
          fill: "origin",
        },
      ],
    },
    options: {
      ...commonChartOptions({
        yTitle: "Drawdown (%)",
        tickFormatter: (value) => `${axisNumber(value, 0)}%`,
        labelFormatter: formatPercent,
        title: "Portfolio Drawdown",
      }),
      scales: {
        x: {
          ticks: {
            autoSkip: true,
            maxTicksLimit: 12,
            minRotation: 0,
            maxRotation: 40,
          },
          grid: {
            color: "rgba(49, 72, 102, 0.3)",
          },
        },
        y: {
          title: {
            display: true,
            text: "Drawdown (%)",
          },
          suggestedMax: 0,
          ticks: {
            callback(value) {
              return `${axisNumber(value, 0)}%`;
            },
          },
          grid: {
            color: "rgba(49, 72, 102, 0.3)",
          },
        },
      },
    },
  });
}

function renderStrategyPanel(strategy) {
  const panel = getPanel(strategy);
  if (!panel) {
    return;
  }

  const error = strategyErrors[strategy];
  const data = strategyData[strategy];
  const title = getPanelRole(strategy, "strategyTitle");
  const note = getPanelRole(strategy, "strategyNote");

  if (title) {
    title.textContent = data && data.strategy_label ? data.strategy_label : STRATEGIES[strategy].label;
  }
  if (note) {
    note.textContent = data && data.strategy_description ? data.strategy_description : STRATEGIES[strategy].note;
  }

  if (error) {
    panel.dataset.loading = "false";
    setPanelStatus(strategy, error.message || "Unable to load this strategy.", true);
    clearDetailList(getPanelRole(strategy, "parameterSummary"), "Unavailable");
    clearDetailList(getPanelRole(strategy, "strategyDetails"), "Unavailable");
    showEmptyTradeTable(strategy, error.message || "Unable to load trades.");
    KPI_DEFINITIONS.forEach((definition) => {
      const value = getKpiValueElement(strategy, definition.key);
      if (!value) {
        return;
      }
      value.textContent = EMPTY_VALUE;
      value.classList.remove("positive", "negative");
    });
    destroyStrategyCharts(strategy);
    return;
  }

  if (!data) {
    clearStrategyPanel(strategy, "Run strategies to load this tab.");
    return;
  }

  panel.dataset.loading = "false";
  setPanelStatus(
    strategy,
    `${data.strategy_label} loaded for the ${universeLabel(data.universe).toLowerCase()}. Actual start date: ${formatDateDisplay(data.actual_start_date)}.`,
    false
  );

  renderKpis(strategy, data);
  renderDetailList(getPanelRole(strategy, "parameterSummary"), getConfigRows(data));
  renderDetailList(getPanelRole(strategy, "strategyDetails"), getDetailRowsForStrategy(strategy, data));
  renderTradeTable(strategy, data.trades || []);

  if (strategy === activeStrategy) {
    renderPortfolioChart(strategy, data);
    renderEquityChart(strategy, data);
    renderDrawdownChart(strategy, data);
  }
}

function buildStrategyUrl(strategy) {
  const universe = getSelectedUniverse();
  const startDate = getSelectedStartDate();
  const initialCapital = getSelectedInitialCapital();
  const query = new URLSearchParams({
    universe,
    initial_cash: String(initialCapital),
    start_date: startDate,
  });
  return `${API}/strategy/${encodeURIComponent(strategy)}?${query.toString()}`;
}

async function fetchJson(url, fallbackMessage) {
  const response = await fetch(url);
  let payload = null;

  try {
    payload = await response.json();
  } catch (error) {
    payload = null;
  }

  if (!response.ok) {
    const detail = payload && Object.prototype.hasOwnProperty.call(payload, "detail") ? payload.detail : null;
    const message = typeof detail === "string" ? detail : (detail && detail.message) || fallbackMessage;
    const error = new Error(message);
    error.detail = detail;
    throw error;
  }

  return payload;
}

async function checkHealth() {
  try {
    const payload = await fetchJson(`${API}/health`, "Unable to reach backend.");
    setStatusMessage(`Backend status: ${payload.status}`);
    return true;
  } catch (error) {
    console.error(error);
    setStatusMessage("Backend not reachable. Start the FastAPI server to use the dashboard.");
    return false;
  }
}

async function loadStrategyMetadata() {
  const universe = getSelectedUniverse();
  const hint = document.getElementById("startDateHint");
  const startDateInput = document.getElementById("portfolioStartDate");

  try {
    strategyMeta = await fetchJson(
      `${API}/strategy-metadata?universe=${encodeURIComponent(universe)}`,
      "Unable to load strategy metadata."
    );

    if (startDateInput) {
      startDateInput.min = strategyMeta.market_history_start_date;
      startDateInput.max = strategyMeta.latest_start_date;

      const currentValue = startDateInput.value;
      const minDate = parseIsoDate(strategyMeta.market_history_start_date);
      const maxDate = parseIsoDate(strategyMeta.latest_start_date);
      const currentDate = currentValue ? parseIsoDate(currentValue) : null;
      const currentIsValid = currentDate
        && minDate
        && maxDate
        && currentDate >= minDate
        && currentDate <= maxDate;

      if (!currentIsValid) {
        startDateInput.value = strategyMeta.common_earliest_start_date;
      }
    }

    if (hint) {
      hint.textContent =
        `Common earliest comparison start for the ${universeLabel(universe).toLowerCase()}: `
        + `${formatDateDisplay(strategyMeta.common_earliest_start_date)}. `
        + "Earlier dates remain selectable, but neural tabs may return a clear unavailable message.";
    }
  } catch (error) {
    console.error(error);
    strategyMeta = null;
    if (hint) {
      hint.textContent = error.message || "Unable to load strategy metadata.";
    }
  }
}

function validateControls() {
  const startDate = getSelectedStartDate();
  const initialCapital = getSelectedInitialCapital();

  if (!startDate) {
    throw new Error("Please choose a portfolio start date.");
  }
  if (!Number.isFinite(initialCapital) || initialCapital <= 0) {
    throw new Error("Initial capital must be greater than zero.");
  }
}

function normalizeRunError(error) {
  if (!error) {
    return { message: "Unknown strategy error." };
  }
  if (error.detail && typeof error.detail === "object") {
    return {
      message: error.detail.message || error.message || "Strategy unavailable.",
      detail: error.detail,
    };
  }
  return {
    message: error.message || "Strategy unavailable.",
  };
}

async function runStrategies() {
  const runButton = document.getElementById("runDashboardButton");
  let initialCapital = NaN;

  try {
    validateControls();
    initialCapital = getSelectedInitialCapital();
  } catch (error) {
    setDashboardStatus(error.message || "Please review the shared controls.");
    return;
  }

  const requestToken = ++activeRequestToken;
  if (runButton) {
    runButton.disabled = true;
  }

  strategyData = createStrategyState(null);
  strategyErrors = createStrategyState(null);
  STRATEGY_KEYS.forEach((strategy) => {
    setStrategyLoading(strategy, "Running strategy...");
  });

  const universe = getSelectedUniverse();
  const startDate = getSelectedStartDate();
  setDashboardStatus("Running strategies...");

  const tasks = STRATEGY_KEYS.map(async (strategy) => {
    try {
      const payload = await fetchJson(buildStrategyUrl(strategy), "Strategy request failed.");
      if (requestToken !== activeRequestToken) {
        return;
      }
      strategyData[strategy] = payload;
      strategyErrors[strategy] = null;
    } catch (error) {
      if (requestToken !== activeRequestToken) {
        return;
      }
      strategyData[strategy] = null;
      strategyErrors[strategy] = normalizeRunError(error);
    }
  });

  await Promise.allSettled(tasks);

  if (requestToken !== activeRequestToken) {
    return;
  }

  STRATEGY_KEYS.forEach((strategy) => {
    renderStrategyPanel(strategy);
  });

  const successCount = STRATEGY_KEYS.filter((strategy) => Boolean(strategyData[strategy])).length;
  const failureCount = STRATEGY_KEYS.length - successCount;

  if (successCount === STRATEGY_KEYS.length) {
    setDashboardStatus(
      `Loaded all four strategies for ${formatDateDisplay(startDate)}, ${universeLabel(universe).toLowerCase()}, and ${formatCurrency(initialCapital)}.`
    );
  } else if (successCount > 0) {
    setDashboardStatus(
      `Loaded ${successCount} strategy tabs and ${failureCount} tab${failureCount === 1 ? "" : "s"} reported a clear error for the current start date.`
    );
  } else {
    setDashboardStatus("No strategy completed successfully for the current settings.");
  }

  renderStrategyPanel(activeStrategy);
  updateVisibleDateRangeLabel();

  if (runButton && requestToken === activeRequestToken) {
    runButton.disabled = false;
  }
}

async function initializeDashboard() {
  if (initializationStarted) {
    return;
  }
  initializationStarted = true;

  buildStrategyPanels();
  attachEventListeners();
  setDateRangeSelection("ALL");
  clearAllPanels();

  const backendHealthy = await checkHealth();
  await loadStrategyMetadata();

  if (backendHealthy) {
    await runStrategies();
  } else {
    setDashboardStatus("Backend unavailable. Start the server, then reload the page.");
  }
}

function clearAllPanels() {
  STRATEGY_KEYS.forEach((strategy) => {
    clearStrategyPanel(strategy, "Run strategies to load this tab.");
  });
}

initializeDashboard();
