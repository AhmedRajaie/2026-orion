const API = "http://127.0.0.1:8000";


// ============================================================
// CURRENT UNIVERSE
// ============================================================

let currentUniverse = "small";


// ============================================================
// CHART REFERENCES
// ============================================================

let priceChart = null;

let equityChart = null;

let strategyChart = null;

let drawdownChart = null;


// ============================================================
// HELPER
// ============================================================

function universeURL(endpoint) {

    return (
        API +
        endpoint +
        "?universe=" +
        encodeURIComponent(
            currentUniverse
        )
    );
}


// ============================================================
// CHECK BACKEND
// ============================================================

async function checkHealth() {

    try {

        const response =
            await fetch(
                API + "/health"
            );


        if (!response.ok) {

            throw new Error(
                "Backend returned " +
                response.status
            );

        }


        const data =
            await response.json();


        document.getElementById(
            "status"
        ).textContent =
            "🟢 Backend : " +
            data.status;

    }

    catch (error) {

        document.getElementById(
            "status"
        ).textContent =
            "🔴 Backend not reachable";

        console.error(
            "Health error:",
            error
        );
    }
}


// ============================================================
// LOAD UNIVERSE
// ============================================================

async function loadUniverse() {

    try {

        const response =
            await fetch(
                universeURL(
                    "/universe"
                )
            );


        if (!response.ok) {

            throw new Error(
                "Universe request failed: " +
                response.status
            );

        }


        const data =
            await response.json();


        const select =
            document.getElementById(
                "stockSelect"
            );


        select.innerHTML = "";


        data.symbols.forEach(
            symbol => {

                const option =
                    document.createElement(
                        "option"
                    );

                option.value =
                    symbol;

                option.textContent =
                    symbol;

                select.appendChild(
                    option
                );

            }
        );


        if (
            data.symbols.length > 0
        ) {

            await loadStock(
                data.symbols[0]
            );

        }

    }

    catch (error) {

        console.error(
            "Universe error:",
            error
        );

        document.getElementById(
            "stockSelect"
        ).innerHTML =
            "<option>Error loading stocks</option>";
    }
}


// ============================================================
// LOAD STOCK
// ============================================================

async function loadStock(symbol) {

    try {

        const response =
            await fetch(
                universeURL(
                    "/prices/" +
                    encodeURIComponent(
                        symbol
                    )
                )
            );


        if (!response.ok) {

            throw new Error(
                "Stock request failed: " +
                response.status
            );

        }


        const data =
            await response.json();


        // ----------------------------------------------------
        // SYMBOL
        // ----------------------------------------------------

        document.getElementById(
            "symbol"
        ).textContent =
            data.symbol;


        // ----------------------------------------------------
        // CURRENT PRICE
        // ----------------------------------------------------

        const lastPrice =
            data.price[
                data.price.length - 1
            ];


        document.getElementById(
            "currentPrice"
        ).textContent =
            Number(lastPrice).toFixed(2) +
            " EGP";


        // ----------------------------------------------------
        // PRICE CHART
        // ----------------------------------------------------

        createPriceChart(
            data
        );

    }

    catch (error) {

        console.error(
            "Stock loading error:",
            error
        );

        document.getElementById(
            "symbol"
        ).textContent =
            "-";

        document.getElementById(
            "currentPrice"
        ).textContent =
            "-";
    }
}


// ============================================================
// PRICE CHART
// ============================================================

function createPriceChart(data) {

    const canvas =
        document.getElementById(
            "priceChart"
        );


    if (priceChart !== null) {

        priceChart.destroy();

    }


    priceChart =
        new Chart(
            canvas,
            {

                type: "line",

                data: {

                    labels:
                        data.dates,

                    datasets: [

                        {

                            label:
                                "Close Price",

                            data:
                                data.price,

                            pointRadius:
                                0,

                            borderWidth:
                                2,

                            tension:
                                0.2

                        },

                        {

                            label:
                                "SMA 9",

                            data:
                                data.ma9,

                            pointRadius:
                                0,

                            borderWidth:
                                1.5,

                            tension:
                                0.2

                        },

                        {

                            label:
                                "SMA 20",

                            data:
                                data.ma20,

                            pointRadius:
                                0,

                            borderWidth:
                                1.5,

                            tension:
                                0.2

                        }

                    ]

                },

                options: {

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,

                    interaction: {

                        mode:
                            "index",

                        intersect:
                            false

                    },

                    plugins: {

                        legend: {

                            display:
                                true

                        }

                    },

                    scales: {

                        x: {

                            ticks: {

                                maxTicksLimit:
                                    12

                            }

                        }

                    }

                }

            }
        );
}


// ============================================================
// LOAD EQUITY CURVE
// ============================================================

async function loadEquityCurve() {

    try {

        const response =
            await fetch(
                universeURL(
                    "/backtest"
                )
            );


        if (!response.ok) {

            throw new Error(
                "Backtest request failed: " +
                response.status
            );

        }


        const data =
            await response.json();


        createEquityChart(
            data
        );

    }

    catch (error) {

        console.error(
            "Equity error:",
            error
        );
    }
}


// ============================================================
// EQUITY CHART
// ============================================================

function createEquityChart(data) {

    const canvas =
        document.getElementById(
            "equityChart"
        );


    if (equityChart !== null) {

        equityChart.destroy();

    }


    equityChart =
        new Chart(
            canvas,
            {

                type: "line",

                data: {

                    labels:
                        data.dates,

                    datasets: [

                        {

                            label:
                                "SMA 9/20 Strategy",

                            data:
                                data.portfolio,

                            pointRadius:
                                0,

                            borderWidth:
                                2,

                            tension:
                                0.15

                        },

                        {

                            label:
                                "Benchmark",

                            data:
                                data.benchmark,

                            pointRadius:
                                0,

                            borderWidth:
                                2,

                            borderDash:
                                [6, 5],

                            tension:
                                0.15

                        }

                    ]

                },

                options: {

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,

                    interaction: {

                        mode:
                            "index",

                        intersect:
                            false

                    },

                    plugins: {

                        title: {

                            display:
                                true,

                            text:
                                "Strategy vs Benchmark"
                        }

                    },

                    scales: {

                        x: {

                            ticks: {

                                maxTicksLimit:
                                    12

                            }

                        }

                    }

                }

            }
        );
}


// ============================================================
// LOAD METRICS
// ============================================================

async function loadMetrics() {

    try {

        const response =
            await fetch(
                universeURL(
                    "/metrics"
                )
            );


        if (!response.ok) {

            throw new Error(
                "Metrics request failed: " +
                response.status
            );

        }


        const data =
            await response.json();


        document.getElementById(
            "totalReturn"
        ).textContent =
            (
                Number(
                    data.total_return
                ) * 100
            ).toFixed(2) +
            "%";


        document.getElementById(
            "sharpe"
        ).textContent =
            Number(
                data.sharpe
            ).toFixed(3);


        document.getElementById(
            "maxDrawdown"
        ).textContent =
            (
                Number(
                    data.max_drawdown
                ) * 100
            ).toFixed(2) +
            "%";

    }

    catch (error) {

        console.error(
            "Metrics error:",
            error
        );
    }
}


// ============================================================
// LOAD STRATEGY PERFORMANCE
// ============================================================

async function loadStrategyPerformance() {

    try {

        const response =
            await fetch(
                universeURL(
                    "/strategy-performance"
                )
            );


        if (!response.ok) {

            throw new Error(
                "Strategy performance failed: " +
                response.status
            );

        }


        const data =
            await response.json();


        // ====================================================
        // BASE
        // ====================================================

        document.getElementById(
            "baseFinal"
        ).textContent =
            Number(
                data.base_strategy.final_value
            ).toFixed(2) +
            " EGP";


        document.getElementById(
            "baseReturn"
        ).textContent =
            Number(
                data.base_strategy.total_return
            ).toFixed(2) +
            "%";


        document.getElementById(
            "baseDrawdown"
        ).textContent =
            Number(
                data.base_strategy.max_drawdown
            ).toFixed(2) +
            "%";


        document.getElementById(
            "baseSharpe"
        ).textContent =
            Number(
                data.base_strategy.sharpe
            ).toFixed(3);


        document.getElementById(
            "baseTrades"
        ).textContent =
            data.base_strategy.total_trades;


        // ====================================================
        // NEW
        // ====================================================

        document.getElementById(
            "newFinal"
        ).textContent =
            Number(
                data.new_strategy.final_value
            ).toFixed(2) +
            " EGP";


        document.getElementById(
            "newReturn"
        ).textContent =
            Number(
                data.new_strategy.total_return
            ).toFixed(2) +
            "%";


        document.getElementById(
            "newDrawdown"
        ).textContent =
            Number(
                data.new_strategy.max_drawdown
            ).toFixed(2) +
            "%";


        document.getElementById(
            "newSharpe"
        ).textContent =
            Number(
                data.new_strategy.sharpe
            ).toFixed(3);


        document.getElementById(
            "newTrades"
        ).textContent =
            data.new_strategy.total_trades;


        // ====================================================
        // WINNER
        // ====================================================

        document.getElementById(
            "winner"
        ).textContent =
            "🏆 Better strategy: " +
            data.winner;


        // ====================================================
        // STRATEGY CURVES
        // ====================================================

        createStrategyChart(
            data
        );


        // ====================================================
        // DRAWDOWN
        // ====================================================

        createDrawdownChart(
            data
        );

    }

    catch (error) {

        console.error(
            "Strategy performance error:",
            error
        );

        document.getElementById(
            "winner"
        ).textContent =
            "⚠️ Could not load strategy performance";
    }
}


// ============================================================
// STRATEGY CURVE CHART
// ============================================================

function createStrategyChart(data) {

    const canvas =
        document.getElementById(
            "strategyChart"
        );


    if (strategyChart !== null) {

        strategyChart.destroy();

    }


    strategyChart =
        new Chart(
            canvas,
            {

                type: "line",

                data: {

                    labels:
                        data.dates,

                    datasets: [

                        {

                            label:
                                "Base — SMA 9/20",

                            data:
                                data.base_curve,

                            pointRadius:
                                0,

                            borderWidth:
                                2,

                            tension:
                                0.15

                        },

                        {

                            label:
                                "New — SMA20 + Momentum",

                            data:
                                data.new_curve,

                            pointRadius:
                                0,

                            borderWidth:
                                2,

                            tension:
                                0.15

                        }

                    ]

                },

                options: {

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,

                    interaction: {

                        mode:
                            "index",

                        intersect:
                            false

                    },

                    plugins: {

                        title: {

                            display:
                                true,

                            text:
                                "Strategy Performance Over Time"

                        }

                    },

                    scales: {

                        x: {

                            ticks: {

                                maxTicksLimit:
                                    12

                            }

                        },

                        y: {

                            title: {

                                display:
                                    true,

                                text:
                                    "Portfolio Value (EGP)"

                            }

                        }

                    }

                }

            }
        );
}


// ============================================================
// DRAWDOWN CHART
// ============================================================

function createDrawdownChart(data) {

    const canvas =
        document.getElementById(
            "drawdownChart"
        );


    if (drawdownChart !== null) {

        drawdownChart.destroy();

    }


    drawdownChart =
        new Chart(
            canvas,
            {

                type: "line",

                data: {

                    labels:
                        data.dates,

                    datasets: [

                        {

                            label:
                                "Base — SMA 9/20",

                            data:
                                data.base_drawdown,

                            pointRadius:
                                0,

                            borderWidth:
                                2,

                            tension:
                                0.15

                        },

                        {

                            label:
                                "New — SMA20 + Momentum",

                            data:
                                data.new_drawdown,

                            pointRadius:
                                0,

                            borderWidth:
                                2,

                            tension:
                                0.15

                        }

                    ]

                },

                options: {

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,

                    interaction: {

                        mode:
                            "index",

                        intersect:
                            false

                    },

                    plugins: {

                        title: {

                            display:
                                true,

                            text:
                                "Drawdown Over Time"

                        }

                    },

                    scales: {

                        x: {

                            ticks: {

                                maxTicksLimit:
                                    12

                            }

                        },

                        y: {

                            title: {

                                display:
                                    true,

                                text:
                                    "Drawdown (%)"

                            },

                            ticks: {

                                callback:
                                    function(value) {

                                        return value + "%";

                                    }

                            }

                        }

                    }

                }

            }
        );
}


// ============================================================
// REFRESH WHOLE DASHBOARD
// ============================================================

async function refreshDashboard() {

    console.log(
        "Loading universe:",
        currentUniverse
    );


    // Load stocks first

    await loadUniverse();


    // Load everything else

    await Promise.all([

        loadEquityCurve(),

        loadMetrics(),

        loadStrategyPerformance()

    ]);

}


// ============================================================
// UNIVERSE BUTTONS
// ============================================================

document
    .getElementById(
        "smallUniverse"
    )
    .addEventListener(
        "click",
        async function() {

            if (
                currentUniverse === "small"
            ) {

                return;

            }


            currentUniverse =
                "small";


            document
                .getElementById(
                    "smallUniverse"
                )
                .classList
                .add("active");


            document
                .getElementById(
                    "fullUniverse"
                )
                .classList
                .remove("active");


            await refreshDashboard();

        }
    );


document
    .getElementById(
        "fullUniverse"
    )
    .addEventListener(
        "click",
        async function() {

            if (
                currentUniverse === "full"
            ) {

                return;

            }


            currentUniverse =
                "full";


            document
                .getElementById(
                    "fullUniverse"
                )
                .classList
                .add("active");


            document
                .getElementById(
                    "smallUniverse"
                )
                .classList
                .remove("active");


            await refreshDashboard();

        }
    );


// ============================================================
// STOCK DROPDOWN
// ============================================================

document
    .getElementById(
        "stockSelect"
    )
    .addEventListener(
        "change",
        function() {

            loadStock(
                this.value
            );

        }
    );


// ============================================================
// START DASHBOARD
// ============================================================

async function startDashboard() {

    await checkHealth();

    await refreshDashboard();

}


startDashboard();