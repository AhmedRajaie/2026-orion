// Dashboard frontend. Grows via dashboard/tasks/.
const API = "http://localhost:8000";

let priceChart;

async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const j = await r.json();
    document.getElementById("status").textContent = "backend: " + j.status;
  } catch (e) {
    document.getElementById("status").textContent =
      "backend not reachable — start uvicorn";
  }
}

async function loadUniverse() {
  const symbolSelect = document.getElementById("symbolSelect");

  const universe = await fetch(`${API}/universe`).then((r) => r.json());

  symbolSelect.innerHTML = universe
    .map((symbol) => `<option value="${symbol}">${symbol}</option>`)
    .join("");

  symbolSelect.onchange = () => renderChart(symbolSelect.value);

  return universe[0];
}

// ============================
// KPI UPDATE
// ============================

function updateKpis(closes, sma9Series, sma20Series) {
  const latestClose = closes.at(-1);
  const previousClose = closes.at(-2);

  const dailyChange =
    ((latestClose - previousClose) / previousClose) * 100;

  const totalReturn =
    ((latestClose - closes[0]) / closes[0]) * 100;

  let runningMax = closes[0];
  let maxDrawdown = 0;

  for (const close of closes) {
    runningMax = Math.max(runningMax, close);

    const drawdown =
      ((close - runningMax) / runningMax) * 100;

    maxDrawdown = Math.min(maxDrawdown, drawdown);
  }

  const latestSma9 = sma9Series.filter(v => v !== null).at(-1);
  const latestSma20 = sma20Series.filter(v => v !== null).at(-1);

  // ============================
  // Trend
  // ============================

  const trend =
    latestSma9 > latestSma20 ? "Bullish 📈" : "Bearish 📉";

  // ============================
  // BUY / SELL SIGNAL
  // ============================

  let signal = "Hold";

  const prev9 = sma9Series.at(-2);
  const prev20 = sma20Series.at(-2);

  if (
    prev9 != null &&
    prev20 != null &&
    latestSma9 != null &&
    latestSma20 != null
  ) {
    if (prev9 <= prev20 && latestSma9 > latestSma20) {
      signal = "BUY 🟢";
    } else if (prev9 >= prev20 && latestSma9 < latestSma20) {
      signal = "SELL 🔴";
    }
  }

  document.getElementById("kpiLatest").textContent =
    latestClose.toFixed(2);

  document.getElementById("kpiDaily").textContent =
    `${dailyChange.toFixed(2)}%`;

  document.getElementById("kpiReturn").textContent =
    `${totalReturn.toFixed(2)}%`;

  document.getElementById("kpiDrawdown").textContent =
    `${maxDrawdown.toFixed(2)}%`;

  document.getElementById("kpiSma9").textContent =
    latestSma9?.toFixed(2) ?? "n/a";

  document.getElementById("kpiSma20").textContent =
    latestSma20?.toFixed(2) ?? "n/a";

  document.getElementById("kpiTrend").textContent = trend;

  document.getElementById("kpiSignal").textContent = signal;
}

// ============================
// CHART
// ============================

async function renderChart(symbol) {

  const priceJson = await fetch(`${API}/prices/${symbol}`).then(r => r.json());

  const indicatorJson = await fetch(
    `${API}/indicators/${symbol}`
  ).then(r => r.json());

  updateKpis(
    priceJson.close,
    indicatorJson.sma9,
    indicatorJson.sma20
  );

  const data = {

    labels: priceJson.dates,

    datasets: [

      {
        label: `${symbol} Close`,
        data: priceJson.close,
        borderColor: "#60a5fa",
        tension: 0,
        fill: false
      },

      {
        label: "SMA (9)",
        data: indicatorJson.sma9,
        borderColor: "#22c55e",
        pointRadius: 0,
        tension: 0,
        fill: false
      },

      {
        label: "SMA (20)",
        data: indicatorJson.sma20,
        borderColor: "#f59e0b",
        pointRadius: 0,
        tension: 0,
        fill: false
      }

    ]
  };

  if (priceChart) {
    priceChart.destroy();
  }

  priceChart = new Chart(
    document.getElementById("priceChart"),
    {
      type: "line",
      data,
      options: {
        responsive: true,

        plugins: {
          legend: {
            labels: {
              color: "#e6edf3"
            }
          }
        },

        scales: {

          x: {
            ticks: {
              color: "#cbd5e1"
            },
            grid: {
              color: "rgba(255,255,255,0.08)"
            }
          },

          y: {
            ticks: {
              color: "#cbd5e1"
            },
            grid: {
              color: "rgba(255,255,255,0.08)"
            }
          }

        }
      }
    }
  );
}

async function init() {
  await checkHealth();

  const defaultSymbol = await loadUniverse();

  await renderChart(defaultSymbol);
}

init();