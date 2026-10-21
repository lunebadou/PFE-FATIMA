/* =========================================================
   Structure commune admin / client :
   menu, profil, mot de passe, paramètres, actualisation, notifications
========================================================= */

const Shell = {
    user: null,
    onRefresh: null,
    onPageChange: null,
    titles: {},
    currentPage: "dashboard",
    timer: null,
    lastAlertId: null,
};


/* ---------- Paramètres enregistrés dans le navigateur ---------- */

function getSetting(name, fallback) {
    try {
        const value = localStorage.getItem(`timdeiz_${name}`);
        return value === null ? fallback : value;
    } catch {
        return fallback;
    }
}

function setSetting(name, value) {
    try {
        localStorage.setItem(`timdeiz_${name}`, String(value));
    } catch {
        // navigation privée : le réglage ne sera pas mémorisé
    }
}


/* ---------- Navigation ---------- */

function showPage(page) {
    if (!$(`page-${page}`)) return;
    Shell.currentPage = page;
    document.querySelectorAll(".page").forEach(p => p.classList.toggle("active", p.id === `page-${page}`));
    document.querySelectorAll(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.page === page));
    setText("pageTitle", Shell.titles[page] || "");
    closeSidebar();
    if (Shell.onPageChange) Shell.onPageChange(page);
}

function closeSidebar() {
    $("sidebar")?.classList.remove("open");
    $("sidebarBackdrop")?.classList.remove("open");
}

function setupNavigation() {
    document.querySelectorAll(".nav-item").forEach(button =>
        button.addEventListener("click", () => showPage(button.dataset.page)));

    $("menuButton")?.addEventListener("click", () => {
        $("sidebar").classList.toggle("open");
        $("sidebarBackdrop").classList.toggle("open");
    });
    $("sidebarBackdrop")?.addEventListener("click", closeSidebar);
    $("logoutButton")?.addEventListener("click", logout);
    $("refreshButton")?.addEventListener("click", async () => {
        await refreshNow();
        showToast("Données actualisées.");
    });
}


/* ---------- Fenêtres modales ---------- */

function openModal(id) {
    const modal = $(id);
    modal.classList.add("open");
    modal.querySelector(".form-error")?.replaceChildren();
    modal.querySelector("input")?.focus();
}

function closeModal(id) {
    $(id).classList.remove("open");
}

function setupModals() {
    document.querySelectorAll(".modal").forEach(modal => {
        modal.addEventListener("click", event => {
            if (event.target === modal || event.target.hasAttribute("data-close")) closeModal(modal.id);
        });
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape") document.querySelectorAll(".modal.open").forEach(m => closeModal(m.id));
    });
}


/* ---------- Profil ---------- */

function renderProfile(user) {
    const initials = (user.name || "?").split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
    setText("profileAvatar", initials);
    setText("profileName", user.name);
    setText("profileEmail", user.email);
    setText("profileNameValue", user.name);
    setText("profileEmailValue", user.email);
    setText("profilePhoneValue", user.phone || "Non renseigné");
    setText("userName", user.name);
}

function setupProfile() {
    $("editProfileButton")?.addEventListener("click", () => {
        $("profileNameInput").value = Shell.user.name || "";
        $("profileEmailInput").value = Shell.user.email || "";
        $("profilePhoneInput").value = Shell.user.phone || "";
        openModal("profileModal");
    });

    $("profileForm")?.addEventListener("submit", async event => {
        event.preventDefault();
        try {
            const data = await api("/api/profile", {
                method: "PUT",
                body: {
                    name: $("profileNameInput").value,
                    email: $("profileEmailInput").value,
                    phone: $("profilePhoneInput").value || null,
                },
            });
            Shell.user = data.user;
            updateStoredUser(data.user);
            renderProfile(data.user);
            closeModal("profileModal");
            showToast(data.message);
        } catch (error) {
            setText("profileError", error.message);
        }
    });

    $("changePasswordButton")?.addEventListener("click", () => {
        $("passwordForm").reset();
        openModal("passwordModal");
    });

    $("passwordForm")?.addEventListener("submit", async event => {
        event.preventDefault();
        if ($("newPassword").value !== $("confirmPassword").value) {
            setText("passwordError", "Les deux nouveaux mots de passe ne correspondent pas.");
            return;
        }
        try {
            const data = await api("/api/change-password", {
                method: "PUT",
                body: { current_password: $("currentPassword").value, new_password: $("newPassword").value },
            });
            closeModal("passwordModal");
            showToast(data.message);
        } catch (error) {
            setText("passwordError", error.message);
        }
    });
}


/* ---------- Paramètres et actualisation automatique ---------- */

function scheduleRefresh() {
    clearInterval(Shell.timer);
    if (getSetting("auto_refresh", "true") === "true") {
        Shell.timer = setInterval(refreshNow, Number(getSetting("refresh_interval", Shell.defaultInterval)));
    }
}

async function refreshNow() {
    if (Shell.onRefresh) await Shell.onRefresh();
}

function setupSettings() {
    const bindToggle = (id, name, after) => {
        const input = $(id);
        if (!input) return;
        input.checked = getSetting(name, "true") === "true";
        input.addEventListener("change", () => {
            setSetting(name, input.checked);
            if (after) after(input.checked);
        });
    };

    bindToggle("notificationsSetting", "notifications", on => {
        if (on && "Notification" in window && Notification.permission === "default") Notification.requestPermission();
    });
    bindToggle("autoRefreshSetting", "auto_refresh", scheduleRefresh);
    bindToggle("darkModeSetting", "dark_mode", applyTheme);

    const interval = $("refreshIntervalSetting");
    if (interval) {
        interval.value = getSetting("refresh_interval", Shell.defaultInterval);
        interval.addEventListener("change", () => {
            setSetting("refresh_interval", interval.value);
            scheduleRefresh();
            showToast(`Actualisation toutes les ${interval.selectedOptions[0].textContent.trim()}.`);
        });
    }
}


/* ---------- Notification à chaque nouvelle alerte ---------- */

function beep() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        [0, 0.3, 0.6].forEach(delay => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.frequency.value = 880;
            gain.gain.value = 0.15;
            osc.connect(gain).connect(ctx.destination);
            osc.start(ctx.currentTime + delay);
            osc.stop(ctx.currentTime + delay + 0.18);
        });
    } catch {
        // pas de son disponible
    }
}

/** À appeler avec l'alerte active la plus récente ; prévient seulement si elle est nouvelle. */
function notifyIfNewAlert(alert) {
    const id = alert ? alert.id : 0;
    const isNew = Shell.lastAlertId !== null && id > Shell.lastAlertId;
    Shell.lastAlertId = Math.max(Shell.lastAlertId ?? 0, id);
    if (!isNew || getSetting("notifications", "true") !== "true") return;

    const text = `${alertTypeLabel(alert.alert_type)} : ${alert.message}`;
    showToast(`🚨 ${text}`, true);
    beep();
    if ("Notification" in window && Notification.permission === "granted") {
        new Notification("TIMDEIZ Incendie", { body: text, icon: "icons/logo.jpg" });
    }
}


/* ---------- Indicateur de connexion au serveur ---------- */

function setConnection(ok, text) {
    const dot = $("connectionDot");
    if (dot) dot.className = `connection-dot ${ok ? "ok" : "ko"}`;
    setText("connectionText", text);
}


/* ---------- Démarrage ---------- */

function initShell({ role, titles, onRefresh, onPageChange, defaultInterval = "10000" }) {
    const user = requireRole(role);
    if (!user) return null;
    Object.assign(Shell, { user, titles, onRefresh, onPageChange, defaultInterval });

    applyTheme();
    setupNavigation();
    setupModals();
    setupProfile();
    setupSettings();
    renderProfile(user);

    // Recharge le profil depuis le serveur (au cas où il a changé ailleurs)
    api("/api/profile").then(data => {
        Shell.user = data.user;
        updateStoredUser(data.user);
        renderProfile(data.user);
    }).catch(() => {});

    refreshNow();
    scheduleRefresh();
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) refreshNow();
    });
    return user;
}
