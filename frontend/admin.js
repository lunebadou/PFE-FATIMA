/* =========================================================
   TIMDEIZ INCENDIE — interface administrateur
========================================================= */

const TITLES = {
    dashboard: "Tableau de bord",
    alerts: "Alertes",
    sites: "Sites",
    measurements: "Historique",
    users: "Utilisateurs",
    profile: "Mon profil",
    settings: "Paramètres",
};

const STATES = {
    ok: ["✅", "Sécurisé", "Aucune flamme ni fuite de gaz détectée."],
    alert: ["⚠️", "Alerte en attente", "Le danger est passé mais des alertes restent à résoudre."],
    gas: ["💨", "Alerte fuite de gaz", "Le niveau de gaz dépasse le seuil de sécurité."],
    fire: ["🔥", "Flamme détectée", "Un départ de feu est signalé par le capteur."],
    offline: ["📴", "Aucune donnée", "Aucune mesure reçue pour l'instant."],
};

let history = [];
let chartMetric = "temperature";
let gasThreshold = 300;


/* ---------- Tableau de bord ---------- */

function setGauge(id, value, max) {
    const gauge = $(id);
    if (gauge) gauge.style.width = `${Math.max(0, Math.min(100, (Number(value) / max) * 100)) || 0}%`;
}

function setServiceState(id, ok, okText, koText) {
    const element = $(id);
    if (!element) return;
    element.className = ok ? "status-online" : "status-offline";
    element.textContent = ok ? `● ${okText}` : `● ${koText}`;
}

function renderDashboard(dash) {
    const m = dash.measurement;
    gasThreshold = dash.gas_threshold;

    const [icon, title, detail] = STATES[m ? dash.state : "offline"];
    $("stateBanner").className = `state-banner ${m ? dash.state : "offline"}`;
    $("stateBanner").querySelector(".state-icon").textContent = icon;
    setText("stateText", title);
    setText("stateDetail", m && !dash.device_online ? `${detail} Attention : l'ESP32 n'envoie plus de données.` : detail);

    setText("temperature", m ? formatNumber(m.temperature) : "--");
    setText("humidity", m ? formatNumber(m.humidity) : "--");
    setText("gas", m ? formatNumber(m.gas, 0) : "--");
    setGauge("temperatureGauge", m?.temperature, 60);
    setGauge("humidityGauge", m?.humidity, 100);
    setGauge("gasGauge", m?.gas, gasThreshold * 1.5);
    setText("gasDetail", dash.gas_leak ? `ppm — au-dessus du seuil (${gasThreshold})` : `ppm — seuil ${gasThreshold}`);
    $("gasCard").classList.toggle("danger", dash.gas_leak);

    setText("flame", dash.flame ? "Flamme détectée" : "Aucune flamme");
    setText("flameDetail", dash.flame ? "⚠️ Détection de flamme" : "✅ Aucun incendie détecté");
    $("flameCard").classList.toggle("danger", dash.flame);

    setText("lastUpdate", m ? `${formatDate(m.created_at)} (${timeAgo(m.created_at)})` : "aucune");

    const count = dash.active_alerts;
    setText("alertState", count);
    $("alertState").className = count ? "status-offline" : "status-online";
    setText("navAlertCount", count || "");
    notifyIfNewAlert(dash.latest_alert);
}

function renderStatus(status) {
    setServiceState("serverState", status.server, "En ligne", "Hors ligne");
    const mqtt = status.mqtt;
    if (!mqtt.enabled) {
        $("mqttState").className = "status-pending";
        $("mqttState").textContent = "● Désactivé";
    } else {
        setServiceState("mqttState", mqtt.connected, "Connecté", "Déconnecté");
    }
    $("mqttState").title = `${mqtt.broker} — topic ${mqtt.topic} — ${mqtt.messages} message(s) reçu(s)`;
    const total = status.devices.length;
    setServiceState("sensorState", status.devices_online > 0, `En ligne (${status.devices_online}/${total})`, "Hors ligne");
}

function renderStats(stats) {
    setText("statAlerts", stats.active_alerts);
    setText("statSensors", stats.sensors);
    setText("statEquipments", stats.equipments);
    setText("statUsers", stats.users);
    setText("statDevices", `${stats.devices_online} / ${stats.devices}`);
    setText("statDevicesDetail", `${stats.devices_online} en ligne · ${stats.devices_offline} hors ligne`);
    setText("statSites", stats.sites);
}

function renderChart() {
    const points = history.slice(0, 120).reverse().map(m => ({
        time: m.created_at,
        value: m[chartMetric] === null ? null : Number(m[chartMetric]),
        flame: m.flame_detected,
    }));
    const colors = { temperature: "#ff9f43", humidity: "#38bdf8", gas: "#a78bfa" };
    drawLineChart($("chart"), points, {
        color: colors[chartMetric],
        threshold: chartMetric === "gas" ? gasThreshold : undefined,
        label: `Évolution : ${chartMetric}`,
    });
}

function alertItem(alert) {
    const cls = alert.status !== "active" ? "success" : alert.severity === "warning" ? "warning" : "";
    return `
        <div class="alert-item ${cls}">
            <div>
                <div class="alert-title">${alertTypeLabel(alert.alert_type)} — ${escapeHTML(alert.message)}</div>
                <div class="alert-meta">
                    ${severityBadge(alert.severity)} ${statusBadge(alert.status)}
                    ${escapeHTML(alert.site_name || alert.device_name || "")}
                    · ${formatNumber(alert.temperature)} °C · ${formatNumber(alert.gas, 0)} ppm
                </div>
                <div class="alert-date">${formatDate(alert.created_at)}</div>
            </div>
            ${alert.status === "active"
                ? `<button class="btn btn-success btn-small" data-resolve="${alert.id}">✅ Résoudre</button>`
                : ""}
        </div>`;
}

function renderRecentAlerts(alerts) {
    $("recentAlerts").innerHTML = alerts.length
        ? alerts.slice(0, 5).map(alertItem).join("")
        : '<p class="muted">Aucune alerte enregistrée.</p>';
}

const SITE_STATES = {
    ok: "🟢 Normal",
    alert: "🟠 Alerte",
    fire: "🔴 Incendie",
    offline: "⚫ Hors ligne",
};

function renderSitesSummary(sites) {
    if (!sites.length) {
        $("sitesSummary").innerHTML = `
            <p class="muted">Aucun site surveillé pour l'instant.</p>
            <button class="btn btn-primary btn-small" data-go-sites>➕ Créer mon premier site</button>`;
        return;
    }
    $("sitesSummary").innerHTML = sites.map(site => `
        <div class="alert-item ${site.state === "ok" ? "success" : site.state === "alert" ? "warning" : ""}">
            <div>
                <div class="alert-title">${escapeHTML(site.name)}</div>
                <div class="alert-meta">${escapeHTML(site.address || "-")}</div>
            </div>
            <span>${SITE_STATES[site.state]}</span>
        </div>`).join("");
}

async function loadDashboard() {
    const [dash, stats, status, data, sites, alerts] = await Promise.all([
        api("/api/dashboard"),
        api("/api/admin/dashboard"),
        api("/api/status"),
        api("/api/data?limit=120"),
        api("/api/sites"),
        api("/api/alerts?limit=5"),
    ]);
    renderDashboard(dash);
    renderStats(stats);
    renderStatus(status);
    history = data.measurements;
    renderChart();
    renderRecentAlerts(alerts.alerts);
    renderSitesSummary(sites.sites);
}


/* ---------- Alertes ---------- */

async function loadAlerts() {
    const filter = $("alertFilter").value;
    const data = await api(`/api/alerts?limit=500${filter ? `&status=${filter}` : ""}`);
    const alerts = data.alerts;
    $("resolveAllButton").hidden = !alerts.some(a => a.status === "active");

    if (!alerts.length) {
        $("alertsTable").innerHTML = '<p class="muted">Aucune alerte enregistrée.</p>';
        return;
    }
    $("alertsTable").innerHTML = `
        <table>
            <thead><tr>
                <th>#</th><th>Type</th><th>Sévérité</th><th>Message</th><th>Site</th>
                <th>Mesures</th><th>Statut</th><th>Date</th><th>Action</th>
            </tr></thead>
            <tbody>${alerts.map(a => `
                <tr class="${a.status === "active" ? "row-danger" : ""}">
                    <td>${a.id}</td>
                    <td>${alertTypeLabel(a.alert_type)}</td>
                    <td>${severityBadge(a.severity)}</td>
                    <td>${escapeHTML(a.message)}</td>
                    <td>${escapeHTML(a.site_name || a.device_name || "-")}</td>
                    <td>${formatNumber(a.temperature)} °C · ${formatNumber(a.humidity)} % · ${formatNumber(a.gas, 0)} ppm</td>
                    <td>${statusBadge(a.status)}${a.resolved_at
                        ? `<div class="muted">${formatDate(a.resolved_at)}${a.resolved_by_name ? ` par ${escapeHTML(a.resolved_by_name)}` : ""}</div>`
                        : ""}</td>
                    <td>${formatDate(a.created_at)}</td>
                    <td>${a.status === "active"
                        ? `<button class="btn btn-success btn-small" data-resolve="${a.id}">✅ Résoudre</button>`
                        : "-"}</td>
                </tr>`).join("")}
            </tbody>
        </table>`;
}

async function resolveAlert(id) {
    try {
        const data = await api(`/api/alerts/${id}/resolve`, { method: "PUT" });
        showToast(data.message);
        await refreshNow();
    } catch (error) {
        showToast(error.message, true);
    }
}


/* ---------- Sites ---------- */

let sitesCache = [];

async function loadSites() {
    const data = await api("/api/sites");
    const sites = data.sites;
    sitesCache = sites;
    if (!sites.length) {
        $("sitesTable").innerHTML = '<p class="muted">Aucun site enregistré. Cliquez sur « Ajouter un site » et indiquez le n° de votre ESP32 (1 par défaut).</p>';
        return;
    }
    $("sitesTable").innerHTML = `
        <p class="muted" style="margin-top:0">${sites.length} site(s) enregistré(s)</p>
        <table>
            <thead><tr><th>ID</th><th>Nom</th><th>Adresse</th><th>Coordonnées</th><th>Client</th><th>ESP32</th><th>État</th><th></th></tr></thead>
            <tbody>${sites.map(s => `
                <tr>
                    <td>${s.id}</td>
                    <td><strong>${escapeHTML(s.name)}</strong></td>
                    <td>${escapeHTML(s.address || "-")}</td>
                    <td>${s.latitude !== null && s.longitude !== null
                        ? `<a href="https://www.google.com/maps?q=${s.latitude},${s.longitude}" target="_blank" rel="noopener" style="color:var(--orange)">${formatNumber(s.latitude, 4)}, ${formatNumber(s.longitude, 4)}</a>`
                        : "-"}</td>
                    <td>${escapeHTML(s.client_name || "-")}</td>
                    <td>${s.devices.length
                        ? s.devices.map(d => `${d.online ? "🟢" : "⚫"} #${d.id}`).join("<br>")
                        : "-"}</td>
                    <td>${SITE_STATES[s.state]}</td>
                    <td style="white-space:nowrap">
                        <button class="btn btn-link btn-small" data-edit-site="${s.id}" title="Modifier">✏️</button>
                        <button class="btn btn-link btn-small" data-delete-site="${s.id}" title="Supprimer">🗑️</button>
                    </td>
                </tr>`).join("")}
            </tbody>
        </table>`;
}

let editingSiteId = null;

async function openSiteModal(site = null) {
    editingSiteId = site ? site.id : null;
    $("siteForm").reset();
    setText("siteModalTitle", site ? "Modifier le site" : "Ajouter un site");
    setText("siteSubmit", site ? "Enregistrer" : "Ajouter");

    const [users, devices] = await Promise.all([
        api("/api/users").catch(() => ({ users: [] })),
        api("/api/devices").catch(() => ({ devices: [] })),
    ]);
    $("siteClient").innerHTML = '<option value="">Aucun</option>' + users.users
        .filter(u => u.role === "client")
        .map(u => `<option value="${u.id}">${escapeHTML(u.name)} (${escapeHTML(u.email)})</option>`)
        .join("");
    $("deviceList").innerHTML = devices.devices
        .map(d => `<option value="${d.id}">${escapeHTML(d.name)}${d.site_name ? ` — ${escapeHTML(d.site_name)}` : ""}</option>`)
        .join("");

    if (site) {
        $("siteName").value = site.name;
        $("siteAddress").value = site.address || "";
        $("siteLat").value = site.latitude ?? "";
        $("siteLon").value = site.longitude ?? "";
        $("siteClient").value = site.client_id || "";
        $("siteDevice").value = site.devices[0]?.id ?? "";
    } else if (!devices.devices.some(d => d.site_id)) {
        $("siteDevice").value = devices.devices[0]?.id ?? 1;
    }
    openModal("siteModal");
}

async function saveSite(event) {
    event.preventDefault();
    const number = id => ($(id).value === "" ? null : Number($(id).value));
    try {
        const data = await api(editingSiteId ? `/api/sites/${editingSiteId}` : "/api/sites", {
            method: editingSiteId ? "PUT" : "POST",
            body: {
                name: $("siteName").value,
                address: $("siteAddress").value || null,
                latitude: number("siteLat"),
                longitude: number("siteLon"),
                client_id: number("siteClient"),
                device_id: number("siteDevice"),
            },
        });
        closeModal("siteModal");
        showToast(data.message);
        loadSites();
        loadDashboard().catch(() => {});
    } catch (error) {
        setText("siteError", error.message);
    }
}

async function deleteSite(id) {
    if (!window.confirm("Supprimer ce site ? Ses mesures et alertes sont conservées.")) return;
    try {
        const data = await api(`/api/sites/${id}`, { method: "DELETE" });
        showToast(data.message);
        loadSites();
    } catch (error) {
        showToast(error.message, true);
    }
}


/* ---------- Historique ---------- */

let historyRows = [];

async function loadHistory() {
    const data = await api(`/api/data?limit=${$("historyLimit").value}`);
    historyRows = data.measurements;
    if (!historyRows.length) {
        $("historyTable").innerHTML = '<p class="muted">Aucune mesure disponible.</p>';
        return;
    }
    $("historyTable").innerHTML = `
        <table>
            <thead><tr><th>ID</th><th>ESP32</th><th>Température</th><th>Humidité</th><th>Gaz</th><th>Flamme</th><th>Date</th></tr></thead>
            <tbody>${historyRows.map(m => `
                <tr class="${m.flame_detected ? "row-danger" : ""}">
                    <td>${m.id}</td>
                    <td>#${m.device_id}</td>
                    <td>${formatNumber(m.temperature)} °C</td>
                    <td>${formatNumber(m.humidity)} %</td>
                    <td>${formatNumber(m.gas, 0)} ppm</td>
                    <td>${m.flame_detected ? "🔥 Flamme" : "✅ Normal"}</td>
                    <td>${formatDate(m.created_at)}</td>
                </tr>`).join("")}
            </tbody>
        </table>`;
}

function exportHistory() {
    if (!historyRows.length) return;
    const header = "id;device_id;temperature;humidity;gaz;flamme;date";
    const lines = historyRows.map(m =>
        [m.id, m.device_id, m.temperature, m.humidity, m.gas, m.flame_detected, m.created_at].join(";"));
    const blob = new Blob(["﻿" + [header, ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `historique_timdeiz_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
}


/* ---------- Utilisateurs ---------- */

let usersList = [];
let editingUserId = null;

async function loadUsers() {
    const data = await api("/api/users");
    usersList = data.users;
    const me = Shell.user.id;
    $("usersTable").innerHTML = `
        <table>
            <thead><tr><th>ID</th><th>Nom</th><th>Email</th><th>Téléphone</th><th>Rôle</th><th>Sites</th><th>Statut</th><th>Créé le</th><th></th></tr></thead>
            <tbody>${usersList.map(u => `
                <tr>
                    <td>${u.id}</td>
                    <td>${escapeHTML(u.name)}${u.id === me ? ' <span class="muted">(vous)</span>' : ""}</td>
                    <td>${escapeHTML(u.email)}</td>
                    <td>${escapeHTML(u.phone || "-")}</td>
                    <td>${u.role === "admin"
                        ? '<span class="badge badge-danger">Administrateur</span>'
                        : '<span class="badge badge-neutral">Client</span>'}</td>
                    <td>${u.role === "admin" ? "Tous" : u.sites}</td>
                    <td>${u.status === "active"
                        ? '<span class="badge badge-success">Actif</span>'
                        : '<span class="badge badge-warning">Désactivé</span>'}</td>
                    <td>${formatDate(u.created_at)}</td>
                    <td style="white-space:nowrap">
                        <button class="btn btn-link btn-small" data-edit-user="${u.id}" title="Modifier">✏️</button>
                        ${u.id === me ? "" : `<button class="btn btn-link btn-small" data-delete-user="${u.id}" title="Supprimer">🗑️</button>`}
                    </td>
                </tr>`).join("")}
            </tbody>
        </table>`;
}

function openUserModal(user = null) {
    editingUserId = user ? user.id : null;
    $("userForm").reset();
    setText("userModalTitle", user ? "Modifier l'utilisateur" : "Ajouter un utilisateur");
    setText("userSubmit", user ? "Enregistrer" : "Ajouter");
    setText("userPasswordLabel", user ? "Nouveau mot de passe (laisser vide pour ne pas changer)" : "Mot de passe");
    $("userPasswordInput").required = !user;
    $("userEmailInput").disabled = Boolean(user);
    const isMe = user && user.id === Shell.user.id;
    $("userRoleInput").disabled = isMe;
    $("userStatusInput").disabled = isMe;
    if (user) {
        $("userNameInput").value = user.name;
        $("userEmailInput").value = user.email;
        $("userPhoneInput").value = user.phone || "";
        $("userRoleInput").value = user.role;
        $("userStatusInput").value = user.status === "active" ? "active" : "disabled";
    }
    openModal("userModal");
}

async function saveUser(event) {
    event.preventDefault();
    const body = {
        name: $("userNameInput").value,
        phone: $("userPhoneInput").value,
        role: $("userRoleInput").value,
        password: $("userPasswordInput").value || null,
    };
    try {
        let data;
        if (editingUserId) {
            body.status = $("userStatusInput").value;
            if (editingUserId === Shell.user.id) {
                delete body.role;
                delete body.status;
            }
            data = await api(`/api/users/${editingUserId}`, { method: "PUT", body });
        } else {
            body.email = $("userEmailInput").value;
            data = await api("/api/users", { method: "POST", body });
        }
        closeModal("userModal");
        showToast(data.message);
        loadUsers();
    } catch (error) {
        setText("userError", error.message);
    }
}

async function deleteUser(id) {
    const user = usersList.find(u => u.id === Number(id));
    if (!window.confirm(`Supprimer le compte de ${user ? user.name : "cet utilisateur"} ?`)) return;
    try {
        const data = await api(`/api/users/${id}`, { method: "DELETE" });
        showToast(data.message);
        loadUsers();
    } catch (error) {
        showToast(error.message, true);
    }
}


/* ---------- Actualisation selon la page ouverte ---------- */

const LOADERS = {
    dashboard: loadDashboard,
    alerts: loadAlerts,
    sites: loadSites,
    measurements: loadHistory,
    users: loadUsers,
};

async function refreshCurrentPage() {
    try {
        // Le tableau de bord tourne toujours pour détecter les nouvelles alertes
        const tasks = [loadDashboard()];
        const extra = LOADERS[Shell.currentPage];
        if (extra && extra !== loadDashboard && Shell.currentPage !== "measurements") tasks.push(extra());
        await Promise.all(tasks);
        setConnection(true, "Connecté au serveur");
    } catch (error) {
        setConnection(false, "Serveur injoignable");
        console.error(error);
    }
}

function onPageChange(page) {
    const loader = LOADERS[page];
    if (loader) loader().catch(error => showToast(error.message, true));
}


/* ---------- Événements ---------- */

document.addEventListener("click", event => {
    const resolve = event.target.closest("[data-resolve]");
    if (resolve) resolveAlert(resolve.dataset.resolve);
    const remove = event.target.closest("[data-delete-site]");
    if (remove) deleteSite(remove.dataset.deleteSite);
    const editSite = event.target.closest("[data-edit-site]");
    if (editSite) openSiteModal(sitesCache.find(s => s.id === Number(editSite.dataset.editSite)));
    const editUser = event.target.closest("[data-edit-user]");
    if (editUser) openUserModal(usersList.find(u => u.id === Number(editUser.dataset.editUser)));
    const removeUser = event.target.closest("[data-delete-user]");
    if (removeUser) deleteUser(removeUser.dataset.deleteUser);
    if (event.target.closest("[data-go-sites]")) showPage("sites");
    const tab = event.target.closest(".chart-tab");
    if (tab) {
        chartMetric = tab.dataset.metric;
        document.querySelectorAll(".chart-tab").forEach(t => t.classList.toggle("active", t === tab));
        renderChart();
    }
});

$("alertFilter").addEventListener("change", () => loadAlerts().catch(e => showToast(e.message, true)));
$("resolveAllButton").addEventListener("click", async () => {
    if (!window.confirm("Marquer toutes les alertes actives comme résolues ?")) return;
    try {
        const data = await api("/api/alerts/resolve-all", { method: "PUT" });
        showToast(data.message);
        refreshNow();
    } catch (error) {
        showToast(error.message, true);
    }
});
$("addSiteButton").addEventListener("click", () => openSiteModal());
$("addUserButton").addEventListener("click", () => openUserModal());
$("userForm").addEventListener("submit", saveUser);
$("siteForm").addEventListener("submit", saveSite);
$("historyLimit").addEventListener("change", () => loadHistory().catch(e => showToast(e.message, true)));
$("exportButton").addEventListener("click", exportHistory);

initShell({ role: "admin", titles: TITLES, onRefresh: refreshCurrentPage, onPageChange });
