const API = "http://localhost:8000";
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

let baseCompChart, newCompChart, tiktokCompChart;

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
    `Universe: ${data.universe.join(", ")} — same date range and starting capital for all three strategies`;

  renderComparisonStats("baseStatsGrid", data.base);
  renderComparisonStats("newStatsGrid", data.new);
  renderComparisonStats("tiktokStatsGrid", data.tiktok);

  if (baseCompChart) baseCompChart.destroy();
  if (newCompChart) newCompChart.destroy();
  if (tiktokCompChart) tiktokCompChart.destroy();
  baseCompChart = renderComparisonChart("baseCompChart", data.base, "#38bdf8");
  newCompChart = renderComparisonChart("newCompChart", data.new, "#4ade80");
  tiktokCompChart = renderComparisonChart("tiktokCompChart", data.tiktok, "#fbbf24");
}

let compareChart, compareValueChart;

// Draws a value label centered above each bar. Relies on the chart's own
// y-scale headroom (see suggestedMax below) so the label never gets clipped
// by the top of the canvas even when a bar nearly reaches the axis max.
function drawBarValueLabels(chart, formatFn) {
  const { ctx } = chart;
  ctx.save();
  ctx.fillStyle = "#e6edf3";
  ctx.font = "600 13px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  chart.data.datasets.forEach((dataset, di) => {
    const meta = chart.getDatasetMeta(di);
    meta.data.forEach((bar, i) => {
      ctx.fillText(formatFn(dataset.data[i]), bar.x, bar.y - 8);
    });
  });
  ctx.restore();
}

const barChartBaseOptions = {
  responsive: true,
  layout: { padding: { top: 28 } },
  plugins: { legend: { display: false } },
  scales: {
    y: {
      beginAtZero: true,
      grid: { color: "#1b2740" },
      title: { color: "#8b98a9" },
      ticks: { color: "#8b98a9" }
    },
    x: {
      grid: { display: false },
      ticks: { color: "#c7d1e0", font: { weight: "600" } }
    }
  }
};

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

  const lossValues = [data.mlp_test_loss, data.lstm_test_loss];
  const lossMax = Math.max(...lossValues);

  const lossCtx = document.getElementById("compareChart").getContext("2d");
  if (compareChart) compareChart.destroy();
  compareChart = new Chart(lossCtx, {
    type: "bar",
    data: {
      labels: ["MLP", "LSTM"],
      datasets: [{
        label: "Test loss",
        data: lossValues,
        backgroundColor: ["#38bdf8", "#f87171"],
        borderRadius: 8,
        maxBarThickness: 140
      }]
    },
    options: {
      ...barChartBaseOptions,
      scales: {
        ...barChartBaseOptions.scales,
        y: {
          ...barChartBaseOptions.scales.y,
          // 25% headroom above the tallest bar so the value label always
          // has clear space above it, regardless of how close the two
          // values are to each other.
          suggestedMax: lossMax * 1.25,
          title: { display: true, text: "Test Loss (MSE)", color: "#8b98a9" }
        }
      }
    },
    plugins: [{ id: "lossLabels", afterDatasetsDraw: c => drawBarValueLabels(c, v => v.toFixed(6)) }]
  });

  const valueValues = [data.mlp_final_value, data.lstm_final_value, data.benchmark_final_value];
  const valueMax = Math.max(...valueValues);

  const valueCtx = document.getElementById("compareValueChart").getContext("2d");
  if (compareValueChart) compareValueChart.destroy();
  compareValueChart = new Chart(valueCtx, {
    type: "bar",
    data: {
      labels: ["MLP", "LSTM", "Benchmark"],
      datasets: [{
        label: "Final value (EGP)",
        data: valueValues,
        backgroundColor: ["#38bdf8", "#f87171", "#8b98a9"],
        borderRadius: 8,
        maxBarThickness: 140
      }]
    },
    options: {
      ...barChartBaseOptions,
      scales: {
        ...barChartBaseOptions.scales,
        y: {
          ...barChartBaseOptions.scales.y,
          suggestedMax: valueMax * 1.15,
          title: { display: true, text: "Final Portfolio Value (EGP)", color: "#8b98a9" }
        }
      }
    },
    plugins: [{ id: "valueLabels", afterDatasetsDraw: c => drawBarValueLabels(c, v => v.toFixed(0) + " EGP") }]
  });

  const lossGapPct = (Math.abs(data.mlp_test_loss - data.lstm_test_loss) / data.mlp_test_loss * 100).toFixed(1);
  const valueGapPct = (Math.abs(data.mlp_final_value - data.lstm_final_value) / data.mlp_final_value * 100).toFixed(0);
  document.getElementById("compareNote").textContent =
    `Test loss differs by only ${lossGapPct}% — yet the backtested outcome differs by ${valueGapPct}%. Raw prediction accuracy barely tells you which model will actually make money.`;
}

let leaderboardChart;

async function loadLeaderboard() {
  let data;
  try {
    const r = await fetch(`${API}/leaderboard`);
    if (!r.ok) throw new Error("not found");
    data = await r.json();
  } catch (e) {
    console.warn("leaderboard.json not available yet — run the Day 5 notebook first");
    return;
  }

  const ctx = document.getElementById("leaderboardChart").getContext("2d");
  if (leaderboardChart) leaderboardChart.destroy();
  leaderboardChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: data.dates,
      datasets: [
        { label: "SMA crossover", data: data.sma, borderColor: "#38bdf8", pointRadius: 0, tension: 0.1 },
        { label: "MPT (walk-forward)", data: data.mpt, borderColor: "#fbbf24", pointRadius: 0, tension: 0.1 },
        { label: "Benchmark", data: data.benchmark, borderColor: "#8b98a9", borderDash: [5, 5], pointRadius: 0, tension: 0.1 }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { maxTicksLimit: 8 } },
        y: { ticks: { callback: v => v.toLocaleString() + " EGP" } }
      }
    }
  });

  const tbody = document.querySelector("#riskTable tbody");
  const rows = [
    ["SMA crossover", data.risk.sma],
    ["MPT (walk-forward)", data.risk.mpt],
    ["Benchmark", data.risk.benchmark],
  ];
  tbody.innerHTML = rows.map(([name, r]) => `
    <tr>
      <td>${name}</td>
      <td class="${r.total_return_pct >= 0 ? 'buy' : 'sell'}">${r.total_return_pct.toFixed(2)}%</td>
      <td>${r.volatility_pct.toFixed(2)}%</td>
      <td class="sell">${r.max_drawdown_pct.toFixed(2)}%</td>
      <td>${r.final_value.toFixed(2)} EGP</td>
    </tr>
  `).join("");
}

// --- Day 4: news & sentiment ---

async function loadNewsSymbolSelect() {
  const select = document.getElementById("newsSymbolSelect");
  const universe = await fetch(`${API}/universe`).then(r => r.json());
  select.innerHTML = universe.map(s => `<option value="${s}">${s}</option>`).join("");
}

async function loadNews() {
  const symbol = document.getElementById("newsSymbolSelect").value;
  const summaryEl = document.getElementById("newsSummary");
  const listEl = document.getElementById("newsHeadlines");
  summaryEl.textContent = "Loading…";
  listEl.innerHTML = "";
  try {
    const data = await fetch(`${API}/news/${symbol}`).then(r => r.json());
    summaryEl.textContent = data.summary;
    listEl.innerHTML = data.headlines.map(h => `<li>${h}</li>`).join("");
  } catch (e) {
    summaryEl.textContent = "Couldn't load news right now.";
  }
}

// --- Day 4: chat agent ---

function appendChatMessage(role, text) {
  const log = document.getElementById("chatLog");
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

async function sendChatMessage() {
  const input = document.getElementById("chatInput");
  const message = input.value.trim();
  if (!message) return;
  appendChatMessage("user", message);
  input.value = "";

  const loadingDiv = appendChatMessage("assistant", "…");

  try {
    const res = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, symbol: currentSymbol })
    });
    const data = await res.json();
    loadingDiv.textContent = data.reply || "No response.";
  } catch (e) {
    loadingDiv.textContent = "Sorry, something went wrong.";
  }
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
  await loadLeaderboard();

  await loadNewsSymbolSelect();
  document.getElementById("newsBtn").addEventListener("click", loadNews);

  document.getElementById("chatSendBtn").addEventListener("click", sendChatMessage);
  document.getElementById("chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendChatMessage();
  });
})();