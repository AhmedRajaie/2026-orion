// Dashboard frontend. Grows via dashboard/tasks/.
const API_CANDIDATES = ["http://127.0.0.1:8000", "http://localhost:8000"];
let combinedChart;
let currentSymbol = null;

async function checkHealth() {
  for (const api of API_CANDIDATES) {
    try {
      const r = await fetch(`${api}/health`);
      if (!r.ok) continue;
      const j = await r.json();
      document.getElementById("status").textContent = "backend: " + j.status;
      return api;
    } catch (e) {
      // Try the next local backend URL.
    }
  }

  document.getElementById("status").textContent = "backend not reachable — start uvicorn";
  return null;
}

async function renderCombinedChart(api, symbol) {
  const [pricesRes, indicatorsRes, btRes] = await Promise.all([
    fetch(`${api}/prices/${symbol}`),
    fetch(`${api}/indicators/${symbol}?window=20`),
    fetch(`${api}/backtest/${symbol}?fast=9&slow=20&initial_cash=1000`),
  ]);
  const prices = await pricesRes.json();
  const indicators = await indicatorsRes.json();
  const bt = await btRes.json();

  const statsEl = document.getElementById("backtestStats");
  if (statsEl) {
    statsEl.innerHTML = `
      <div class="stat-box"><div class="label">Initial Cash</div><div class="value">${bt.initial_cash.toFixed(2)} EGP</div></div>
      <div class="stat-box"><div class="label">Final Value</div><div class="value">${bt.final_value.toFixed(2)} EGP</div></div>
      <div class="stat-box"><div class="label">Max Drawdown</div><div class="value">${(bt.max_drawdown_pct * 100).toFixed(2)}%</div></div>
      <div class="stat-box"><div class="label">Trades</div><div class="value">${bt.num_buys + bt.num_sells}</div></div>
      <div class="stat-box"><div class="label">Buys</div><div class="value">${bt.num_buys}</div></div>
    `;
  }

  const buyPoints = {};
  const sellPoints = {};
  bt.trades.forEach((t) => {
    const i = bt.dates.indexOf(t.date);
    if (i === -1) return;
    if (t.side === "buy") buyPoints[i] = bt.equity_curve[i];
    else sellPoints[i] = bt.equity_curve[i];
  });

  if (combinedChart) {
    combinedChart.destroy();
  }

  const ctx = document.getElementById("dashboardChart").getContext("2d");
  combinedChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: prices.dates,
      datasets: [
        {
          label: `${symbol} close`,
          data: prices.close,
          borderColor: "#4f8cff",
          backgroundColor: "rgba(79, 140, 255, 0.2)",
          yAxisID: "price",
          fill: false,
          tension: 0.1,
        },
        {
          label: `${symbol} SMA(20)`,
          data: indicators.sma,
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.2)",
          yAxisID: "price",
          fill: false,
          tension: 0.1,
        },
        {
          label: "Portfolio value",
          data: bt.equity_curve,
          borderColor: "#22c55e",
          backgroundColor: "rgba(34, 197, 94, 0.15)",
          yAxisID: "equity",
          fill: true,
          tension: 0.1,
          pointRadius: 0,
        },
        {
          label: "Buy",
          data: bt.dates.map((_, i) => (i in buyPoints ? buyPoints[i] : null)),
          borderColor: "#4f8cff",
          backgroundColor: "#4f8cff",
          yAxisID: "equity",
          showLine: false,
          pointStyle: "triangle",
          pointRadius: 8,
        },
        {
          label: "Sell",
          data: bt.dates.map((_, i) => (i in sellPoints ? sellPoints[i] : null)),
          borderColor: "#ef4444",
          backgroundColor: "#ef4444",
          yAxisID: "equity",
          showLine: false,
          pointStyle: "rectRot",
          pointRadius: 8,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        tooltip: {
          mode: "index",
          intersect: false,
        },
      },
      scales: {
        price: {
          type: "linear",
          position: "left",
          title: { display: true, text: "Price" },
          beginAtZero: false,
        },
        equity: {
          type: "linear",
          position: "right",
          title: { display: true, text: "Portfolio value" },
          beginAtZero: false,
          grid: { drawOnChartArea: false },
        },
      },
    },
  });
}

async function renderMetrics(api, symbol) {
  const res = await fetch(`${api}/metrics/${symbol}?fast=9&slow=20&initial_cash=1000`);
  const metrics = await res.json();

  const metricsEl = document.getElementById("metricsGrid");
  if (metricsEl) {
    metricsEl.innerHTML = `
      <div class="stat-box"><div class="label">Total return</div><div class="value">${(metrics.total_return * 100).toFixed(2)}%</div></div>
      <div class="stat-box"><div class="label">Sharpe ratio</div><div class="value">${metrics.sharpe.toFixed(2)}</div></div>
      <div class="stat-box"><div class="label">Max drawdown</div><div class="value">${(metrics.max_drawdown * 100).toFixed(2)}%</div></div>
      <div class="stat-box"><div class="label">Final value</div><div class="value">${metrics.final_value.toFixed(2)} EGP</div></div>
      <div class="stat-box"><div class="label">Strategy</div><div class="value">MA9/MA20</div></div>
    `;
  }

  const summaryEl = document.getElementById("summaryCards");
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="metric-card"><div class="label">Symbol</div><div class="value">${symbol}</div></div>
      <div class="metric-card"><div class="label">Final equity</div><div class="value">${metrics.final_value.toFixed(2)} EGP</div></div>
      <div class="metric-card"><div class="label">Strategy return</div><div class="value">${(metrics.total_return * 100).toFixed(2)}%</div></div>
    `;
  }
}

async function renderDashboardForSymbol(api, symbol) {
  await Promise.all([
    renderCombinedChart(api, symbol),
    renderMetrics(api, symbol),
  ]);
}

async function loadDashboard() {
  const api = await checkHealth();
  if (!api) return;

  const universeRes = await fetch(`${api}/universe`);
  const universe = await universeRes.json();
  const select = document.getElementById("symbolSelect");
  select.innerHTML = "";

  universe.symbols.forEach((symbol) => {
    const option = document.createElement("option");
    option.value = symbol;
    option.textContent = symbol;
    select.appendChild(option);
  });

  currentSymbol = universe.symbols[0];
  select.value = currentSymbol;
  select.onchange = () => {
    currentSymbol = select.value;
    renderDashboardForSymbol(api, currentSymbol);
  };

  await renderDashboardForSymbol(api, currentSymbol);
}

loadDashboard();