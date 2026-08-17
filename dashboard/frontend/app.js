// Dashboard frontend.
const API = "http://localhost:8000";
const statusEl = document.getElementById("status");
const chartMessageEl = document.getElementById("chartMessage");
const strategyStatusEl = document.getElementById("strategyStatus");
const runBacktestButtonEl = document.getElementById("runBacktestButton");
const priceSymbolSelectEl = document.getElementById("priceSymbolSelect");
const strategySymbolSelectEl = document.getElementById("strategySymbolSelect");
const priceSmaWindowEl = document.getElementById("priceSmaWindow");
const runPredictionButtonEl = document.getElementById("runPredictionButton");
const predictionStatusEl = document.getElementById("predictionStatus");
const predictionPortfolioCanvas = document.getElementById("predictionPortfolioChart");
const compareStatusEl = document.getElementById("compareStatus");
const compareMetricsEl = document.getElementById("compareMetrics");
const topNInput = document.getElementById("topNInput");
const epochsInput = document.getElementById("epochsInput");
const trainFracInput = document.getElementById("trainFracInput");
const compareSymbolSelect = document.getElementById("compareSymbol");
const seqLenInput = document.getElementById("seqLenInput");
const hiddenInput = document.getElementById("hiddenInput");
const runCompareButtonEl = document.getElementById("runCompareButton");

let priceChart = null;
let portfolioChart = null;
let predictionChart = null;

if (typeof Chart !== "undefined" && typeof window.ChartZoom !== "undefined") {
  Chart.register(window.ChartZoom);
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#f87171" : "#e6edf3";
}

function setChartMessage(message) {
  chartMessageEl.textContent = message;
}

function setStrategyStatus(message, isError = false) {
  strategyStatusEl.textContent = message;
  strategyStatusEl.style.color = isError ? "#f87171" : "#8fb4ff";
}

function setPredictionStatus(message, isError = false) {
  predictionStatusEl.textContent = message;
  predictionStatusEl.style.color = isError ? "#f87171" : "#8fb4ff";
}

function setCompareStatus(message, isError = false) {
  compareStatusEl.textContent = message;
  compareStatusEl.style.color = isError ? "#f87171" : "#8fb4ff";
}

function setupTabs() {
  const tabButtons = document.querySelectorAll(".tab-button");
  tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const tabId = button.dataset.tab;
      const activeButtons = document.querySelectorAll(".tab-button.active");
      const activeContents = document.querySelectorAll(".tab-content.active");

      activeButtons.forEach((activeButton) => activeButton.classList.remove("active"));
      activeContents.forEach((activeContent) => activeContent.classList.remove("active"));

      button.classList.add("active");
      const tabContent = document.getElementById(tabId);
      if (tabContent) {
        tabContent.classList.add("active");
      }
    });
  });
}

function populateSelect(selectEl, symbols) {
  if (!selectEl) {
    return;
  }

  selectEl.innerHTML = "";
  symbols.forEach((symbol) => {
    const option = document.createElement("option");
    option.value = symbol;
    option.textContent = symbol;
    selectEl.appendChild(option);
  });

  if (symbols.length > 0) {
    selectEl.value = symbols[0];
  }
}

function populateSymbolSelects(symbols) {
  populateSelect(priceSymbolSelectEl, symbols);
  populateSelect(strategySymbolSelectEl, symbols);
  populateSelect(compareSymbolSelect, symbols);
}

function setValueState(element, value) {
  if (!element) {
    return;
  }
  element.classList.remove("positive", "negative");
  if (value > 0) {
    element.classList.add("positive");
  } else if (value < 0) {
    element.classList.add("negative");
  }
}

async function checkHealth() {
  try {
    const payload = await fetchJson("/health");
    setStatus(`backend: ${payload.status}`);
  } catch (error) {
    console.error("Health check failed", error);
    setStatus("backend not reachable — start uvicorn", true);
  }
}

async function fetchJson(path) {
  try {
    const response = await fetch(`${API}${path}`);
    if (!response.ok) {
      let detail = `Request failed: ${response.status}`;
      try {
        const payload = await response.json();
        if (payload && payload.detail) {
          detail = payload.detail;
        }
      } catch (parseError) {
        // Ignore JSON parse errors and fall back to the status message.
      }
      throw new Error(detail);
    }

    const text = await response.text();
    if (!text) {
      return {};
    }

    try {
      return JSON.parse(text);
    } catch (parseError) {
      console.error(`Invalid JSON from ${path}`, parseError);
      throw new Error("The server returned invalid JSON.");
    }
  } catch (error) {
    console.error(`Fetch failed for ${path}`, error);
    throw error;
  }
}

function formatEGP(value) {
  return new Intl.NumberFormat("en-EG", {
    style: "currency",
    currency: "EGP",
    maximumFractionDigits: 2,
  }).format(Number(value) || 0);
}

function formatPercent(value) {
  return `${(Number(value) || 0).toFixed(2)}%`;
}

function renderKpis(kpis) {
  const finalValueEl = document.getElementById("kpiFinalValue");
  const profitLossEl = document.getElementById("kpiProfitLoss");
  const totalReturnEl = document.getElementById("kpiTotalReturn");
  const maxDrawdownEl = document.getElementById("kpiMaxDrawdown");
  const maxDrawdownPctEl = document.getElementById("kpiMaxDrawdownPct");
  const buyOpsEl = document.getElementById("kpiBuyOperations");
  const sellOpsEl = document.getElementById("kpiSellOperations");
  const completedTradesEl = document.getElementById("kpiCompletedTrades");
  const exposureEl = document.getElementById("kpiExposure");
  const finalPositionEl = document.getElementById("kpiFinalPosition");
  const buyHoldReturnEl = document.getElementById("kpiBuyHoldReturn");
  const excessReturnEl = document.getElementById("kpiExcessReturn");

  finalValueEl.textContent = formatEGP(kpis.final_portfolio_value);
  profitLossEl.textContent = formatEGP(kpis.profit_loss_egp);
  totalReturnEl.textContent = formatPercent(kpis.total_return_pct);
  maxDrawdownEl.textContent = formatEGP(kpis.maximum_drawdown_egp);
  maxDrawdownPctEl.textContent = formatPercent(kpis.maximum_drawdown_pct);
  buyOpsEl.textContent = kpis.buy_operations;
  sellOpsEl.textContent = kpis.sell_operations;
  completedTradesEl.textContent = kpis.completed_trades;
  exposureEl.textContent = formatPercent(kpis.exposure_pct);
  finalPositionEl.textContent = kpis.current_position;
  buyHoldReturnEl.textContent = formatPercent(kpis.buy_hold_return_pct);
  excessReturnEl.textContent = formatPercent(kpis.excess_return_pct_points);

  setValueState(profitLossEl, Number(kpis.profit_loss_egp) || 0);
  setValueState(totalReturnEl, Number(kpis.total_return_pct) || 0);
  setValueState(excessReturnEl, Number(kpis.excess_return_pct_points) || 0);
}

function renderPredictionChart(data) {
  if (!predictionPortfolioCanvas) {
    return;
  }

  if (predictionChart) {
    predictionChart.destroy();
  }

  const ctx = predictionPortfolioCanvas.getContext("2d");
  predictionChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: data.dates || [],
      datasets: [
        {
          label: "Prediction portfolio",
          data: data.portfolio || [],
          borderColor: "#22c55e",
          backgroundColor: "rgba(34, 197, 94, 0.15)",
          borderWidth: 1.8,
          pointRadius: 0,
          tension: 0.2,
        },
        {
          label: "Benchmark",
          data: data.benchmark || [],
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.15)",
          borderWidth: 1.8,
          pointRadius: 0,
          tension: 0.2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          labels: {
            color: "#f8fafc",
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#cbd5e1",
            maxTicksLimit: 10,
          },
          grid: {
            color: "rgba(255,255,255,0.06)",
          },
        },
        y: {
          ticks: {
            color: "#cbd5e1",
          },
          grid: {
            color: "rgba(255,255,255,0.06)",
          },
        },
      },
    },
  });
}

function renderComparisonMetrics(data) {
  if (!compareMetricsEl) {
    return;
  }

  compareMetricsEl.innerHTML = "";
  const metrics = [
    { label: "MLP train MSE", value: data.mlp.train.mse },
    { label: "MLP train RMSE", value: data.mlp.train.rmse },
    { label: "MLP train MAE", value: data.mlp.train.mae },
    { label: "MLP train R²", value: data.mlp.train.r2 },
    { label: "MLP test MSE", value: data.mlp.test.mse },
    { label: "MLP test RMSE", value: data.mlp.test.rmse },
    { label: "MLP test MAE", value: data.mlp.test.mae },
    { label: "MLP test R²", value: data.mlp.test.r2 },
    { label: "LSTM train MSE", value: data.lstm.train.mse },
    { label: "LSTM train RMSE", value: data.lstm.train.rmse },
    { label: "LSTM train MAE", value: data.lstm.train.mae },
    { label: "LSTM train R²", value: data.lstm.train.r2 },
    { label: "LSTM test MSE", value: data.lstm.test.mse },
    { label: "LSTM test RMSE", value: data.lstm.test.rmse },
    { label: "LSTM test MAE", value: data.lstm.test.mae },
    { label: "LSTM test R²", value: data.lstm.test.r2 },
  ];

  metrics.forEach((metric) => {
    const card = document.createElement("div");
    card.className = "metric-card";
    card.innerHTML = `<strong>${metric.label}</strong><span>${metric.value}</span>`;
    compareMetricsEl.appendChild(card);
  });
}

function renderPriceChart(data) {
  const canvas = document.getElementById("strategyPriceChart");
  if (!canvas) {
    return;
  }

  if (priceChart) {
    priceChart.destroy();
  }

  const ctx = canvas.getContext("2d");
  priceChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: data.dates || [],
      datasets: [
        {
          label: "Close",
          data: data.close || [],
          borderColor: "#60a5fa",
          backgroundColor: "rgba(96, 165, 250, 0.15)",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.2,
          spanGaps: false,
        },
        {
          label: `SMA ${data.window || 20}`,
          data: data.sma || [],
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.15)",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.2,
          spanGaps: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          labels: {
            color: "#f8fafc",
          },
        },
        tooltip: {
          enabled: true,
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#cbd5e1",
            maxTicksLimit: 10,
          },
          grid: {
            color: "rgba(255,255,255,0.06)",
          },
        },
        y: {
          title: {
            display: true,
            text: "Price (EGP)",
            color: "#e6edf3",
          },
          ticks: {
            color: "#cbd5e1",
          },
          grid: {
            color: "rgba(255,255,255,0.06)",
          },
        },
      },
    },
  });
}

function renderPortfolioChart(data) {
  const canvas = document.getElementById("portfolioChart");
  if (!canvas) {
    return;
  }

  if (portfolioChart) {
    portfolioChart.destroy();
  }

  const ctx = canvas.getContext("2d");
  const initialCash = Number(data.parameters && data.parameters.initial_cash) || 0;
  const initialCapital = Array(data.dates ? data.dates.length : 0).fill(initialCash);

  portfolioChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: data.dates || [],
      datasets: [
        {
          label: "Strategy portfolio",
          data: data.portfolio_values || [],
          borderColor: "#22c55e",
          backgroundColor: "rgba(34, 197, 94, 0.12)",
          borderWidth: 1.8,
          pointRadius: 0,
          tension: 0.2,
        },
        {
          label: "Buy and hold",
          data: data.buy_hold_values || [],
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.12)",
          borderWidth: 1.8,
          pointRadius: 0,
          tension: 0.2,
        },
        {
          label: "Initial capital",
          data: initialCapital,
          borderColor: "#f8fafc",
          backgroundColor: "rgba(248, 250, 252, 0.12)",
          borderWidth: 1.4,
          pointRadius: 0,
          tension: 0.2,
          borderDash: [5, 5],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          labels: {
            color: "#f8fafc",
          },
        },
        tooltip: {
          enabled: true,
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#cbd5e1",
            maxTicksLimit: 10,
          },
          grid: {
            color: "rgba(255,255,255,0.06)",
          },
        },
        y: {
          title: {
            display: true,
            text: "Portfolio value (EGP)",
            color: "#e6edf3",
          },
          ticks: {
            color: "#cbd5e1",
          },
          grid: {
            color: "rgba(255,255,255,0.06)",
          },
        },
      },
    },
  });
}

function renderTradeTable(trades) {
  const tableBody = document.getElementById("tradeTableBody");
  tableBody.innerHTML = "";

  if (!trades || trades.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "empty-state";
    cell.textContent = "No buy or sell operations occurred for this period.";
    row.appendChild(cell);
    tableBody.appendChild(row);
    return;
  }

  trades.forEach((trade) => {
    const row = document.createElement("tr");
    const columns = [
      trade.type,
      trade.date,
      formatEGP(trade.price),
      trade.shares,
      formatEGP(trade.cash_after),
      formatEGP(trade.portfolio_value_after),
    ];

    columns.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });

    tableBody.appendChild(row);
  });
}

async function loadPriceData(symbol, indicatorWindow = 20) {
  if (!symbol) {
    return;
  }

  setChartMessage("Loading price and indicator data...");
  try {
    const [priceData, indicatorData] = await Promise.all([
      fetchJson(`/prices/${encodeURIComponent(symbol)}`),
      fetchJson(`/indicators/${encodeURIComponent(symbol)}?window=${indicatorWindow}`),
    ]);

    if (!priceData || !Array.isArray(priceData.dates) || !Array.isArray(priceData.close)) {
      throw new Error("The prices endpoint did not return valid data.");
    }
    if (!indicatorData || !Array.isArray(indicatorData.dates) || !Array.isArray(indicatorData.sma)) {
      throw new Error("The indicators endpoint did not return valid data.");
    }

    renderPriceChart({
      dates: priceData.dates,
      close: priceData.close,
      sma: indicatorData.sma,
      window: indicatorWindow,
    });
    setChartMessage("");
  } catch (error) {
    console.error("Price load failed", error);
    setChartMessage(error.message || "Could not load price chart.");
  }
}

async function runBacktest() {
  if (!strategySymbolSelectEl) {
    return;
  }

  const symbol = strategySymbolSelectEl.value;
  const fastWindow = Number(document.getElementById("fastWindow").value);
  const slowWindow = Number(document.getElementById("slowWindow").value);
  const initialCash = Number(document.getElementById("initialCash").value);

  if (!symbol) {
    setStrategyStatus("Please select a symbol.", true);
    return;
  }
  if (!Number.isFinite(fastWindow) || fastWindow < 1) {
    setStrategyStatus("Fast window must be at least 1.", true);
    return;
  }
  if (!Number.isFinite(slowWindow) || slowWindow < 2) {
    setStrategyStatus("Slow window must be at least 2.", true);
    return;
  }
  if (fastWindow >= slowWindow) {
    setStrategyStatus("Fast window must be lower than the slow window.", true);
    return;
  }
  if (!Number.isFinite(initialCash) || initialCash <= 0) {
    setStrategyStatus("Initial cash must be greater than zero.", true);
    return;
  }

  runBacktestButtonEl.disabled = true;
  setStrategyStatus("Running backtest...");

  try {
    const data = await fetchJson(
      `/backtest/${encodeURIComponent(symbol)}?fast_window=${fastWindow}&slow_window=${slowWindow}&initial_cash=${initialCash}`
    );

    if (!data || !Array.isArray(data.dates)) {
      throw new Error("The backtest endpoint did not return valid data.");
    }

    renderKpis(data.kpis || {});
    renderPortfolioChart(data);
    renderTradeTable(data.trades || []);
    setStrategyStatus(`Backtest complete for ${symbol}.`);
  } catch (error) {
    console.error("Backtest failed", error);
    setStrategyStatus(error.message || "The backtest could not be completed.", true);
  } finally {
    runBacktestButtonEl.disabled = false;
  }
}

async function runPrediction() {
  const topN = Number(topNInput.value);
  const epochs = Number(epochsInput.value);
  const trainFrac = Number(trainFracInput.value);

  if (!Number.isFinite(topN) || topN < 1) {
    setPredictionStatus("Top N must be at least 1.", true);
    return;
  }
  if (!Number.isFinite(epochs) || epochs < 1) {
    setPredictionStatus("Epochs must be at least 1.", true);
    return;
  }
  if (!Number.isFinite(trainFrac) || trainFrac <= 0 || trainFrac >= 1) {
    setPredictionStatus("Train fraction must be between 0 and 1.", true);
    return;
  }

  runPredictionButtonEl.disabled = true;
  setPredictionStatus("Building prediction portfolio...");

  try {
    const data = await fetchJson(
      `/prediction_portfolio?top_n=${topN}&train_frac=${trainFrac}&epochs=${epochs}`
    );

    if (!data || !Array.isArray(data.dates)) {
      throw new Error("The prediction endpoint did not return valid data.");
    }

    renderPredictionChart(data);
    setPredictionStatus("Prediction portfolio generated.");
  } catch (error) {
    console.error("Prediction portfolio failed", error);
    setPredictionStatus(error.message || "Prediction portfolio generation failed.", true);
  } finally {
    runPredictionButtonEl.disabled = false;
  }
}

async function runModelCompare() {
  if (!compareSymbolSelect) {
    return;
  }

  const symbol = compareSymbolSelect.value;
  const seqLen = Number(seqLenInput.value);
  const hidden = Number(hiddenInput.value);

  if (!symbol) {
    setCompareStatus("Please select a symbol.", true);
    return;
  }
  if (!Number.isFinite(seqLen) || seqLen < 1) {
    setCompareStatus("Sequence length must be at least 1.", true);
    return;
  }
  if (!Number.isFinite(hidden) || hidden < 1) {
    setCompareStatus("Hidden size must be at least 1.", true);
    return;
  }

  runCompareButtonEl.disabled = true;
  setCompareStatus("Comparing models...");

  try {
    const data = await fetchJson(
      `/model_compare?symbol=${encodeURIComponent(symbol)}&seq_len=${seqLen}&hidden=${hidden}`
    );

    const success = data && (data.success === undefined ? true : data.success === true);
    if (!success) {
      const errorMessage = data?.error || `Model comparison failed${data?.stage ? ' at ' + data.stage : ''}`;
      throw new Error(errorMessage);
    }

    if (!data || !data.mlp || !data.lstm) {
      throw new Error("Model comparison returned invalid data.");
    }

    renderComparisonMetrics(data);
    setCompareStatus(`Model comparison complete for ${symbol}.`);
  } catch (error) {
    console.error("Model comparison failed", error);
    setCompareStatus(error.message || "Model comparison failed.", true);
  } finally {
    runCompareButtonEl.disabled = false;
  }
}

async function loadPricePanel() {
  if (!priceSymbolSelectEl) {
    return;
  }

  const symbol = priceSymbolSelectEl.value;
  const window = Number(priceSmaWindowEl.value) || 20;
  await loadPriceData(symbol, window);
}

async function loadUniverse() {
  try {
    const symbols = await fetchJson("/universe");
    if (!Array.isArray(symbols) || symbols.length === 0) {
      throw new Error("No symbols available.");
    }

    populateSymbolSelects(symbols);
    await loadPricePanel();
    await runBacktest();
  } catch (error) {
    console.error("Universe loading failed", error);
    setStrategyStatus(error.message || "Could not load the symbol universe.", true);
    setChartMessage(error.message || "No market data available.");
  }
}

async function initializeDashboard() {
  await checkHealth();
  setupTabs();
  await loadUniverse();
}

runBacktestButtonEl.addEventListener("click", () => {
  runBacktest();
});

runPredictionButtonEl.addEventListener("click", () => {
  runPrediction();
});

runCompareButtonEl.addEventListener("click", () => {
  runModelCompare();
});

priceSymbolSelectEl.addEventListener("change", async () => {
  await loadPricePanel();
});

priceSmaWindowEl.addEventListener("change", async () => {
  await loadPricePanel();
});

strategySymbolSelectEl.addEventListener("change", async () => {
  await runBacktest();
});

initializeDashboard();
