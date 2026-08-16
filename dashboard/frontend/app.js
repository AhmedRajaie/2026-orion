// Dashboard frontend. Grows via dashboard/tasks/.
const API = "http://localhost:8000";

async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const j = await r.json();
    document.getElementById("status").textContent = "backend: " + j.status;
  } catch (e) {
    document.getElementById("status").textContent = "backend not reachable — start uvicorn";
  }
}
checkHealth();
// TASK_02+ : fetch /prices and render a chart, etc.

async function drawPriceChartFor(symbol, smaWindow = 20) {
  try {
    const r = await fetch(`${API}/prices/${encodeURIComponent(symbol)}`);
    if (!r.ok) throw new Error('failed to fetch prices');
    const data = await r.json();

    // fetch SMA for the requested window (default 20)
    let smaData = null;
    try {
      const s = await fetch(`${API}/indicators/${encodeURIComponent(symbol)}?window=${smaWindow}`);
      if (s.ok) {
        const sj = await s.json();
        smaData = sj.sma;
      }
    } catch (e) {
      console.warn('failed to fetch sma', e);
    }

    // also fetch SMA(9) for the special '@sma(9)' annotation/dataset
    let sma9 = null;
    try {
      const s9 = await fetch(`${API}/indicators/${encodeURIComponent(symbol)}?window=9`);
      if (s9.ok) {
        const s9j = await s9.json();
        sma9 = s9j.sma;
      }
    } catch (e) {
      console.warn('failed to fetch sma9', e);
    }

    // fetch backtest results (equity & trades)
    let back = null;
    try {
      // build commission-aware query params
      function _commissionQueryFor(sym) {
        const rate = parseFloat(document.getElementById('commissionRate')?.value || '0');
        const applyAll = document.getElementById('commissionApplyAll')?.checked;
        const params = new URLSearchParams();
        params.set('initial', '1000');
        if (!isNaN(rate) && rate > 0) {
          params.set('commission_rate', String(rate));
          if (applyAll) params.set('apply_commission_to_all', 'true');
          else params.set('commission_symbol', sym);
        }
        return params.toString();
      }
      const q = _commissionQueryFor(symbol);
      const b = await fetch(`${API}/backtest/${encodeURIComponent(symbol)}?${q}`);
      if (b.ok) back = await b.json();
    } catch (e) {
      console.warn('failed to fetch backtest', e);
    }

    updateMetrics(back);
    renderStrategyComparison(back);
    // store latest backtest globally for export and rendering
    window.latestBacktest = back;
    renderTrades((back && back.base && back.base.trades) || []);

    const el = document.getElementById('priceChart');
    if (!el) return;
    const ctx = el.getContext('2d');
    if (window.priceChartInstance) window.priceChartInstance.destroy();

    const datasets = [{
      label: `${symbol} close`,
      data: data.close,
      borderColor: '#4fd1c5',
      backgroundColor: 'rgba(79,209,197,0.08)',
      pointRadius: 0,
      borderWidth: 2,
      tension: 0.15,
      yAxisID: 'price'
    }];

    if (smaData) {
      datasets.push({
        label: `${symbol} SMA(${smaWindow})`,
        data: smaData,
        borderColor: '#f6ad55',
        backgroundColor: 'rgba(246,173,85,0.06)',
        pointRadius: 0,
        borderWidth: 2,
        tension: 0.2,
        yAxisID: 'price'
      });
    }

    if (sma9) {
      // Add SMA(9) as a dashed, subtle line and label it '@sma(9)'
      datasets.push({
        label: `@sma(9)`,
        data: sma9,
        borderColor: '#a78bfa',
        backgroundColor: 'rgba(167,139,250,0.04)',
        pointRadius: 0,
        borderWidth: 2,
        tension: 0.2,
        borderDash: [6, 4],
        yAxisID: 'price'
      });
    }

    // add equity curve on right axis if backtest present
    if (back && back.base && back.base.equity) {
      // enable export button
      const exportBtn = document.getElementById('exportCsvBtn');
      if (exportBtn) {
        exportBtn.disabled = false;
        exportBtn.onclick = () => exportBacktestCSV(back);
      }
      datasets.push({
        label: 'Equity (EGP)',
        data: back.base.equity,
        borderColor: '#60a5fa',
        backgroundColor: 'rgba(96,165,250,0.06)',
        pointRadius: 0,
        borderWidth: 2,
        tension: 0.15,
        yAxisID: 'equity'
      });

      // buy/sell markers as separate datasets (nulls except trade points)
      const buys = new Array(data.dates.length).fill(null);
      const sells = new Array(data.dates.length).fill(null);
      (back.base && back.base.trades ? back.base.trades : []).forEach((tr) => {
        const i = tr.index;
        if (tr.type === 'buy') buys[i] = tr.price;
        if (tr.type === 'sell') sells[i] = tr.price;
      });

      datasets.push({
        label: 'Buys',
        data: buys,
        pointStyle: 'triangle',
        pointRadius: 8,
        showLine: false,
        backgroundColor: '#10b981',
        borderColor: '#10b981',
        yAxisID: 'price'
      });

      datasets.push({
        label: 'Sells',
        data: sells,
        pointStyle: 'triangle',
        pointRadius: 8,
        rotation: 180,
        showLine: false,
        backgroundColor: '#ef4444',
        borderColor: '#ef4444',
        yAxisID: 'price'
      });
    }

    window.priceChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.dates,
        datasets: datasets
      },
      options: {
        scales: {
          x: { ticks: { color: '#cbd5e1' } },
          price: { type: 'linear', position: 'left', ticks: { color: '#cbd5e1' } },
          equity: { type: 'linear', position: 'right', ticks: { color: '#93c5fd' }, grid: { drawOnChartArea: false } }
        },
        plugins: { legend: { labels: { color: '#cbd5e1' } } },
        maintainAspectRatio: false
      }
    });
  } catch (e) {
    console.error(e);
  }
}

function updateMetrics(back) {
  const el = document.getElementById('metricsContent');
  if (!el) return;
  if (!back || !back.base) {
    el.textContent = 'No backtest data';
    return;
  }
  const base = back.base;
  const final = Number(base.final_value || 0);
  const total = Number(base.total_return || 0);
  const ann = Number(base.annualized_return || 0);
  const sharpe = Number(base.sharpe_ratio || 0);
  const mdd = Number(base.max_drawdown_pct || 0);
  const buys = base.buys || 0;
  const sells = base.sells || 0;

  el.innerHTML = `
    <div>Final equity: <strong>${final.toFixed(2)}</strong> EGP</div>
    <div>Total return: <strong>${(total * 100).toFixed(2)}%</strong></div>
    <div>Annualized return: <strong>${(ann * 100).toFixed(2)}%</strong></div>
    <div>Sharpe ratio: <strong>${sharpe.toFixed(2)}</strong></div>
    <div>Max drawdown: <strong>${(mdd * 100).toFixed(2)}%</strong></div>
    <div>Buys: <strong>${buys}</strong> &nbsp; Sells: <strong>${sells}</strong></div>
  `;
}

function renderStrategyComparison(back) {
  const el = document.getElementById('strategyMetricsContent');
  if (!el) return;
  if (!back || !back.base || !back.new_strategy) {
    el.textContent = 'No strategy comparison data available.';
    return;
  }

  const base = back.base;
  const other = back.new_strategy;
  el.innerHTML = `
    <div style="display:flex;flex-wrap:wrap;gap:18px;">
      <div style="flex:1;min-width:240px;padding:12px;border-radius:10px;background:#0f172a;">
        <strong>Base SMA crossover</strong>
        <div style="margin-top:8px;line-height:1.6;">
          <div>Total return: <strong>${(Number(base.total_return || 0) * 100).toFixed(2)}%</strong></div>
          <div>Sharpe: <strong>${Number(base.sharpe_ratio || 0).toFixed(2)}</strong></div>
          <div>Max drawdown: <strong>${(Number(base.max_drawdown_pct || 0) * 100).toFixed(2)}%</strong></div>
          <div>Buys: <strong>${base.buys || 0}</strong> Sells: <strong>${base.sells || 0}</strong></div>
        </div>
      </div>
      <div style="flex:1;min-width:240px;padding:12px;border-radius:10px;background:#0f172a;">
        <strong>Drop/rise strategy</strong>
        <div style="margin-top:8px;line-height:1.6;">
          <div>Total return: <strong>${(Number(other.total_return || 0) * 100).toFixed(2)}%</strong></div>
          <div>Sharpe: <strong>${Number(other.sharpe_ratio || 0).toFixed(2)}</strong></div>
          <div>Max drawdown: <strong>${(Number(other.max_drawdown_pct || 0) * 100).toFixed(2)}%</strong></div>
          <div>Buys: <strong>${other.buys || 0}</strong> Sells: <strong>${other.sells || 0}</strong></div>
        </div>
      </div>
    </div>
  `;

  const chartEl = document.getElementById('strategyChart');
  if (!chartEl) return;
  const ctx = chartEl.getContext('2d');
  if (window.strategyChartInstance) window.strategyChartInstance.destroy();

  window.strategyChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: back.dates,
      datasets: [
        {
          label: 'SMA crossover equity',
          data: base.equity,
          borderColor: '#60a5fa',
          backgroundColor: 'rgba(96,165,250,0.08)',
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.15,
        },
        {
          label: 'Drop/rise strategy equity',
          data: other.equity,
          borderColor: '#f97316',
          backgroundColor: 'rgba(249,115,22,0.08)',
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.15,
          borderDash: [6, 4],
        }
      ]
    },
    options: {
      scales: {
        x: { ticks: { color: '#cbd5e1' } },
        y: { ticks: { color: '#cbd5e1' }, grid: { color: 'rgba(148,163,184,0.16)' } }
      },
      plugins: {
        legend: { labels: { color: '#cbd5e1' } }
      },
      maintainAspectRatio: false,
    }
  });
}

function renderSymbolControls(symbols, selectedSymbol) {
  const filterInput = document.getElementById('symbolFilter');
  const select = document.getElementById('symbolSelect');

  function updateOptions() {
    const query = filterInput.value.trim().toUpperCase();
    const filtered = symbols.filter((symbol) => symbol.includes(query));
    select.innerHTML = '';
    filtered.forEach((symbol) => {
      const option = document.createElement('option');
      option.value = symbol;
      option.textContent = symbol;
      select.appendChild(option);
    });
    if (filtered.length === 0) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No matching symbols';
      select.appendChild(option);
      select.disabled = true;
      return;
    }
    select.disabled = false;
    if (filtered.includes(selectedSymbol)) {
      select.value = selectedSymbol;
    } else {
      select.value = filtered[0];
      selectedSymbol = filtered[0];
    }
  }

  filterInput.addEventListener('input', () => {
    updateOptions();
  });

  select.addEventListener('change', async () => {
    if (!select.value) return;
    const symbol = select.value;
    updateUrlSymbol(symbol);
    document.getElementById('status').textContent = `backend: ok — ${symbol}`;
    await drawPriceChartFor(symbol);
  });

  updateOptions();
}

function updateUrlSymbol(symbol) {
  const url = new URL(window.location.href);
  url.searchParams.set('symbol', symbol);
  window.history.replaceState({}, '', url);
}

function renderTrades(trades) {
  const tbody = document.querySelector('#tradesTable tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  trades.forEach((tr, i) => {
    const trEl = document.createElement('tr');
    trEl.style.borderBottom = '1px solid #24303f';
    const idxTd = document.createElement('td'); idxTd.style.padding = '6px'; idxTd.textContent = i + 1;
    const dateTd = document.createElement('td'); dateTd.style.padding = '6px'; dateTd.textContent = tr.date || '';
    const typeTd = document.createElement('td'); typeTd.style.padding = '6px'; typeTd.textContent = tr.type || '';
    const priceTd = document.createElement('td'); priceTd.style.padding = '6px'; priceTd.style.textAlign = 'right'; priceTd.textContent = tr.price != null ? Number(tr.price).toFixed(2) : '';
    const sharesTd = document.createElement('td'); sharesTd.style.padding = '6px'; sharesTd.style.textAlign = 'right'; sharesTd.textContent = tr.shares != null ? Number(tr.shares).toFixed(6) : '';
    const cashTd = document.createElement('td'); cashTd.style.padding = '6px'; cashTd.style.textAlign = 'right'; cashTd.textContent = tr.cash != null ? Number(tr.cash).toFixed(2) : '';
    trEl.appendChild(idxTd);
    trEl.appendChild(dateTd);
    trEl.appendChild(typeTd);
    trEl.appendChild(priceTd);
    trEl.appendChild(sharesTd);
    trEl.appendChild(cashTd);
    tbody.appendChild(trEl);
  });
}

function exportBacktestCSV(back) {
  if (!back) return;
  const rows = [];
  // header
  rows.push(['date','price','sma9','sma20','equity','trade_type','trade_shares','trade_price','trade_cash']);
  // map trades by index (allow multiple per day)
  const tradesByIndex = {};
  (back.base && back.base.trades ? back.base.trades : []).forEach((t) => {
    if (!tradesByIndex[t.index]) tradesByIndex[t.index] = [];
    tradesByIndex[t.index].push(t);
  });
  const n = back.dates.length;
  for (let i = 0; i < n; i++) {
    const date = back.dates[i] || '';
    const price = back.price && back.price[i] != null ? back.price[i] : '';
    const sma9 = back.sma9 && back.sma9[i] != null ? back.sma9[i] : '';
    const sma20 = back.sma20 && back.sma20[i] != null ? back.sma20[i] : '';
    const equity = back.base && back.base.equity && back.base.equity[i] != null ? back.base.equity[i] : '';
    const trades = tradesByIndex[i] || [];
    if (trades.length === 0) {
      rows.push([date, price, sma9, sma20, equity, '', '', '', '']);
    } else {
      trades.forEach((t, j) => {
        rows.push([date, price, sma9, sma20, equity, t.type || '', t.shares != null ? t.shares : '', t.price != null ? t.price : '', t.cash != null ? t.cash : '']);
      });
    }
  }
  // stringify CSV
  const csv = rows.map(r => r.map(v => typeof v === 'string' ? '"' + String(v).replace(/"/g, '""') + '"' : v).join(',')).join('\n');
  const blob = new Blob([csv], {type: 'text/csv;charset=utf-8;'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const sym = (new URL(window.location.href)).searchParams.get('symbol') || 'symbol';
  a.download = `${sym}-backtest.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function fetchAndRenderModelCompare() {
  try {
    const r = await fetch(`${API}/compare`);
    if (!r.ok) return;
    const j = await r.json();
    const el = document.getElementById('modelCompareContent');
    if (!el) return;
    const mlp = j.mlp;
    const lstm = j.lstm;
    if ((mlp == null) && (lstm == null)) {
      el.textContent = 'No model compare data available.';
      return;
    }
    // If one missing, show the available one
    const entries = [];
    if (mlp != null) entries.push({name: 'MLP', val: Number(mlp), color: '#60a5fa'});
    if (lstm != null) entries.push({name: 'LSTM', val: Number(lstm), color: '#a78bfa'});
    const max = Math.max(...entries.map(e => e.val));
    const html = entries.map(e => {
      const pct = max > 0 ? Math.round((1 - e.val / max) * 100) : 50;
      return `
        <div style="margin-top:8px;">
          <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:6px;"><span>${e.name}</span><span>${e.val.toFixed(6)}</span></div>
          <div style="background:#071025;border-radius:6px;height:12px;">
            <div style="width:${pct}%;height:12px;background:${e.color};border-radius:6px;"></div>
          </div>
        </div>
      `;
    }).join('');
    el.innerHTML = html;
  } catch (e) {
    console.warn('failed to fetch model compare', e);
  }
}

// Commission helper and panel fetch/render functions (MLP/LSTM/loss)
function _getCommissionQueryFor(sym) {
  const rate = parseFloat(document.getElementById('commissionRate')?.value || '0');
  const applyAll = document.getElementById('commissionApplyAll')?.checked;
  const params = new URLSearchParams();
  params.set('initial', '1000');
  if (!isNaN(rate) && rate > 0) {
    params.set('commission_rate', String(rate));
    if (applyAll) params.set('apply_commission_to_all', 'true');
    else params.set('commission_symbol', sym);
  }
  return params.toString();
}

let lossChartInstance = null;
async function fetchAndRenderLoss() {
  try {
    const r = await fetch(`${API}/loss`);
    if (!r.ok) {
      document.getElementById('lossContent').textContent = 'No loss data available.';
      return;
    }
    const j = await r.json();
    const el = document.getElementById('lossContent');
    if (!el) return;
    // create/replace canvas
    el.innerHTML = '';
    const c = document.createElement('canvas');
    c.width = 800; c.height = 220; c.style.width = '100%'; c.style.height = '220px';
    el.appendChild(c);
    const ctx = c.getContext('2d');
    if (lossChartInstance) lossChartInstance.destroy();
    const train = j.train || [];
    const test = j.test || [];
    const epochs = train.map((_, i) => i+1);
    lossChartInstance = new Chart(ctx, {
      type: 'line',
      data: { labels: epochs, datasets: [
        { label: 'Train loss', data: train, borderColor: '#60a5fa', backgroundColor:'rgba(96,165,250,0.06)', pointRadius:0 },
        { label: 'Test loss', data: test, borderColor: '#a78bfa', backgroundColor:'rgba(167,139,250,0.04)', pointRadius:0 }
      ]},
      options: { plugins:{legend:{labels:{color:'#cbd5e1'}}}, scales:{x:{ticks:{color:'#cbd5e1'}}, y:{ticks:{color:'#cbd5e1'}}}, maintainAspectRatio:false }
    });
  } catch (e) {
    console.warn('failed to fetch loss', e);
  }
}

let mlpChartInstance = null;
async function fetchAndRenderMLP() {
  try {
    const r = await fetch(`${API}/mlp`);
    if (!r.ok) {
      const el = document.getElementById('mlpPanel'); if (el) { el.style.opacity = '0.8'; }
      return;
    }
    const j = await r.json();
    const c = document.getElementById('mlpChart');
    if (!c) return;
    const ctx = c.getContext('2d');
    if (mlpChartInstance) mlpChartInstance.destroy();
    const portfolio = j.portfolio || j.portfolio || [];
    const benchmark = j.benchmark || j.benchmark || [];
    const labels = portfolio.map((_,i) => i+1);
    mlpChartInstance = new Chart(ctx, { type:'line', data:{ labels, datasets:[ {label:'MLP portfolio',data:portfolio,borderColor:'#34d399',pointRadius:0,fill:false},{label:'Benchmark',data:benchmark,borderColor:'#60a5fa',pointRadius:0,fill:false} ]}, options:{scales:{x:{ticks:{color:'#cbd5e1'}}, y:{ticks:{color:'#cbd5e1'}}},plugins:{legend:{labels:{color:'#cbd5e1'}}},maintainAspectRatio:false} });
  } catch (e) {
    console.warn('failed to fetch mlp equity', e);
  }
}

let lstmChartInstance = null;
async function fetchAndRenderLSTM() {
  try {
    const r = await fetch(`${API}/lstm`);
    if (!r.ok) {
      const el = document.getElementById('lstmPanel'); if (el) { el.style.opacity = '0.8'; }
      return;
    }
    const j = await r.json();
    const c = document.getElementById('lstmChart');
    if (!c) return;
    const ctx = c.getContext('2d');
    if (lstmChartInstance) lstmChartInstance.destroy();
    const portfolio = j.portfolio || j.portfolio || [];
    const benchmark = j.benchmark || j.benchmark || [];
    const labels = portfolio.map((_,i) => i+1);
    lstmChartInstance = new Chart(ctx, { type:'line', data:{ labels, datasets:[ {label:'LSTM portfolio',data:portfolio,borderColor:'#a78bfa',pointRadius:0,fill:false},{label:'Benchmark',data:benchmark,borderColor:'#60a5fa',pointRadius:0,fill:false} ]}, options:{scales:{x:{ticks:{color:'#cbd5e1'}}, y:{ticks:{color:'#cbd5e1'}}},plugins:{legend:{labels:{color:'#cbd5e1'}}},maintainAspectRatio:false} });
  } catch (e) {
    console.warn('failed to fetch lstm equity', e);
  }
}

async function initPrices() {
  try {
    const u = await fetch(`${API}/universe`);
    if (!u.ok) return;
    const uj = await u.json();
    const syms = uj.symbols || [];
    if (syms.length === 0) return;
    const urlSym = new URLSearchParams(window.location.search).get('symbol');
    const symbol = urlSym || syms[0];
    renderSymbolControls(syms, symbol);
    document.getElementById('status').textContent = `backend: ok — ${symbol}`;
    await drawPriceChartFor(symbol);
    // load model comparison panel
    fetchAndRenderModelCompare();
    // load week2 panels (loss, mlp, lstm)
    fetchAndRenderLoss();
    fetchAndRenderMLP();
    fetchAndRenderLSTM();

    // re-run backtest when commission inputs change
    document.getElementById('commissionRate')?.addEventListener('change', () => {
      const s = document.getElementById('symbolSelect').value; if (s) drawPriceChartFor(s);
    });
    document.getElementById('commissionApplyAll')?.addEventListener('change', () => {
      const s = document.getElementById('symbolSelect').value; if (s) drawPriceChartFor(s);
    });
  } catch (e) {
    console.error(e);
  }
}

initPrices();
