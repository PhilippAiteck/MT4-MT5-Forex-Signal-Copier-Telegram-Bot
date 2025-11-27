async function fetchJSON(url) {
  const r = await fetch(url);
  return await r.json();
}

/* Load SUMMARY */
async function loadSummary() {
  const days = document.getElementById("days").value;
  const symbol = document.getElementById("symbol").value;

  let url = `/api/summary?days=${days}`;
  if (symbol) url += `&symbol=${symbol}`;

  const data = await fetchJSON(url);
  const box = document.getElementById("summary");

  box.innerHTML = `
        <h2>Résumé</h2>
        <p><b>Deals :</b> ${data.nb_deals}</p>
        <p><b>PNL Total :</b> ${data.pnl_total.toFixed(2)}</p>
        <p><b>Winrate :</b> ${data.winrate.toFixed(1)}%</p>
        <p><b>PNL moyen :</b> ${data.avg_profit.toFixed(2)}</p>

        <h3>Top Symboles</h3>
        <ul>
            ${data.top_symbols
              .map(
                (s) =>
                  `<li>${s.symbol} → ${s.pnl.toFixed(2)} (${s.nb_deals})</li>`
              )
              .join("")}
        </ul>
    `;
}

/* Load Equity curve */
let chart = null;

async function loadEquity() {
  const days = document.getElementById("days").value;
  const symbol = document.getElementById("symbol").value;

  let url = `/api/pnl-by-day?days=${days}`;
  if (symbol) url += `&symbol=${symbol}`;

  const data = await fetchJSON(url);

  const labels = data.map((x) => x.day);
  const pnl = data.map((x) => x.pnl);

  if (chart) chart.destroy();

  const ctx = document.getElementById("equity-chart").getContext("2d");
  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "PNL",
          data: pnl,
          borderColor: "#4ea1ff",
          borderWidth: 2,
        },
      ],
    },
    options: {
      plugins: { legend: { labels: { color: "#fff" } } },
      scales: {
        x: { ticks: { color: "#aaa" } },
        y: { ticks: { color: "#aaa" } },
      },
    },
  });
}

/* Load Live Positions */
async function loadOpenTrades() {
  const data = await fetchJSON("/api/open-trades");
  const tbody = document.querySelector("#open-trades tbody");

  tbody.innerHTML = "";

  data.items.forEach((p) => {
    const cls = p.profit >= 0 ? "pnl-positive" : "pnl-negative";

    tbody.innerHTML += `
            <tr>
                <td>${p.id}</td>
                <td>${p.symbol}</td>
                <td>${p.type}</td>
                <td>${p.volume}</td>
                <td>${p.openPrice}</td>
                <td class="${cls}">${p.profit}</td>
            </tr>
        `;
  });
}

/* Load last deals */
async function loadDeals() {
  const days = document.getElementById("days").value;
  const symbol = document.getElementById("symbol").value;

  let url = `/api/deals?days=${days}&limit=100`;
  if (symbol) url += `&symbol=${symbol}`;

  const data = await fetchJSON(url);
  const tbody = document.querySelector("#deals tbody");

  tbody.innerHTML = "";

  data.items.forEach((tr) => {
    const cls = tr.profit >= 0 ? "pnl-positive" : "pnl-negative";

    tbody.innerHTML += `
            <tr>
                <td>${tr.time}</td>
                <td>${tr.symbol}</td>
                <td>${tr.type}</td>
                <td>${tr.volume}</td>
                <td>${tr.price}</td>
                <td class="${cls}">${tr.profit}</td>
            </tr>
        `;
  });
}

/* Reload everything */
async function reloadAll() {
  loadSummary();
  loadEquity();
  loadOpenTrades();
  loadDeals();
}

/* Filter button */
document.getElementById("reload-btn").onclick = reloadAll;

/* Initial load */
reloadAll();

/* Auto-refresh LIVE positions every 10s */
setInterval(loadOpenTrades, 10000);
