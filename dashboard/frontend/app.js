// ============================================================
// EGX TRADING DASHBOARD - FRONTEND
// ============================================================

const API = "http://127.0.0.1:8000";


// ============================================================
// CHART INSTANCES
// ============================================================

let priceChart = null;
let strategyChart = null;
let drawdownChart = null;

let lstmLossChart = null;
let lstmPortfolioChart = null;


// ============================================================
// HELPERS
// ============================================================

function setText(id, value) {

    const element =
        document.getElementById(id);

    if (element) {
        element.textContent = value;
    }
}


function formatNumber(value, decimals = 2) {

    if (
        value === null ||
        value === undefined ||
        !Number.isFinite(Number(value))
    ) {
        return "-";
    }

    return Number(value).toFixed(decimals);
}


function formatPercent(value) {

    if (
        value === null ||
        value === undefined ||
        !Number.isFinite(Number(value))
    ) {
        return "-";
    }

    return (
        Number(value) * 100
    ).toFixed(2) + "%";
}


function destroyChart(chart) {

    if (chart) {
        chart.destroy();
    }

    return null;
}


// ============================================================
// BACKEND HEALTH
// ============================================================

async function checkHealth() {

    const status =
        document.getElementById("status");

    try {

        const response =
            await fetch(
                `${API}/health`
            );

        if (!response.ok) {

            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const data =
            await response.json();

        if (data.status === "ok") {

            status.textContent =
                "🟢 Backend: OK";

        } else {

            status.textContent =
                "🔴 Backend: Error";
        }

    } catch (error) {

        console.error(
            "Health error:",
            error
        );

        status.textContent =
            "🔴 Backend: Not connected";
    }
}


// ============================================================
// LOAD STOCK SYMBOLS
// ============================================================

async function loadSymbols() {

    const select =
        document.getElementById(
            "stockSelect"
        );

    try {

        select.innerHTML =
            "<option>Loading stocks...</option>";

        const response =
            await fetch(
                `${API}/symbols`
            );

        if (!response.ok) {

            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const result =
            await response.json();

        const symbols =
            result.symbols || [];

        if (symbols.length === 0) {

            select.innerHTML =
                "<option>No stocks found</option>";

            return;
        }

        select.innerHTML = "";

        symbols.forEach(
            symbol => {

                const option =
                    document.createElement(
                        "option"
                    );

                option.value = symbol;
                option.textContent = symbol;

                select.appendChild(
                    option
                );
            }
        );

        await loadStock(
            symbols[0]
        );

    } catch (error) {

        console.error(
            "Error loading stocks:",
            error
        );

        select.innerHTML =
            "<option>Error loading stocks</option>";
    }
}


// ============================================================
// LOAD STOCK
// ============================================================

async function loadStock(symbol) {

    if (!symbol) {
        return;
    }

    try {

        const response =
            await fetch(
                `${API}/stock/${encodeURIComponent(symbol)}`
            );

        if (!response.ok) {

            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const stock =
            await response.json();

        setText(
            "symbol",
            stock.symbol || symbol
        );

        setText(
    "currentPrice",
    formatNumber(
        stock.current_price
    )
);

setText(
    "totalReturn",
    formatPercent(
        stock.total_return
    )
);

setText(
    "sharpe",
    formatNumber(
        stock.sharpe
    )
);

setText(
    "maxDrawdown",
    formatPercent(
        stock.max_drawdown
    )
);

drawPriceChart(stock);

    } catch (error) {

        console.error(
            "Error loading stock:",
            error
        );

        setText(
            "symbol",
            "-"
        );

        setText(
            "currentPrice",
            "-"
        );
    }
}


// ============================================================
// PRICE + SMA CHART
// ============================================================

function drawPriceChart(stock) {

    const canvas =
        document.getElementById(
            "priceChart"
        );

    if (!canvas) {
        return;
    }

    priceChart =
        destroyChart(
            priceChart
        );

    const data =
        stock.data || [];

    if (data.length === 0) {
        return;
    }

    const labels =
        data.map(
            row => row.day
        );

    const prices =
        data.map(
            row => row.close
        );

    const sma9 =
        data.map(
            row => row.sma9
        );

    const sma20 =
        data.map(
            row => row.sma20
        );

    priceChart =
        new Chart(
            canvas,
            {

                type: "line",

                data: {

                    labels: labels,

                    datasets: [

                        {
                            label:
                                "Close Price",

                            data: prices,

                            borderWidth: 2,

                            pointRadius: 0,

                            tension: 0.2
                        },

                        {
                            label:
                                "SMA 9",

                            data: sma9,

                            borderWidth: 2,

                            pointRadius: 0,

                            tension: 0.2
                        },

                        {
                            label:
                                "SMA 20",

                            data: sma20,

                            borderWidth: 2,

                            pointRadius: 0,

                            tension: 0.2
                        }
                    ]
                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    interaction: {
                        mode: "index",
                        intersect: false
                    }
                }
            }
        );
}


// ============================================================
// STRATEGY COMPARISON
// ============================================================

async function loadStrategyComparison() {

    try {

        const response =
            await fetch(
                `${API}/strategy-comparison`
            );

        if (!response.ok) {

            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const result =
            await response.json();

        const base =
            result.base_strategy;

        const newStrategy =
            result.new_strategy;

        if (base) {

            setText(
                "baseFinal",
                formatNumber(
                    base.final_value
                )
            );

            setText(
                "baseReturn",
                formatPercent(
                    base.total_return
                )
            );

            setText(
                "baseDrawdown",
                formatPercent(
                    base.max_drawdown
                )
            );

            setText(
                "baseSharpe",
                formatNumber(
                    base.sharpe
                )
            );

            setText(
                "baseTrades",
                base.total_trades
            );
        }

        if (newStrategy) {

            setText(
                "newFinal",
                formatNumber(
                    newStrategy.final_value
                )
            );

            setText(
                "newReturn",
                formatPercent(
                    newStrategy.total_return
                )
            );

            setText(
                "newDrawdown",
                formatPercent(
                    newStrategy.max_drawdown
                )
            );

            setText(
                "newSharpe",
                formatNumber(
                    newStrategy.sharpe
                )
            );

            setText(
                "newTrades",
                newStrategy.total_trades
            );
        }

        setText(
            "winner",
            `Winner: ${result.winner || "-"}`
        );

        drawStrategyChart(
            result.dates || [],
            result.curves || {}
        );

        drawDrawdownChart(
            result.dates || [],
            result.drawdowns || {}
        );

    } catch (error) {

        console.error(
            "Strategy comparison error:",
            error
        );

        setText(
            "winner",
            "Error loading strategy comparison"
        );
    }
}


// ============================================================
// STRATEGY CURVES
// ============================================================

function drawStrategyChart(
    dates,
    curves
) {

    const canvas =
        document.getElementById(
            "strategyChart"
        );

    if (!canvas) {
        return;
    }

    strategyChart =
        destroyChart(
            strategyChart
        );

    strategyChart =
        new Chart(
            canvas,
            {

                type: "line",

                data: {

                    labels: dates,

                    datasets: [

                        {
                            label:
                                "Base Strategy",

                            data:
                                curves.base || [],

                            borderWidth: 2,

                            pointRadius: 0,

                            tension: 0.2
                        },

                        {
                            label:
                                "SMA20 + Momentum",

                            data:
                                curves.new || [],

                            borderWidth: 2,

                            pointRadius: 0,

                            tension: 0.2
                        }
                    ]
                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    interaction: {
                        mode: "index",
                        intersect: false
                    },

                    scales: {

                        y: {

                            title: {
                                display: true,
                                text:
                                    "Portfolio Value"
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

function drawDrawdownChart(
    dates,
    drawdowns
) {

    const canvas =
        document.getElementById(
            "drawdownChart"
        );

    if (!canvas) {
        return;
    }

    drawdownChart =
        destroyChart(
            drawdownChart
        );

    drawdownChart =
        new Chart(
            canvas,
            {

                type: "line",

                data: {

                    labels: dates,

                    datasets: [

                        {
                            label:
                                "Base Strategy",

                            data:
                                drawdowns.base || [],

                            borderWidth: 2,

                            pointRadius: 0
                        },

                        {
                            label:
                                "SMA20 + Momentum",

                            data:
                                drawdowns.new || [],

                            borderWidth: 2,

                            pointRadius: 0
                        }
                    ]
                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    scales: {

                        y: {

                            title: {
                                display: true,
                                text:
                                    "Drawdown (%)"
                            }
                        }
                    }
                }
            }
        );
}


// ============================================================
// LSTM RESULTS
// ============================================================

async function loadLSTMResults() {

    console.log(
        "Loading LSTM results..."
    );

    try {

        const response =
            await fetch(
                `${API}/model-results`
            );

        if (!response.ok) {

            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const result =
            await response.json();

        console.log(
            "LSTM results:",
            result
        );

        if (result.status !== "ok") {

            setText(
                "lstmStatus",
                "⚠ LSTM results not available"
            );

            return;
        }

        setText(
            "lstmStatus",
            "LSTM results loaded successfully"
        );


        // ====================================================
        // MODEL INFORMATION
        // ====================================================

        const model =
            result.model || {};

        setText(
            "lstmModel",
            model.name || "LSTM"
        );

        setText(
            "lstmSequence",
            model.sequence_length ?? "-"
        );

        setText(
            "lstmTopK",
            model.top_k ?? "-"
        );

        setText(
            "lstmEpochs",
            model.epochs ?? "-"
        );


        // ====================================================
        // LOSSES
        // ====================================================

        const loss =
            result.loss || {};

        const trainLosses =
            Array.isArray(loss.train)
                ? loss.train
                : [];

        const testLosses =
            Array.isArray(loss.test)
                ? loss.test
                : [];


        console.log(
            "Training losses:",
            trainLosses.length
        );

        console.log(
            "Testing losses:",
            testLosses.length
        );


        if (trainLosses.length > 0) {

            setText(
                "lstmTrainLoss",
                formatNumber(
                    trainLosses[
                        trainLosses.length - 1
                    ],
                    6
                )
            );

        } else {

            setText(
                "lstmTrainLoss",
                "-"
            );
        }


        if (testLosses.length > 0) {

            setText(
                "lstmTestLoss",
                formatNumber(
                    testLosses[
                        testLosses.length - 1
                    ],
                    6
                )
            );

        } else {

            setText(
                "lstmTestLoss",
                "-"
            );
        }


        // ====================================================
        // LOSS CHART
        // ====================================================

        drawLSTMLossChart(
            trainLosses,
            testLosses
        );


        // ====================================================
        // FINAL PORTFOLIO VALUES
        // ====================================================

        const finalValues =
            result.final_values || {};

        const lstmValue =
            finalValues.lstm;

        const mlpValue =
            finalValues.mlp;

        const benchmarkValue =
            finalValues.benchmark;


        setText(
            "lstmFinalValue",
            formatNumber(
                lstmValue,
                2
            )
        );

        setText(
            "mlpFinalValue",
            formatNumber(
                mlpValue,
                2
            )
        );

        setText(
            "benchmarkFinalValue",
            formatNumber(
                benchmarkValue,
                2
            )
        );


        // ====================================================
        // PORTFOLIO CHART
        // ====================================================

        drawLSTMPortfolioChart(
            finalValues
        );


        // ====================================================
        // OPTIONAL NOTEBOOK DATA
        // ====================================================

        const predictions =
            result.predictions || [];

        const actual =
            result.actual || [];

        if (
            predictions.length > 0 &&
            actual.length > 0
        ) {

            drawLSTMActualPredictedChart(
                actual,
                predictions
            );
        }

    } catch (error) {

        console.error(
            "LSTM results error:",
            error
        );

        setText(
            "lstmStatus",
            "❌ Error loading LSTM results"
        );
    }
}


// ============================================================
// LSTM LOSS CHART
// ============================================================

function drawLSTMLossChart(
    trainLosses,
    testLosses
) {

    const canvas =
        document.getElementById(
            "lstmLossChart"
        );

    if (!canvas) {
        return;
    }

    lstmLossChart =
        destroyChart(
            lstmLossChart
        );


    const maxLength =
        Math.max(
            trainLosses.length,
            testLosses.length
        );


    if (maxLength === 0) {

        return;
    }


    const epochs =
        Array.from(
            {
                length: maxLength
            },
            (_, i) => i + 1
        );


    lstmLossChart =
        new Chart(
            canvas,
            {

                type: "line",

                data: {

                    labels: epochs,

                    datasets: [

                        {
                            label:
                                "Training Loss",

                            data:
                                trainLosses,

                            borderWidth: 2,

                            pointRadius: 0,

                            tension: 0.2
                        },

                        {
                            label:
                                "Testing Loss",

                            data:
                                testLosses,

                            borderWidth: 2,

                            pointRadius: 0,

                            tension: 0.2
                        }
                    ]
                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    interaction: {

                        mode: "index",

                        intersect: false
                    },

                    plugins: {

                        legend: {
                            display: true
                        }
                    },

                    scales: {

                        x: {

                            title: {

                                display: true,

                                text:
                                    "Epoch"
                            }
                        },

                        y: {

                            title: {

                                display: true,

                                text:
                                    "Loss"
                            }
                        }
                    }
                }
            }
        );
}


// ============================================================
// LSTM PORTFOLIO CHART
// ============================================================

function drawLSTMPortfolioChart(
    finalValues
) {

    const canvas =
        document.getElementById(
            "lstmPortfolioChart"
        );

    if (!canvas) {
        return;
    }

    lstmPortfolioChart =
        destroyChart(
            lstmPortfolioChart
        );


    const values = [

        Number(
            finalValues.lstm
        ) || 0,

        Number(
            finalValues.mlp
        ) || 0,

        Number(
            finalValues.benchmark
        ) || 0
    ];


    lstmPortfolioChart =
        new Chart(
            canvas,
            {

                type: "bar",

                data: {

                    labels: [
                        "LSTM",
                        "MLP",
                        "Benchmark"
                    ],

                    datasets: [

                        {
                            label:
                                "Final Portfolio Value",

                            data:
                                values,

                            borderWidth: 1
                        }
                    ]
                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    plugins: {

                        legend: {
                            display: true
                        }
                    },

                    scales: {

                        y: {

                            beginAtZero: true,

                            title: {

                                display: true,

                                text:
                                    "Portfolio Value"
                            }
                        }
                    }
                }
            }
        );
}


// ============================================================
// OPTIONAL LSTM ACTUAL VS PREDICTED
// ============================================================

function drawLSTMActualPredictedChart(
    actual,
    predictions
) {

    const canvas =
        document.getElementById(
            "lstmPredictionChart"
        );

    if (!canvas) {
        return;
    }


    const n =
        Math.min(
            actual.length,
            predictions.length,
            300
        );


    const labels =
        Array.from(
            {
                length: n
            },
            (_, i) => i + 1
        );


    new Chart(
        canvas,
        {

            type: "line",

            data: {

                labels: labels,

                datasets: [

                    {
                        label:
                            "Actual",

                        data:
                            actual.slice(0, n),

                        borderWidth: 2,

                        pointRadius: 0
                    },

                    {
                        label:
                            "Predicted",

                        data:
                            predictions.slice(
                                0,
                                n
                            ),

                        borderWidth: 2,

                        pointRadius: 0
                    }
                ]
            },

            options: {

                responsive: true,

                maintainAspectRatio: false
            }
        }
    );
}


// ============================================================
// STOCK SELECT
// ============================================================

document
    .getElementById("stockSelect")
    .addEventListener(
        "change",
        function () {

            loadStock(
                this.value
            );
        }
    );


// ============================================================
// UNIVERSE BUTTONS
// ============================================================

document
    .getElementById("smallUniverse")
    .addEventListener(
        "click",
        function () {

            this.classList.add(
                "active"
            );

            document
                .getElementById(
                    "fullUniverse"
                )
                .classList.remove(
                    "active"
                );

            loadSymbols();
        }
    );


document
    .getElementById("fullUniverse")
    .addEventListener(
        "click",
        function () {

            this.classList.add(
                "active"
            );

            document
                .getElementById(
                    "smallUniverse"
                )
                .classList.remove(
                    "active"
                );

            loadSymbols();
        }
    );


// ============================================================
// INITIALIZATION
// ============================================================

async function init() {

    console.log(
        "Initializing dashboard..."
    );

    await checkHealth();

    await loadSymbols();

    await loadStrategyComparison();

    await loadLSTMResults();

    console.log(
        "Dashboard initialized."
    );
}

// ============================================================
// AI ASSISTANT
// ============================================================

async function sendAIMessage() {

    const input =
        document.getElementById("aiInput");

    const messages =
        document.getElementById("aiMessages");

    const sendButton =
        document.getElementById("aiSendButton");

    const message =
        input.value.trim();

    if (!message) {
        return;
    }

    // Show user's message
    addAIMessage(
        message,
        "user"
    );

    input.value = "";

    sendButton.disabled = true;
    sendButton.textContent = "Thinking...";

    try {

        // Get currently selected stock
        const stockSelect =
            document.getElementById("stockSelect");

        const symbol =
            stockSelect
                ? stockSelect.value
                : null;

        // Collect dashboard data
        const context = {

            selected_stock: symbol,

            current_price:
                document.getElementById(
                    "currentPrice"
                )?.textContent || "-",

            total_return:
                document.getElementById(
                    "totalReturn"
                )?.textContent || "-",

            sharpe:
                document.getElementById(
                    "sharpe"
                )?.textContent || "-",

            max_drawdown:
                document.getElementById(
                    "maxDrawdown"
                )?.textContent || "-",

            lstm_prediction:
                document.getElementById(
                    "lstmPrediction"
                )?.textContent || "-",

            lstm_confidence:
                document.getElementById(
                    "lstmConfidence"
                )?.textContent || "-",

            mlp_prediction:
                document.getElementById(
                    "mlpPrediction"
                )?.textContent || "-",

            mlp_confidence:
                document.getElementById(
                    "mlpConfidence"
                )?.textContent || "-",

            strategy_winner:
                document.getElementById(
                    "winner"
                )?.textContent || "-",

            lstm_final_value:
                document.getElementById(
                    "lstmFinalValue"
                )?.textContent || "-",

            mlp_final_value:
                document.getElementById(
                    "mlpFinalValue"
                )?.textContent || "-",

            benchmark_final_value:
                document.getElementById(
                    "benchmarkFinalValue"
                )?.textContent || "-"
        };

        const response =
            await fetch(
                `${API}/ai-chat`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        message: message,

                        context: context
                    })
                }
            );

        const result =
            await response.json();

        if (!response.ok) {

            throw new Error(
                result.detail ||
                `HTTP ${response.status}`
            );
        }

        addAIMessage(
            result.reply ||
            "I couldn't generate a response.",
            "bot"
        );

    } catch (error) {

        console.error(
            "AI Assistant error:",
            error
        );

        addAIMessage(
            "❌ Unable to connect to the AI assistant. " +
            "Please make sure the FastAPI backend is running.",
            "bot"
        );

    } finally {

        sendButton.disabled = false;
        sendButton.textContent = "Send";
    }
}


// ============================================================
// ADD MESSAGE TO CHAT
// ============================================================

function addAIMessage(
    message,
    type
) {

    const messages =
        document.getElementById(
            "aiMessages"
        );

    if (!messages) {
        return;
    }

    const messageDiv =
        document.createElement(
            "div"
        );

    messageDiv.className =
        `ai-message ${type}`;

    const icon =
        type === "bot"
            ? "🤖"
            : "👤";

    const sender =
        type === "bot"
            ? "AI Assistant"
            : "You";

    messageDiv.innerHTML = `

        <div class="message-icon">
            ${icon}
        </div>

        <div class="message-content">

            <strong>
                ${sender}
            </strong>

            <p>
                ${escapeHTML(message)}
            </p>

        </div>
    `;

    messages.appendChild(
        messageDiv
    );

    messages.scrollTop =
        messages.scrollHeight;
}


// ============================================================
// SUGGESTIONS
// ============================================================

function askSuggestion(
    question
) {

    const input =
        document.getElementById(
            "aiInput"
        );

    input.value =
        question;

    sendAIMessage();
}


// ============================================================
// ENTER KEY
// ============================================================

document
    .getElementById("aiInput")
    ?.addEventListener(
        "keydown",
        function(event) {

            if (
                event.key === "Enter"
            ) {

                event.preventDefault();

                sendAIMessage();
            }
        }
    );


// ============================================================
// HTML ESCAPE
// ============================================================

function escapeHTML(
    text
) {

    const div =
        document.createElement(
            "div"
        );

    div.textContent =
        text;

    return div.innerHTML;
}


init();