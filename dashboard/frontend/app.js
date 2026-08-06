const API_BASE = "http://127.0.0.1:8000";
let priceChartInstance = null;
let portfolioChartInstance = null;
let drawdownChartInstance = null;

async function initDashboard() {
  setStatus("Loading stock list...");

  try {
    const symbols = await fetchStocks();
    populateStockSelector(symbols);

    const initialSymbol = symbols[0] || "ADIB";
    await loadSymbol(initialSymbol);
  } catch (error) {
    console.error(error);
    setStatus("Error ❌");
  }
}

async function fetchStocks() {
  const response = await fetch(`${API_BASE}/stocks`);
  if (!response.ok) {
    throw new Error(`Stocks request failed: ${response.status}`);
  }

  const data = await response.json();
  return data.symbols || [];
}

function populateStockSelector(symbols) {
  const selector = document.getElementById("stockSelector");
  selector.innerHTML = "";

  symbols.forEach((symbol) => {
    const option = document.createElement("option");
    option.value = symbol;
    option.textContent = symbol;
    selector.appendChild(option);
  });

  selector.addEventListener("change", async (event) => {
    await loadSymbol(event.target.value);
  });
}

async function loadSymbol(symbol) {
  setStatus(`Loading ${symbol}...`);

  try {
    const data = await fetchSymbolData(symbol);
    console.log("Loaded data for", symbol, data);

    if (!isValidData(data)) {
      clearCharts();
      setStatus("No data available ❌");
      return;
    }

    renderKpiCards(data.metrics);
    createPriceChart(data);
    createPortfolioChart(data);
    createDrawdownChart(data);
    setStatus(`Connected — ${symbol}`);
  } catch (error) {
    console.error(error);
    setStatus("Error ❌");
  }
}

async function fetchSymbolData(symbol) {
  const url = `${API_BASE}/data?symbol=${encodeURIComponent(symbol)}`;
  const response = await fetch(url);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Data request failed: ${response.status} ${errorText}`);
  }
  return await response.json();
}

function setStatus(message) {
  document.getElementById("status").innerText = message;
}

function isValidData(data) {
  return (
    data &&
    Array.isArray(data.prices) &&
    data.prices.length > 0 &&
    Array.isArray(data.portfolio_value) &&
    data.portfolio_value.length > 0 &&
    Array.isArray(data.drawdown) &&
    data.drawdown.length > 0
  );
}

function renderKpiCards(metrics) {
  const grid = document.getElementById("kpiGrid");
  grid.innerHTML = "";

  const cards = [
    {
      title: "Total Return %",
      value: metrics.total_return_pct,
      format: "percent",
    },
    {
      title: "Final Portfolio Value",
      value: metrics.final_portfolio_value,
      format: "currency",
    },
    {
      title: "Max Drawdown %",
      value: metrics.max_drawdown_pct,
      format: "percent",
    },
    {
      title: "Sharpe Ratio",
      value: metrics.sharpe_ratio,
      format: "number",
    },
  ];

  cards.forEach((card) => {
    const kpi = document.createElement("div");
    kpi.className = `kpi-card ${card.value !== null && card.value < 0 ? "negative" : "positive"}`;

    const label = document.createElement("p");
    label.className = "label";
    label.textContent = card.title;

    const value = document.createElement("p");
    value.className = "value";
    value.textContent = formatMetric(card.value, card.format);

    kpi.appendChild(label);
    kpi.appendChild(value);
    grid.appendChild(kpi);
  });
}

function formatMetric(value, format) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  if (format === "percent") {
    return `${Number(value).toFixed(2)} %`;
  }

  if (format === "currency") {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(Number(value));
  }

  return Number(value).toFixed(2);
}

function clearCharts() {
  if (priceChartInstance) {
    priceChartInstance.destroy();
    priceChartInstance = null;
  }
  if (portfolioChartInstance) {
    portfolioChartInstance.destroy();
    portfolioChartInstance = null;
  }
  if (drawdownChartInstance) {
    drawdownChartInstance.destroy();
    drawdownChartInstance = null;
  }
}

function createPriceChart(data) {
  clearCharts();

  const labels = data.dates && data.dates.length ? data.dates : data.prices.map((_, index) => index + 1);
  const closeValues = data.prices.map((item) => Number(item.close ?? item));

  priceChartInstance = new Chart(document.getElementById("priceChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Price",
          data: closeValues,
          borderColor: "#38bdf8",
          backgroundColor: "transparent",
          tension: 0.2,
          pointRadius: 0,
          borderWidth: 2,
          spanGaps: true,
        },
        {
          label: "SMA9",
          data: data.sma_9.map((value) => (value === null ? null : Number(value))),
          borderColor: "#4ade80",
          backgroundColor: "transparent",
          tension: 0.2,
          pointRadius: 0,
          borderWidth: 1.5,
          spanGaps: true,
        },
        {
          label: "SMA20",
          data: data.sma_20.map((value) => (value === null ? null : Number(value))),
          borderColor: "#fbbf24",
          backgroundColor: "transparent",
          tension: 0.2,
          pointRadius: 0,
          borderWidth: 1.5,
          spanGaps: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: { labels: { color: "#cbd5e1" } },
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        x: {
          ticks: { color: "#cbd5e1" },
          grid: { color: "rgba(148, 163, 184, 0.12)" },
        },
        y: {
          ticks: { color: "#cbd5e1" },
          grid: { color: "rgba(148, 163, 184, 0.12)" },
        },
      },
    },
  });
}

function createPortfolioChart(data) {
  if (portfolioChartInstance) {
    portfolioChartInstance.destroy();
    portfolioChartInstance = null;
  }

  const labels = data.dates && data.dates.length ? data.dates : data.portfolio_value.map((_, index) => index + 1);

  portfolioChartInstance = new Chart(document.getElementById("portfolioChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Portfolio Value",
          data: data.portfolio_value.map((value) => Number(value)),
          borderColor: "#a855f7",
          backgroundColor: "transparent",
          tension: 0.2,
          pointRadius: 0,
          borderWidth: 2,
          spanGaps: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: { labels: { color: "#cbd5e1" } },
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        x: {
          ticks: { color: "#cbd5e1" },
          grid: { color: "rgba(148, 163, 184, 0.12)" },
        },
        y: {
          ticks: { color: "#cbd5e1" },
          grid: { color: "rgba(148, 163, 184, 0.12)" },
        },
      },
    },
  });
}

function createDrawdownChart(data) {
  if (drawdownChartInstance) {
    drawdownChartInstance.destroy();
    drawdownChartInstance = null;
  }

  const labels = data.dates && data.dates.length ? data.dates : data.drawdown.map((_, index) => index + 1);

  drawdownChartInstance = new Chart(document.getElementById("drawdownChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Drawdown",
          data: data.drawdown.map((value) => Number(value)),
          borderColor: "#f87171",
          backgroundColor: "rgba(248, 113, 113, 0.16)",
          tension: 0.2,
          pointRadius: 0,
          borderWidth: 2,
          fill: true,
          spanGaps: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: { labels: { color: "#cbd5e1" } },
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        x: {
          ticks: { color: "#cbd5e1" },
          grid: { color: "rgba(148, 163, 184, 0.12)" },
        },
        y: {
          ticks: { color: "#cbd5e1" },
          grid: { color: "rgba(148, 163, 184, 0.12)" },
        },
      },
    },
  });
}

initDashboard();
