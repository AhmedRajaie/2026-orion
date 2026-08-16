const API = "http://localhost:8001";  // update to 8000 once that port's old process clears
let priceChart, equityChart;

async function checkHealth() {
  const statusEl = document.getElementById("status");
  try {
    const r = await fetch(`${API}/health`);
    const j = await r.json();
    statusEl.textContent = "backend: " + j.status;
    statusEl.className = "panel ok";
  } catch (e) {
    statusEl.textContent = "backend not reachable — start uvicorn";
    statusEl.className = "panel bad";
  }
}

async function loadUniverse() {
  const universe = await fetch(`${API}/universe`).then(r => r.json());
  const select = document.getElementById("symbolSelect");
  select.innerHTML = universe.map(s => `<option value="${s}">${s}</option>`).join("");
  select.addEventListener("change", () => {
    const { fast, slow } = getParams();
    loadBacktest(select.value, fast, slow);
  });
  return universe[0];
}

function renderStats(data) {
  const grid = document.getElementById("statsGrid");
  const returnClass = data.total_return_pct >= 0 ? "positive" : "negative";
  grid.innerHTML = `
    <div class="stat-card"><div class="label">Final Value</div><div class="value">${data.final_value.toFixed(2)} EGP</div></div>
    <div class="stat-card"><div class="label">Total Return</div><div class="value ${returnClass}">${data.total_return_pct.toFixed(2)}%</div></div>
    <div class="stat-card"><div class="label">Max Drawdown</div><div class="value negative">${data.max_drawdown_pct.toFixed(2)}%</div></div>
    <div class="stat-card"><div class="label">Buy / Sell Ops</div><div class="value">${data.buy_count} / ${data.sell_count}</div></div>
  `;
}

function renderTradeLog(data) {
  const tbody = document.querySelector("#tradeLog tbody");
  const rows = [];
  data.buy_signals.forEach(s => rows.push({ type: "BUY", date: s.date, price: s.price }));
  data.sell_signals.forEach(s => rows.push({ type: "SELL", date: s.date, price: s.price }));
  rows.sort((a, b) => a.date.localeCompare(b.date));
  tbody.innerHTML = rows.map(r =>
    `<tr><td class="${r.type === 'BUY' ? 'buy' : 'sell'}">${r.type}</td><td>${r.date}</td><td>${r.price.toFixed(2)}</td></tr>`
  ).join("");
}

function renderPriceChart(data) {
  const ctx = document.getElementById("priceChart").getContext("2d");
  const buyPoints = data.buy_signals.map(s => ({ x: s.date, y: s.price }));
  const sellPoints = data.sell_signals.map(s => ({ x: s.date, y: s.price }));

  if (priceChart) priceChart.destroy();
  priceChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: data.dates,
      datasets: [
        { label: "Close", data: data.close, borderColor: "#38bdf8", pointRadius: 0, tension: 0.1 },
        { label: "MA9", data: data.ma9, borderColor: "#fbbf24", pointRadius: 0, tension: 0.1 },
        { label: "MA20", data: data.ma20, borderColor: "#a78bfa", pointRadius: 0, tension: 0.1 },
        {
          label: "Buy", data: buyPoints, type: "scatter",
          backgroundColor: "#4ade80", pointStyle: "triangle", radius: 6
        },
        {
          label: "Sell", data: sellPoints, type: "scatter",
          backgroundColor: "#f87171", pointStyle: "triangle", rotation: 180, radius: 6
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: { x: { ticks: { maxTicksLimit: 10 } } }
    }
  });
}

function renderEquityChart(data) {
  const ctx = document.getElementById("equityChart").getContext("2d");
  if (equityChart) equityChart.destroy();
  equityChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: data.dates,
      datasets: [{
        label: "Portfolio (EGP)", data: data.portfolio,
        borderColor: "#a78bfa", backgroundColor: "rgba(167,139,250,0.1)",
        fill: true, pointRadius: 0, tension: 0.1
      }]
    },
    options: {
      responsive: true,
      scales: { x: { ticks: { maxTicksLimit: 10 } } }
    }
  });
}

let currentSymbol = null;

async function loadBacktest(symbol, fast, slow) {
  currentSymbol = symbol;
  const url = `${API}/backtest/${symbol}?fast=${fast}&slow=${slow}`;
  const data = await fetch(url).then(r => r.json());
  renderStats(data);
  renderPriceChart(data);
  renderEquityChart(data);
  renderTradeLog(data);
}

function getParams() {
  const fast = parseInt(document.getElementById("fastInput").value, 10);
  const slow = parseInt(document.getElementById("slowInput").value, 10);
  return { fast, slow };
}

let baseCompChart, newCompChart;

function renderComparisonStats(containerId, data) {
  const grid = document.getElementById(containerId);
  const returnClass = data.total_return_pct >= 0 ? "positive" : "negative";
  grid.innerHTML = `
    <div class="stat-card"><div class="label">Final Value</div><div class="value">${data.final_value.toFixed(2)} EGP</div></div>
    <div class="stat-card"><div class="label">Total Return</div><div class="value ${returnClass}">${data.total_return_pct.toFixed(2)}%</div></div>
    <div class="stat-card"><div class="label">Max Drawdown</div><div class="value negative">${data.max_drawdown_pct.toFixed(2)}%</div></div>
  `;
}

function renderComparisonChart(canvasId, data, color) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  return new Chart(ctx, {
    type: "line",
    data: {
      labels: data.dates,
      datasets: [{
        label: "Portfolio (EGP)", data: data.equity,
        borderColor: color, backgroundColor: color + "1a",
        fill: true, pointRadius: 0, tension: 0.1
      }]
    },
    options: {
      responsive: true,
      scales: { x: { ticks: { maxTicksLimit: 8 } } }
    }
  });
}

async function loadStrategyComparison() {
  const data = await fetch(`${API}/strategy-comparison`).then(r => r.json());

  document.getElementById("comparisonSubtitle").textContent =
    `Universe: ${data.universe.join(", ")} — same date range and starting capital for both strategies`;

  renderComparisonStats("baseStatsGrid", data.base);
  renderComparisonStats("newStatsGrid", data.new);

  if (baseCompChart) baseCompChart.destroy();
  if (newCompChart) newCompChart.destroy();
  baseCompChart = renderComparisonChart("baseCompChart", data.base, "#38bdf8");
  newCompChart = renderComparisonChart("newCompChart", data.new, "#4ade80");
}

let compareChart;

async function loadModelCompare() {
  let data;
  try {
    const r = await fetch(`${API}/compare`);
    if (!r.ok) throw new Error("not found");
    data = await r.json();
  } catch (e) {
    console.warn("model_compare.json not available yet — run the Day 3 notebook first");
    return;
  }

  const ctx = document.getElementById("compareChart").getContext("2d");
  if (compareChart) compareChart.destroy();
  compareChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: ["MLP", "LSTM"],
      datasets: [{
        label: "Test loss",
        data: [data.mlp_test_loss, data.lstm_test_loss],
        backgroundColor: ["#38bdf8", "#f87171"]
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true } }
    }
  });
}

(async function init() {
  await checkHealth();
  const firstSymbol = await loadUniverse();

  document.getElementById("applyBtn").addEventListener("click", () => {
    const { fast, slow } = getParams();
    loadBacktest(currentSymbol, fast, slow);
  });

  const { fast, slow } = getParams();
  await loadBacktest(firstSymbol, fast, slow);
  await loadStrategyComparison();
  await loadModelCompare();
})();