const API = "http://localhost:8000";

async function checkHealth(){

    try{

        const r = await fetch(API + "/health");

        const j = await r.json();

        document.getElementById("status").textContent =
        "Backend : " + j.status;

    }

    catch{

        document.getElementById("status").textContent =
        "Backend not reachable";

    }

}

async function loadBacktest(){

    const r = await fetch(API + "/backtest");

    const data = await r.json();

    document.getElementById("symbol").textContent =
    data.symbol;

    document.getElementById("portfolio").textContent =
    data.portfolio + " EGP";

    document.getElementById("drawdown").textContent =
    data.drawdown + " EGP";

    document.getElementById("buy").textContent =
    data.buy_count;

    document.getElementById("sell").textContent =
    data.sell_count;

    new Chart(document.getElementById("priceChart"),{

        type:"line",

        data:{

            labels:data.price.map((_,i)=>i),

            datasets:[

            {

                label:"Close",

                data:data.price

            },

            {

                label:"MA9",

                data:data.ma9

            },

            {

                label:"MA20",

                data:data.ma20

            }

            ]

        }

    });

}

checkHealth();

loadBacktest();