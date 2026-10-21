/* =========================================================
   TIMDEIZ INCENDIE — espace client
========================================================= */

const CLIENT_TITLES = {
    dashboard: "Suivi en direct",
    alerts: "Mes alertes",
    measurements: "Historique",
    profile: "Mon profil",
    settings: "Paramètres",
};

const SITE_LABELS = {
    ok: "🟢 Normal",
    alert: "🟠 Alerte",
    fire: "🔴 Incendie",
    offline: "⚫ Capteur hors ligne",
};

let clientHistory = [];
let clientMetric = "temperature";
let clientThreshold = 300;

function setBadge(id, message, danger) {
    const element = $(id);
    if (!element) return;
    element.textContent = message;
    element.className = `badge ${danger ? "badge-danger" : "badge-success"}`;
}

function renderLive(dash) {
    const m = dash.measurement;
    clientThreshold = dash.gas_threshold;
    $("noSite").hidden = dash.has_devices;

    setText("client-temp", m ? `${formatNumber(m.temperature)} °C` : "-- °C");
    setText("client-humidity", m ? `${formatNumber(m.humidity)} %` : "-- %");
    setText("client-gas", m ? `${formatNumber(m.gas, 0)} ppm` : "-- ppm");
    setBadge("flame-alert-badge", dash.flame ? "🔥 FEU DÉTECTÉ" : "SÉCURISÉ", dash.flame);
    setBadge("gas-alert-badge", dash.gas_leak ? "⚠️ FUITE DE GAZ" : "SÉCURISÉ", dash.gas_leak);
    setText("lastUpdate", m ? `${formatDate(m.created_at)} (${timeAgo(m.created_at)})` : "aucune");
    setText("navAlertCount", dash.active_alerts || "");
    notifyIfNewAlert(dash.latest_alert);
}

function renderClientChart() {
    const points = clientHistory.slice(0, 120).reverse().map(m => ({
        time: m.created_at,
        value: m[clientMetric] === null ? null : Number(m[clientMetric]),
        flame: m.flame_detected,
    }));
    const colors = { temperature: "#ff9f43", humidity: "#38bdf8", gas: "#a78bfa" };
    drawLineChart($("chart"), points, {
        color: colors[clientMetric],
        threshold: clientMetric === "gas" ? clientThreshold : undefined,
    });
}

function renderMySites(sites) {
    $("mySites").innerHTML = sites.length
        ? sites.map(s => `
            <div class="alert-item ${s.state === "ok" ? "success" : s.state === "alert" ? "warning" : ""}">
                <div>
                    <div class="alert-title">${escapeHTML(s.name)}</div>
                    <div class="alert-meta">${escapeHTML(s.address || "-")}</div>
                </div>
                <span>${SITE_LABELS[s.state]}</span>
            </div>`).join("")
        : '<p class="muted">Aucun site rattaché à votre compte.</p>';
}

async function loadLive() {
    const [dash, data, sites] = await Promise.all([
        api("/api/dashboard"),
        api("/api/data?limit=120"),
        api("/api/sites"),
    ]);
    renderLive(dash);
    clientHistory = data.measurements;
    renderClientChart();
    renderMySites(sites.sites);
}

async function loadClientAlerts() {
    const data = await api("/api/alerts?limit=200");
    $("alertsList").innerHTML = data.alerts.length
        ? data.alerts.map(a => `
            <div class="alert-item ${a.status !== "active" ? "success" : a.severity === "warning" ? "warning" : ""}">
                <div>
                    <div class="alert-title">${alertTypeLabel(a.alert_type)} — ${escapeHTML(a.message)}</div>
                    <div class="alert-meta">${severityBadge(a.severity)} ${statusBadge(a.status)}
                        · ${formatNumber(a.temperature)} °C · ${formatNumber(a.gas, 0)} ppm</div>
                    <div class="alert-date">${formatDate(a.created_at)}</div>
                </div>
            </div>`).join("")
        : '<p class="muted">Aucune alerte sur votre site.</p>';
}

async function loadClientHistory() {
    const data = await api("/api/data?limit=200");
    $("historyTable").innerHTML = data.measurements.length
        ? `<table>
            <thead><tr><th>Date</th><th>Température</th><th>Humidité</th><th>Gaz</th><th>Flamme</th></tr></thead>
            <tbody>${data.measurements.map(m => `
                <tr class="${m.flame_detected ? "row-danger" : ""}">
                    <td>${formatDate(m.created_at)}</td>
                    <td>${formatNumber(m.temperature)} °C</td>
                    <td>${formatNumber(m.humidity)} %</td>
                    <td>${formatNumber(m.gas, 0)} ppm</td>
                    <td>${m.flame_detected ? "🔥 Flamme" : "✅ Normal"}</td>
                </tr>`).join("")}
            </tbody>
          </table>`
        : '<p class="muted">Aucune mesure disponible.</p>';
}

const CLIENT_LOADERS = { dashboard: loadLive, alerts: loadClientAlerts, measurements: loadClientHistory };

async function refreshClient() {
    try {
        const tasks = [loadLive()];
        if (Shell.currentPage === "alerts") tasks.push(loadClientAlerts());
        await Promise.all(tasks);
        setConnection(true, "Connecté au serveur");
    } catch (error) {
        setConnection(false, "Serveur injoignable");
        setBadge("flame-alert-badge", "⚠️ SERVEUR INDISPONIBLE", true);
        setBadge("gas-alert-badge", "⚠️ SERVEUR INDISPONIBLE", true);
        console.error(error);
    }
}

document.addEventListener("click", event => {
    const tab = event.target.closest(".chart-tab");
    if (!tab) return;
    clientMetric = tab.dataset.metric;
    document.querySelectorAll(".chart-tab").forEach(t => t.classList.toggle("active", t === tab));
    renderClientChart();
});

initShell({
    role: "client",
    titles: CLIENT_TITLES,
    onRefresh: refreshClient,
    onPageChange: page => CLIENT_LOADERS[page]?.().catch(error => showToast(error.message, true)),
    defaultInterval: "2000",
});
