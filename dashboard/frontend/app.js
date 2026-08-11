// Dashboard frontend. Grows via dashboard/tasks/.
const API_CANDIDATES = ["http://127.0.0.1:8000", "http://localhost:8000"];
let equityChart;
let selectedSymbols = [];
let commissionValue = 0.0;
let apiBase = null;

async function checkHealth() {
  const statusEl = document.getElementById("status");
  for (const api of API_CANDIDATES) {
    try {
      const r = await fetch(`${api}/health`);
      if (!r.ok) continue;
      const j = await r.json();
      if (statusEl) {
        statusEl.textContent = "backend: " + j.status;
      }
      return api;
    } catch (e) {
      // Try the next local backend URL.
    }
  }

  if (statusEl) {
    statusEl.textContent = "backend not reachable — start uvicorn";
  }
  return null;
}

function getSelectedSymbols() {
  return Array.from(document.querySelectorAll(".symbol-chip.selected")).map((chip) => chip.dataset.symbol);
}

function renderSymbolList(symbols) {
  const list = document.getElementById("symbolList");
  if (!list) return;
  list.innerHTML = "";

  symbols.forEach((symbol) => {
    const chip = document.createElement("div");
    chip.className = "symbol-chip";
    chip.dataset.symbol = symbol;
    chip.textContent = symbol;
    chip.onclick = () => {
      chip.classList.toggle("selected");
      selectedSymbols = getSelectedSymbols();
    };
    list.appendChild(chip);
  });
}

function getCommission() {
  const input = document.getElementById("commissionInput");
  return parseFloat(input.value) || 0.0;
}

function updateStatsPanel(backtest) {
  const statsEl = document.getElementById("backtestStats");
  if (!statsEl) return;

  statsEl.innerHTML = `
    <div class="stat-box"><div class="label">Initial cash</div><div class="value">1000.00 EGP</div></div>
    <div class="stat-box"><div class="label">Symbols</div><div class="value">${backtest.symbols.join(", ")}</div></div>
    <div class="stat-box"><div class="label">Commission</div><div class="value">${commissionValue.toFixed(2)}%</div></div>
    <div class="stat-box"><div class="label">SMA final value</div><div class="value">${backtest.sma.final_value.toFixed(2)} EGP</div></div>
    <div class="stat-box"><div class="label">Drop/Rise final value</div><div class="value">${backtest.drop_rise.final_value.toFixed(2)} EGP</div></div>
  `;
}

async function renderEquityChart(backtest) {
  const canvas = document.getElementById("equityChart");
  if (!canvas) return;

  if (equityChart) {
    equityChart.destroy();
  }

  const ctx = canvas.getContext("2d");
  equityChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: backtest.dates,
      datasets: [
        {
          label: "Benchmark",
          data: backtest.benchmark,
          borderColor: "#94a3b8",
          backgroundColor: "rgba(148, 163, 184, 0.15)",
          fill: false,
          tension: 0.1,
        },
        {
          label: "SMA strategy",
          data: backtest.sma.equity_curve,
          borderColor: "#22c55e",
          backgroundColor: "rgba(34, 197, 94, 0.15)",
          fill: false,
          tension: 0.1,
        },
        {
          label: "Drop/Rise strategy",
          data: backtest.drop_rise.equity_curve,
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.15)",
          fill: false,
          tension: 0.1,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        y: { title: { display: true, text: "Equity" }, beginAtZero: false },
      },
    },
  });
}

async function renderMetrics(metrics) {
  const metricsEl = document.getElementById("metricsGrid");
  if (metricsEl) {
    metricsEl.innerHTML = `
      <div class="stat-box"><div class="label">SMA total return</div><div class="value">${(metrics.sma.total_return * 100).toFixed(2)}%</div></div>
      <div class="stat-box"><div class="label">SMA Sharpe</div><div class="value">${metrics.sma.sharpe.toFixed(2)}</div></div>
      <div class="stat-box"><div class="label">SMA max drawdown</div><div class="value">${(metrics.sma.max_drawdown * 100).toFixed(2)}%</div></div>
      <div class="stat-box"><div class="label">Drop/Rise total return</div><div class="value">${(metrics.drop_rise.total_return * 100).toFixed(2)}%</div></div>
      <div class="stat-box"><div class="label">Drop/Rise Sharpe</div><div class="value">${metrics.drop_rise.sharpe.toFixed(2)}</div></div>
      <div class="stat-box"><div class="label">Drop/Rise max drawdown</div><div class="value">${(metrics.drop_rise.max_drawdown * 100).toFixed(2)}%</div></div>
    `;
  }

  const summaryEl = document.getElementById("summaryCards");
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="metric-card"><div class="label">Symbols</div><div class="value">${selectedSymbols.join(", ")}</div></div>
      <div class="metric-card"><div class="label">SMA final</div><div class="value">${metrics.sma.final_value.toFixed(2)} EGP</div></div>
      <div class="metric-card"><div class="label">Drop/Rise final</div><div class="value">${metrics.drop_rise.final_value.toFixed(2)} EGP</div></div>
    `;
  }

  const performanceEl = document.getElementById("performanceGrid");
  if (performanceEl) {
    performanceEl.innerHTML = `
      <div class="stat-box"><div class="label">SMA return</div><div class="value">${(metrics.sma.total_return * 100).toFixed(2)}%</div></div>
      <div class="stat-box"><div class="label">Drop/Rise return</div><div class="value">${(metrics.drop_rise.total_return * 100).toFixed(2)}%</div></div>
      <div class="stat-box"><div class="label">SMA drawdown</div><div class="value">${(metrics.sma.max_drawdown * 100).toFixed(2)}%</div></div>
      <div class="stat-box"><div class="label">Drop/Rise drawdown</div><div class="value">${(metrics.drop_rise.max_drawdown * 100).toFixed(2)}%</div></div>
    `;
  }
}

async function renderDashboardForSymbols() {
  if (!apiBase) return;
  selectedSymbols = getSelectedSymbols();
  const statusEl = document.getElementById("status");
  if (!selectedSymbols.length) {
    if (statusEl) {
      statusEl.textContent = "Select at least one symbol.";
    }
    return;
  }

  commissionValue = getCommission();
  const commissionFraction = commissionValue / 100.0;
  const symbolParam = encodeURIComponent(selectedSymbols.join(","));
  const [backtestRes, metricsRes] = await Promise.all([
    fetch(`${apiBase}/backtest?symbols=${symbolParam}&fast=9&slow=20&initial_cash=1000&commission=${commissionFraction}`),
    fetch(`${apiBase}/metrics?symbols=${symbolParam}&fast=9&slow=20&initial_cash=1000&commission=${commissionFraction}`),
  ]);

  const backtest = await backtestRes.json();
  const metrics = await metricsRes.json();

  updateStatsPanel(backtest);
  await Promise.all([
    renderEquityChart(backtest),
    renderMetrics(metrics),
  ]);
}

async function loadDashboard() {
  apiBase = await checkHealth();
  if (!apiBase) return;

  const universeRes = await fetch(`${apiBase}/universe`);
  const universe = await universeRes.json();
  selectedSymbols = universe.symbols.slice(0, Math.min(4, universe.symbols.length));

  renderSymbolList(universe.symbols);
  selectedSymbols.forEach((symbol) => {
    const chip = document.querySelector(`.symbol-chip[data-symbol='${symbol}']`);
    if (chip) chip.classList.add("selected");
  });

  const updateButton = document.getElementById("updateButton");
  if (updateButton) {
    updateButton.onclick = renderDashboardForSymbols;
  }
  await renderDashboardForSymbols();
}

loadDashboard();