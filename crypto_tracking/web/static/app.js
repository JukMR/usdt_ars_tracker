/* Crypto Tracker dashboard — vanilla JS, no build step. */
(() => {
  "use strict";

  const CFG = window.TRACKER_CONFIG || {};
  const PALETTE = ["#4f8cff", "#22d3ee", "#a78bfa", "#34d399", "#fbbf24", "#fb7185", "#60a5fa", "#f472b6"];

  const state = {
    config: null,
    pairs: [],
    overview: null,
    alerts: [],
    events: [],
    selectedPair: null,
    range: "24h",
    paused: false,
    chart: null,
    timer: null,
    refreshing: false,
    lastLoadedAt: null,
  };

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  // ------------------------------------------------------------------ helpers
  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });

    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }

    if (!response.ok) {
      const message =
        payload && (payload.error || payload.message)
          ? payload.error || payload.message
          : `Request failed with HTTP ${response.status}`;
      throw new Error(message);
    }
    return payload;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => {
      const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
      return map[character];
    });
  }

  function fmtNumber(value) {
    if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
      return "—";
    }
    const number = Number(value);
    const absolute = Math.abs(number);
    const maximumFractionDigits = absolute >= 1000 ? 2 : absolute >= 1 ? 4 : 8;
    const minimumFractionDigits = absolute >= 1000 ? 2 : 0;
    return new Intl.NumberFormat(undefined, { maximumFractionDigits, minimumFractionDigits }).format(number);
  }

  function fmtPercent(value) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) {
      return "—";
    }
    const number = Number(value);
    return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
  }

  function fmtTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "—";
    }
    return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
  }

  function fmtRelative(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "—";
    }
    const seconds = Math.round((date.getTime() - Date.now()) / 1000);
    const absolute = Math.abs(seconds);
    const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

    if (absolute < 60) return formatter.format(seconds, "second");
    if (absolute < 3600) return formatter.format(Math.round(seconds / 60), "minute");
    if (absolute < 86400) return formatter.format(Math.round(seconds / 3600), "hour");
    return formatter.format(Math.round(seconds / 86400), "day");
  }

  function pairKey(asset, quoteCurrency) {
    return `${asset}|${quoteCurrency}`;
  }

  function splitPair(key) {
    return String(key || "").split("|");
  }

  function labelForPairKey(key) {
    const [asset, quote] = splitPair(key);
    return asset && quote ? `${asset}/${quote}` : "—";
  }

  function mergePairs(...lists) {
    const merged = new Map();
    for (const list of lists) {
      for (const pair of list || []) {
        merged.set(pairKey(pair.asset, pair.quote_currency), pair);
      }
    }
    return Array.from(merged.values()).sort((a, b) => {
      const left = pairKey(a.asset, a.quote_currency);
      const right = pairKey(b.asset, b.quote_currency);
      return left.localeCompare(right);
    });
  }

  function setStatus(kind, text) {
    const badge = $("#status-badge");
    badge.classList.remove("live", "offline", "paused");
    if (kind) badge.classList.add(kind);
    $("#status-text").textContent = text;
  }

  function showError(message) {
    const banner = $("#error-banner");
    banner.textContent = message;
    banner.classList.remove("hidden");
  }

  function hideError() {
    $("#error-banner").classList.add("hidden");
  }

  let toastTimer = null;
  function toast(message, kind = "success") {
    const element = $("#toast");
    element.textContent = message;
    element.className = `toast ${kind}`;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => element.classList.add("hidden"), 4500);
  }

  // ------------------------------------------------------------------- config
  async function loadConfig() {
    const config = await api("/api/config");
    state.config = config;

    if (!config.ranges.includes(state.range)) {
      state.range = config.ranges.includes("24h") ? "24h" : config.ranges[0];
    }

    renderRangeButtons(config.ranges);
    renderProviderChips(config.providers);
    renderChannelCheckboxes(config.notifiers, config.default_channels);
    updatePairOptions(config.pairs, []);
  }

  function renderRangeButtons(ranges) {
    const container = $("#range-buttons");
    container.innerHTML = ranges
      .map(
        (range) =>
          `<button type="button" data-range="${escapeHtml(range)}" class="${range === state.range ? "active" : ""}">${escapeHtml(range)}</button>`,
      )
      .join("");
  }

  function renderProviderChips(providers) {
    const container = $("#provider-chips");
    if (!providers || providers.length === 0) {
      container.innerHTML = '<span class="chip">No providers enabled</span>';
      return;
    }
    container.innerHTML = providers.map((provider) => `<span class="chip">${escapeHtml(provider)}</span>`).join("");
  }

  function renderChannelCheckboxes(notifiers, defaultChannels) {
    const container = $("#alert-channels");
    if (!notifiers || notifiers.length === 0) {
      container.innerHTML = '<span class="muted small">No channels available</span>';
      return;
    }

    const defaults = new Set(defaultChannels || []);
    container.innerHTML = notifiers
      .map(
        (notifier) =>
          `<label class="checkbox"><input type="checkbox" class="channel-checkbox" value="${escapeHtml(
            notifier.name,
          )}" ${defaults.has(notifier.name) ? "checked" : ""}> ${escapeHtml(notifier.name)}</label>`,
      )
      .join("");
  }

  function updatePairOptions(configuredPairs, overviewPairs) {
    state.pairs = mergePairs(configuredPairs, overviewPairs, state.pairs);
    const keys = state.pairs.map((pair) => pairKey(pair.asset, pair.quote_currency));

    if (!state.selectedPair || !keys.includes(state.selectedPair)) {
      state.selectedPair = keys[0] || null;
    }

    const options = state.pairs
      .map(
        (pair) =>
          `<option value="${escapeHtml(pairKey(pair.asset, pair.quote_currency))}">${escapeHtml(
            `${pair.asset}/${pair.quote_currency}`,
          )}</option>`,
      )
      .join("");

    const pairSelect = $("#pair-select");
    pairSelect.innerHTML = options || '<option value="">No pairs</option>';
    if (state.selectedPair) pairSelect.value = state.selectedPair;

    const alertPair = $("#alert-pair");
    const currentAlertPair = alertPair.value;
    alertPair.innerHTML = options || '<option value="">No pairs</option>';
    alertPair.value = keys.includes(currentAlertPair) ? currentAlertPair : state.selectedPair || "";

    updateSourceOptions();
    updateTradingViewLink();
  }

  function updateSourceOptions() {
    const select = $("#alert-source");
    if (!select) return;

    const selected = $("#alert-pair").value;
    const entry = (state.overview?.pairs || []).find(
      (pair) => pairKey(pair.asset, pair.quote_currency) === selected,
    );
    const current = select.value;
    const sources = entry?.sources || [];

    select.innerHTML =
      '<option value="">Any source</option>' +
      sources.map((source) => `<option value="${escapeHtml(source)}">${escapeHtml(source)}</option>`).join("");

    if (Array.from(select.options).some((option) => option.value === current)) {
      select.value = current;
    }
  }

  function updateTradingViewLink() {
    const link = $("#tradingview-link");
    const entry =
      state.pairs.find((pair) => pairKey(pair.asset, pair.quote_currency) === state.selectedPair) ||
      (state.overview?.pairs || []).find(
        (pair) => pairKey(pair.asset, pair.quote_currency) === state.selectedPair,
      );
    link.href = entry?.tradingview_url || "https://www.tradingview.com/";
  }

  // ------------------------------------------------------------------ overview
  async function loadOverview() {
    const overview = await api(`/api/overview?range=${encodeURIComponent(state.range)}`);
    state.overview = overview;

    updatePairOptions(state.config?.pairs || [], overview.pairs || []);
    renderPriceCards(overview.pairs || []);
    updateSourceOptions();
    updateTradingViewLink();
    return overview;
  }

  function renderPriceCards(pairs) {
    const container = $("#price-cards");
    if (!pairs || pairs.length === 0) {
      container.innerHTML =
        '<div class="empty">No prices yet. Start the poller with <code>uv run crypto-track serve</code> or fetch one round with <code>uv run crypto-track poll --once</code>.</div>';
      return;
    }

    container.innerHTML = pairs
      .map((pair) => {
        const key = pairKey(pair.asset, pair.quote_currency);
        const latest = pair.latest;
        const stats = pair.stats || {};
        const change = stats.change_percent;
        const changeClass = change > 0 ? "up" : change < 0 ? "down" : "flat";
        const selected = key === state.selectedPair ? " selected" : "";

        return `<article class="price-card${selected}" data-pair="${escapeHtml(key)}" tabindex="0" role="button" aria-label="Show ${escapeHtml(
          pair.pair,
        )} chart">
          <div class="price-card-head">
            <div class="pair-name">${escapeHtml(pair.asset)}<span>/${escapeHtml(pair.quote_currency)}</span></div>
            <span class="change-badge ${changeClass}">${fmtPercent(change)}</span>
          </div>
          <div class="price-value">${latest ? fmtNumber(latest.price) : "—"}</div>
          <div class="price-meta">
            <span>Bid ${latest ? fmtNumber(latest.bid) : "—"}</span>
            <span>Ask ${latest ? fmtNumber(latest.ask) : "—"}</span>
          </div>
          <div class="price-range">
            <span>Low ${fmtNumber(stats.min)}</span>
            <span>High ${fmtNumber(stats.max)}</span>
          </div>
          <div class="price-source">
            ${latest ? `${escapeHtml(latest.source)} · ${escapeHtml(fmtRelative(latest.timestamp))}` : "no data"}
          </div>
        </article>`;
      })
      .join("");
  }

  // ------------------------------------------------------------------- history
  async function loadHistory() {
    if (!state.selectedPair) {
      renderChart([]);
      $("#chart-subtitle").textContent = "Select a pair to inspect its history.";
      return;
    }

    const [asset, quote] = splitPair(state.selectedPair);
    const params = new URLSearchParams({
      asset,
      quote_currency: quote,
      range: state.range,
      max_points: "800",
    });
    const data = await api(`/api/prices/history?${params.toString()}`);

    $("#chart-subtitle").textContent = `${asset}/${quote} · ${state.range} · ${data.points.length} point(s)`;
    renderChart(data.points || []);
    updateTradingViewLink();
  }

  function renderChart(points) {
    const empty = !points || points.length === 0;
    $("#chart-empty").classList.toggle("hidden", !empty);

    if (typeof Chart === "undefined") {
      $("#chart-empty").textContent = "Chart library failed to load. Reinstall the static vendor file.";
      $("#chart-empty").classList.remove("hidden");
      return;
    }

    const grouped = new Map();
    for (const point of points || []) {
      if (!grouped.has(point.source)) grouped.set(point.source, []);
      grouped.get(point.source).push({ x: point.t, y: point.price });
    }

    const datasets = Array.from(grouped.entries()).map(([source, data], index) => ({
      label: source,
      data,
      borderColor: PALETTE[index % PALETTE.length],
      backgroundColor: PALETTE[index % PALETTE.length],
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 3,
      tension: 0.22,
      fill: false,
    }));

    if (!state.chart) {
      state.chart = new Chart($("#price-chart").getContext("2d"), {
        type: "line",
        data: { datasets: [] },
        options: chartOptions(),
      });
    }

    state.chart.data.datasets = datasets;
    state.chart.options.plugins.legend.display = datasets.length > 1;

    if (points && points.length > 0) {
      const first = points[0].t;
      const last = points[points.length - 1].t;
      const pad = first === last ? 60 * 60 * 1000 : 0;
      state.chart.options.scales.x.min = first - pad;
      state.chart.options.scales.x.max = last + pad;
    } else {
      state.chart.options.scales.x.min = undefined;
      state.chart.options.scales.x.max = undefined;
    }

    state.chart.update("none");
  }

  function chartOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      plugins: {
        legend: {
          display: true,
          labels: { color: "#8a9ab5", boxWidth: 12, boxHeight: 2, usePointStyle: true },
        },
        tooltip: {
          backgroundColor: "#0f172a",
          borderColor: "#2b3a55",
          borderWidth: 1,
          titleColor: "#e8eef9",
          bodyColor: "#cbd5e1",
          padding: 10,
          callbacks: {
            title: (items) => (items.length ? new Date(items[0].parsed.x).toLocaleString() : ""),
            label: (context) => `${context.dataset.label}: ${fmtNumber(context.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          type: "linear",
          grid: { color: "rgba(31, 43, 64, 0.55)" },
          border: { color: "#1f2b40" },
          ticks: {
            color: "#64748b",
            maxTicksLimit: 8,
            callback: (value) => formatAxisTime(Number(value)),
          },
        },
        y: {
          position: "right",
          grid: { color: "rgba(31, 43, 64, 0.55)" },
          border: { color: "#1f2b40" },
          ticks: {
            color: "#64748b",
            maxTicksLimit: 7,
            callback: (value) => fmtNumber(Number(value)),
          },
        },
      },
    };
  }

  function formatAxisTime(milliseconds) {
    const date = new Date(milliseconds);
    if (Number.isNaN(date.getTime())) return "";
    if (["1h", "6h", "24h"].includes(state.range)) {
      return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    }
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  // -------------------------------------------------------------------- alerts
  async function loadAlerts() {
    const data = await api("/api/alerts");
    state.alerts = data.data || [];
    renderAlerts();
  }

  function renderAlerts() {
    const body = $("#alerts-body");
    if (!state.alerts.length) {
      body.innerHTML = '<tr><td colspan="6" class="empty-cell">No alerts yet.</td></tr>';
      return;
    }

    body.innerHTML = state.alerts
      .map((alert) => {
        const channels = alert.channels.length
          ? alert.channels.map((channel) => `<span class="chip">${escapeHtml(channel)}</span>`).join("")
          : '<span class="muted">none</span>';
        const details = [alert.label, alert.source, alert.repeat ? "repeat" : null].filter(Boolean);
        return `<tr data-alert-id="${alert.id}">
          <td>
            <label class="switch" title="Enable or disable this alert">
              <input type="checkbox" class="alert-toggle" ${alert.enabled ? "checked" : ""}>
              <span></span>
            </label>
          </td>
          <td class="alert-condition">
            <div><strong>${escapeHtml(alert.pair)}</strong> ${escapeHtml(alert.condition)}</div>
            <div class="muted small">${details.length ? details.map(escapeHtml).join(" · ") : "—"}</div>
          </td>
          <td>${channels}</td>
          <td>${alert.cooldown_seconds}s</td>
          <td>${alert.last_triggered_at ? escapeHtml(fmtRelative(alert.last_triggered_at)) : "—"}</td>
          <td><button type="button" class="icon-btn delete-alert" title="Delete alert" aria-label="Delete alert">✕</button></td>
        </tr>`;
      })
      .join("");
  }

  async function createAlert(event) {
    event.preventDefault();
    const pairValue = $("#alert-pair").value;
    if (!pairValue) {
      toast("Select a pair first.", "error");
      return;
    }

    const [asset, quote] = splitPair(pairValue);
    const channels = $$(".channel-checkbox:checked").map((checkbox) => checkbox.value);
    const threshold = Number($("#alert-threshold").value);
    if (!Number.isFinite(threshold)) {
      toast("Threshold must be a number.", "error");
      return;
    }

    const payload = {
      asset,
      quote_currency: quote,
      metric: $("#alert-metric").value,
      operator: $("#alert-operator").value,
      threshold,
      channels,
      cooldown_seconds: Number($("#alert-cooldown").value || 0),
      repeat: $("#alert-repeat").checked,
      label: $("#alert-label").value.trim() || null,
    };
    const source = $("#alert-source").value;
    if (source) payload.source = source;

    try {
      await api("/api/alerts", { method: "POST", body: JSON.stringify(payload) });
      $("#alert-threshold").value = "";
      $("#alert-label").value = "";
      $("#alert-repeat").checked = false;
      toast(channels.length ? "Alert created." : "Alert created without channels; it will appear in event history only.");
      await loadAlerts();
    } catch (error) {
      toast(error.message, "error");
    }
  }

  async function toggleAlert(alertId, enabled) {
    try {
      await api(`/api/alerts/${alertId}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      });
      toast(enabled ? "Alert enabled." : "Alert disabled.");
      await loadAlerts();
    } catch (error) {
      toast(error.message, "error");
      await loadAlerts();
    }
  }

  async function deleteAlert(alertId) {
    if (!window.confirm(`Delete alert #${alertId}?`)) return;
    try {
      await api(`/api/alerts/${alertId}`, { method: "DELETE" });
      toast("Alert deleted.");
      await loadAlerts();
    } catch (error) {
      toast(error.message, "error");
    }
  }

  // -------------------------------------------------------------------- events
  async function loadEvents() {
    const data = await api("/api/events?limit=50");
    state.events = data.data || [];
    renderEvents();
  }

  function renderEvents() {
    const body = $("#events-body");
    if (!state.events.length) {
      body.innerHTML = '<tr><td colspan="4" class="empty-cell">No events yet.</td></tr>';
      return;
    }

    body.innerHTML = state.events
      .map((event) => {
        const deliveries = event.deliveries.length
          ? event.deliveries
              .map(
                (delivery) =>
                  `<span class="chip ${delivery.success ? "ok" : "fail"}" title="${escapeHtml(
                    delivery.error || (delivery.success ? "Delivered" : "Failed"),
                  )}">${escapeHtml(delivery.channel)} ${delivery.success ? "✓" : "✗"}</span>`,
              )
              .join("")
          : '<span class="muted">none</span>';

        return `<tr>
          <td title="${escapeHtml(fmtTime(event.triggered_at))}">${escapeHtml(fmtRelative(event.triggered_at))}</td>
          <td>${escapeHtml(event.pair)}</td>
          <td>
            <div>${escapeHtml(event.metric)} ${escapeHtml(event.operator)} ${fmtNumber(event.threshold)}</div>
            <div class="muted small">value ${fmtNumber(event.value)} · ${escapeHtml(event.source)}</div>
          </td>
          <td>${deliveries}</td>
        </tr>`;
      })
      .join("");
  }

  // ------------------------------------------------------------------ refresh
  async function refreshData({ history = true } = {}) {
    if (state.refreshing) return;
    state.refreshing = true;
    setStatus(state.paused ? "paused" : "", state.paused ? "Paused" : "Updating…");

    try {
      const results = await Promise.allSettled([loadOverview(), loadAlerts(), loadEvents()]);
      const failed = results.find((result) => result.status === "rejected");
      if (failed) throw failed.reason;

      if (history) await loadHistory();

      hideError();
      state.lastLoadedAt = new Date();
      $("#last-updated").textContent = `Updated ${state.lastLoadedAt.toLocaleTimeString()}`;
      setStatus(state.paused ? "paused" : "live", state.paused ? "Paused" : "Live");
    } catch (error) {
      setStatus("offline", "Offline");
      showError(error.message || String(error));
    } finally {
      state.refreshing = false;
    }
  }

  function startTimer() {
    if (state.timer) clearInterval(state.timer);
    state.timer = null;
    if (state.paused) return;

    const seconds = Math.max(2, Number(CFG.refreshSeconds || state.config?.refresh_seconds || 10));
    state.timer = setInterval(() => {
      if (!state.paused && !document.hidden) {
        refreshData();
      }
    }, seconds * 1000);
  }

  function togglePause() {
    state.paused = !state.paused;
    $("#pause-button").textContent = state.paused ? "Resume live" : "Pause live";
    if (state.paused) {
      if (state.timer) clearInterval(state.timer);
      state.timer = null;
      setStatus("paused", "Paused");
    } else {
      setStatus("live", "Live");
      startTimer();
      refreshData();
    }
  }

  async function checkNow() {
    const button = $("#check-button");
    button.disabled = true;
    try {
      const result = await api("/api/check", { method: "POST", body: "{}" });
      toast(result.count ? `${result.count} alert(s) triggered.` : "No alerts triggered.");
      await refreshData();
    } catch (error) {
      toast(error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  function selectPair(key, { scroll = false } = {}) {
    if (!key) return;
    state.selectedPair = key;
    $("#pair-select").value = key;
    updateSourceOptions();
    updateTradingViewLink();
    renderPriceCards(state.overview?.pairs || []);
    if (scroll) {
      $("#chart-section").scrollIntoView({ behavior: "smooth", block: "start" });
    }
    loadHistory().catch((error) => {
      showError(error.message || String(error));
      setStatus("offline", "Offline");
    });
  }

  // ------------------------------------------------------------------- events
  function setupEventListeners() {
    $("#refresh-button").addEventListener("click", () => refreshData());
    $("#pause-button").addEventListener("click", togglePause);
    $("#check-button").addEventListener("click", checkNow);
    $("#alert-form").addEventListener("submit", createAlert);

    $("#range-buttons").addEventListener("click", (event) => {
      const button = event.target.closest("[data-range]");
      if (!button || button.dataset.range === state.range) return;
      state.range = button.dataset.range;
      $$("#range-buttons button").forEach((candidate) => {
        candidate.classList.toggle("active", candidate === button);
      });
      refreshData();
    });

    $("#pair-select").addEventListener("change", (event) => selectPair(event.target.value));

    $("#alert-pair").addEventListener("change", () => {
      updateSourceOptions();
      updateTradingViewLink();
    });

    $("#price-cards").addEventListener("click", (event) => {
      const card = event.target.closest("[data-pair]");
      if (card) selectPair(card.dataset.pair, { scroll: true });
    });

    $("#price-cards").addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const card = event.target.closest("[data-pair]");
      if (card) {
        event.preventDefault();
        selectPair(card.dataset.pair, { scroll: true });
      }
    });

    $("#alerts-body").addEventListener("change", (event) => {
      if (!event.target.classList.contains("alert-toggle")) return;
      const row = event.target.closest("[data-alert-id]");
      if (row) toggleAlert(row.dataset.alertId, event.target.checked);
    });

    $("#alerts-body").addEventListener("click", (event) => {
      const button = event.target.closest(".delete-alert");
      if (!button) return;
      const row = button.closest("[data-alert-id]");
      if (row) deleteAlert(row.dataset.alertId);
    });
  }

  // --------------------------------------------------------------------- init
  async function init() {
    setupEventListeners();

    try {
      await loadConfig();
    } catch (error) {
      setStatus("offline", "Offline");
      showError(`Cannot load configuration: ${error.message || error}`);
      return;
    }

    await refreshData({ history: true });
    startTimer();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
