// Dashboard frontend. Grows via dashboard/tasks/.
const API = "http://localhost:8000";
let strategyPriceChart = null;
let portfolioChart = null;
let initializationStarted = false;
let isSynchronizingCharts = false;
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

function getVisibleDateRangeText(startIndex, endIndex, totalPoints) {
  if (!Number.isFinite(startIndex) || !Number.isFinite(endIndex) || totalPoints <= 0) {
    return "Showing all available dates";
  }

  const labels = currentBacktestData && Array.isArray(currentBacktestData.dates) ? currentBacktestData.dates : [];
  const startLabel = labels[startIndex];
  const endLabel = labels[endIndex];

  if (!startLabel || !endLabel) {
    return `Showing ${startIndex + 1}-${endIndex + 1} of ${totalPoints} dates`;
  }

  return `Showing ${startLabel} to ${endLabel}`;
}

function updateVisibleDateRangeLabel() {
  const labelElement = document.getElementById("visibleDateRange");
  if (!labelElement) {
    return;
  }

  const visibleRange = getVisibleDateRange();
  labelElement.textContent = visibleRange.text;
}

function getVisibleDateRange() {
  const labels = currentBacktestData && Array.isArray(currentBacktestData.dates) ? currentBacktestData.dates : [];
  if (!labels.length) {
    return { startIndex: 0, endIndex: 0, text: "Showing all available dates" };
  }

  const total = labels.length;
  const endIndex = total - 1;
  let startIndex = 0;

  if (selectedDateRange !== "ALL") {
    const latestLabel = labels[endIndex];
    const latestDate = latestLabel ? new Date(latestLabel) : null;

    if (latestDate && !Number.isNaN(latestDate.getTime())) {
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
        const currentDate = labels[index] ? new Date(labels[index]) : null;
        if (currentDate && !Number.isNaN(currentDate.getTime()) && currentDate >= cutoffDate) {
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

function getFilteredBacktestView() {
  if (!currentBacktestData) {
    return null;
  }

  const { startIndex, endIndex } = getVisibleDateRange();
  const labels = Array.isArray(currentBacktestData.dates) ? currentBacktestData.dates : [];
  const total = labels.length;

  if (startIndex >= total || endIndex < 0) {
    return null;
  }

  const safeStart = Math.max(0, Math.min(total - 1, startIndex));
  const safeEnd = Math.max(safeStart, Math.min(total - 1, endIndex));

  const slice = (values) => Array.isArray(values) ? values.slice(safeStart, safeEnd + 1) : [];
  const sliceLabels = labels.slice(safeStart, safeEnd + 1);

  return {
    ...currentBacktestData,
    dates: sliceLabels,
    close: slice(currentBacktestData.close),
    fast_ma: slice(currentBacktestData.fast_ma),
    slow_ma: slice(currentBacktestData.slow_ma),
    buy_markers: slice(currentBacktestData.buy_markers),
    sell_markers: slice(currentBacktestData.sell_markers),
    portfolio_values: slice(currentBacktestData.portfolio_values),
    buy_hold_values: slice(currentBacktestData.buy_hold_values),
  };
}

function applyChartDefaults(chart) {
  if (!chart) {
    return;
  }
  chart.options.animation = false;
  chart.options.normalized = true;
  chart.options.interaction = {
    mode: "nearest",
    axis: "x",
    intersect: false,
  };
  chart.options.scales.x.ticks = {
    autoSkip: true,
    maxTicksLimit: 14,
    minRotation: 0,
    maxRotation: 45,
  };
}

function setChartView(chart) {
  if (!chart) {
    return;
  }
  applyChartDefaults(chart);
  chart.update("none");
}

function setChartRangeState(chart, data) {
  if (!chart) {
    return;
  }
  applyChartDefaults(chart);
  setChartView(chart);
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
    renderStrategyPriceChart(currentBacktestData);
    renderPortfolioChart(currentBacktestData);
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
  const priceCanvas = document.getElementById("strategyPriceChart");
  const portfolioCanvas = document.getElementById("portfolioChart");

  if (priceCanvas) {
    priceCanvas.addEventListener("dblclick", () => setDateRangeSelection("ALL"));
  }
  if (portfolioCanvas) {
    portfolioCanvas.addEventListener("dblclick", () => setDateRangeSelection("ALL"));
  }
}

function clearKpiValues() {
  const ids = [
    "kpiFinalValue",
    "kpiProfitLoss",
    "kpiTotalReturn",
    "kpiMaxDrawdown",
    "kpiMaxDrawdownPct",
    "kpiBuyOperations",
    "kpiSellOperations",
    "kpiCompletedTrades",
    "kpiExposure",
    "kpiFinalPosition",
    "kpiBuyHoldReturn",
    "kpiExcessReturn",
  ];

  ids.forEach((id) => {
    const element = document.getElementById(id);
    if (element) {
      element.textContent = "—";
      element.classList.remove("positive", "negative");
    }
  });
}

function formatEGP(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} EGP`;
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function applyValueClass(element, value) {
  if (!element) {
    return;
  }
  element.classList.remove("positive", "negative");
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return;
  }
  if (Number(value) > 0) {
    element.classList.add("positive");
  } else if (Number(value) < 0) {
    element.classList.add("negative");
  }
}

function renderKpis(kpis) {
  if (!kpis) {
    clearKpiValues();
    return;
  }

  const finalValue = document.getElementById("kpiFinalValue");
  const profitLoss = document.getElementById("kpiProfitLoss");
  const totalReturn = document.getElementById("kpiTotalReturn");
  const maxDrawdown = document.getElementById("kpiMaxDrawdown");
  const maxDrawdownPct = document.getElementById("kpiMaxDrawdownPct");
  const buyOperations = document.getElementById("kpiBuyOperations");
  const sellOperations = document.getElementById("kpiSellOperations");
  const completedTrades = document.getElementById("kpiCompletedTrades");
  const exposure = document.getElementById("kpiExposure");
  const finalPosition = document.getElementById("kpiFinalPosition");
  const buyHoldReturn = document.getElementById("kpiBuyHoldReturn");
  const excessReturn = document.getElementById("kpiExcessReturn");

  if (finalValue) {
    finalValue.textContent = formatEGP(kpis.final_portfolio_value);
    applyValueClass(finalValue, kpis.final_portfolio_value);
  }
  if (profitLoss) {
    profitLoss.textContent = formatEGP(kpis.profit_loss_egp);
    applyValueClass(profitLoss, kpis.profit_loss_egp);
  }
  if (totalReturn) {
    totalReturn.textContent = formatPercent(kpis.total_return_pct);
    applyValueClass(totalReturn, kpis.total_return_pct);
  }
  if (maxDrawdown) {
    maxDrawdown.textContent = formatEGP(kpis.maximum_drawdown_egp);
    applyValueClass(maxDrawdown, kpis.maximum_drawdown_egp);
  }
  if (maxDrawdownPct) {
    maxDrawdownPct.textContent = formatPercent(kpis.maximum_drawdown_pct);
    applyValueClass(maxDrawdownPct, kpis.maximum_drawdown_pct);
  }
  if (buyOperations) {
    buyOperations.textContent = kpis.buy_operations;
  }
  if (sellOperations) {
    sellOperations.textContent = kpis.sell_operations;
  }
  if (completedTrades) {
    completedTrades.textContent = kpis.completed_trades;
  }
  if (exposure) {
    exposure.textContent = formatPercent(kpis.exposure_pct);
  }
  if (finalPosition) {
    finalPosition.textContent = kpis.current_position || "—";
  }
  if (buyHoldReturn) {
    buyHoldReturn.textContent = formatPercent(kpis.buy_hold_return_pct);
    applyValueClass(buyHoldReturn, kpis.buy_hold_return_pct);
  }
  if (excessReturn) {
    excessReturn.textContent = formatPercent(kpis.excess_return_pct_points);
    applyValueClass(excessReturn, kpis.excess_return_pct_points);
  }
}

function destroyChart(chartInstance) {
  if (chartInstance) {
    chartInstance.destroy();
  }
}

function renderStrategyPriceChart(data) {
  destroyChart(strategyPriceChart);

  const symbolSelect = document.getElementById("symbolSelect");
  const fastWindowInput = document.getElementById("fastWindow");
  const slowWindowInput = document.getElementById("slowWindow");
  const symbol = symbolSelect ? symbolSelect.value : "";
  const fastWindow = fastWindowInput ? fastWindowInput.value : "9";
  const slowWindow = slowWindowInput ? slowWindowInput.value : "20";
  const viewData = getFilteredBacktestView() || data;

  const labels = Array.isArray(viewData.dates) ? viewData.dates : [];
  const close = Array.isArray(viewData.close) ? viewData.close : [];
  const fastMa = Array.isArray(viewData.fast_ma) ? viewData.fast_ma : [];
  const slowMa = Array.isArray(viewData.slow_ma) ? viewData.slow_ma : [];
  const buyMarkers = Array.isArray(viewData.buy_markers) ? viewData.buy_markers : [];
  const sellMarkers = Array.isArray(viewData.sell_markers) ? viewData.sell_markers : [];

  const canvas = document.getElementById("strategyPriceChart");
  strategyPriceChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Close",
          data: close,
          type: "line",
          borderColor: "#4f8cff",
          backgroundColor: "rgba(79, 140, 255, 0.2)",
          pointRadius: 0,
          borderWidth: 1.2,
          spanGaps: false,
        },
        {
          label: `MA${fastWindow}`,
          data: fastMa,
          type: "line",
          borderColor: "#f59e0b",
          pointRadius: 0,
          borderWidth: 1.5,
          spanGaps: true,
        },
        {
          label: `MA${slowWindow}`,
          data: slowMa,
          type: "line",
          borderColor: "#8b5cf6",
          pointRadius: 0,
          borderWidth: 1.5,
          spanGaps: true,
        },
        {
          label: "Buy",
          data: buyMarkers,
          type: "line",
          showLine: false,
          pointStyle: "triangle",
          pointRadius: 7,
          pointHoverRadius: 9,
          borderColor: "#22c55e",
          backgroundColor: "#22c55e",
          spanGaps: false,
        },
        {
          label: "Sell",
          data: sellMarkers,
          type: "line",
          showLine: false,
          pointStyle: "triangle",
          pointRotation: 180,
          pointRadius: 7,
          pointHoverRadius: 9,
          borderColor: "#ef4444",
          backgroundColor: "#ef4444",
          spanGaps: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      normalized: true,
      interaction: {
        mode: "nearest",
        axis: "x",
        intersect: false,
      },
      plugins: {
        legend: {
          display: true,
        },
        title: {
          display: true,
          text: `${symbol} — MA${fastWindow}/${slowWindow} crossover`,
        },
      },
      scales: {
        x: {
          ticks: {
            autoSkip: true,
            maxTicksLimit: 14,
            minRotation: 0,
            maxRotation: 45,
          },
        },
        y: {
          title: {
            display: true,
            text: "Price (EGP)",
          },
        },
      },
    },
  });

  applyChartDefaults(strategyPriceChart);
  setChartRangeState(strategyPriceChart, viewData);
  if (portfolioChart) {
    setChartRangeState(portfolioChart, viewData);
  }
}

function renderPortfolioChart(data) {
  destroyChart(portfolioChart);

  const viewData = getFilteredBacktestView() || data;
  const labels = Array.isArray(viewData.dates) ? viewData.dates : [];
  const initialCash = Number(viewData.parameters && viewData.parameters.initial_cash) || 0;
  const initialReference = Array(labels.length).fill(initialCash);

  const canvas = document.getElementById("portfolioChart");
  portfolioChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Strategy portfolio",
          data: Array.isArray(viewData.portfolio_values) ? viewData.portfolio_values : [],
          borderColor: "#4f8cff",
          backgroundColor: "rgba(79, 140, 255, 0.2)",
          tension: 0.2,
          pointRadius: 0,
        },
        {
          label: "Buy and hold",
          data: Array.isArray(viewData.buy_hold_values) ? viewData.buy_hold_values : [],
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.2)",
          tension: 0.2,
          pointRadius: 0,
        },
        {
          label: "Initial capital",
          data: initialReference,
          borderColor: "#94a3b8",
          borderDash: [6, 4],
          pointRadius: 0,
          tension: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      normalized: true,
      interaction: {
        mode: "nearest",
        axis: "x",
        intersect: false,
      },
      plugins: {
        legend: {
          display: true,
        },
        title: {
          display: true,
          text: "Portfolio performance",
        },
      },
      scales: {
        x: {
          ticks: {
            autoSkip: true,
            maxTicksLimit: 14,
            minRotation: 0,
            maxRotation: 45,
          },
        },
        y: {
          title: {
            display: true,
            text: "Portfolio value (EGP)",
          },
        },
      },
    },
  });

  applyChartDefaults(portfolioChart);
  setChartRangeState(portfolioChart, viewData);
  if (strategyPriceChart) {
    setChartRangeState(strategyPriceChart, viewData);
  }
}

function renderTradeTable(trades) {
  const tbody = document.getElementById("tradeTableBody");
  if (!tbody) {
    return;
  }

  tbody.replaceChildren();

  if (!trades || trades.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "empty-state";
    cell.textContent = "No buy or sell operations occurred for this period.";
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }

  trades.forEach((trade) => {
    const row = document.createElement("tr");
    const columns = [
      trade.type || "—",
      trade.date || "—",
      formatEGP(trade.price),
      trade.shares !== undefined ? trade.shares : "—",
      formatEGP(trade.cash_after),
      formatEGP(trade.portfolio_value_after),
    ];

    columns.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });

    tbody.appendChild(row);
  });
}

async function checkHealth() {
  try {
    const response = await fetch(`${API}/health`);
    const data = await response.json();
    setStatusMessage("backend: " + data.status);
    return true;
  } catch (error) {
    setStatusMessage("backend not reachable — start uvicorn");
    return false;
  }
}

async function loadUniverse() {
  try {
    const response = await fetch(`${API}/universe`);
    if (!response.ok) {
      throw new Error("Unable to load universe.");
    }

    const universe = await response.json();
    const select = document.getElementById("symbolSelect");

    if (!select) {
      return [];
    }

    while (select.firstChild) {
      select.removeChild(select.firstChild);
    }

    const currentValue = select.value;
    universe.forEach((symbol) => {
      const option = document.createElement("option");
      option.value = symbol;
      option.textContent = symbol;
      select.appendChild(option);
    });

    if (Array.isArray(universe) && universe.length > 0) {
      const defaultSymbol = universe[0];
      const hasCurrentValue = currentValue && universe.includes(currentValue);
      select.value = hasCurrentValue ? currentValue : defaultSymbol;
    }

    return universe;
  } catch (error) {
    console.error(error);
    setStrategyStatus("Unable to load universe.");
    return [];
  }
}

async function runBacktest() {
  const symbolSelect = document.getElementById("symbolSelect");
  const fastWindowInput = document.getElementById("fastWindow");
  const slowWindowInput = document.getElementById("slowWindow");
  const initialCashInput = document.getElementById("initialCash");
  const runButton = document.getElementById("runBacktestButton");

  if (!symbolSelect || !fastWindowInput || !slowWindowInput || !initialCashInput || !runButton) {
    return;
  }

  const symbol = symbolSelect.value;
  const fastWindow = Number.parseInt(fastWindowInput.value, 10);
  const slowWindow = Number.parseInt(slowWindowInput.value, 10);
  const initialCash = Number.parseFloat(initialCashInput.value);

  if (!symbol) {
    setStrategyStatus("Please select a symbol.");
    return;
  }
  if (!Number.isFinite(fastWindow) || fastWindow < 1) {
    setStrategyStatus("Fast window must be at least 1.");
    return;
  }
  if (!Number.isFinite(slowWindow) || slowWindow < 2) {
    setStrategyStatus("Slow window must be at least 2.");
    return;
  }
  if (fastWindow >= slowWindow) {
    setStrategyStatus("Fast window must be smaller than slow window.");
    return;
  }
  if (!Number.isFinite(initialCash) || initialCash <= 0) {
    setStrategyStatus("Initial cash must be greater than zero.");
    return;
  }

  runButton.disabled = true;
  setStrategyStatus("Running backtest...");

  try {
    const url = `${API}/backtest/${encodeURIComponent(symbol)}?fast_window=${fastWindow}&slow_window=${slowWindow}&initial_cash=${initialCash}`;
    const response = await fetch(url);
    let payload = null;

    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }

    if (!response.ok) {
      const detail = payload && payload.detail ? payload.detail : "Backtest request failed.";
      throw new Error(detail);
    }

    currentBacktestData = payload;
    updateVisibleDateRangeLabel();
    renderKpis(payload.kpis || {});
    renderStrategyPriceChart(payload);
    renderPortfolioChart(payload);
    renderTradeTable(payload.trades || []);
    setStrategyStatus("");
  } catch (error) {
    console.error(error);
    renderKpis({});
    destroyChart(strategyPriceChart);
    destroyChart(portfolioChart);
    renderTradeTable([]);
    setStrategyStatus(error.message || "Unable to load backtest data.");
  } finally {
    runButton.disabled = false;
  }
}

function attachEventListeners() {
  const runButton = document.getElementById("runBacktestButton");
  const symbolSelect = document.getElementById("symbolSelect");

  if (runButton) {
    runButton.addEventListener("click", runBacktest);
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

  await checkHealth();
  const universe = await loadUniverse();
  attachEventListeners();
  attachChartNavigationListeners();
  addChartCanvasEvents();

  if (Array.isArray(universe) && universe.length > 0) {
    const select = document.getElementById("symbolSelect");
    if (select) {
      select.value = universe[0];
    }
    await runBacktest();
  }
}

initializeDashboard();
