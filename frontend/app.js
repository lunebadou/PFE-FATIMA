/* =========================================================
   TIMDEIZ INCENDIE — fonctions communes à toutes les pages
========================================================= */

// L'API est servie par le même serveur que les pages : l'adresse suit donc
// automatiquement celle utilisée dans le navigateur (localhost sur le PC,
// 192.168.x.x sur un téléphone du même Wi-Fi).
const API_PORT = window.location.port || "5000";
const API = `${window.location.protocol}//${window.location.hostname}:${API_PORT}`;

const STORAGE_TOKEN = "timdeiz_token";
const STORAGE_USER = "timdeiz_user";


/* ---------- Session ---------- */

function getToken() {
    return localStorage.getItem(STORAGE_TOKEN) || sessionStorage.getItem(STORAGE_TOKEN);
}

function getUser() {
    try {
        return JSON.parse(localStorage.getItem(STORAGE_USER) || sessionStorage.getItem(STORAGE_USER) || "null");
    } catch {
        return null;
    }
}

function saveSession(token, user, remember) {
    clearSession();
    const store = remember ? localStorage : sessionStorage;
    store.setItem(STORAGE_TOKEN, token);
    store.setItem(STORAGE_USER, JSON.stringify(user));
}

function updateStoredUser(user) {
    const store = localStorage.getItem(STORAGE_TOKEN) ? localStorage : sessionStorage;
    store.setItem(STORAGE_USER, JSON.stringify(user));
}

function clearSession() {
    [localStorage, sessionStorage].forEach(store => {
        store.removeItem(STORAGE_TOKEN);
        store.removeItem(STORAGE_USER);
    });
}

function homeFor(user) {
    return user && user.role === "admin" ? "admin.html" : "client.html";
}

/** Redirige vers la connexion si l'utilisateur n'a pas le bon rôle. */
function requireRole(role) {
    const user = getUser();
    if (!getToken() || !user) {
        window.location.replace("index.html");
        return null;
    }
    if (role && user.role !== role) {
        window.location.replace(homeFor(user));
        return null;
    }
    return user;
}

async function logout() {
    try {
        await api("/api/logout", { method: "POST" });
    } catch {
        // déjà déconnecté côté serveur : on continue
    }
    clearSession();
    window.location.replace("index.html");
}


/* ---------- Appels à l'API ---------- */

async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json" };
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    let response;
    try {
        response = await fetch(API + path, {
            method: options.method || "GET",
            headers,
            body: options.body ? JSON.stringify(options.body) : undefined,
            cache: "no-store",
        });
    } catch {
        throw new Error("Serveur injoignable. Vérifiez que l'application est lancée.");
    }

    const data = await response.json().catch(() => ({}));

    if (response.status === 401 && !path.startsWith("/api/login")) {
        clearSession();
        window.location.replace("index.html");
    }

    if (!response.ok || data.success === false) {
        let message = data.detail || data.message || `Erreur ${response.status}`;
        if (Array.isArray(message)) message = "Champs invalides : vérifiez le formulaire.";
        throw new Error(message);
    }
    return data;
}


/* ---------- Affichage ---------- */

function $(id) {
    return document.getElementById(id);
}

function setText(id, value) {
    const element = $(id);
    if (element) element.textContent = value;
}

function escapeHTML(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatNumber(value, decimals = 1) {
    if (value === null || value === undefined || value === "") return "--";
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(decimals).replace(".", ",") : "--";
}

function formatDate(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("fr-FR", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
}

function timeAgo(value) {
    if (!value) return "jamais";
    const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000);
    if (seconds < 5) return "à l'instant";
    if (seconds < 60) return `il y a ${seconds} s`;
    if (seconds < 3600) return `il y a ${Math.floor(seconds / 60)} min`;
    if (seconds < 86400) return `il y a ${Math.floor(seconds / 3600)} h`;
    return formatDate(value);
}

const ALERT_TYPES = { fire: "🔥 Incendie", gas: "💨 Fuite de gaz" };
const SEVERITIES = { critical: "Critique", warning: "Avertissement" };

function alertTypeLabel(type) {
    return ALERT_TYPES[type] || type || "Alerte";
}

function severityBadge(severity) {
    const cls = severity === "critical" ? "badge-danger" : "badge-warning";
    return `<span class="badge ${cls}">${escapeHTML(SEVERITIES[severity] || severity || "-")}</span>`;
}

function statusBadge(status) {
    return status === "active"
        ? '<span class="badge badge-danger">Active</span>'
        : '<span class="badge badge-success">Résolue</span>';
}

let toastTimer = null;

function showToast(message, isError = false) {
    const toast = $("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3500);
}


/* ---------- Petit graphique SVG (sans bibliothèque externe) ---------- */

function drawLineChart(container, points, options = {}) {
    if (!container) return;
    const values = points.map(p => p.value).filter(v => v !== null && Number.isFinite(v));
    if (values.length < 2) {
        container.innerHTML = '<p class="muted">Pas encore assez de mesures pour tracer la courbe.</p>';
        return;
    }

    const width = Math.max(300, Math.round(container.clientWidth) || 800);
    const height = 220;
    const pad = { top: 12, right: 12, bottom: 24, left: 42 };
    let min = Math.min(...values);
    let max = Math.max(...values);
    if (options.threshold !== undefined) max = Math.max(max, options.threshold * 1.05);
    if (max - min < 1) { max += 1; min -= 1; }
    const span = max - min;
    min -= span * 0.08;
    max += span * 0.08;

    const x = i => pad.left + (i / (points.length - 1)) * (width - pad.left - pad.right);
    const y = v => pad.top + (1 - (v - min) / (max - min)) * (height - pad.top - pad.bottom);

    let grid = "";
    for (let k = 0; k <= 4; k++) {
        const v = min + ((max - min) * k) / 4;
        grid += `<line class="grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${y(v)}" y2="${y(v)}"/>`;
        grid += `<text class="axis-label" x="${pad.left - 6}" y="${y(v) + 4}" text-anchor="end">${Math.round(v)}</text>`;
    }

    const labels = [0, Math.floor((points.length - 1) / 2), points.length - 1].map(i => {
        const anchor = i === 0 ? "start" : i === points.length - 1 ? "end" : "middle";
        const time = new Date(points[i].time).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
        return `<text class="axis-label" x="${x(i)}" y="${height - 6}" text-anchor="${anchor}">${time}</text>`;
    }).join("");

    const path = points
        .map((p, i) => (p.value === null ? null : `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`))
        .filter(Boolean)
        .join(" L");

    const color = options.color || "#38bdf8";
    const threshold = options.threshold !== undefined
        ? `<line class="threshold" x1="${pad.left}" x2="${width - pad.right}" y1="${y(options.threshold)}" y2="${y(options.threshold)}"/>`
        : "";

    const flames = points
        .map((p, i) => (p.flame ? `<circle cx="${x(i)}" cy="${y(p.value)}" r="4" fill="#ef4444"/>` : ""))
        .join("");

    container.innerHTML = `
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${escapeHTML(options.label || "Graphique")}">
            ${grid}${threshold}
            <path d="M${path}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/>
            ${flames}${labels}
        </svg>`;
}


/* ---------- Thème clair / sombre ---------- */

function applyTheme() {
    let dark = true;
    try {
        dark = localStorage.getItem("timdeiz_dark_mode") !== "false";
    } catch {
        // stockage indisponible : thème sombre
    }
    document.body.classList.toggle("light", !dark);
}


/* ---------- Application installable (PWA) ---------- */

if ("serviceWorker" in navigator && window.isSecureContext) {
    window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}
