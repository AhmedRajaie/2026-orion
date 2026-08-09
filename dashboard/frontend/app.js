const API = "http://localhost:8000";

let equityChart = null;
let chart = null;
let universeChart = null;
let strategyChart = null;
let egx30Chart = null;
let drawdownChart = null;
let smaChart = null;
let buySignals = [];
let sellSignals = [];

// =========================
// Health Check
// =========================

async function checkHealth() {
    try {
        const response = await fetch(`${API}/health`);
        const data = await response.json();

        document.getElementById("status").innerHTML =
            "🟢 Backend Online";
    }
    catch {

        document.getElementById("status").innerHTML =
            "🔴 Backend Offline";

    }
}

// =========================
// Load Symbols
// =========================

async function loadUniverse() {

    const response = await fetch(`${API}/universe`);

    const symbols = await response.json();

    const select = document.getElementById("symbolSelect");
    const multiSelect = document.getElementById("symbolMultiSelect");

    select.innerHTML = "";
    multiSelect.innerHTML = "";

    symbols.forEach(symbol => {

        const option = document.createElement("option");

        option.value = symbol;

        option.textContent = symbol;

        select.appendChild(option);

        const multiOption = option.cloneNode(true);
        multiOption.selected = true;
        multiSelect.appendChild(multiOption);

    });

    loadPrice(symbols[0]);

    select.addEventListener("change", () => {

        loadPrice(select.value);

    });

    document.getElementById("applyUniverseFilter").addEventListener("click", loadWeeklyStrategy);
    document.getElementById("selectAllUniverse").addEventListener("click", () => {
        Array.from(multiSelect.options).forEach(option => option.selected = true);
        loadWeeklyStrategy();
    });

    loadWeeklyStrategy();

}

async function loadWeeklyStrategy() {
    const selected = Array.from(document.getElementById("symbolMultiSelect").selectedOptions)
        .map(option => option.value);
    const errorBox = document.getElementById("dashboardError");
    errorBox.textContent = "";

    if (!selected.length) {
        errorBox.textContent = "Select at least one stock.";
        return;
    }

    const query = selected.map(symbol => `symbols=${encodeURIComponent(symbol)}`).join("&");
    const response = await fetch(`${API}/weekly-strategy?${query}`);
    const data = await response.json();

    if (!response.ok || data.error) {
        errorBox.textContent = data.error || "Could not load the weekly strategy.";
        return;
    }

    drawUniverseChart(data);
    drawStrategyChart(data);
    drawSmaChart(data);
    drawEgx30Chart(data);
    drawDrawdownChart(data);
    updateWeeklyReport(data);
}

// =========================
// Load Prices
// =========================

async function loadPrice(symbol) {

    const priceResponse =
        await fetch(`${API}/prices/${symbol}`);

    const priceData =
        await priceResponse.json();

    const indicatorResponse =
        await fetch(`${API}/indicators/${symbol}`);

    const indicatorData =
        await indicatorResponse.json();

    updateCards(priceData);

    await loadBacktest(symbol);

    drawChart(symbol, priceData, indicatorData);

}

// =========================
// Update Cards
// =========================

function updateCards(data) {

    const lastPrice = data.close[data.close.length - 1];

    const highest = Math.max(...data.high);

    const lowest = Math.min(...data.low);

    const avgVolume =
        data.volume.reduce((a, b) => a + b, 0) /
        data.volume.length;

    document.getElementById("lastPrice").innerHTML =
        lastPrice.toFixed(2);

    document.getElementById("highPrice").innerHTML =
        highest.toFixed(2);

    document.getElementById("lowPrice").innerHTML =
        lowest.toFixed(2);

    document.getElementById("avgVolume").innerHTML =
        Math.round(avgVolume).toLocaleString();

}

// =========================
// Draw Chart
// =========================

function drawChart(symbol, priceData, indicatorData) {

    const ctx =
        document.getElementById("priceChart").getContext("2d");

    if(chart)
        chart.destroy();

    chart = new Chart(ctx,{

        type:"line",

        data:{

            labels:priceData.dates,

            datasets:[

                {

                    label:"Close",

                    data:priceData.close,

                    borderColor:"#38bdf8",

                    pointRadius:0,

                    borderWidth:2,

                    tension:.2

                },

                {

                    label:"MA 9",

                    data:indicatorData.ma9,

                    borderColor:"#22c55e",

                    pointRadius:0,

                    borderWidth:2,

                    tension:.2

                },

                {

                    label:"MA 20",

                    data:indicatorData.ma20,

                    borderColor:"#f97316",

                    pointRadius:0,

                    borderWidth:2,

                    tension:.2

                },
                {
                   label: "Buy",

                   data: buySignals,

                   showLine: false,

                   pointRadius: 10,
                   pointHoverRadius: 12,

                   pointStyle: "triangle",

                   rotation: 0,

                   backgroundColor: "#00ff88",

                   borderColor: "#00ff88"

                },

                {
                   label: "Sell",

                   data: sellSignals,

                   showLine: false,

                   pointRadius: 10,
                   pointHoverRadius: 12,

                   pointStyle: "triangle",

                   rotation: 180,

                   backgroundColor: "#ff4444",

                   borderColor: "#ff4444"

                }

            ]

        },

        options:{

            responsive:true,

            maintainAspectRatio:false,

            plugins:{

                legend:{

                    labels:{

                        color:"white"

                    }

                }

            },

            scales:{

                x:{

                    ticks:{

                        color:"white",

                        maxTicksLimit:10

                    },

                    grid:{

                        color:"rgba(255,255,255,.05)"

                    }

                },

                y:{

                    ticks:{

                        color:"white"

                    },

                    grid:{

                        color:"rgba(255,255,255,.05)"

                    }

                }

            }

        }

    });

}

async function loadBacktest(symbol){

    const response = await fetch(`${API}/backtest/${symbol}`);

    const data = await response.json();

    document.getElementById("portfolioValue").textContent =
        data.portfolio.toFixed(2)+" EGP";

    document.getElementById("drawdown").textContent =
        data.drawdown.toFixed(2)+" %";

    document.getElementById("buyCount").textContent =
        data.buy;

    document.getElementById("sellCount").textContent =
        data.sell;

    buySignals = data.buy_points;
    sellSignals = data.sell_points;

    drawEquityChart(data.equity);


}

function drawEquityChart(values){

    const ctx=document.getElementById("equityChart").getContext("2d");

    if(equityChart){

        equityChart.destroy();

    }

    equityChart=new Chart(ctx,{

        type:"line",

        data:{

            labels:values.map((_,i)=>i),

            datasets:[

                {

                    label:"Portfolio",

                    data:values,

                    borderColor:"#00E676",

                    borderWidth:2,

                    fill:true,

                    backgroundColor:"rgba(0,230,118,.15)",

                    tension:.3,

                    pointRadius:0

                }

            ]

        },

        options:{

            responsive:true,

            plugins:{

                legend:{

                    labels:{

                        color:"white"

                    }

                }

            },

            scales:{

                x:{

                    ticks:{color:"#ccc"},

                    grid:{color:"#333"}

                },

                y:{

                    ticks:{color:"#ccc"},

                    grid:{color:"#333"}

                }

            }

        }

    });

}

function chartOptions() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "white" } } },
        scales: {
            x: { ticks: { color: "#ccc", maxTicksLimit: 10 }, grid: { color: "#333" } },
            y: { ticks: { color: "#ccc" }, grid: { color: "#333" } }
        }
    };
}

function drawUniverseChart(data) {
    const ctx = document.getElementById("universeChart").getContext("2d");
    if (universeChart) universeChart.destroy();

    const colors = ["#38bdf8", "#22c55e", "#f97316", "#e879f9", "#facc15", "#fb7185"];
    universeChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: data.dates,
            datasets: data.symbols.map((symbol, index) => ({
                label: symbol,
                data: data.prices[symbol],
                borderColor: colors[index % colors.length],
                pointRadius: 0,
                borderWidth: 1.8,
                tension: .2
            }))
        },
        options: chartOptions()
    });
}

function drawStrategyChart(data) {
    const ctx = document.getElementById("strategyChart").getContext("2d");
    if (strategyChart) strategyChart.destroy();

    strategyChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: data.dates,
            datasets: [
                {
                    label: "Weekly buy/sell strategy",
                    data: data.portfolio,
                    borderColor: "#00E676",
                    backgroundColor: "rgba(0,230,118,.12)",
                    fill: true,
                    pointRadius: 0,
                    borderWidth: 2,
                    tension: .25
                },
                {
                    label: "Equal-weight benchmark",
                    data: data.benchmark,
                    borderColor: "#f97316",
                    pointRadius: 0,
                    borderWidth: 2,
                    borderDash: [6, 4],
                    tension: .2
                },
            ]
        },
        options: chartOptions()
    });
}

function updateWeeklyReport(data) {
    document.getElementById("weeklyReturn").textContent = formatPercent(data.total_return);
    document.getElementById("weeklyDrawdown").textContent = formatPercent(-data.max_drawdown);
    document.getElementById("smaReturn").textContent = formatPercent(data.sma_return);
    document.getElementById("smaDrawdown").textContent = formatPercent(-data.sma_max_drawdown);
    document.getElementById("benchmarkReturn").textContent = formatPercent(data.benchmark_return);
    document.getElementById("egx30Return").textContent = data.egx30_return === null
        ? "Unavailable"
        : formatPercent(data.egx30_return);
}

function formatPercent(value) {
    return `${(value * 100).toFixed(1)}%`;
}

function drawEgx30Chart(data) {
    const ctx = document.getElementById("egx30Chart").getContext("2d");
    if (egx30Chart) egx30Chart.destroy();

    const datasets = [
        {
            label: "SMA 9/20 strategy",
            data: data.sma_portfolio,
            borderColor: "#00E676",
            pointRadius: 0,
            borderWidth: 2,
            tension: .2
        },
        {
            label: "Equal-weight benchmark",
            data: data.sma_benchmark,
            borderColor: "#f97316",
            borderDash: [6, 4],
            pointRadius: 0,
            borderWidth: 2,
            tension: .2
        }
    ];

    if (data.sma_egx30) {
        datasets.push({
            label: "Real EGX30 index",
            data: data.sma_egx30,
            borderColor: "#a78bfa",
            borderDash: [2, 4],
            pointRadius: 0,
            borderWidth: 2,
            tension: .2
        });
    }

    egx30Chart = new Chart(ctx, {
        type: "line",
        data: { labels: data.sma_dates, datasets },
        options: chartOptions()
    });
}

function drawSmaChart(data) {
    const ctx = document.getElementById("smaChart").getContext("2d");
    if (smaChart) smaChart.destroy();

    smaChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: data.sma_dates,
            datasets: [
                {
                    label: "SMA 9/20 strategy",
                    data: data.sma_portfolio,
                    borderColor: "#a78bfa",
                    backgroundColor: "rgba(167,139,250,.12)",
                    fill: true,
                    pointRadius: 0,
                    borderWidth: 2,
                    tension: .2
                },
                {
                    label: "Equal-weight benchmark",
                    data: data.sma_benchmark,
                    borderColor: "#f97316",
                    borderDash: [6, 4],
                    pointRadius: 0,
                    borderWidth: 2,
                    tension: .2
                }
            ]
        },
        options: chartOptions()
    });
}

function drawDrawdownChart(data) {
    const ctx = document.getElementById("drawdownChart").getContext("2d");
    if (drawdownChart) drawdownChart.destroy();

    drawdownChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: data.sma_dates,
            datasets: [{
                label: "Drawdown",
                data: data.sma_drawdown.map(value => -value),
                borderColor: "#fb7185",
                backgroundColor: "rgba(251,113,133,.2)",
                fill: true,
                pointRadius: 0,
                borderWidth: 2,
                tension: .2
            }]
        },
        options: {
            ...chartOptions(),
            scales: {
                ...chartOptions().scales,
                y: {
                    ticks: {
                        color: "#fb7185",
                        callback: value => `${(value * 100).toFixed(1)}%`
                    },
                    grid: { color: "#333" }
                }
            }
        }
    });
}


// =========================

checkHealth();

loadUniverse();
