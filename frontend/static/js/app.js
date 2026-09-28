/**
 * Tempo Worklog Console — Frontend Client Application
 * Communicates with /api REST endpoints and renders UI components.
 */

// State
let activeTimer = null;
let timerInterval = null;
let currentSummary = null;
let currentConfig = null;

// DOM Elements
document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

async function initApp() {
    setupEventListeners();
    await loadConfig();
    await loadHealth();
    await refreshTimer();
    await refreshSummary();
    await refreshWorklogs();

    // Auto-poll timer every 2 seconds if running
    setInterval(() => {
        if (activeTimer && activeTimer.active) {
            updateLiveTimerDisplay();
        }
    }, 1000);

    // Set today's date in quick log
    const todayInput = document.getElementById("log-date");
    if (todayInput) {
        todayInput.value = new Date().toISOString().split("T")[0];
    }
}

function showToast(msg, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `ui-toast ui-toast-${type}`;
    toast.style.cssText = `
        padding: 12px 18px;
        margin-bottom: 8px;
        border-radius: 8px;
        font-size: 14px;
        display: flex;
        align-items: center;
        gap: 10px;
        background: ${type === 'danger' ? '#7f1d1d' : type === 'success' ? '#064e3b' : '#1e1b4b'};
        color: #f8fafc;
        border: 1px solid ${type === 'danger' ? '#ef4444' : type === 'success' ? '#10b981' : '#6366f1'};
        box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        animation: fadeIn 0.2s ease-out;
    `;
    toast.innerHTML = `<span>${msg}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ----------------- Auth & API Helpers -----------------

function getAuthToken() {
    try {
        const urlParams = new URLSearchParams(window.location.search);
        const urlToken = urlParams.get("token");
        if (urlToken) {
            sessionStorage.setItem("tempo_web_token", urlToken);
            urlParams.delete("token");
            const cleanQuery = urlParams.toString() ? "?" + urlParams.toString() : "";
            const cleanUrl = window.location.pathname + cleanQuery + window.location.hash;
            window.history.replaceState({}, document.title, cleanUrl);
        }
    } catch (e) {
        console.error("Token parse error:", e);
    }
    return sessionStorage.getItem("tempo_web_token") || "";
}

function apiFetch(url, options = {}) {
    const token = getAuthToken();
    const headers = Object.assign({}, options.headers || {});
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }
    return fetch(url, Object.assign({}, options, { headers }));
}

// ----------------- API Calls -----------------

async function loadHealth() {
    try {
        const res = await apiFetch("/api/health");
        const data = await res.json();
        updateHealthBadges(data);
    } catch (err) {
        console.error("Health check error:", err);
    }
}

function updateHealthBadges(data) {
    const tempoBadge = document.getElementById("badge-tempo");
    const jiraBadge = document.getElementById("badge-jira");

    if (tempoBadge) {
        if (data.tempo_ok) {
            tempoBadge.className = "ui-badge ui-badge-success";
            tempoBadge.textContent = "Tempo: Connected";
        } else {
            tempoBadge.className = "ui-badge ui-badge-danger";
            tempoBadge.textContent = "Tempo: Disconnected";
        }
    }

    if (jiraBadge) {
        if (data.jira_ok === true) {
            jiraBadge.className = "ui-badge ui-badge-success";
            jiraBadge.textContent = "Jira: Connected";
        } else if (data.jira_ok === false) {
            jiraBadge.className = "ui-badge ui-badge-danger";
            jiraBadge.textContent = "Jira: Error";
        } else {
            jiraBadge.className = "ui-badge ui-badge-secondary";
            jiraBadge.textContent = "Jira: Unconfigured";
        }
    }
}

async function loadConfig() {
    try {
        const res = await apiFetch("/api/config");
        currentConfig = await res.json();
        populateConfigModal(currentConfig);
    } catch (err) {
        console.error("Failed to load config:", err);
    }
}

function populateConfigModal(cfg) {
    if (!cfg) return;
    document.getElementById("cfg-tempo-token").value = cfg.tempo_token_preview || "";
    document.getElementById("cfg-jira-base").value = cfg.jira_base_url || "";
    document.getElementById("cfg-jira-email").value = cfg.jira_email || "";
    document.getElementById("cfg-jira-token").value = cfg.jira_token_set ? "••••••••••••••••" : "";
    document.getElementById("cfg-jira-account").value = cfg.jira_account_id || "";
    document.getElementById("cfg-jira-server").checked = Boolean(cfg.is_server);
}

async function saveConfig() {
    const tempoToken = document.getElementById("cfg-tempo-token").value.trim();
    const jiraBase = document.getElementById("cfg-jira-base").value.trim();
    const jiraEmail = document.getElementById("cfg-jira-email").value.trim();
    const jiraToken = document.getElementById("cfg-jira-token").value.trim();
    const jiraAccount = document.getElementById("cfg-jira-account").value.trim();
    const isServer = document.getElementById("cfg-jira-server").checked;
    const useKeyring = document.getElementById("cfg-storage-keyring").checked;

    const payload = {
        tempo_token: tempoToken.startsWith("•••") ? "" : tempoToken,
        jira_base_url: jiraBase,
        jira_email: jiraEmail,
        jira_token: jiraToken.startsWith("•••") ? "" : jiraToken,
        jira_account_id: jiraAccount,
        is_server: isServer,
        use_keyring: useKeyring,
    };

    try {
        const res = await apiFetch("/api/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (res.ok) {
            showToast("Configuration saved successfully!", "success");
            closeConfigModal();
            loadHealth();
            loadConfig();
        } else {
            showToast(`Save failed: ${data.error}`, "danger");
        }
    } catch (err) {
        showToast(`Save error: ${err}`, "danger");
    }
}

// ----------------- Stopwatch / Timer -----------------

async function refreshTimer() {
    try {
        const res = await apiFetch("/api/timer");
        activeTimer = await res.json();
        renderTimerWidget(activeTimer);
    } catch (err) {
        console.error("Timer check error:", err);
    }
}

function renderTimerWidget(timer) {
    const panel = document.getElementById("timer-panel");
    const display = document.getElementById("timer-display");
    const label = document.getElementById("timer-label");
    const startBtn = document.getElementById("btn-start-timer");
    const stopBtn = document.getElementById("btn-stop-timer");
    const discardBtn = document.getElementById("btn-discard-timer");

    if (timer && timer.active) {
        display.textContent = timer.formatted_duration || "00:00:00";
        label.innerHTML = `<strong>${timer.issue || timer.issue_id}</strong> &bull; Billable: ~${timer.elapsed_hours}h <br><span style="color:#94a3b8;font-size:12px">${timer.description || 'No description'}</span>`;
        if (startBtn) startBtn.style.display = "none";
        if (stopBtn) stopBtn.style.display = "inline-flex";
        if (discardBtn) discardBtn.style.display = "inline-flex";
    } else {
        display.textContent = "00:00:00";
        label.textContent = "○ Stopwatch Idle (Ready to start)";
        if (startBtn) startBtn.style.display = "inline-flex";
        if (stopBtn) stopBtn.style.display = "none";
        if (discardBtn) discardBtn.style.display = "none";
    }
}

function updateLiveTimerDisplay() {
    if (!activeTimer || !activeTimer.started_at) return;
    const start = new Date(activeTimer.started_at).getTime();
    const now = new Date().getTime();
    const elapsedSecs = Math.max(0, Math.floor((now - start) / 1000));

    const hours = String(Math.floor(elapsedSecs / 3600)).padStart(2, "0");
    const minutes = String(Math.floor((elapsedSecs % 3600) / 60)).padStart(2, "0");
    const seconds = String(elapsedSecs % 60).padStart(2, "0");

    const display = document.getElementById("timer-display");
    if (display) {
        display.textContent = `${hours}:${minutes}:${seconds}`;
    }
}

async function startNewTimer() {
    const issue = document.getElementById("timer-input-issue").value.trim();
    const desc = document.getElementById("timer-input-desc").value.trim();

    if (!issue) {
        showToast("Please enter a Jira Issue Key (e.g. PROJ-123)", "warning");
        return;
    }

    try {
        const res = await apiFetch("/api/timer/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ issue, description: desc }),
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`Timer started for ${issue}!`, "success");
            document.getElementById("timer-input-issue").value = "";
            document.getElementById("timer-input-desc").value = "";
            refreshTimer();
        } else {
            showToast(data.error, "danger");
        }
    } catch (err) {
        showToast(`Error: ${err}`, "danger");
    }
}

async function stopActiveTimer() {
    if (!confirm("Stop timer and submit worklog to Tempo?")) return;
    try {
        const res = await apiFetch("/api/timer/stop", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`Logged ${data.hours}h to ${data.issue}! Worklog ID: ${data.result.tempoWorklogId || 'OK'}`, "success");
            refreshTimer();
            refreshSummary();
            refreshWorklogs();
        } else {
            showToast(data.error, "danger");
        }
    } catch (err) {
        showToast(`Error stopping timer: ${err}`, "danger");
    }
}

async function discardActiveTimer() {
    if (!confirm("Are you sure you want to discard this timer without logging?")) return;
    try {
        const res = await apiFetch("/api/timer/discard", { method: "POST" });
        if (res.ok) {
            showToast("Timer discarded.", "info");
            refreshTimer();
        }
    } catch (err) {
        showToast(`Error: ${err}`, "danger");
    }
}

// ----------------- Quick Log Work -----------------

async function submitQuickLog(e) {
    if (e) e.preventDefault();
    const issue = document.getElementById("log-issue").value.trim();
    const hours = parseFloat(document.getElementById("log-hours").value);
    const date = document.getElementById("log-date").value;
    const desc = document.getElementById("log-desc").value.trim();

    if (!issue || isNaN(hours) || hours <= 0) {
        showToast("Provide a valid issue key and hours > 0", "warning");
        return;
    }

    const btn = document.getElementById("btn-submit-worklog");
    btn.disabled = true;
    btn.textContent = "Logging to Tempo...";

    try {
        const res = await apiFetch("/api/worklog", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ issue, hours, date, description: desc }),
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`Successfully logged ${hours}h on ${issue}!`, "success");
            document.getElementById("log-hours").value = "";
            document.getElementById("log-desc").value = "";
            refreshSummary();
            refreshWorklogs();
        } else {
            showToast(`Failed: ${data.error}`, "danger");
        }
    } catch (err) {
        showToast(`Network error: ${err}`, "danger");
    } finally {
        btn.disabled = false;
        btn.textContent = "Log Work to Tempo";
    }
}

// ----------------- Metrics & Worklogs -----------------

async function refreshSummary() {
    try {
        const res = await apiFetch("/api/summary");
        currentSummary = await res.json();
        renderSummaryMetrics(currentSummary);
    } catch (err) {
        console.error("Summary error:", err);
    }
}

function renderSummaryMetrics(summary) {
    if (!summary) return;
    const totalHours = summary.total_hours || 0;
    const todayStr = new Date().toISOString().split("T")[0];
    const todayHours = (summary.daily_totals && summary.daily_totals[todayStr]) || 0;

    // Daily
    const todayVal = document.getElementById("stat-today-hours");
    const todayBar = document.getElementById("stat-today-bar");
    if (todayVal) todayVal.textContent = `${todayHours.toFixed(2)}h / 8.00h`;
    if (todayBar) {
        const pct = Math.min(100, Math.round((todayHours / 8.0) * 100));
        todayBar.style.width = `${pct}%`;
        todayBar.textContent = `${pct}%`;
    }

    // Weekly
    const weekVal = document.getElementById("stat-week-hours");
    const weekBar = document.getElementById("stat-week-bar");
    if (weekVal) weekVal.textContent = `${totalHours.toFixed(2)}h / 40.00h`;
    if (weekBar) {
        const pct = Math.min(100, Math.round((totalHours / 40.0) * 100));
        weekBar.style.width = `${pct}%`;
        weekBar.textContent = `${pct}%`;
    }

    // Issues breakdown
    const issuesContainer = document.getElementById("issues-breakdown-list");
    if (issuesContainer) {
        issuesContainer.innerHTML = "";
        const issues = summary.issue_totals || {};
        const keys = Object.keys(issues).sort((a, b) => issues[b] - issues[a]);
        if (keys.length === 0) {
            issuesContainer.innerHTML = `<p style="color:#64748b;font-size:13px">No logged issues recorded yet this week.</p>`;
        } else {
            keys.slice(0, 6).forEach((key) => {
                const hrs = issues[key];
                const pct = Math.min(100, Math.round((hrs / Math.max(1, totalHours)) * 100));
                const item = document.createElement("div");
                item.style.marginBottom = "10px";
                item.innerHTML = `
                    <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px">
                        <span style="font-weight:600;color:#c7d2fe">${key}</span>
                        <span style="color:#94a3b8">${hrs.toFixed(2)}h (${pct}%)</span>
                    </div>
                    <div class="ui-progress" style="height:6px">
                        <div class="ui-progress-bar" style="width:${pct}%;background:#6366f1"></div>
                    </div>
                `;
                issuesContainer.appendChild(item);
            });
        }
    }
}

async function refreshWorklogs() {
    try {
        const res = await apiFetch("/api/worklogs?limit=15");
        const data = await res.json();
        renderWorklogTable(data.worklogs || []);
    } catch (err) {
        console.error("Failed to load worklogs:", err);
    }
}

function renderWorklogTable(logs) {
    const tbody = document.getElementById("worklog-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (logs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#64748b;padding:24px">No worklog entries recorded yet.</td></tr>`;
        return;
    }

    logs.forEach((log) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td style="font-weight:500;color:#94a3b8">${escapeHtml(log.start_date || "-")}</td>
            <td><span class="ui-badge ui-badge-primary">${escapeHtml(log.issue_key || log.issue_id || "-")}</span></td>
            <td style="font-weight:600;color:#f8fafc">${(log.hours || 0).toFixed(2)}h</td>
            <td style="color:#cbd5e1;max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(log.description || "")}</td>
            <td style="color:#64748b;font-size:12px">#${escapeHtml(log.tempo_worklog_id || "-")}</td>
        `;
        tbody.appendChild(tr);
    });
}

// ----------------- Modal Controls -----------------

function openConfigModal() {
    const modal = document.getElementById("config-modal");
    if (modal) modal.classList.add("ui-active");
}

function closeConfigModal() {
    const modal = document.getElementById("config-modal");
    if (modal) modal.classList.remove("ui-active");
}

function setupEventListeners() {
    // Buttons
    document.getElementById("btn-settings")?.addEventListener("click", openConfigModal);
    document.getElementById("btn-close-modal")?.addEventListener("click", closeConfigModal);
    document.getElementById("btn-save-config")?.addEventListener("click", saveConfig);
    document.getElementById("btn-test-health")?.addEventListener("click", async () => {
        showToast("Testing connection...", "info");
        await loadHealth();
        showToast("Health test completed!", "success");
    });

    document.getElementById("btn-refresh")?.addEventListener("click", () => {
        loadHealth();
        refreshTimer();
        refreshSummary();
        refreshWorklogs();
        showToast("Dashboard refreshed", "info");
    });

    document.getElementById("btn-start-timer")?.addEventListener("click", startNewTimer);
    document.getElementById("btn-stop-timer")?.addEventListener("click", stopActiveTimer);
    document.getElementById("btn-discard-timer")?.addEventListener("click", discardActiveTimer);
    document.getElementById("form-quick-log")?.addEventListener("submit", submitQuickLog);

    // Quick chips
    document.querySelectorAll(".chip-hours")?.forEach((btn) => {
        btn.addEventListener("click", () => {
            const h = btn.getAttribute("data-hours");
            document.getElementById("log-hours").value = h;
        });
    });

    // Close modal on backdrop click
    document.getElementById("config-modal")?.addEventListener("click", (e) => {
        if (e.target.id === "config-modal") closeConfigModal();
    });
}
