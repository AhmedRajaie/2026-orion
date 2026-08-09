// Dashboard frontend for the weekly contrarian strategy.
const API = "http://localhost:8000";

let equityChart = null;
let priceChart = null;
let operationsChart = null;
let initializationStarted = false;
let activeRequestToken = 0;
let selectedUniverse = "small";
let currentBacktestData = null;
let selectedDateRange = "ALL";

function setStatusMessage(message) {
  const statusElement = document.getElementById("status");
  if (statusElement) {
    statusElement.textContent = message;
  }
}

function setStrategyStatus(message) {
  const statusElement = document.getElementById("strategyStatus");
  if (statusElement) {
    statusElement.textContent = message;
  }
}

function defaultStrategyStatus() {
  return "Portfolio: selected universe. Price chart: selected stock.";
}

function destroyChart(chartInstance) {
  if (chartInstance) {
    chartInstance.destroy();
  }
}

function destroyAllCharts() {
  destroyChart(equityChart);
  destroyChart(priceChart);
  destroyChart(operationsChart);
  equityChart = null;
  priceChart = null;
  operationsChart = null;
}

function clearKpiValues() {
  const ids = [
    "kpiTotalReturn",
    "kpiSharpe",
    "kpiMaxDrawdown",
    "kpiFinalValue",
    "kpiProfitLoss",
    "kpiBenchmarkReturn",
    "kpiExcessReturn",
    "kpiBuyOperations",
    "kpiSellOperations",
    "kpiSkippedBuys",
    "kpiOpenPositions",
  ];

  ids.forEach((id) => {
    const element = document.getElementById(id);
    if (!element) {
      return;
    }
    element.textContent = "—";
    element.classList.remove("positive", "negative");
  });
}

function showEmptyTradeTable(message) {
  const tbody = document.getElementById("tradeTableBody");
  if (!tbody) {
    return;
  }

  tbody.replaceChildren();
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 9;
  cell.className = "empty-state";
  cell.textContent = message;
  row.appendChild(cell);
  tbody.appendChild(row);
}

function clearDashboardResults(message) {
  currentBacktestData = null;
  destroyAllCharts();
  clearKpiValues();
  updateVisibleDateRangeLabel();
  showEmptyTradeTable(message);
}

function getVisibleDateRangeText(startIndex, endIndex, totalPoints) {
  if (!Number.isFinite(startIndex) || !Number.isFinite(endIndex) || totalPoints <= 0) {
    return "Showing all available dates";
  }

  const labels = currentBacktestData && Array.isArray(currentBacktestData.dates)
    ? currentBacktestData.dates
    : [];
  const startLabel = labels[startIndex];
  const endLabel = labels[endIndex];

  if (!startLabel || !endLabel) {
    return `Showing ${startIndex + 1}-${endIndex + 1} of ${totalPoints} dates`;
  }

  return `Showing ${startLabel} to ${endLabel}`;
}

function getVisibleDateRange() {
  const labels = currentBacktestData && Array.isArray(currentBacktestData.dates)
    ? currentBacktestData.dates
    : [];

  if (!labels.length) {
    return { startIndex: 0, endIndex: 0, text: "Showing all available dates" };
  }

  const total = labels.length;
  const endIndex = total - 1;
  let startIndex = 0;

  if (selectedDateRange !== "ALL") {
    const latestDate = new Date(labels[endIndex]);
    if (!Number.isNaN(latestDate.getTime())) {
      const cutoffDate = new Date(latestDate);
      if (selectedDateRange === "1M") {
        cutoffDate.setMonth(cutoffDate.getMonth() - 1);
      } else if (selectedDateRange === "3M") {
        cutoffDate.setMonth(cutoffDate.getMonth() - 3);
      } else if (selectedDateRange === "6M") {
        cutoffDate.setMonth(cutoffDate.getMonth() - 6);
      } else if (selectedDateRange === "1Y") {
        cutoffDate.setFullYear(cutoffDate.getFullYear() - 1);
      } else if (selectedDateRange === "3Y") {
        cutoffDate.setFullYear(cutoffDate.getFullYear() - 3);
      }

      for (let index = 0; index < labels.length; index += 1) {
        const currentDate = new Date(labels[index]);
        if (!Number.isNaN(currentDate.getTime()) && currentDate >= cutoffDate) {
          startIndex = index;
          break;
        }
      }
    }
  }

  return {
    startIndex,
    endIndex,
    text: getVisibleDateRangeText(startIndex, endIndex, total),
  };
}

function updateVisibleDateRangeLabel() {
  const labelElement = document.getElementById("visibleDateRange");
  if (!labelElement) {
    return;
  }
  labelElement.textContent = getVisibleDateRange().text;
}

function sliceSeries(values, startIndex, endIndex) {
  return Array.isArray(values) ? values.slice(startIndex, endIndex + 1) : [];
}

function getFilteredBacktestView() {
  if (!currentBacktestData) {
    return null;
  }

  const { startIndex, endIndex } = getVisibleDateRange();
  const safeStart = Math.max(0, startIndex);
  const safeEnd = Math.max(safeStart, endIndex);

  return {
    ...currentBacktestData,
    dates: sliceSeries(currentBacktestData.dates, safeStart, safeEnd),
    portfolio: sliceSeries(currentBacktestData.portfolio, safeStart, safeEnd),
    benchmark: sliceSeries(currentBacktestData.benchmark, safeStart, safeEnd),
    portfolio_values_egp: sliceSeries(currentBacktestData.portfolio_values_egp, safeStart, safeEnd),
    benchmark_values_egp: sliceSeries(currentBacktestData.benchmark_values_egp, safeStart, safeEnd),
    cash_history: sliceSeries(currentBacktestData.cash_history, safeStart, safeEnd),
    invested_value_history: sliceSeries(currentBacktestData.invested_value_history, safeStart, safeEnd),
    number_of_positions_history: sliceSeries(currentBacktestData.number_of_positions_history, safeStart, safeEnd),
    daily_buy_operations: sliceSeries(currentBacktestData.daily_buy_operations, safeStart, safeEnd),
    daily_sell_operations: sliceSeries(currentBacktestData.daily_sell_operations, safeStart, safeEnd),
    selected_asset: currentBacktestData.selected_asset
      ? {
          ...currentBacktestData.selected_asset,
          dates: sliceSeries(currentBacktestData.selected_asset.dates, safeStart, safeEnd),
          close: sliceSeries(currentBacktestData.selected_asset.close, safeStart, safeEnd),
          buy_markers: sliceSeries(currentBacktestData.selected_asset.buy_markers, safeStart, safeEnd),
          sell_markers: sliceSeries(currentBacktestData.selected_asset.sell_markers, safeStart, safeEnd),
        }
      : null,
  };
}

function applyChartDefaults(chart) {
  if (!chart) {
    return;
  }

  chart.options.animation = false;
  chart.options.normalized = true;
  chart.options.interaction = {
    mode: "index",
    axis: "x",
    intersect: false,
  };

  if (chart.options.scales && chart.options.scales.x) {
    chart.options.scales.x.ticks = {
      autoSkip: true,
      maxTicksLimit: 14,
      minRotation: 0,
      maxRotation: 45,
    };
  }

  chart.update("none");
}

function setDateRangeSelection(range) {
  selectedDateRange = range;
  const buttons = document.querySelectorAll(".date-range-button");
  buttons.forEach((button) => {
    const isActive = button.getAttribute("data-range") === range;
    button.classList.toggle("active", isActive);
  });

  updateVisibleDateRangeLabel();
  if (currentBacktestData) {
    renderEquityChart(currentBacktestData);
    renderPriceChart(currentBacktestData);
    renderOperationsChart(currentBacktestData);
  }
}

function attachChartNavigationListeners() {
  const buttons = document.querySelectorAll(".date-range-button");
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      setDateRangeSelection(button.getAttribute("data-range") || "ALL");
    });
  });
}

function addChartCanvasEvents() {
  ["equityChart", "priceChart", "operationsChart"].forEach((id) => {
    const canvas = document.getElementById(id);
    if (canvas) {
      canvas.addEventListener("dblclick", () => setDateRangeSelection("ALL"));
    }
  });
}

function formatEGP(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  return `${numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} EGP`;
}

function formatPercentDecimal(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  return `${(numeric * 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function formatRatio(value, digits = 3) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  return numeric.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function formatCount(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  return Math.round(numeric).toLocaleString();
}

function formatShares(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  return numeric.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 6 });
}

function setValueClass(element, state) {
  if (!element) {
    return;
  }
  element.classList.remove("positive", "negative");
  if (state === "positive") {
    element.classList.add("positive");
  } else if (state === "negative") {
    element.classList.add("negative");
  }
}

function renderKpis(metrics, parameters) {
  if (!metrics) {
    clearKpiValues();
    return;
  }

  const initialCash = parameters ? Number(parameters.initial_cash) : NaN;

  const totalReturn = document.getElementById("kpiTotalReturn");
  const sharpe = document.getElementById("kpiSharpe");
  const maxDrawdown = document.getElementById("kpiMaxDrawdown");
  const finalValue = document.getElementById("kpiFinalValue");
  const profitLoss = document.getElementById("kpiProfitLoss");
  const benchmarkReturn = document.getElementById("kpiBenchmarkReturn");
  const excessReturn = document.getElementById("kpiExcessReturn");
  const buyOperations = document.getElementById("kpiBuyOperations");
  const sellOperations = document.getElementById("kpiSellOperations");
  const skippedBuys = document.getElementById("kpiSkippedBuys");
  const openPositions = document.getElementById("kpiOpenPositions");

  if (totalReturn) {
    totalReturn.textContent = formatPercentDecimal(metrics.total_return);
    setValueClass(totalReturn, Number(metrics.total_return) >= 0 ? "positive" : "negative");
  }
  if (sharpe) {
    sharpe.textContent = formatRatio(metrics.sharpe, 3);
    setValueClass(sharpe, Number(metrics.sharpe) >= 0 ? "positive" : "negative");
  }
  if (maxDrawdown) {
    maxDrawdown.textContent = formatPercentDecimal(metrics.max_drawdown);
    setValueClass(maxDrawdown, Number(metrics.max_drawdown) > 0 ? "negative" : null);
  }
  if (finalValue) {
    finalValue.textContent = formatEGP(metrics.final_portfolio_value);
    if (Number.isFinite(initialCash)) {
      if (Number(metrics.final_portfolio_value) > initialCash) {
        setValueClass(finalValue, "positive");
      } else if (Number(metrics.final_portfolio_value) < initialCash) {
        setValueClass(finalValue, "negative");
      } else {
        setValueClass(finalValue, null);
      }
    }
  }
  if (profitLoss) {
    profitLoss.textContent = formatEGP(metrics.profit_loss_egp);
    setValueClass(profitLoss, Number(metrics.profit_loss_egp) >= 0 ? "positive" : "negative");
  }
  if (benchmarkReturn) {
    benchmarkReturn.textContent = formatPercentDecimal(metrics.benchmark_total_return);
    setValueClass(benchmarkReturn, Number(metrics.benchmark_total_return) >= 0 ? "positive" : "negative");
  }
  if (excessReturn) {
    excessReturn.textContent = formatPercentDecimal(metrics.excess_return);
    setValueClass(excessReturn, Number(metrics.excess_return) >= 0 ? "positive" : "negative");
  }
  if (buyOperations) {
    buyOperations.textContent = formatCount(metrics.buy_operations);
  }
  if (sellOperations) {
    sellOperations.textContent = formatCount(metrics.sell_operations);
  }
  if (skippedBuys) {
    skippedBuys.textContent = formatCount(metrics.skipped_buy_operations);
  }
  if (openPositions) {
    openPositions.textContent = formatCount(metrics.open_positions);
  }
}

function renderEquityChart(data) {
  destroyChart(equityChart);

  const viewData = getFilteredBacktestView() || data;
  const canvas = document.getElementById("equityChart");
  if (!canvas) {
    return;
  }

  equityChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: Array.isArray(viewData.dates) ? viewData.dates : [],
      datasets: [
        {
          label: "Weekly contrarian strategy",
          data: Array.isArray(viewData.portfolio) ? viewData.portfolio : [],
          borderColor: "#4f8cff",
          backgroundColor: "rgba(79, 140, 255, 0.18)",
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.18,
        },
        {
          label: "Equal-weight buy and hold",
          data: Array.isArray(viewData.benchmark) ? viewData.benchmark : [],
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.16)",
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.18,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true },
        title: {
          display: true,
          text: "Equity curve vs benchmark",
        },
      },
      scales: {
        x: {},
        y: {
          title: {
            display: true,
            text: "Growth of 1.0 EGP",
          },
        },
      },
    },
  });

  applyChartDefaults(equityChart);
}

function renderPriceChart(data) {
  destroyChart(priceChart);

  const viewData = getFilteredBacktestView() || data;
  const asset = viewData.selected_asset || {};
  const canvas = document.getElementById("priceChart");
  if (!canvas) {
    return;
  }

  priceChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: Array.isArray(asset.dates) ? asset.dates : [],
      datasets: [
        {
          label: "Close",
          data: Array.isArray(asset.close) ? asset.close : [],
          borderColor: "#7dd3fc",
          backgroundColor: "rgba(125, 211, 252, 0.16)",
          pointRadius: 0,
          borderWidth: 1.8,
          tension: 0.15,
          spanGaps: false,
        },
        {
          label: "Executed buys",
          data: Array.isArray(asset.buy_markers) ? asset.buy_markers : [],
          showLine: false,
          pointStyle: "triangle",
          pointRadius: 7,
          pointHoverRadius: 9,
          pointBorderColor: "#22c55e",
          pointBackgroundColor: "#22c55e",
          borderColor: "#22c55e",
          backgroundColor: "#22c55e",
          spanGaps: false,
        },
        {
          label: "Executed sells",
          data: Array.isArray(asset.sell_markers) ? asset.sell_markers : [],
          showLine: false,
          pointStyle: "triangle",
          pointRotation: 180,
          pointRadius: 7,
          pointHoverRadius: 9,
          pointBorderColor: "#ef4444",
          pointBackgroundColor: "#ef4444",
          borderColor: "#ef4444",
          backgroundColor: "#ef4444",
          spanGaps: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true },
        title: {
          display: true,
          text: `${data.selected_symbol} — executed weekly contrarian trades`,
        },
      },
      scales: {
        x: {},
        y: {
          title: {
            display: true,
            text: "Price (EGP)",
          },
        },
      },
    },
  });

  applyChartDefaults(priceChart);
}

function renderOperationsChart(data) {
  destroyChart(operationsChart);

  const viewData = getFilteredBacktestView() || data;
  const canvas = document.getElementById("operationsChart");
  if (!canvas) {
    return;
  }

  operationsChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: Array.isArray(viewData.dates) ? viewData.dates : [],
      datasets: [
        {
          label: "Daily buys",
          data: Array.isArray(viewData.daily_buy_operations) ? viewData.daily_buy_operations : [],
          backgroundColor: "rgba(34, 197, 94, 0.7)",
          borderColor: "#22c55e",
          borderWidth: 1,
        },
        {
          label: "Daily sells",
          data: Array.isArray(viewData.daily_sell_operations) ? viewData.daily_sell_operations : [],
          backgroundColor: "rgba(239, 68, 68, 0.7)",
          borderColor: "#ef4444",
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true },
        title: {
          display: true,
          text: "Daily buy and sell operations",
        },
      },
      scales: {
        x: {},
        y: {
          beginAtZero: true,
          title: {
            display: true,
            text: "Operations",
          },
          ticks: {
            precision: 0,
          },
        },
      },
    },
  });

  applyChartDefaults(operationsChart);
}

function renderTradeTable(trades) {
  const tbody = document.getElementById("tradeTableBody");
  if (!tbody) {
    return;
  }

  tbody.replaceChildren();
  if (!Array.isArray(trades) || trades.length === 0) {
    showEmptyTradeTable("No executed trades occurred for this backtest.");
    return;
  }

  trades.forEach((trade) => {
    const row = document.createElement("tr");
    const values = [
      trade.operation || "—",
      trade.date || "—",
      trade.symbol || "—",
      formatPercentDecimal(trade.signal_return),
      formatEGP(trade.price),
      formatEGP(trade.notional),
      formatShares(trade.shares),
      formatEGP(trade.cash_after),
      formatShares(trade.position_after),
    ];

    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });

    tbody.appendChild(row);
  });
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
    const detail = payload && payload.detail ? payload.detail : fallbackMessage;
    throw new Error(detail);
  }

  return payload;
}

async function checkHealth() {
  try {
    const data = await fetchJson(`${API}/health`, "Unable to reach backend.");
    setStatusMessage(`backend: ${data.status}`);
    return true;
  } catch (error) {
    console.error(error);
    setStatusMessage("backend not reachable — start uvicorn");
    return false;
  }
}

async function loadUniverse(universe, preferredSymbol) {
  const universeSelect = document.getElementById("universeSelect");
  const symbolSelect = document.getElementById("symbolSelect");
  if (!symbolSelect) {
    return [];
  }

  if (universeSelect) {
    universeSelect.value = universe;
  }

  const symbols = await fetchJson(
    `${API}/universe?universe=${encodeURIComponent(universe)}`,
    "Unable to load universe."
  );

  symbolSelect.replaceChildren();
  symbols.forEach((symbol) => {
    const option = document.createElement("option");
    option.value = symbol;
    option.textContent = symbol;
    symbolSelect.appendChild(option);
  });

  if (symbols.length > 0) {
    const nextSymbol = preferredSymbol && symbols.includes(preferredSymbol)
      ? preferredSymbol
      : symbols[0];
    symbolSelect.value = nextSymbol;
  }

  return symbols;
}

function getStrategyParameters() {
  const symbolSelect = document.getElementById("symbolSelect");
  const lookbackInput = document.getElementById("lookbackDays");
  const buyThresholdInput = document.getElementById("buyThreshold");
  const sellThresholdInput = document.getElementById("sellThreshold");
  const buyNotionalInput = document.getElementById("buyNotional");
  const sellNotionalInput = document.getElementById("sellNotional");
  const initialCashInput = document.getElementById("initialCash");

  const symbol = symbolSelect ? symbolSelect.value : "";
  const lookbackDays = Number.parseInt(lookbackInput ? lookbackInput.value : "", 10);
  const buyThresholdPercent = Number.parseFloat(buyThresholdInput ? buyThresholdInput.value : "");
  const sellThresholdPercent = Number.parseFloat(sellThresholdInput ? sellThresholdInput.value : "");
  const buyNotional = Number.parseFloat(buyNotionalInput ? buyNotionalInput.value : "");
  const sellNotional = Number.parseFloat(sellNotionalInput ? sellNotionalInput.value : "");
  const initialCash = Number.parseFloat(initialCashInput ? initialCashInput.value : "");

  if (!symbol) {
    throw new Error("Please select a stock for the diagnostic chart.");
  }
  if (!Number.isFinite(lookbackDays) || lookbackDays < 1) {
    throw new Error("Lookback days must be at least 1.");
  }
  if (!Number.isFinite(buyThresholdPercent) || buyThresholdPercent >= 0) {
    throw new Error("Buy threshold must be negative.");
  }
  if (!Number.isFinite(sellThresholdPercent) || sellThresholdPercent <= 0) {
    throw new Error("Sell threshold must be positive.");
  }
  if (!Number.isFinite(buyNotional) || buyNotional <= 0) {
    throw new Error("Buy notional must be greater than zero.");
  }
  if (!Number.isFinite(sellNotional) || sellNotional <= 0) {
    throw new Error("Sell notional must be greater than zero.");
  }
  if (!Number.isFinite(initialCash) || initialCash <= 0) {
    throw new Error("Initial cash must be greater than zero.");
  }

  return {
    universe: selectedUniverse,
    symbol,
    lookback_days: lookbackDays,
    buy_threshold: buyThresholdPercent / 100,
    sell_threshold: sellThresholdPercent / 100,
    buy_notional: buyNotional,
    sell_notional: sellNotional,
    initial_cash: initialCash,
  };
}

function buildBacktestUrl(parameters) {
  const query = new URLSearchParams({
    universe: parameters.universe,
    symbol: parameters.symbol,
    lookback_days: String(parameters.lookback_days),
    buy_threshold: String(parameters.buy_threshold),
    sell_threshold: String(parameters.sell_threshold),
    buy_notional: String(parameters.buy_notional),
    sell_notional: String(parameters.sell_notional),
    initial_cash: String(parameters.initial_cash),
  });
  return `${API}/backtest?${query.toString()}`;
}

async function runBacktest() {
  const runButton = document.getElementById("runBacktestButton");
  let parameters;

  try {
    parameters = getStrategyParameters();
  } catch (error) {
    setStrategyStatus(error.message || "Please review the strategy parameters.");
    return;
  }

  const requestToken = ++activeRequestToken;
  if (runButton) {
    runButton.disabled = true;
  }

  clearDashboardResults("Running weekly contrarian backtest...");
  setStrategyStatus("Running weekly contrarian backtest...");

  try {
    const payload = await fetchJson(
      buildBacktestUrl(parameters),
      "Backtest request failed."
    );

    if (requestToken !== activeRequestToken) {
      return;
    }

    currentBacktestData = payload;
    updateVisibleDateRangeLabel();
    renderKpis(payload.metrics || {}, payload.parameters || {});
    renderEquityChart(payload);
    renderPriceChart(payload);
    renderOperationsChart(payload);
    renderTradeTable(payload.trades || []);
    setStrategyStatus(
      `${payload.strategy.name} loaded for the ${payload.universe} universe. `
      + `Selected stock diagnostics: ${payload.selected_symbol}.`
    );
  } catch (error) {
    console.error(error);
    if (requestToken !== activeRequestToken) {
      return;
    }
    clearDashboardResults("No executed trades occurred for this backtest.");
    setStrategyStatus(error.message || "Unable to load backtest data.");
  } finally {
    if (runButton && requestToken === activeRequestToken) {
      runButton.disabled = false;
    }
  }
}

async function handleUniverseChange() {
  const universeSelect = document.getElementById("universeSelect");
  const nextUniverse = universeSelect ? universeSelect.value : "small";
  selectedUniverse = nextUniverse;

  try {
    setStrategyStatus("Loading the selected universe...");
    await loadUniverse(selectedUniverse);
    await runBacktest();
  } catch (error) {
    console.error(error);
    clearDashboardResults("Run a backtest to load trades.");
    setStrategyStatus(error.message || "Unable to load the selected universe.");
  }
}

function attachEventListeners() {
  const runButton = document.getElementById("runBacktestButton");
  const universeSelect = document.getElementById("universeSelect");
  const symbolSelect = document.getElementById("symbolSelect");

  if (runButton) {
    runButton.addEventListener("click", runBacktest);
  }
  if (universeSelect) {
    universeSelect.addEventListener("change", handleUniverseChange);
  }
  if (symbolSelect) {
    symbolSelect.addEventListener("change", runBacktest);
  }
}

async function initializeDashboard() {
  if (initializationStarted) {
    return;
  }
  initializationStarted = true;

  setDateRangeSelection("ALL");
  setStrategyStatus(defaultStrategyStatus());
  attachEventListeners();
  attachChartNavigationListeners();
  addChartCanvasEvents();

  await checkHealth();

  const universeSelect = document.getElementById("universeSelect");
  if (universeSelect && universeSelect.value) {
    selectedUniverse = universeSelect.value;
  }

  try {
    await loadUniverse(selectedUniverse);
    await runBacktest();
  } catch (error) {
    console.error(error);
    setStrategyStatus(error.message || "Unable to initialize the dashboard.");
  }
}

initializeDashboard();
