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


function displayLstmMetrics(data) {
  document.getElementById("final-value").textContent =
    formatEGP(data.final_portfolio_value_egp);
  const returnElement = document.getElementById("total-return");
  returnElement.textContent = formatPercent(data.total_return_percent);
  setReturnColor(returnElement, data.total_return_percent);
  document.getElementById("max-drawdown").textContent =
    `${formatEGP(data.max_drawdown_egp)} (${formatPercent(data.max_drawdown_percent)})`;
  document.getElementById("operations-label").textContent = "Portfolio rule";
  document.getElementById("operations").textContent = `Top ${data.top_k}`;
  document.getElementById("operations-note").textContent =
    `Rebalanced every ${data.rebalance_days} trading days`;
  setCard(
    "comparison",
    formatEGP(data.benchmark_final_value_egp),
    "Equal-weight benchmark",
    `Benchmark return: ${formatPercent(data.benchmark_return_percent)}`,
  );
  setCard(
    "cost",
    formatPercent(data.commission_percent),
    "Turnover commission",
    `Strategy Sharpe: ${data.sharpe.toFixed(3)}`,
  );
}


function renderLstmSummaryChart(data) {
  const canvas = document.getElementById("price-chart");
  priceChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: ["My optimized LSTM", "Equal-weight benchmark"],
      datasets: [{
        label: "Final portfolio value (EGP)",
        data: [data.final_portfolio_value_egp, data.benchmark_final_value_egp],
        backgroundColor: ["#60a5fa", "#f59e0b"],
        borderRadius: 8,
      }],
    },
    options: chartOptions("Final value (EGP)", false),
  });
}


function renderLstmEquityChart(data) {
  const canvas = document.getElementById("equity-chart");
  const equity = data.equity_curve;
  equityChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: equity.map((row) => row.date),
      datasets: [
        {
          label: "My optimized LSTM",
          data: equity.map((row) => row.portfolio_value),
          borderColor: "#60a5fa",
          backgroundColor: "rgba(96, 165, 250, 0.12)",
          fill: true,
          borderWidth: 2,
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


function renderLstmDrawdownChart(data) {
  const canvas = document.getElementById("drawdown-chart");
  const equity = data.equity_curve;
  drawdownChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: equity.map((row) => row.date),
      datasets: [{
        label: "LSTM drawdown",
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


function renderLstmParameters(data) {
  document.getElementById("table-head").innerHTML =
    "<tr><th>Parameter</th><th>Selected value</th><th>Meaning</th></tr>";
  const rows = [
    ["Stocks held", data.top_k, "Highest positive LSTM forecasts"],
    ["Rebalance interval", `${data.rebalance_days} days`, "Reduces turnover and noise"],
    ["Prediction threshold", formatPercent(data.threshold_percent), "Minimum forecast required"],
    ["Commission", formatPercent(data.commission_percent), "Charged on portfolio turnover"],
    ["Validation Sharpe", data.validation_sharpe.toFixed(3), "Used to select the parameters"],
  ];
  document.getElementById("trade-table").innerHTML = rows.map((row) =>
    `<tr><td>${row[0]}</td><td class="buy">${row[1]}</td><td>${row[2]}</td></tr>`
  ).join("");
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
    type: "line",
    data: {
      labels,
      datasets: [
        {
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
          pointRadius: 0,
        },
      ],
    },
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


async function loadLstm() {
  try {
    setStatus("Loading optimized LSTM…");
    strategySelect.disabled = true;
    destroyCharts();
    const response = await fetch(`${API_BASE}/portfolio/lstm`);
    if (!response.ok) throw new Error("Could not load optimized LSTM export.");
    const data = await response.json();
    displayLstmMetrics(data);
    renderLstmSummaryChart(data);
    renderLstmEquityChart(data);
    renderLstmDrawdownChart(data);
    renderLstmParameters(data);
    document.getElementById("primary-chart-title").textContent =
      "Optimized LSTM vs benchmark · final value";
    document.getElementById("equity-chart-title").textContent =
      "Optimized LSTM equity curve vs benchmark";
    document.getElementById("drawdown-chart-title").textContent =
      "Optimized LSTM drawdown";
    document.getElementById("table-title").textContent = "Selected hyperparameters";
    assetDescription.textContent =
      `34 assets · top ${data.top_k} · rebalance every ${data.rebalance_days} days · ` +
      `${formatPercent(data.commission_percent)} commission`;
    insightBanner.textContent =
      `${data.description} This chart covers ${data.start_date} through ${data.end_date}. ` +
      `The notebook's walk-forward tests remain the honest robustness verdict.`;
    setStatus("Optimized LSTM: ready", "ok");
  } catch (error) {
    console.error(error);
    setStatus("Optimized LSTM failed", "error");
  } finally {
    strategySelect.disabled = false;
  }
}


async function switchStrategy() {
  const mode = strategySelect.value;
  if (mode === "mean-reversion") {
    assetControl.style.display = "none";
    await loadMeanReversion();
  } else if (mode === "lstm") {
    assetControl.style.display = "none";
    await loadLstm();
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
