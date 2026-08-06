const API = "http://localhost:8000";

let equityChart = null;
let chart = null;
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

    select.innerHTML = "";

    symbols.forEach(symbol => {

        const option = document.createElement("option");

        option.value = symbol;

        option.textContent = symbol;

        select.appendChild(option);

    });

    loadPrice(symbols[0]);

    select.addEventListener("change", () => {

        loadPrice(select.value);

    });

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


// =========================

checkHealth();

loadUniverse();
