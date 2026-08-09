const API = "http://localhost:8000";
const COLORS = {
  price: "#60a5fa",
  sma: "#f59e0b",
  ma20: "#a78bfa",
  strategy: "#60a5fa",
  benchmark: "#a78bfa",
  scalping: "#f59e0b",
  buy: "#34d399",
  sell: "#fb7185",
  drawdown: "#fb7185",
  grid: "rgba(148, 163, 184, 0.16)",
};
let selectedUniverse = "small";
let selectedRange = "all";
let selectedSymbol = null;
let priceChartInstance = null;
let strategyChartInstance = null;
let drawdownChartInstance = null;
let equityChartInstance = null;
let baseStrategyChartInstance = null;
let newStrategyChartInstance = null;
let fullPriceData = null;
let fullStrategyData = null;
let strategyTradeTooltip = null;
let tradeSortNewest = true;
let tradeSearchTerm = "";

function getUniverseQuery() {
  return `?universe=${selectedUniverse}`;
}

function getStrategyQuery() {
  const cashValue = getStartingCash();
  return `?cash=${cashValue}&universe=${selectedUniverse}`;
}

function getStartingCash() {
  const input = document.getElementById("startingCashInput");
  if (!input) return 1000;
  const value = Number(input.value);
  return Number.isFinite(value) && value >= 0 ? value : 1000;
}

function formatBadge(isOpen) {
  return `<span class="badge ${isOpen ? "badge-yes" : "badge-no"}">${isOpen ? "Yes" : "No"}</span>`;
}

function updateStrategySummary(symbol, startingCash, openPosition) {
  const summaryAsset = document.getElementById("summaryAsset");
  const summaryCash = document.getElementById("summaryStartingCash");
  const summaryOpenPosition = document.getElementById("summaryOpenPosition");
  if (summaryAsset) summaryAsset.textContent = symbol || "-";
  if (summaryCash) summaryCash.textContent = Number(startingCash).toFixed(0);
  if (summaryOpenPosition) summaryOpenPosition.innerHTML = formatBadge(openPosition);
}

function renderTradeHistory(tradeLog) {
  const tbody = document.querySelector("#tradeHistoryTable tbody");
  if (!tbody) return;
  const normalized = tradeLog
    .filter((trade) => {
      const filter = tradeSearchTerm.trim().toLowerCase();
      if (!filter) return true;
      const dateMatch = trade.date.toLowerCase().includes(filter);
      const actionMatch = trade.action.toLowerCase().includes(filter);
      return dateMatch || actionMatch;
    })
    .slice()
    .sort((a, b) => {
      const dateA = new Date(a.date).getTime();
      const dateB = new Date(b.date).getTime();
      return tradeSortNewest ? dateB - dateA : dateA - dateB;
    });

  if (!normalized.length) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color: var(--muted);">No trades found.</td></tr>`;
    return;
  }

  tbody.innerHTML = normalized
    .map((trade) => {
      const label = trade.action === "buy"
        ? `<span class="badge badge-yes">BUY</span>`
        : `<span class="badge badge-no">SELL</span>`;
      return `<tr>
          <td>${trade.date}</td>
          <td>${label}</td>
          <td>${Number(trade.price).toFixed(2)}</td>
          <td>${Number(trade.shares).toFixed(4)}</td>
          <td>${Number(trade.portfolio_value).toFixed(2)}</td>
        </tr>`;
    })
    .join("");
}

function bindStrategyControls() {
  const cashInput = document.getElementById("startingCashInput");
  const searchInput = document.getElementById("tradeSearchInput");
  const sortBtn = document.getElementById("tradeSortBtn");

  if (cashInput) {
    cashInput.addEventListener("change", () => {
      loadStrategyChart(selectedSymbol);
    });
    cashInput.addEventListener("blur", () => {
      cashInput.value = getStartingCash();
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      tradeSearchTerm = searchInput.value;
      if (fullStrategyData?.trade_log) {
        renderTradeHistory(fullStrategyData.trade_log);
      }
    });
  }

  if (sortBtn) {
    sortBtn.addEventListener("click", () => {
      tradeSortNewest = !tradeSortNewest;
      sortBtn.textContent = tradeSortNewest ? "Newest first" : "Oldest first";
      if (fullStrategyData?.trade_log) {
        renderTradeHistory(fullStrategyData.trade_log);
      }
    });
  }
}

function setUniverse(value) {
  selectedUniverse = value;
  document.querySelectorAll(".universe-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.universe === selectedUniverse);
  });
  selectedRange = "all";
  updateRangeButtons();
  refreshDashboard();
}

function bindUniverseToggle() {
  document.querySelectorAll(".universe-btn").forEach((btn) => {
    btn.addEventListener("click", () => setUniverse(btn.dataset.universe));
  });
}

function updateRangeButtons() {
  document.querySelectorAll(".range-btn").forEach((rangeBtn) => {
    rangeBtn.classList.toggle("active", rangeBtn.dataset.range === selectedRange);
  });
}

function bindTimeRangeToggle() {
  document.querySelectorAll(".range-btn").forEach((btn) => {
    if (!btn.dataset.range) return; // skip the trade-sort button, which reuses .range-btn styling
    btn.addEventListener("click", () => {
      selectedRange = btn.dataset.range;
      updateRangeButtons();
      applyTimeRangeFilter();
    });
  });
}

function setPanelLoading(panelId, isLoading) {
  const panel = document.getElementById(panelId);
  if (panel) {
    panel.classList.toggle("is-loading", isLoading);
  }
}

function populateSymbolSelector(symbols) {
  const select = document.getElementById("symbolSelect");
  if (!select) return;

  const currentSelection = selectedSymbol && symbols.includes(selectedSymbol) ? selectedSymbol : symbols[0] || null;
  select.innerHTML = "";

  if (!symbols.length) {
    const option = document.createElement("option");
    option.textContent = "No symbols";
    option.value = "";
    select.appendChild(option);
    selectedSymbol = null;
    return;
  }

  symbols.forEach((symbol) => {
    const option = document.createElement("option");
    option.value = symbol;
    option.textContent = symbol;
    select.appendChild(option);
  });

  selectedSymbol = currentSelection;
  select.value = currentSelection;
}

function bindAssetSelector() {
  const select = document.getElementById("symbolSelect");
  if (!select) return;

  select.addEventListener("change", () => {
    selectedSymbol = select.value;
    selectedRange = "all";
    updateRangeButtons();
    refreshDashboard();
  });
}

function ensureStrategyTradeTooltip() {
  if (strategyTradeTooltip) return strategyTradeTooltip;

  strategyTradeTooltip = document.createElement("div");
  strategyTradeTooltip.className = "strategy-trade-tooltip";
  strategyTradeTooltip.style.display = "none";
  document.body.appendChild(strategyTradeTooltip);
  return strategyTradeTooltip;
}

function hideStrategyTradeTooltip() {
  const tooltip = ensureStrategyTradeTooltip();
  tooltip.style.display = "none";
  tooltip.innerHTML = "";
}

function showStrategyTradeTooltip(event, trade) {
  const tooltip = ensureStrategyTradeTooltip();
  const actionLabel = trade.action === "buy" ? "Buy" : "Sell";
  tooltip.innerHTML = `
    <strong>${actionLabel}</strong>
    <div>Date: ${trade.date}</div>
    <div>Price: ${Number(trade.price).toFixed(2)}</div>
    <div>Portfolio value: ${Number(trade.portfolio_value).toFixed(2)}</div>
  `;
  tooltip.style.display = "block";
  tooltip.style.left = `${Math.min(event.clientX + 12, window.innerWidth - 230)}px`;
  tooltip.style.top = `${Math.max(event.clientY + 12, 12)}px`;
}

function getChartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: {
        labels: {
          color: "#e2e8f0",
          boxWidth: 12,
          usePointStyle: true,
          padding: 16,
        },
      },
      tooltip: {
        backgroundColor: "#111827",
        titleColor: "#f8fafc",
        bodyColor: "#f8fafc",
      },
    },
    scales: {
      x: {
        ticks: {
          color: "#94a3b8",
          autoSkip: true,
          maxTicksLimit: 8,
          maxRotation: 0,
          minRotation: 0,
        },
        grid: {
          color: COLORS.grid,
          drawBorder: false,
        },
      },
      y: {
        ticks: {
          color: "#94a3b8",
        },
        grid: {
          color: COLORS.grid,
          drawBorder: false,
        },
      },
    },
  };
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function getCutoffDate(rangeKey) {
  const now = new Date();
  if (rangeKey === "all") return null;
  const [amount, unit] = rangeKey === "1m"
    ? [1, "month"]
    : rangeKey === "6m"
      ? [6, "month"]
      : rangeKey === "1y"
        ? [1, "year"]
        : rangeKey === "5y"
          ? [5, "year"]
          : [10, "year"];

  const date = new Date(now);
  if (unit === "month") {
    date.setMonth(date.getMonth() - amount);
  } else {
    date.setFullYear(date.getFullYear() - amount);
  }
  return date;
}

function applyTimeRangeFilter() {
  if (!fullPriceData || !fullStrategyData) return;

  const cutoff = getCutoffDate(selectedRange);
  const filterDates = (dates, values) => {
    if (!cutoff) return { dates, values };
    const startIndex = dates.findIndex((date) => parseDate(date) && parseDate(date) >= cutoff);
    const safeStart = startIndex >= 0 ? startIndex : dates.length;
    return {
      dates: dates.slice(safeStart),
      values: values.slice(safeStart),
    };
  };

  const priceFiltered = filterDates(fullPriceData.dates, fullPriceData.close);
  const priceSmaFiltered = filterDates(fullPriceData.dates, fullPriceData.sma || []);
  const strategyFiltered = filterDates(fullStrategyData.dates, fullStrategyData.close);

  if (priceChartInstance) {
    priceChartInstance.data.labels = priceFiltered.dates;
    priceChartInstance.data.datasets[0].data = priceFiltered.values;
    priceChartInstance.data.datasets[1].data = priceSmaFiltered.values;
    priceChartInstance.update();
  }

  if (strategyChartInstance) {
    const filteredMa9 = filterDates(fullStrategyData.dates, fullStrategyData.ma9);
    const filteredMa20 = filterDates(fullStrategyData.dates, fullStrategyData.ma20);
    const filteredBuy = filterDates(fullStrategyData.dates, fullStrategyData.buy_markers);
    const filteredSell = filterDates(fullStrategyData.dates, fullStrategyData.sell_markers);

    strategyChartInstance.data.labels = strategyFiltered.dates;
    strategyChartInstance.data.datasets[0].data = strategyFiltered.values;
    strategyChartInstance.data.datasets[1].data = filteredMa9.values;
    strategyChartInstance.data.datasets[2].data = filteredMa20.values;
    strategyChartInstance.data.datasets[3].data = filteredBuy.values;
    strategyChartInstance.data.datasets[4].data = filteredSell.values;
    strategyChartInstance.update();
  }

  if (drawdownChartInstance && fullStrategyData.drawdown_series) {
    const ddDates = fullStrategyData.drawdown_series.map((d) => d.date);
    const ddValues = fullStrategyData.drawdown_series.map((d) => d.drawdown_pct);
    const ddFiltered = filterDates(ddDates, ddValues);
    drawdownChartInstance.data.labels = ddFiltered.dates;
    drawdownChartInstance.data.datasets[0].data = ddFiltered.values;
    drawdownChartInstance.update();
  }
}

async function checkHealth() {
  const statusEl = document.getElementById("status");
  try {
    const response = await fetch(`${API}/health`);
    const data = await response.json();
    statusEl.textContent = "backend: " + data.status;
    console.log("[checkHealth] ok:", data);
  } catch (err) {
    statusEl.textContent = "backend not reachable";
    console.error("[checkHealth] failed:", err);
  }
}

async function loadPriceChart(symbol) {
  try {
    if (!symbol) return;

    const priceResponse = await fetch(`${API}/prices/${symbol}${getUniverseQuery()}`);
    if (!priceResponse.ok) throw new Error(`/prices/${symbol} returned ${priceResponse.status}`);
    const prices = await priceResponse.json();

    const indicatorsResponse = await fetch(`${API}/indicators/${symbol}?window=20${getUniverseQuery().replace("?", "&")}`);
    if (!indicatorsResponse.ok) throw new Error(`/indicators/${symbol} returned ${indicatorsResponse.status}`);
    const indicators = await indicatorsResponse.json();

    if (!prices.dates || prices.dates.length === 0) return;

    fullPriceData = {
      dates: prices.dates,
      close: prices.close,
      sma: indicators.sma,
    };

    const canvasEl = document.getElementById("priceChart");
    const ctx = canvasEl.getContext("2d");

    if (priceChartInstance) {
      priceChartInstance.destroy();
    }

    priceChartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: prices.dates,
        datasets: [
          {
            label: symbol,
            data: prices.close,
            borderColor: COLORS.price,
            backgroundColor: "rgba(96, 165, 250, 0.16)",
            pointRadius: 0,
            tension: 0.15,
            fill: false,
            borderWidth: 2,
          },
          {
            label: `SMA(${20})`,
            data: indicators.sma,
            borderColor: COLORS.sma,
            pointRadius: 0,
            tension: 0.15,
            fill: false,
            borderWidth: 2,
          },
        ],
      },
      options: getChartOptions(),
    });

    await loadStrategyChart(symbol);
  } catch (err) {
    console.error("[loadPriceChart] failed:", err);
  }
}

async function loadStrategyChart(symbol) {
  try {
    const res = await fetch(`${API}/strategy/${symbol}${getUniverseQuery()}&cash=${getStartingCash()}`);
    if (!res.ok) throw new Error(`/strategy/${symbol} returned ${res.status}`);
    const s = await res.json();

    const canvasEl = document.getElementById("strategyChart");
    const ctx = canvasEl.getContext("2d");

    if (strategyChartInstance) {
      strategyChartInstance.destroy();
    }

    const tradeLog = Array.isArray(s.trade_log) ? s.trade_log : [];

    fullStrategyData = {
      dates: s.dates,
      close: s.close,
      ma9: s.ma9,
      ma20: s.ma20,
      buy_markers: Array.isArray(s.buy_markers) ? s.buy_markers : [],
      sell_markers: Array.isArray(s.sell_markers) ? s.sell_markers : [],
      trade_log: tradeLog,
      drawdown_series: Array.isArray(s.drawdown_series) ? s.drawdown_series : [],
    };

    const buyMarkers = fullStrategyData.buy_markers;
    const sellMarkers = fullStrategyData.sell_markers;

    const options = getChartOptions();
    options.onClick = (event, elements) => {
      event.native?.stopPropagation?.();
      if (!elements.length) {
        hideStrategyTradeTooltip();
        return;
      }

      const point = elements[0];
      if (![3, 4].includes(point.datasetIndex)) {
        hideStrategyTradeTooltip();
        return;
      }

      const label = strategyChartInstance?.data?.labels?.[point.index];
      if (!label) {
        hideStrategyTradeTooltip();
        return;
      }

      const trade = tradeLog.find((entry) => entry.date === label);
      if (!trade) {
        hideStrategyTradeTooltip();
        return;
      }

      showStrategyTradeTooltip(event.native ?? event, trade);
    };

    strategyChartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: s.dates,
        datasets: [
          {
            label: "Close",
            data: s.close,
            borderColor: COLORS.price,
            pointRadius: 0,
            tension: 0.1,
            fill: false,
            borderWidth: 2,
          },
          {
            label: "MA9",
            data: s.ma9,
            borderColor: COLORS.sma,
            pointRadius: 0,
            tension: 0.1,
            fill: false,
            borderWidth: 2,
          },
          {
            label: "MA20",
            data: s.ma20,
            borderColor: COLORS.ma20,
            pointRadius: 0,
            tension: 0.1,
            fill: false,
            borderWidth: 2,
          },
          {
            label: "Buy",
            data: buyMarkers,
            borderColor: "transparent",
            backgroundColor: COLORS.buy,
            pointStyle: "triangle",
            pointRadius: 8,
            showLine: false,
          },
          {
            label: "Sell",
            data: sellMarkers,
            borderColor: "transparent",
            backgroundColor: COLORS.sell,
            pointStyle: "rectRot",
            pointRadius: 7,
            showLine: false,
          },
        ],
      },
      options,
    });

    // --- Drawdown Over Time chart ---
    const drawdownCanvas = document.getElementById("drawdownChart");
    if (drawdownCanvas) {
      if (drawdownChartInstance) {
        drawdownChartInstance.destroy();
      }
      const ddDates = fullStrategyData.drawdown_series.map((d) => d.date);
      const ddValues = fullStrategyData.drawdown_series.map((d) => d.drawdown_pct);

      drawdownChartInstance = new Chart(drawdownCanvas.getContext("2d"), {
        type: "line",
        data: {
          labels: ddDates,
          datasets: [
            {
              label: "Drawdown %",
              data: ddValues,
              borderColor: COLORS.drawdown,
              backgroundColor: "rgba(251, 113, 133, 0.16)",
              pointRadius: 0,
              tension: 0.1,
              fill: true,
              borderWidth: 2,
            },
          ],
        },
        options: getChartOptions(),
      });
    }

    // --- Stat cards ---
    const finalValue = Number(s.stats?.final_value ?? 0);
    const buyCount = Number(s.stats?.buy_count ?? 0);
    const sellCount = Number(s.stats?.sell_count ?? 0);
    const maxDrawdown = Number(s.stats?.max_drawdown_pct ?? 0);
    const pnl = Number(s.pnl ?? 0);
    const returnPct = Number(s.return_pct ?? 0);
    const openPosition = Boolean(s.open_position);

    document.getElementById("statFinalValue").textContent = `${finalValue.toFixed(2)} EGP`;
    document.getElementById("statBuyCount").textContent = String(buyCount);
    document.getElementById("statSellCount").textContent = String(sellCount);
    document.getElementById("statMaxDrawdown").textContent = `${maxDrawdown.toFixed(2)}%`;
    document.getElementById("statPL").textContent = `${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)} EGP`;
    document.getElementById("statReturnPct").textContent = `${returnPct >= 0 ? "+" : ""}${returnPct.toFixed(2)}%`;
    document.getElementById("statOpenPosition").innerHTML = formatBadge(openPosition);

    // --- Strategy Summary ---
    updateStrategySummary(symbol, getStartingCash(), openPosition);

    // --- Trade History table ---
    renderTradeHistory(tradeLog);

    applyTimeRangeFilter();
  } catch (err) {
    console.error("[loadStrategyChart] failed:", err);
  }
}

async function loadEquityChart() {
  try {
    setPanelLoading("equityPanel", true);
    const res = await fetch(`${API}/backtest${getUniverseQuery()}`);
    if (!res.ok) throw new Error(`/backtest returned ${res.status}`);
    const backtest = await res.json();

    const canvasEl = document.getElementById("equityChart");
    const ctx = canvasEl.getContext("2d");

    if (equityChartInstance) {
      equityChartInstance.destroy();
    }

    equityChartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: Array.from({ length: backtest.portfolio.length }, (_, i) => i + 1),
        datasets: [
          {
            label: "Strategy",
            data: backtest.portfolio,
            borderColor: COLORS.strategy,
            pointRadius: 0,
            tension: 0.1,
            fill: false,
            borderWidth: 2,
          },
          {
            label: "Benchmark",
            data: backtest.benchmark,
            borderColor: COLORS.benchmark,
            pointRadius: 0,
            tension: 0.1,
            fill: false,
            borderWidth: 2,
          },
        ],
      },
      options: getChartOptions(),
    });
  } catch (err) {
    console.error("[loadEquityChart] failed:", err);
  } finally {
    setPanelLoading("equityPanel", false);
  }
}

async function loadFeaturesPanel() {
  try {
    setPanelLoading("featuresPanelWrapper", true);
    const res = await fetch(`${API}/features`);
    if (!res.ok) throw new Error(`/features returned ${res.status}`);
    const features = await res.json();
    const entries = Object.entries(features || {});
    const panel = document.getElementById("featuresPanel");

    if (!entries.length) {
      panel.innerHTML = "No feature data available.";
      return;
    }

    const maxAbs = Math.max(...entries.map(([, value]) => Math.abs(Number(value) || 0)), 1);
    panel.innerHTML = entries
      .map(([name, value]) => {
        const numeric = Number(value);
        const safeValue = Number.isFinite(numeric) ? numeric : 0;
        const width = Math.min(100, Math.abs(safeValue) / maxAbs * 100);
        return `
          <div class="feature-row">
            <div>${name}</div>
            <div class="feature-bar"><span style="width:${width}%"></span></div>
            <div class="feature-value">${safeValue.toFixed(3)}</div>
          </div>
        `;
      })
      .join("");
  } catch (err) {
    console.error("[loadFeaturesPanel] failed:", err);
  } finally {
    setPanelLoading("featuresPanelWrapper", false);
  }
}

function renderStrategyChart(instance, canvasId, dates, portfolio, benchmark, color) {
  const canvasEl = document.getElementById(canvasId);
  const ctx = canvasEl.getContext("2d");
  if (instance) {
    instance.destroy();
  }
  return new Chart(ctx, {
    type: "line",
    data: {
      labels: dates,
      datasets: [
        {
          label: "Strategy",
          data: portfolio,
          borderColor: color,
          pointRadius: 0,
          tension: 0.1,
          fill: false,
          borderWidth: 2,
        },
        {
          label: "Benchmark",
          data: benchmark,
          borderColor: COLORS.benchmark,
          pointRadius: 0,
          tension: 0.1,
          fill: false,
          borderWidth: 2,
        },
      ],
    },
    options: getChartOptions(),
  });
}

function renderStrategyStats(prefix, metrics) {
  const totalReturnPct = Number(metrics.total_return) * 100;
  const maxDrawdownPct = Number(metrics.max_drawdown) * 100;
  document.getElementById(`${prefix}TotalReturn`).textContent =
    `${totalReturnPct >= 0 ? "+" : ""}${totalReturnPct.toFixed(1)}%`;
  document.getElementById(`${prefix}Sharpe`).textContent = Number(metrics.sharpe).toFixed(2);
  document.getElementById(`${prefix}MaxDrawdown`).textContent = `${maxDrawdownPct.toFixed(1)}%`;
}

async function loadStrategyPerformance() {
  setPanelLoading("baseStrategyChartPanel", true);
  setPanelLoading("newStrategyChartPanel", true);
  try {
    const res = await fetch(`${API}/strategies${getUniverseQuery()}`);
    if (!res.ok) throw new Error(`/strategies returned ${res.status}`);
    const data = await res.json();

    baseStrategyChartInstance = renderStrategyChart(
      baseStrategyChartInstance, "baseStrategyChart", data.dates, data.sma.portfolio, data.benchmark, COLORS.strategy
    );
    newStrategyChartInstance = renderStrategyChart(
      newStrategyChartInstance, "newStrategyChart", data.dates, data.scalping.portfolio, data.benchmark, COLORS.scalping
    );

    renderStrategyStats("base", data.sma);
    renderStrategyStats("new", data.scalping);
  } catch (err) {
    console.error("[loadStrategyPerformance] failed:", err);
  } finally {
    setPanelLoading("baseStrategyChartPanel", false);
    setPanelLoading("newStrategyChartPanel", false);
  }
}

async function loadMetrics() {
  try {
    const res = await fetch(`${API}/metrics${getUniverseQuery()}`);
    if (!res.ok) throw new Error(`/metrics returned ${res.status}`);
    await res.json();
  } catch (err) {
    console.error("[loadMetrics] failed:", err);
  }
}

async function refreshDashboard() {
  setPanelLoading("pricePanel", true);
  setPanelLoading("strategyPanel", true);
  try {
    await checkHealth();

    const universeResponse = await fetch(`${API}/universe${getUniverseQuery()}`);
    if (!universeResponse.ok) throw new Error(`/universe returned ${universeResponse.status}`);
    const symbols = await universeResponse.json();
    populateSymbolSelector(symbols);

    if (!selectedSymbol) {
      selectedSymbol = symbols[0] || null;
    } else if (!symbols.includes(selectedSymbol)) {
      selectedSymbol = symbols[0] || null;
    }

    if (!selectedSymbol) {
      return;
    }

    document.getElementById("symbolSelect").value = selectedSymbol;

    await loadFeaturesPanel();
    await loadPriceChart(selectedSymbol);
    await loadEquityChart();
    await loadMetrics();
    await loadStrategyPerformance();
  } catch (err) {
    console.error("[refreshDashboard] failed:", err);
  } finally {
    setPanelLoading("pricePanel", false);
    setPanelLoading("strategyPanel", false);
  }
}

bindUniverseToggle();
bindTimeRangeToggle();
bindAssetSelector();
bindStrategyControls();
document.addEventListener("click", (event) => {
  if (!event.target.closest(".strategy-trade-tooltip")) {
    hideStrategyTradeTooltip();
  }
});
refreshDashboard();