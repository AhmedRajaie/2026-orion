// Dashboard frontend v2

const API = "http://localhost:8000";

let priceChart;
let strategyChart;
let comparisonChart;
let trendChart;
let signalChart;
let scoreChart;
let currentSymbol = "";
let chatHistory = [];

// ============================
// API HELPER
// ============================

async function apiGet(path) {
    const response = await fetch(`${API}${path}`);

    if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
    }

    return response.json();
}


// ============================
// HEALTH CHECK
// ============================

async function checkHealth() {
    try {
        const data = await apiGet("/health");

        document.getElementById("status").textContent =
            "backend: " + (data.status || "ok");

    } catch (error) {

        document.getElementById("status").textContent =
            "backend not reachable — start uvicorn";
    }
}


// ============================
// LOAD STOCK UNIVERSE
// ============================

async function loadUniverse() {

    const select = document.getElementById("symbolSelect");
    const compareSelect = document.getElementById("compareSelect");
    const strategySymbolSelect = document.getElementById("strategySymbolSelect");

    const universe = await apiGet("/universe");

    const options = universe
        .map(
            symbol =>
                `<option value="${symbol}">${symbol}</option>`
        )
        .join("");

    select.innerHTML = options;

    if (compareSelect) {
        compareSelect.innerHTML = options;
        if (universe.length) {
            compareSelect.value = universe[0];
        }
    }

    if (strategySymbolSelect) {
        strategySymbolSelect.innerHTML = '<option value="ALL">ALL</option>' + options;
        if (universe.length) {
            strategySymbolSelect.value = "ALL";
        }
        strategySymbolSelect.onchange = async () => {
            await renderStrategyComparison();
        };
    }

    currentSymbol = universe[0] || "";

    select.value = currentSymbol;

    select.onchange = async () => {

        currentSymbol = select.value;

        await renderChart(currentSymbol);

        await loadComparison();
    };

    return currentSymbol;
}


// ============================
// KPI CALCULATIONS
// ============================

function calculateKpis(closes, sma9, sma20) {

    if (!closes || closes.length < 2) {
        return;
    }

    const latest = closes.at(-1);

    const previous = closes.at(-2);


    // Daily change

    const dailyChange =
        ((latest - previous) / previous) * 100;


    // Total return

    const totalReturn =
        ((latest - closes[0]) / closes[0]) * 100;


    // Maximum drawdown

    let runningMax = closes[0];

    let maxDrawdown = 0;


    for (const close of closes) {

        runningMax = Math.max(
            runningMax,
            close
        );

        const drawdown =
            ((close - runningMax) / runningMax) * 100;

        maxDrawdown =
            Math.min(maxDrawdown, drawdown);
    }


    // SMA values

    const valid9 =
        sma9.filter(x => x != null);

    const valid20 =
        sma20.filter(x => x != null);


    const latestSma9 =
        valid9.at(-1);

    const latestSma20 =
        valid20.at(-1);


    // ============================
    // TREND
    // ============================

    const trend =
        latestSma9 != null &&
        latestSma20 != null &&
        latestSma9 > latestSma20

            ? "Bullish 📈"

            : "Bearish 📉";


    // ============================
    // SIGNAL
    // ============================

    let signal = "Hold";

    const prev9 = sma9.at(-2);

    const prev20 = sma20.at(-2);


    if (
        prev9 != null &&
        prev20 != null &&
        latestSma9 != null &&
        latestSma20 != null
    ) {

        if (
            prev9 <= prev20 &&
            latestSma9 > latestSma20
        ) {

            signal = "BUY 🟢";

        } else if (
            prev9 >= prev20 &&
            latestSma9 < latestSma20
        ) {

            signal = "SELL 🔴";
        }
    }


    // ============================
    // UPDATE UI
    // ============================

    document.getElementById("kpiLatest").textContent =
        latest.toFixed(2);

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

    document.getElementById("kpiTrend").textContent =
        trend;

    document.getElementById("kpiSignal").textContent =
        signal;
}


// ============================
// PRICE CHART
// ============================

async function renderChart(symbol) {

    try {

        const price =
            await apiGet(`/prices/${symbol}`);


        const indicators =
            await apiGet(`/indicators/${symbol}`);


        calculateKpis(
            price.close,
            indicators.sma9,
            indicators.sma20
        );


        const data = {

            labels: price.dates,

            datasets: [

                {
                    label: `${symbol} Close`,

                    data: price.close,

                    tension: 0,

                    fill: false
                },

                {
                    label: "SMA (9)",

                    data: indicators.sma9,

                    pointRadius: 0,

                    tension: 0,

                    fill: false
                },

                {
                    label: "SMA (20)",

                    data: indicators.sma20,

                    pointRadius: 0,

                    tension: 0,

                    fill: false
                }

            ]
        };


        if (priceChart) {

            priceChart.destroy();
        }


        priceChart =
            new Chart(
                document.getElementById("priceChart"),
                {

                    type: "line",

                    data: data,

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
                                    color:
                                        "rgba(255,255,255,0.08)"
                                }
                            },

                            y: {

                                ticks: {
                                    color: "#cbd5e1"
                                },

                                grid: {
                                    color:
                                        "rgba(255,255,255,0.08)"
                                }
                            }
                        }
                    }
                }
            );

    } catch (error) {

        console.error(
            "Chart error:",
            error
        );
    }
}


// ============================
// STRATEGY COMPARISON
// ============================

async function renderStrategyComparison() {

    try {

        const strategySymbolSelect =
            document.getElementById(
                "strategySymbolSelect"
            );

        const strategySymbol =
            strategySymbolSelect?.value || "";

        const comparison =
            await apiGet(
                `/strategy-comparison${
                    strategySymbol
                        ? `?symbol=${encodeURIComponent(strategySymbol)}`
                        : ""
                }`
            );


        const summary =
            document.getElementById(
                "strategySummary"
            );


        summary.innerHTML = "";


        for (
            const strategy
            of comparison.strategies || []
        ) {

            const card =
                document.createElement("div");

            card.className =
                "strategy-card";


            card.innerHTML = `

                <strong>
                    ${strategy.name}
                </strong>

                <div>
                    Final portfolio:
                    ${Number(
                        strategy.final_portfolio
                    ).toFixed(2)}
                </div>

                <div>
                    Return:
                    ${Number(
                        strategy.total_return_pct
                    ).toFixed(2)}%
                </div>

                <div>
                    Drawdown:
                    ${Number(
                        strategy.max_drawdown_pct
                    ).toFixed(2)}%
                </div>

                <div>
                    Trades:
                    ${strategy.num_trades}
                </div>

                <div>
                    Beat benchmark:
                    ${
                        strategy.beat_benchmark
                            ? "Yes"
                            : "No"
                    }
                </div>
            `;


            summary.appendChild(card);
        }


        const datasets =
            (comparison.strategies || [])
                .map(strategy => ({

                    label: strategy.name,

                    data: strategy.portfolio,

                    tension: 0,

                    fill: false
                }));


        if (
            comparison.strategies &&
            comparison.strategies.length
        ) {

            datasets.push({

                label:
                    comparison.benchmark_name,

                data:
                    comparison.strategies[0]
                        .benchmark,

                borderDash: [6, 4],

                tension: 0,

                fill: false
            });
        }


        if (strategyChart) {

            strategyChart.destroy();
        }


        strategyChart =
            new Chart(
                document.getElementById(
                    "strategyChart"
                ),
                {

                    type: "line",

                    data: {

                        labels:
                            comparison.dates,

                        datasets
                    },

                    options: {

                        responsive: true,

                        plugins: {

                            legend: {

                                labels: {
                                    color:
                                        "#e6edf3"
                                }
                            }
                        },

                        scales: {

                            x: {

                                ticks: {
                                    color:
                                        "#cbd5e1"
                                },

                                grid: {
                                    color:
                                        "rgba(255,255,255,0.08)"
                                }
                            },

                            y: {

                                ticks: {
                                    color:
                                        "#cbd5e1"
                                },

                                grid: {
                                    color:
                                        "rgba(255,255,255,0.08)"
                                }
                            }
                        }
                    }
                }
            );

    } catch (error) {

        console.error(
            "Strategy comparison error:",
            error
        );
    }
}


// ============================
// MARKET OVERVIEW
// ============================

async function loadMarketOverview() {

    try {

        const result =
            await apiGet(
                "/market-overview"
            );

        const rows =
            Array.isArray(result?.stocks)
                ? result.stocks
                : [];

        const container =
            document.getElementById(
                "marketTableBody"
            );

        if (!container) {
            return;
        }

        container.innerHTML =
            rows
                .map(
                    (stock, index) => `

                    <tr>

                        <td>
                            ${index + 1}
                        </td>

                        <td>
                            ${stock.symbol}
                        </td>

                        <td>
                            ${Number(
                                stock.total_return_pct ?? 0
                            ).toFixed(2)}%
                        </td>

                        <td>
                            ${Number(
                                stock.max_drawdown_pct ?? 0
                            ).toFixed(2)}%
                        </td>

                        <td>
                            ${Number(
                                stock.daily_change_pct ?? 0
                            ).toFixed(2)}%
                        </td>

                        <td>
                            ${stock.trend ?? "N/A"}
                        </td>

                        <td>
                            ${stock.signal ?? "Hold"}
                        </td>

                        <td>
                            ${Number(
                                stock.score ?? 0
                            ).toFixed(2)}
                        </td>

                    </tr>
                `
                )
                .join("");

    } catch (error) {

        console.warn(
            "Market overview unavailable:",
            error
        );
    }
}


// ============================
// RENDER MARKET ANALYTICS CHARTS
// ============================

async function renderMarketAnalytics() {
    try {
        const result = await apiGet("/market-overview");
        const rows = Array.isArray(result?.stocks) ? result.stocks : [];

        if (rows.length === 0) return;

        // Calculate trend distribution
        const trendCounts = { "Up": 0, "Neutral": 0, "Down": 0 };
        rows.forEach(stock => {
            const trend = stock.trend || "Neutral";
            if (trendCounts.hasOwnProperty(trend)) {
                trendCounts[trend]++;
            }
        });

        // Calculate signal distribution
        const signalCounts = { "Buy": 0, "Hold": 0, "Sell": 0 };
        rows.forEach(stock => {
            const signal = stock.signal || "Hold";
            if (signalCounts.hasOwnProperty(signal)) {
                signalCounts[signal]++;
            }
        });

        // Calculate score distribution (Top 30%, Middle 40%, Bottom 30%)
        const scores = rows.map(s => Number(s.score ?? 0)).sort((a, b) => b - a);
        const topThreshold = scores[Math.floor(scores.length * 0.3)];
        const bottomThreshold = scores[Math.floor(scores.length * 0.7)];
        
        const scoreDistribution = { "Top": 0, "Middle": 0, "Low": 0 };
        rows.forEach(stock => {
            const score = Number(stock.score ?? 0);
            if (score >= topThreshold) scoreDistribution["Top"]++;
            else if (score >= bottomThreshold) scoreDistribution["Middle"]++;
            else scoreDistribution["Low"]++;
        });

        // Render Trend Chart
        renderTrendChart(trendCounts);

        // Render Signal Chart
        renderSignalChart(signalCounts);

        // Render Score Chart
        renderScoreChart(scoreDistribution);

    } catch (error) {
        console.warn("Market analytics unavailable:", error);
    }
}

function renderTrendChart(trendCounts) {
    const ctx = document.getElementById("trendChart");
    if (!ctx) return;

    if (trendChart) {
        trendChart.destroy();
    }

    trendChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: ["📈 Up", "➡️ Neutral", "📉 Down"],
            datasets: [{
                data: [trendCounts["Up"], trendCounts["Neutral"], trendCounts["Down"]],
                backgroundColor: [
                    "rgba(74, 222, 128, 0.7)",
                    "rgba(148, 163, 184, 0.7)",
                    "rgba(248, 113, 113, 0.7)"
                ],
                borderColor: ["#4ade80", "#94a3b8", "#f87171"],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: "bottom",
                    labels: {
                        color: "#cbd5e1",
                        font: { size: 12, weight: 600 },
                        padding: 12
                    }
                }
            }
        }
    });
}

function renderSignalChart(signalCounts) {
    const ctx = document.getElementById("signalChart");
    if (!ctx) return;

    if (signalChart) {
        signalChart.destroy();
    }

    signalChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: ["🟢 Buy", "🟡 Hold", "🔴 Sell"],
            datasets: [{
                data: [signalCounts["Buy"], signalCounts["Hold"], signalCounts["Sell"]],
                backgroundColor: [
                    "rgba(34, 197, 94, 0.7)",
                    "rgba(251, 146, 60, 0.7)",
                    "rgba(244, 114, 182, 0.7)"
                ],
                borderColor: ["#22c55e", "#fb923c", "#f472b6"],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: "bottom",
                    labels: {
                        color: "#cbd5e1",
                        font: { size: 12, weight: 600 },
                        padding: 12
                    }
                }
            }
        }
    });
}

function renderScoreChart(scoreDistribution) {
    const ctx = document.getElementById("scoreChart");
    if (!ctx) return;

    if (scoreChart) {
        scoreChart.destroy();
    }

    scoreChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: ["⭐ Top Performers", "📊 Mid Range", "📉 Laggards"],
            datasets: [{
                data: [scoreDistribution["Top"], scoreDistribution["Middle"], scoreDistribution["Low"]],
                backgroundColor: [
                    "rgba(168, 85, 247, 0.7)",
                    "rgba(59, 130, 246, 0.7)",
                    "rgba(107, 114, 128, 0.7)"
                ],
                borderColor: ["#a855f7", "#3b82f6", "#6b7280"],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: "bottom",
                    labels: {
                        color: "#cbd5e1",
                        font: { size: 12, weight: 600 },
                        padding: 12
                    }
                }
            }
        }
    });
}


// ============================
// STOCK COMPARISON
// ============================

async function loadComparison() {

    const comparisonSelect =
        document.getElementById(
            "compareSelect"
        );


    if (!comparisonSelect) {

        return;
    }


    const symbols =
        Array.from(
            comparisonSelect.selectedOptions
        )
        .map(
            option => option.value
        );


    if (
        !symbols.length &&
        currentSymbol
    ) {

        symbols.push(
            currentSymbol
        );
    }


    try {

        const data =
            await apiGet(
                `/compare?symbols=${
                    encodeURIComponent(
                        symbols.join(",")
                    )
                }`
            );


        const cardsContainer =
            document.getElementById(
                "comparisonCards"
            );

        if (
            cardsContainer &&
            Array.isArray(data.stocks)
        ) {
            cardsContainer.innerHTML =
                data.stocks
                    .map(
                        stock => `
                            <div class="strategy-card">
                                <strong>${stock.symbol}</strong>
                                <div>Latest: ${Number(stock.latest_price ?? 0).toFixed(2)}</div>
                                <div>Return: ${Number(stock.total_return_pct ?? 0).toFixed(2)}%</div>
                                <div>Drawdown: ${Number(stock.max_drawdown_pct ?? 0).toFixed(2)}%</div>
                                <div>Trend: ${stock.trend ?? "N/A"}</div>
                                <div>Signal: ${stock.signal ?? "Hold"}</div>
                            </div>
                        `
                    )
                    .join("");
        }


        const chartElement =
            document.getElementById(
                "comparisonChart"
            );


        if (
            !data ||
            !chartElement
        ) {

            return;
        }


        const datasets =
            (data.series || [])
                .map(item => ({

                    label:
                        item.symbol,

                    data:
                        item.values,

                    tension: 0,

                    fill: false
                }));


        if (comparisonChart) {

            comparisonChart.destroy();
        }


        comparisonChart =
            new Chart(
                chartElement,
                {

                    type: "line",

                    data: {

                        labels:
                            data.dates || [],

                        datasets
                    },

                    options: {

                        responsive: true,

                        plugins: {

                            legend: {

                                labels: {
                                    color:
                                        "#e6edf3"
                                }
                            }
                        },

                        scales: {

                            x: {

                                ticks: {
                                    color:
                                        "#cbd5e1"
                                },

                                grid: {
                                    color:
                                        "rgba(255,255,255,0.08)"
                                }
                            },

                            y: {

                                ticks: {
                                    color:
                                        "#cbd5e1"
                                },

                                grid: {
                                    color:
                                        "rgba(255,255,255,0.08)"
                                }
                            }
                        }
                    }
                }
            );

    } catch (error) {

        console.warn(
            "Comparison endpoint unavailable:",
            error
        );
    }
}


// ============================
// CHATBOT
// ============================

async function askChatQuestion(question) {

    const response =
        await fetch(
            `${API}/chat`,
            {

                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({

                    question,

                    symbol:
                        currentSymbol,

                    messages:
                        chatHistory.slice(0, -1)
                })
            }
        );


    if (!response.ok) {

        const error =
            await response
                .json()
                .catch(() => null);


        throw new Error(
            error?.detail ||
            response.statusText
        );
    }


    const json =
        await response.json();


    return json;
}


function addChatHistory(
    role,
    content
) {

    chatHistory.push({

        role,

        content,

        symbol:
            currentSymbol
    });
}


function setChatResponse(
    message
) {

    const element =
        document.getElementById(
            "chatResponse"
        );


    if (element) {

        element.textContent =
            message;
    }
}


async function runInvestmentDebate(headlines) {

    const response = await fetch(
        `${API}/investment-debate`,
        {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: currentSymbol, headlines })
        }
    );

    if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail || response.statusText);
    }

    return response.json();
}


function setDebateResponse(message) {

    const element = document.getElementById("debateResponse");

    if (element) {
        element.textContent = message;
    }
}


// ============================
// INITIALIZATION
// ============================

async function init() {

    await checkHealth();


    try {

        await loadUniverse();

        await renderChart(
            currentSymbol
        );

        await renderStrategyComparison();

        await loadMarketOverview();

        await renderMarketAnalytics();

        await loadComparison();

    } catch (error) {

        console.error(
            "Dashboard initialization error:",
            error
        );
    }


    // ============================
    // CHAT
    // ============================

    const chatInput =
        document.getElementById(
            "chatInput"
        );


    const chatButton =
        document.getElementById(
            "chatSendButton"
        );


    if (
        chatButton &&
        chatInput
    ) {

        chatButton.onclick =
            async () => {

                const question =
                    chatInput.value.trim();


                if (!question) {

                    setChatResponse(
                        "Please type a question first."
                    );

                    return;
                }


                setChatResponse(
                    "Thinking..."
                );


                try {

                    addChatHistory(
                        "user",
                        question
                    );


                    const result =
                        await askChatQuestion(
                            question
                        );

                    const answer = result.answer;


                    addChatHistory(
                        "assistant",
                        answer
                    );


                    setChatResponse(
                        `${answer}\n\nPowered by: ${result.provider}`
                    );

                } catch (error) {

                    setChatResponse(
                        `Error: ${error.message}`
                    );
                }
            };


        chatInput.addEventListener(
            "keydown",
            event => {

                if (
                    event.key === "Enter" &&
                    !event.shiftKey
                ) {

                    event.preventDefault();

                    chatButton.click();
                }
            }
        );
    }


    const debateInput = document.getElementById("debateHeadlines");
    const debateButton = document.getElementById("debateSendButton");

    if (debateButton && debateInput) {
        debateButton.onclick = async () => {
            const headlines = debateInput.value
                .split("\n")
                .map(headline => headline.trim())
                .filter(Boolean);

            if (!headlines.length) {
                setDebateResponse("Please add at least one headline first.");
                return;
            }

            setDebateResponse("Analysts are reviewing the headlines...");
            debateButton.disabled = true;

            try {
                const result = await runInvestmentDebate(headlines);
                setDebateResponse(
                    `BULL CASE\n${result.bull_case}\n\n` +
                    `BEAR CASE\n${result.bear_case}\n\n` +
                    `COMMITTEE VERDICT\n${result.verdict}\n\n` +
                    `Provider: ${result.provider}`
                );
            } catch (error) {
                setDebateResponse(`Error: ${error.message}`);
            } finally {
                debateButton.disabled = false;
            }
        };
    }


    // ============================
    // REFRESH
    // ============================

    const refreshButton =
        document.getElementById(
            "refreshDashboard"
        );

    const compareButton =
        document.getElementById(
            "compareButton"
        );


    if (refreshButton) {

        refreshButton.onclick =
            async () => {

                await checkHealth();

                await renderChart(
                    currentSymbol
                );

                await renderStrategyComparison();

                await loadMarketOverview();

                await renderMarketAnalytics();

                await loadComparison();
            };
    }

    if (compareButton) {
        compareButton.onclick =
            async () => {
                await loadComparison();
            };
    }
}


init();
