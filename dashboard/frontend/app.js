// Dashboard frontend.
const API = "http://localhost:8000";
const statusEl = document.getElementById("status");
const chartMessageEl = document.getElementById("chartMessage");
const strategyStatusEl = document.getElementById("strategyStatus");
const runBacktestButtonEl = document.getElementById("runBacktestButton");
const symbolSelectEl = document.getElementById("symbolSelect");

let strategyPriceChart = null;
let portfolioChart = null;

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

function populateSymbolSelect(symbols) {
  if (!symbolSelectEl) {
    return;
  }

  symbolSelectEl.innerHTML = "";
  symbols.forEach((symbol) => {
    const option = document.createElement("option");
    option.value = symbol;
    option.textContent = symbol;
    symbolSelectEl.appendChild(option);
  });

  if (symbols.length > 0) {
    symbolSelectEl.value = symbols[0];
  }
}

function renderStrategyPriceChart(data) {
  const canvas = document.getElementById("strategyPriceChart");
  if (!canvas) {
    return;
  }

  if (strategyPriceChart) {
    strategyPriceChart.destroy();
  }

  const ctx = canvas.getContext("2d");
  const fastWindow = data.parameters && data.parameters.fast_window ? data.parameters.fast_window : 9;
  const slowWindow = data.parameters && data.parameters.slow_window ? data.parameters.slow_window : 20;

  strategyPriceChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: data.dates || [],
      datasets: [
        {
          label: "Close",
          data: data.close || [],
          borderColor: "#60a5fa",
          backgroundColor: "rgba(96, 165, 250, 0.15)",
          borderWidth: 1.2,
          pointRadius: 0,
          tension: 0.2,
          spanGaps: false,
        },
        {
          label: `MA${fastWindow}`,
          data: data.fast_ma || [],
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.15)",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.2,
          spanGaps: true,
        },
        {
          label: `MA${slowWindow}`,
          data: data.slow_ma || [],
          borderColor: "#8b5cf6",
          backgroundColor: "rgba(139, 92, 246, 0.15)",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.2,
          spanGaps: true,
        },
        {
          label: "Buy",
          data: data.buy_markers || [],
          type: "line",
          showLine: false,
          pointStyle: "triangle",
          pointRadius: 7,
          pointHoverRadius: 9,
          pointBackgroundColor: "#22c55e",
          pointBorderColor: "#22c55e",
          spanGaps: false,
        },
        {
          label: "Sell",
          data: data.sell_markers || [],
          type: "line",
          showLine: false,
          pointStyle: "triangle",
          pointRotation: 180,
          pointRadius: 7,
          pointHoverRadius: 9,
          pointBackgroundColor: "#ef4444",
          pointBorderColor: "#ef4444",
          spanGaps: false,
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

async function runBacktest() {
  if (!symbolSelectEl) {
    return;
  }

  const symbol = symbolSelectEl.value;
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
  setChartMessage("Loading market data...");

  try {
    const data = await fetchJson(
      `/backtest/${encodeURIComponent(symbol)}?fast_window=${fastWindow}&slow_window=${slowWindow}&initial_cash=${initialCash}`
    );

    if (!data || !Array.isArray(data.dates)) {
      throw new Error("The backtest endpoint did not return valid data.");
    }

    renderKpis(data.kpis || {});
    renderStrategyPriceChart(data);
    renderPortfolioChart(data);
    renderTradeTable(data.trades || []);
    setChartMessage("");
    setStrategyStatus(`Backtest complete for ${symbol}.`);
  } catch (error) {
    console.error("Backtest failed", error);
    setStrategyStatus(error.message || "The backtest could not be completed.", true);
    setChartMessage(error.message || "No market data available.");
  } finally {
    runBacktestButtonEl.disabled = false;
  }
}

async function loadUniverse() {
  try {
    const symbols = await fetchJson("/universe");
    if (!Array.isArray(symbols) || symbols.length === 0) {
      throw new Error("No symbols available.");
    }

    populateSymbolSelect(symbols);
    await runBacktest();
  } catch (error) {
    console.error("Universe loading failed", error);
    setStrategyStatus(error.message || "Could not load the symbol universe.", true);
    setChartMessage(error.message || "No market data available.");
  }
}

async function initializeDashboard() {
  await checkHealth();
  await loadUniverse();
}

runBacktestButtonEl.addEventListener("click", () => {
  runBacktest();
});

symbolSelectEl.addEventListener("change", () => {
  runBacktest();
});

initializeDashboard();
