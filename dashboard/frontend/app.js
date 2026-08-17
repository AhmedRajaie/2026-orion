const API_BASE = "http://127.0.0.1:8000";
let priceChartInstance = null;
let portfolioChartInstance = null;
let drawdownChartInstance = null;
let simulationChartInstance = null;
let tiktok06ChartInstance = null;
let frontierChartInstance = null;
let selectedSymbol = "ADIB";
let chatHistory = [];

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
  selectedSymbol = symbol;
  resetChat(symbol);

  try {
    const [data, simulationData, tiktok06Data, frontierData] = await Promise.all([
      fetchSymbolData(symbol),
      fetchSimulations(symbol),
      fetchTikTok06(),
      fetchMptFrontier(),
    ]);
    const mergedData = {
      ...data,
      dates: simulationData?.dates || data.dates,
      simulations: simulationData?.simulations || [],
    };

    console.log("Loaded data for", symbol, mergedData);

    if (!isValidData(mergedData)) {
      clearCharts();
      setStatus("No data available ❌");
      return;
    }

    renderKpiCards(mergedData.metrics);
    createPriceChart(mergedData);
    createPortfolioChart(mergedData);
    createDrawdownChart(mergedData);
    createSimulationChart(mergedData);
    renderSimulationTable(mergedData.simulations || []);
    createTikTok06Chart(tiktok06Data);
    renderTikTok06Table(tiktok06Data);
    renderMptInsights(mergedData.insights || {});
    renderFrontier(frontierData || {});
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

async function fetchSimulations(symbol) {
  const url = `${API_BASE}/simulations?symbol=${encodeURIComponent(symbol)}`;
  const response = await fetch(url);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Simulation request failed: ${response.status} ${errorText}`);
  }
  return await response.json();
}

function resetChat(symbol) {
  const badge = document.getElementById("chatSymbol");
  if (badge) badge.textContent = symbol;

  const messages = document.getElementById("chatMessages");
  if (!messages) return;

  chatHistory = [];
  messages.innerHTML = "";
  appendChatMessage(
    "assistant",
    `I’m Orion. Ask me about ${symbol}'s latest close, SMA signal, or backtest performance.`
  );
}

function appendChatMessage(role, content) {
  const container = document.getElementById("chatMessages");
  if (!container) return;

  const message = document.createElement("article");
  message.className = `chat-message chat-message--${role}`;
  const label = document.createElement("span");
  label.className = "chat-message__label";
  label.textContent = role === "user" ? "You" : "Orion";
  const body = document.createElement("p");
  body.textContent = content;
  message.append(label, body);
  container.appendChild(message);
  container.scrollTop = container.scrollHeight;
}

function setChatLoading(isLoading) {
  const input = document.getElementById("chatInput");
  const button = document.getElementById("chatSend");
  if (input) input.disabled = isLoading;
  if (button) {
    button.disabled = isLoading;
    button.textContent = isLoading ? "Thinking..." : "Send";
  }
}

async function submitChat(event) {
  event.preventDefault();
  const input = document.getElementById("chatInput");
  const message = input?.value.trim();
  if (!message) return;

  appendChatMessage("user", message);
  input.value = "";
  setChatLoading(true);

  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        symbol: selectedSymbol,
        history: chatHistory,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Chat request failed.");

    chatHistory.push({ role: "user", content: message });
    chatHistory.push({ role: "assistant", content: data.answer });
    appendChatMessage("assistant", data.answer);
  } catch (error) {
    console.error(error);
    appendChatMessage("assistant", "I couldn’t reach the AI service. Please confirm the backend is running and the API key is valid.");
  } finally {
    setChatLoading(false);
    input?.focus();
  }
}

document.getElementById("chatForm")?.addEventListener("submit", submitChat);

async function fetchTikTok06() {
  const response = await fetch(`${API_BASE}/production/tiktok-06`);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`TikTok 06 request failed: ${response.status} ${errorText}`);
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
  if (simulationChartInstance) {
    simulationChartInstance.destroy();
    simulationChartInstance = null;
  }
  if (tiktok06ChartInstance) {
    tiktok06ChartInstance.destroy();
    tiktok06ChartInstance = null;
  }
}

async function fetchMptFrontier(samples = 60) {
  const url = `${API_BASE}/mpt/frontier?samples=${encodeURIComponent(samples)}`;
  const response = await fetch(url);
  if (!response.ok) {
    const errorText = await response.text();
    console.warn(`Frontier request failed: ${response.status} ${errorText}`);
    return null;
  }
  return await response.json();
}

function renderFrontier(data) {
  console.log("frontier data:", data);
  // data: { n_assets, symbols, samples, portfolios, frontier }
  const chartEl = document.getElementById("frontierChart");
  const tableEl = document.getElementById("frontierTable");
  if (!chartEl) return;

  const points = (data.portfolios || []).map((p) => ({ x: Number(p.annual_vol_pct), y: Number(p.annual_return_pct) }));
  const frontierPoints = (data.frontier || []).map((p) => ({ x: Number(p.annual_vol_pct), y: Number(p.annual_return_pct) }));

  if (frontierChartInstance) {
    frontierChartInstance.destroy();
    frontierChartInstance = null;
  }

  frontierChartInstance = new Chart(chartEl, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Sampled portfolios",
          data: points,
          backgroundColor: "rgba(56, 189, 248, 0.6)",
          pointRadius: 3,
        },
        {
          label: "Efficient frontier",
          data: frontierPoints,
          type: "line",
          borderColor: "#4ade80",
          backgroundColor: "transparent",
          tension: 0.2,
          showLine: true,
          fill: false,
          pointRadius: 4,
        },
      ],
    },
    options: {
      plugins: { legend: { display: true } },
      scales: {
        x: { title: { display: true, text: "Annual Volatility (%)" } },
        y: { title: { display: true, text: "Annual Return (%)" } },
      },
    },
  });

  if (tableEl) {
    // show frontier points (concise)
    tableEl.innerHTML = "";
    const header = document.createElement("tr");
    header.innerHTML = `<th>Volatility (%)</th><th>Return (%)</th>`;
    tableEl.appendChild(header);
    (data.frontier || []).forEach((p) => {
      const row = document.createElement("tr");
      row.innerHTML = `<td>${p.annual_vol_pct.toFixed(2)}</td><td>${p.annual_return_pct.toFixed(2)}</td>`;
      tableEl.appendChild(row);
    });
  }
}

function renderMptInsights(insights) {
  const container = document.getElementById("mptInsights");
  if (!container) return;
  container.innerHTML = "";

  const titleRow = document.createElement("div");
  titleRow.className = "mpt-title-row";
  const symbol = document.createElement("p");
  symbol.className = "mpt-symbol";
  symbol.textContent = insights.Symbol ? `${insights.Symbol} — MPT Summary` : "MPT Summary";
  titleRow.appendChild(symbol);

  const statsGrid = document.createElement("div");
  statsGrid.className = "mpt-stats-grid";

  const stats = [
    { label: "Expected Annual Return", value: insights["Expected Annual Return (%)"] },
    { label: "Annual Volatility", value: insights["Annual Volatility (%)"] },
    { label: "Sharpe (MPT)", value: insights["MPT Sharpe"] ?? insights["Sharpe Ratio"] },
    { label: "Total Return (backtest)", value: insights["Total Return (%)"] },
  ];

  stats.forEach((s) => {
    const cell = document.createElement("div");
    cell.className = "mpt-stat";
    const label = document.createElement("p");
    label.className = "mpt-stat-label";
    label.textContent = s.label;
    const value = document.createElement("p");
    value.className = "mpt-stat-value";
    value.textContent = s.value === null || s.value === undefined ? "—" : (typeof s.value === "number" ? s.value : s.value);
    cell.appendChild(label);
    cell.appendChild(value);
    statsGrid.appendChild(cell);
  });

  const reco = document.createElement("div");
  reco.className = "mpt-reco";
  const recoTitle = document.createElement("p");
  recoTitle.className = "mpt-reco-title";
  recoTitle.textContent = "Recommendation";
  const recoBody = document.createElement("p");
  recoBody.className = "mpt-reco-body";
  recoBody.textContent = insights["MPT Recommendation"] || "No recommendation available.";
  reco.appendChild(recoTitle);
  reco.appendChild(recoBody);

  container.appendChild(titleRow);
  container.appendChild(statsGrid);
  container.appendChild(reco);
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
      animation: false,
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
      animation: false,
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

function createSimulationChart(data) {
  if (simulationChartInstance) {
    simulationChartInstance.destroy();
    simulationChartInstance = null;
  }

  const labels = data.dates && data.dates.length ? data.dates : Array.from({ length: data.simulations?.[0]?.portfolio_value?.length || 0 }, (_, index) => index + 1);

  const datasets = (data.simulations || []).map((simulation) => ({
    label: simulation.name,
    data: (simulation.portfolio_value || []).map((value) => Number(value)),
    borderColor: simulation.color || "#38bdf8",
    backgroundColor: "transparent",
    tension: 0.2,
    pointRadius: 0,
    borderWidth: 2,
    spanGaps: true,
  }));

  simulationChartInstance = new Chart(document.getElementById("simulationChart"), {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "#cbd5e1" } },
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        x: { ticks: { color: "#cbd5e1" }, grid: { color: "rgba(148, 163, 184, 0.12)" } },
        y: { ticks: { color: "#cbd5e1" }, grid: { color: "rgba(148, 163, 184, 0.12)" } },
      },
    },
  });
}

function renderSimulationTable(simulations) {
  const table = document.getElementById("simulationTable");
  if (!table) {
    return;
  }

  table.innerHTML = "";
  const thead = document.createElement("thead");
  thead.innerHTML = `
    <tr>
      <th>Strategy</th>
      <th>Final Value</th>
      <th>Total Return</th>
      <th>Max Drawdown</th>
      <th>Sharpe</th>
    </tr>
  `;

  const tbody = document.createElement("tbody");
  (simulations || []).forEach((simulation) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${simulation.name}</td>
      <td>${formatMetric(simulation.metrics?.final_portfolio_value, "currency")}</td>
      <td>${formatMetric(simulation.metrics?.total_return_pct, "percent")}</td>
      <td>${formatMetric(simulation.metrics?.max_drawdown_pct, "percent")}</td>
      <td>${formatMetric(simulation.metrics?.sharpe_ratio, "number")}</td>
    `;
    tbody.appendChild(row);
  });

  table.appendChild(thead);
  table.appendChild(tbody);
}

function createTikTok06Chart(data) {
  if (!data) return;
  if (tiktok06ChartInstance) tiktok06ChartInstance.destroy();

  tiktok06ChartInstance = new Chart(document.getElementById("tiktok06Chart"), {
    type: "line",
    data: {
      labels: data.dates,
      datasets: [
        { label: "TikTok 06", data: data.portfolio_value, borderColor: "#a855f7", tension: 0.2, pointRadius: 0, borderWidth: 2 },
        { label: "Equal Weight", data: data.equal_weight, borderColor: "#fbbf24", borderDash: [6, 4], tension: 0.2, pointRadius: 0, borderWidth: 1.5 },
        { label: "EGX30", data: data.egx30, borderColor: "#38bdf8", borderDash: [2, 4], tension: 0.2, pointRadius: 0, borderWidth: 1.5 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#cbd5e1" } }, tooltip: { mode: "index", intersect: false } },
      scales: {
        x: { ticks: { color: "#cbd5e1", maxTicksLimit: 8 }, grid: { color: "rgba(148, 163, 184, 0.12)" } },
        y: { ticks: { color: "#cbd5e1" }, grid: { color: "rgba(148, 163, 184, 0.12)" } },
      },
    },
  });
}

function renderTikTok06Table(data) {
  const table = document.getElementById("tiktok06Table");
  if (!table || !data?.metrics) return;
  const metrics = data.metrics;
  table.innerHTML = `
    <thead><tr><th>Strategy</th><th>Final Value</th><th>Total Return</th><th>Max Drawdown</th><th>Sharpe</th></tr></thead>
    <tbody><tr>
      <td>${data.name}</td>
      <td>${formatMetric(metrics.final_portfolio_value, "currency")}</td>
      <td>${formatMetric(metrics.total_return_pct, "percent")}</td>
      <td>${formatMetric(metrics.max_drawdown_pct, "percent")}</td>
      <td>${formatMetric(metrics.sharpe_ratio, "number")}</td>
    </tr></tbody>`;
}

initDashboard();
