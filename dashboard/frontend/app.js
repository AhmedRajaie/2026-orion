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
let day3ComparisonChartInstance = null;
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

function setPanelError(panelId, hasError) {
  const panel = document.getElementById(panelId);
  if (panel) {
    panel.classList.toggle("is-error", hasError);
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
    syncSymbolDropdownUI();
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
  syncSymbolDropdownUI();
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

function closeSymbolDropdown() {
  const list = document.getElementById("symbolDropdownList");
  const btn = document.getElementById("symbolDropdownBtn");
  if (list) list.hidden = true;
  if (btn) btn.setAttribute("aria-expanded", "false");
}

function openSymbolDropdown() {
  const list = document.getElementById("symbolDropdownList");
  const btn = document.getElementById("symbolDropdownBtn");
  if (list) list.hidden = false;
  if (btn) btn.setAttribute("aria-expanded", "true");
  const selectedItem = list && list.querySelector('li[aria-selected="true"]');
  if (selectedItem) selectedItem.scrollIntoView({ block: "nearest" });
}

// The native <select> stays in the DOM (hidden) as the single source of truth for
// the current symbol list/selection, so all existing selection logic (bindAssetSelector,
// refreshDashboard) is untouched. This just mirrors its <option>s into a CSS-scrollable
// <ul> so every option is actually reachable, since a native popup's internal scrolling
// is OS-rendered and outside CSS's reach.
function syncSymbolDropdownUI() {
  const select = document.getElementById("symbolSelect");
  const list = document.getElementById("symbolDropdownList");
  const label = document.getElementById("symbolDropdownLabel");
  if (!select || !list || !label) return;

  list.innerHTML = "";
  Array.from(select.options).forEach((option) => {
    const item = document.createElement("li");
    item.setAttribute("role", "option");
    item.tabIndex = -1;
    item.dataset.value = option.value;
    item.textContent = option.textContent;
    if (option.value === select.value) {
      item.setAttribute("aria-selected", "true");
    }
    item.addEventListener("click", () => {
      if (select.value !== option.value) {
        select.value = option.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
      closeSymbolDropdown();
    });
    list.appendChild(item);
  });

  label.textContent = select.value || (select.options[0] ? select.options[0].textContent : "No symbols");
}

function bindSymbolDropdown() {
  const btn = document.getElementById("symbolDropdownBtn");
  const list = document.getElementById("symbolDropdownList");
  if (!btn || !list) return;

  btn.addEventListener("click", () => {
    if (list.hidden) {
      openSymbolDropdown();
    } else {
      closeSymbolDropdown();
    }
  });

  btn.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openSymbolDropdown();
      const first = list.querySelector('li[aria-selected="true"]') || list.querySelector("li");
      if (first) first.focus();
    }
  });

  list.addEventListener("keydown", (event) => {
    const items = Array.from(list.querySelectorAll("li"));
    const currentIndex = items.findIndex((item) => item === document.activeElement);
    if (event.key === "Escape") {
      event.preventDefault();
      closeSymbolDropdown();
      btn.focus();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      const next = items[Math.min(currentIndex + 1, items.length - 1)];
      if (next) next.focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      const prev = items[Math.max(currentIndex - 1, 0)];
      if (prev) prev.focus();
    } else if (event.key === "Enter" && currentIndex >= 0) {
      event.preventDefault();
      items[currentIndex].click();
      btn.focus();
    }
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest("#symbolDropdown")) {
      closeSymbolDropdown();
    }
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
    animation: { duration: 300, easing: "easeOutQuart" },
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
  const dotEl = document.getElementById("statusDot");
  try {
    const response = await fetch(`${API}/health`);
    const data = await response.json();
    statusEl.textContent = "backend: " + data.status;
    if (dotEl) {
      dotEl.classList.remove("error");
      dotEl.classList.add("ok");
    }
    console.log("[checkHealth] ok:", data);
  } catch (err) {
    statusEl.textContent = "backend not reachable";
    if (dotEl) {
      dotEl.classList.remove("ok");
      dotEl.classList.add("error");
    }
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
    setPanelError("tradeHistoryPanel", false);
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
    setPanelError("tradeHistoryPanel", true);
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
    setPanelError("featuresPanelWrapper", false);
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
    setPanelError("featuresPanelWrapper", true);
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

const DAY3_STRATEGY_COLORS = {
  mlp: COLORS.price,
  lstm: COLORS.sma,
  equal_weight: COLORS.ma20,
  my_mlp: COLORS.buy,
  my_lstm: COLORS.sell,
};
let day3ComparisonData = null;
let day3SelectedKey = null; // null = overview (all 5 strategies), otherwise a strategies key

// Display-only label overrides for the Week 2 Day 3 panel. Does not affect
// underlying data keys, API "name"/"label" values, ordering, or calculations.
const DAY3_TABLE_LABELS = {
  "My MLP": "mlp",
  "My LSTM": "lstm",
  "Professor's LSTM": "lstm",
  "Professor's MLP": "mlp",
};
function day3TableLabel(label) {
  return DAY3_TABLE_LABELS[label] || label;
}

// Graph (legend/tooltip/title) keeps "My MLP"/"My LSTM" as-is; only the
// professor strategies are shortened here.
const DAY3_GRAPH_LABELS = {
  "Professor's LSTM": "lstm",
  "Professor's MLP": "mlp",
};
function day3GraphLabel(label) {
  return DAY3_GRAPH_LABELS[label] || label;
}

function renderDay3OverviewChart(data) {
  const datasets = Object.entries(data.strategies).map(([key, strategy]) => ({
    label: day3GraphLabel(strategy.label),
    data: strategy.portfolio,
    borderColor: DAY3_STRATEGY_COLORS[key] || COLORS.strategy,
    pointRadius: 0,
    tension: 0.1,
    fill: false,
    borderWidth: 2,
  }));

  datasets.push({
    label: "Benchmark",
    data: data.benchmark,
    borderColor: "#94a3b8",
    borderDash: [4, 4],
    pointRadius: 0,
    tension: 0.1,
    fill: false,
    borderWidth: 2,
  });

  return { labels: data.dates, datasets };
}

function renderDay3StrategyChart(data, key) {
  const strategy = data.strategies[key];
  return {
    labels: data.dates,
    datasets: [
      {
        label: day3GraphLabel(strategy.label),
        data: strategy.portfolio,
        borderColor: DAY3_STRATEGY_COLORS[key] || COLORS.strategy,
        pointRadius: 0,
        tension: 0.1,
        fill: false,
        borderWidth: 2,
      },
      {
        label: "Benchmark",
        data: data.benchmark,
        borderColor: "#94a3b8",
        borderDash: [4, 4],
        pointRadius: 0,
        tension: 0.1,
        fill: false,
        borderWidth: 2,
      },
    ],
  };
}

function renderDay3Chart() {
  if (!day3ComparisonData) return;

  const titleEl = document.getElementById("day3ChartTitle");
  const showAllBtn = document.getElementById("day3ShowAllBtn");
  const chartData = day3SelectedKey
    ? renderDay3StrategyChart(day3ComparisonData, day3SelectedKey)
    : renderDay3OverviewChart(day3ComparisonData);

  if (titleEl) {
    titleEl.textContent = day3SelectedKey
      ? `${day3GraphLabel(day3ComparisonData.strategies[day3SelectedKey].label)} vs Benchmark — Full Universe (Test Period)`
      : "MLP vs LSTM vs Equal-Weight vs MLP vs LSTM — Full Universe (Test Period)";
  }
  if (showAllBtn) {
    showAllBtn.style.display = day3SelectedKey ? "" : "none";
  }

  const canvasEl = document.getElementById("day3ComparisonChart");
  const ctx = canvasEl.getContext("2d");
  if (day3ComparisonChartInstance) {
    day3ComparisonChartInstance.destroy();
  }
  day3ComparisonChartInstance = new Chart(ctx, {
    type: "line",
    data: chartData,
    options: getChartOptions(),
  });
}

function renderDay3RankingTable(ranking) {
  const tbody = document.querySelector("#day3RankingTable tbody");
  if (!tbody) return;

  if (!ranking.length) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color: var(--muted);">No ranking data.</td></tr>`;
    return;
  }

  tbody.innerHTML = ranking
    .map((row, index) => `<tr data-key="${row.key}" style="cursor:pointer;">
        <td>${index + 1}${index === 0 ? ' <span class="badge badge-yes">BEST</span>' : ""}</td>
        <td>${day3TableLabel(row.label)}</td>
        <td>${Number(row.final_value).toLocaleString(undefined, { maximumFractionDigits: 0 })} EGP</td>
        <td>${formatBadge(row.beat_benchmark)}</td>
      </tr>`)
    .join("");

  tbody.querySelectorAll("tr[data-key]").forEach((row) => {
    row.addEventListener("click", () => {
      day3SelectedKey = row.dataset.key;
      renderDay3Chart();
    });
  });
}

function bindDay3Controls() {
  const showAllBtn = document.getElementById("day3ShowAllBtn");
  if (showAllBtn) {
    showAllBtn.addEventListener("click", () => {
      day3SelectedKey = null;
      renderDay3Chart();
    });
  }
}

async function loadDay3Comparison() {
  setPanelLoading("day3ComparisonPanel", true);
  setPanelError("day3ComparisonPanel", false);
  setPanelError("day3RankingPanel", false);
  try {
    const res = await fetch(`${API}/day3-comparison`);
    if (!res.ok) throw new Error(`/day3-comparison returned ${res.status}`);
    day3ComparisonData = await res.json();
    day3SelectedKey = null;

    renderDay3Chart();
    renderDay3RankingTable(day3ComparisonData.ranking || []);
  } catch (err) {
    console.error("[loadDay3Comparison] failed:", err);
    setPanelError("day3ComparisonPanel", true);
    setPanelError("day3RankingPanel", true);
  } finally {
    setPanelLoading("day3ComparisonPanel", false);
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
  setPanelLoading("statusControlsPanel", true);
  try {
    setPanelError("statusControlsPanel", false);
    const universeResponse = await fetch(`${API}/universe${getUniverseQuery()}`);
    if (!universeResponse.ok) throw new Error(`/universe returned ${universeResponse.status}`);
    const symbols = await universeResponse.json();
    populateSymbolSelector(symbols);

    if (!selectedSymbol) {
      selectedSymbol = symbols[0] || null;
    } else if (!symbols.includes(selectedSymbol)) {
      selectedSymbol = symbols[0] || null;
    }

    const healthPromise = checkHealth();
    const featuresPromise = loadFeaturesPanel();
    const equityPromise = loadEquityChart();
    const metricsPromise = loadMetrics();
    const strategyPerfPromise = loadStrategyPerformance();
    const day3Promise = loadDay3Comparison();

    let priceChartPromise = Promise.resolve();
    if (selectedSymbol) {
      document.getElementById("symbolSelect").value = selectedSymbol;
      priceChartPromise = loadPriceChart(selectedSymbol);
    }

    await Promise.allSettled([
      healthPromise,
      featuresPromise,
      equityPromise,
      metricsPromise,
      strategyPerfPromise,
      day3Promise,
      priceChartPromise,
    ]);
  } catch (err) {
    console.error("[refreshDashboard] failed:", err);
    setPanelError("statusControlsPanel", true);
  } finally {
    setPanelLoading("pricePanel", false);
    setPanelLoading("strategyPanel", false);
    setPanelLoading("statusControlsPanel", false);
  }
}

function appendChatMessage(role, text) {
  const messages = document.getElementById("chatMessages");
  if (!messages) return;
  const bubble = document.createElement("div");
  bubble.className = `chat-message ${role}`;
  bubble.textContent = text;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
}

async function sendChatMessage() {
  const input = document.getElementById("chatInput");
  const sendBtn = document.getElementById("chatSendBtn");
  if (!input) return;

  const question = input.value.trim();
  if (!question) return;

  appendChatMessage("user", question);
  input.value = "";
  input.disabled = true;
  if (sendBtn) sendBtn.disabled = true;

  try {
    const response = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        symbol: selectedSymbol,
        universe: selectedUniverse,
      }),
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `/chat returned ${response.status}`);
    }
    const data = await response.json();
    appendChatMessage("assistant", data.answer);
  } catch (err) {
    console.error("[sendChatMessage] failed:", err);
    appendChatMessage("assistant", "Sorry, I couldn't reach the chat backend. Check that GEMINI_API_KEY is configured and the server is running.");
  } finally {
    input.disabled = false;
    if (sendBtn) sendBtn.disabled = false;
    input.focus();
  }
}

function bindChatPanel() {
  const toggleBtn = document.getElementById("chatToggleBtn");
  const section = document.getElementById("chatSection");
  const sendBtn = document.getElementById("chatSendBtn");
  const input = document.getElementById("chatInput");
  if (!toggleBtn || !section) return;

  toggleBtn.addEventListener("click", () => {
    const isOpen = section.style.display !== "none";
    section.style.display = isOpen ? "none" : "block";
    toggleBtn.classList.toggle("active", !isOpen);
    toggleBtn.setAttribute("aria-expanded", String(!isOpen));
  });

  if (sendBtn) sendBtn.addEventListener("click", sendChatMessage);
  if (input) {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") sendChatMessage();
    });
  }
}

bindUniverseToggle();
bindTimeRangeToggle();
bindAssetSelector();
bindSymbolDropdown();
bindStrategyControls();
bindDay3Controls();
bindChatPanel();
document.addEventListener("click", (event) => {
  if (!event.target.closest(".strategy-trade-tooltip")) {
    hideStrategyTradeTooltip();
  }
});
refreshDashboard();