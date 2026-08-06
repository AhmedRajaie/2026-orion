const API_BASE = "http://127.0.0.1:8000";

const statusPanel = document.getElementById("status");
const assetSelect = document.getElementById("asset-select");
const assetDescription = document.getElementById(
  "asset-description"
);

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


function setStatus(message, state = "") {
  statusPanel.textContent = message;
  statusPanel.className = `status ${state}`;
}


function chartOptions(yTitle) {
  return {
    responsive: true,
    maintainAspectRatio: false,

    interaction: {
      mode: "index",
      intersect: false,
    },

    plugins: {
      legend: {
        labels: {
          color: "#e8eef7",
        },
      },

      zoom: {
        limits: {
          x: {
            minRange: 10,
          },
        },

        pan: {
          enabled: true,
          mode: "x",
          modifierKey: "shift",
        },

        zoom: {
          wheel: {
            enabled: true,
            speed: 0.1,
          },

          pinch: {
            enabled: true,
          },

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
        ticks: {
          color: "#91a3ba",
          maxTicksLimit: 12,
        },

        grid: {
          color: "rgba(145, 163, 186, 0.08)",
        },
      },

      y: {
        title: {
          display: true,
          text: yTitle,
          color: "#91a3ba",
        },

        ticks: {
          color: "#91a3ba",
        },

        grid: {
          color: "rgba(145, 163, 186, 0.08)",
        },
      },
    },
  };
}


function displayMetrics(backtest) {
  document.getElementById("final-value").textContent =
    formatEGP(backtest.final_portfolio_value_egp);

  const returnElement =
    document.getElementById("total-return");

  returnElement.textContent =
    `${backtest.total_return_percent.toFixed(2)}%`;

  returnElement.classList.remove("positive", "negative");

  returnElement.classList.add(
    backtest.total_return_percent >= 0
      ? "positive"
      : "negative"
  );

  document.getElementById("max-drawdown").textContent =
    `${formatEGP(backtest.max_drawdown_egp)} ` +
    `(${backtest.max_drawdown_percent.toFixed(2)}%)`;

  document.getElementById("operations").textContent =
    `${backtest.buy_operations} / ` +
    `${backtest.sell_operations}`;
}


function renderPriceChart(indicators, trades) {
  if (priceChart) {
    priceChart.destroy();
  }

  const canvas = document.getElementById("price-chart");
  const labels = indicators.data.map((row) => row.date);

  const buysByDate = new Map(
    trades
      .filter((trade) => trade.operation === "BUY")
      .map((trade) => [
        trade.execution_date,
        trade.execution_price,
      ])
  );

  const sellsByDate = new Map(
    trades
      .filter((trade) => trade.operation === "SELL")
      .map((trade) => [
        trade.execution_date,
        trade.execution_price,
      ])
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
          tension: 0.1,
        },

        {
          label: "SMA 9",
          data: indicators.data.map((row) => row.ma9),
          borderColor: "#32d583",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.1,
        },

        {
          label: "SMA 20",
          data: indicators.data.map((row) => row.ma20),
          borderColor: "#f59e0b",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.1,
        },

        {
          label: "Buy",
          data: labels.map(
            (date) => buysByDate.get(date) ?? null
          ),
          borderColor: "#32d583",
          backgroundColor: "#32d583",
          pointStyle: "triangle",
          pointRadius: labels.map(
            (date) => buysByDate.has(date) ? 7 : 0
          ),
          showLine: false,
        },

        {
          label: "Sell",
          data: labels.map(
            (date) => sellsByDate.get(date) ?? null
          ),
          borderColor: "#ff6b6b",
          backgroundColor: "#ff6b6b",
          pointStyle: "triangle",
          pointRotation: 180,
          pointRadius: labels.map(
            (date) => sellsByDate.has(date) ? 7 : 0
          ),
          showLine: false,
        },
      ],
    },

    options: chartOptions("Price"),
  });

  canvas.ondblclick = () => {
    priceChart.resetZoom();
  };
}


function renderEquityChart(backtest) {
  if (equityChart) {
    equityChart.destroy();
  }

  const canvas = document.getElementById(
    "equity-chart"
  );

  const equity = backtest.equity_curve;

  equityChart = new Chart(canvas, {
    type: "line",

    data: {
      labels: equity.map((row) => row.date),

      datasets: [
        {
          label: "Portfolio value",
          data: equity.map(
            (row) => row.portfolio_value
          ),
          borderColor: "#60a5fa",
          backgroundColor:
            "rgba(96, 165, 250, 0.12)",
          fill: true,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.1,
        },

        {
          label: "Running peak",
          data: equity.map(
            (row) => row.running_peak
          ),
          borderColor: "#91a3ba",
          borderDash: [6, 6],
          borderWidth: 1,
          pointRadius: 0,
        },
      ],
    },

    options: chartOptions(
      "Portfolio value (EGP)"
    ),
  });

  canvas.ondblclick = () => {
    equityChart.resetZoom();
  };
}


function renderDrawdownChart(backtest) {
  if (drawdownChart) {
    drawdownChart.destroy();
  }

  const canvas = document.getElementById(
    "drawdown-chart"
  );

  const equity = backtest.equity_curve;

  drawdownChart = new Chart(canvas, {
    type: "line",

    data: {
      labels: equity.map((row) => row.date),

      datasets: [
        {
          label: "Drawdown",
          data: equity.map(
            (row) => row.drawdown_percent
          ),
          borderColor: "#ff6b6b",
          backgroundColor:
            "rgba(255, 107, 107, 0.3)",
          fill: true,
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.1,
        },
      ],
    },

    options: chartOptions("Drawdown (%)"),
  });

  canvas.ondblclick = () => {
    drawdownChart.resetZoom();
  };
}


function renderTrades(trades) {
  const table = document.getElementById(
    "trade-table"
  );

  table.innerHTML = "";

  if (trades.length === 0) {
    table.innerHTML = `
      <tr>
        <td colspan="6">
          No operations were generated.
        </td>
      </tr>
    `;

    return;
  }

  for (const trade of trades) {
    const row = document.createElement("tr");

    row.innerHTML = `
      <td class="${trade.operation.toLowerCase()}">
        ${trade.operation}
      </td>

      <td>${trade.signal_date}</td>
      <td>${trade.execution_date}</td>

      <td>
        ${trade.execution_price.toFixed(4)}
      </td>

      <td>
        ${trade.shares.toFixed(6)}
      </td>

      <td>
        ${formatEGP(trade.amount_egp)}
      </td>
    `;

    table.appendChild(row);
  }
}


async function loadAsset(symbol) {
  try {
    setStatus(`Loading ${symbol}…`);
    assetSelect.disabled = true;

    const safeSymbol = encodeURIComponent(symbol);

    const [indicatorsResponse, backtestResponse] =
      await Promise.all([
        fetch(
          `${API_BASE}/indicators/${safeSymbol}`
        ),

        fetch(
          `${API_BASE}/backtest/${safeSymbol}`
        ),
      ]);

    if (
      !indicatorsResponse.ok ||
      !backtestResponse.ok
    ) {
      throw new Error(
        `Could not load ${symbol}.`
      );
    }

    const indicators =
      await indicatorsResponse.json();

    const backtest =
      await backtestResponse.json();

    displayMetrics(backtest);

    renderPriceChart(
      indicators,
      backtest.trades
    );

    renderEquityChart(backtest);
    renderDrawdownChart(backtest);
    renderTrades(backtest.trades);

    assetDescription.textContent =
      `${symbol} · SMA 9/20 · ` +
      `Starting capital: 1,000 EGP`;

    setStatus(`${symbol}: ready`, "ok");
  } catch (error) {
    console.error(error);

    setStatus(
      `${symbol}: failed to load`,
      "error"
    );
  } finally {
    assetSelect.disabled = false;
  }
}


async function loadUniverse() {
  try {
    setStatus("Loading assets…");
    assetSelect.disabled = true;

    const [healthResponse, universeResponse] =
      await Promise.all([
        fetch(`${API_BASE}/health`),
        fetch(`${API_BASE}/universe`),
      ]);

    if (
      !healthResponse.ok ||
      !universeResponse.ok
    ) {
      throw new Error(
        "Could not connect to the backend."
      );
    }

    const health = await healthResponse.json();
    const universe = await universeResponse.json();

    if (health.status !== "ok") {
      throw new Error(
        "Backend health check failed."
      );
    }

    if (
      !universe.assets ||
      universe.assets.length === 0
    ) {
      throw new Error(
        "No CSV assets were found."
      );
    }

    assetSelect.innerHTML = "";

    for (const symbol of universe.assets) {
      const option =
        document.createElement("option");

      option.value = symbol;
      option.textContent = symbol;

      assetSelect.appendChild(option);
    }

    const defaultAsset =
      universe.assets.includes("SAUD")
        ? "SAUD"
        : universe.assets[0];

    assetSelect.value = defaultAsset;
    assetSelect.disabled = false;

    await loadAsset(defaultAsset);
  } catch (error) {
    console.error(error);

    setStatus(
      "Assets failed to load",
      "error"
    );

    assetSelect.innerHTML = `
      <option value="">
        No assets available
      </option>
    `;
  }
}


assetSelect.addEventListener(
  "change",
  async (event) => {
    const selectedAsset = event.target.value;

    if (selectedAsset) {
      await loadAsset(selectedAsset);
    }
  }
);


loadUniverse();