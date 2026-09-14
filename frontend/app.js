(() => {
  "use strict";

  const DEFAULT_WEIGHTS = {
    name: 3.0, dob: 1.5, spatiotemporal: 1.2, cooccurrence: 2.5,
    kinematic_penalty: 4.0, dob_conflict_penalty: 5.0,
  };
  const DEFAULT_THRESHOLD = 0.65;

  const state = {
    observations: [],
    obsById: new Map(),
    result: null,
    weights: { ...DEFAULT_WEIGHTS },
    threshold: DEFAULT_THRESHOLD,
    showTruth: true,
    map: null,
    tileLayer: null,
    currentTileTheme: null,
    trajectoryLayerGroup: null,
    backgroundLayerGroup: null,
  };

  const $ = (sel) => document.querySelector(sel);
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  };

  // ---------------------------------------------------------------- init --
  async function init() {
    initTheme();
    bindControls();
    bindTabs();
    const health = await fetchJSON("/api/health");
    $("#statusBadge").textContent = `${health.n_observations} observations loaded`;

    const ds = await fetchJSON("/api/dataset");
    state.observations = ds.observations;
    state.observations.forEach((o) => state.obsById.set(o.observation_id, o));
    renderObservationsTable();

    await runResolve();
  }

  function initTheme() {
    const saved = localStorage.getItem("trajectories_theme") || "system";
    setTheme(saved);

    document.querySelectorAll(".theme-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        setTheme(btn.dataset.themeVal);
      });
    });
  }

  function getEffectiveTheme() {
    const attr = document.documentElement.getAttribute("data-theme");
    if (attr === "dark") return "dark";
    if (attr === "light") return "light";
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function updateMapTiles() {
    if (!state.map || !window.L) return;
    const theme = getEffectiveTheme();
    if (state.currentTileTheme === theme && state.tileLayer) return;

    if (state.tileLayer) {
      state.map.removeLayer(state.tileLayer);
    }

    const tileUrl = theme === "dark"
      ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      : "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";

    const attribution = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>';

    state.tileLayer = L.tileLayer(tileUrl, {
      attribution: attribution,
      subdomains: "abcd",
      maxZoom: 19,
    }).addTo(state.map);

    state.currentTileTheme = theme;
  }

  function setTheme(mode) {
    if (mode === "light") {
      document.documentElement.setAttribute("data-theme", "light");
    } else if (mode === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
      mode = "system";
    }
    localStorage.setItem("trajectories_theme", mode);
    document.querySelectorAll(".theme-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.themeVal === mode);
    });
    updateMapTiles();
  }

  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      const saved = localStorage.getItem("trajectories_theme") || "system";
      if (saved === "system") {
        updateMapTiles();
      }
    });
  }

  function fetchJSON(url, opts) {
    return fetch(url, opts).then((r) => r.json());
  }

  // ------------------------------------------------------------ controls --
  function bindControls() {
    const thresholdInput = $("#threshold");
    thresholdInput.addEventListener("input", () => {
      state.threshold = parseFloat(thresholdInput.value);
      $("#thresholdVal").textContent = state.threshold.toFixed(2);
      debouncedResolve();
    });
    $("#thresholdVal").textContent = state.threshold.toFixed(2);

    document.querySelectorAll(".weight").forEach((input) => {
      const key = input.dataset.key;
      input.value = state.weights[key];
      const label = $(`#w_${key}_val`);
      label.textContent = Number(input.value).toFixed(1);
      input.addEventListener("input", () => {
        state.weights[key] = parseFloat(input.value);
        label.textContent = input.value;
        debouncedResolve();
      });
    });

    $("#resetBtn").addEventListener("click", () => {
      state.weights = { ...DEFAULT_WEIGHTS };
      state.threshold = DEFAULT_THRESHOLD;
      thresholdInput.value = state.threshold;
      $("#thresholdVal").textContent = state.threshold.toFixed(2);
      document.querySelectorAll(".weight").forEach((input) => {
        input.value = state.weights[input.dataset.key];
        $(`#w_${input.dataset.key}_val`).textContent = input.value;
      });
      runResolve();
    });

    $("#truthToggle").addEventListener("change", (e) => {
      state.showTruth = e.target.checked;
      renderEntities();
      renderObservationsTable();
    });

    $("#pairMinScore").addEventListener("input", renderPairs);
    $("#pairOnlyLinked").addEventListener("change", renderPairs);
    $("#pairOnlyBlocked").addEventListener("change", renderPairs);
    $("#mapEntitySelect").addEventListener("change", renderMap);
  }

  let resolveTimer = null;
  function debouncedResolve() {
    clearTimeout(resolveTimer);
    resolveTimer = setTimeout(runResolve, 250);
  }

  function bindTabs() {
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        document.querySelectorAll(".tab-panel").forEach((p) => (p.hidden = true));
        $(`#tab-${tab.dataset.tab}`).hidden = false;
        if (tab.dataset.tab === "map" && state.map) {
          setTimeout(() => {
            state.map.invalidateSize();
            fitCurrentTrajectory();
          }, 150);
        }
      });
    });
  }

  // -------------------------------------------------------------- resolve --
  async function runResolve() {
    $("#statusBadge").textContent = "resolving…";
    const result = await fetchJSON("/api/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ threshold: state.threshold, weights: state.weights }),
    });
    state.result = result;
    $("#statusBadge").textContent = `${state.observations.length} observations · ` +
      `${result.entities.length} resolved entities`;
    renderMetrics();
    renderEntities();
    renderPairs();
    populateMapSelect();
    renderMap();
  }

  // -------------------------------------------------------------- metrics --
  function renderMetrics() {
    const m = state.result.metrics;
    $("#mObs").textContent = m.n_observations;
    $("#mTrue").textContent = m.n_true_entities;
    $("#mPred").textContent = m.n_predicted_clusters;
    $("#mPrec").textContent = m.pairwise_precision.toFixed(3);
    $("#mRec").textContent = m.pairwise_recall.toFixed(3);
    $("#mF1").textContent = m.pairwise_f1.toFixed(3);
  }

  // ------------------------------------------------------------- entities --
  function renderEntities() {
    const list = $("#entityList");
    list.innerHTML = "";
    const entities = state.result.entities;

    // detect under-merge: a true entity spread across >1 predicted cluster
    const truthToClusters = new Map();
    entities.forEach((e) => {
      e.ground_truth_entities.forEach((t) => {
        if (!truthToClusters.has(t)) truthToClusters.set(t, new Set());
        truthToClusters.get(t).add(e.cluster_id);
      });
    });
    const split = [...truthToClusters.entries()].filter(([, cs]) => cs.size > 1);
    const warn = $("#splitWarning");
    if (split.length) {
      warn.hidden = false;
      warn.textContent = `Under-merge detected: ${split.length} true entit${split.length === 1 ? "y is" : "ies are"} ` +
        `split across multiple clusters (${split.map(([t, cs]) => `${t}→${[...cs].join(",")}`).join("; ")}). Try lowering the threshold.`;
    } else {
      warn.hidden = true;
    }

    entities.forEach((e) => {
      const card = el("div", "entity-card" + (e.is_pure ? "" : " mixed"));
      const title = el("h3");
      title.textContent = e.cluster_id;
      const badge = el("span", "badge" + (e.is_pure ? "" : " bad"),
        e.is_pure ? "pure" : `mixed ×${e.ground_truth_entities.length}`);
      title.appendChild(badge);
      card.appendChild(title);

      const dl = el("dl");
      addRow(dl, "Observations", e.size);
      addRow(dl, "Names seen", e.names_seen.join(" / "));
      addRow(dl, "Cities", e.cities_seen.join(", "));
      addRow(dl, "Date span", `${e.date_span[0]} → ${e.date_span[1]}`);
      if (state.showTruth) addRow(dl, "Ground truth", e.ground_truth_entities.join(", "));
      card.appendChild(dl);
      list.appendChild(card);
    });
  }

  function addRow(dl, label, value) {
    const row = el("div");
    row.appendChild(el("dt", null, label));
    row.appendChild(el("dd", null, String(value)));
    dl.appendChild(row);
  }

  // ---------------------------------------------------------------- pairs --
  function renderPairs() {
    const body = $("#pairsBody");
    body.innerHTML = "";
    const minScore = parseFloat($("#pairMinScore").value || 0);
    const onlyLinked = $("#pairOnlyLinked").checked;
    const onlyBlocked = $("#pairOnlyBlocked").checked;

    const rows = state.result.pairs.filter((p) => {
      if (p.score < minScore) return false;
      if (onlyLinked && !p.linked) return false;
      if (onlyBlocked && !p.hard_block) return false;
      return true;
    }).sort((a, b) => b.score - a.score);

    $("#pairCount").textContent = `${rows.length} / ${state.result.pairs.length} pairs shown`;

    const frag = document.createDocumentFragment();
    rows.slice(0, 500).forEach((p) => {
      const tr = document.createElement("tr");
      const f = p.features;
      const isBlocked = p.hard_block || f.dob_conflict;
      tr.className = p.hard_block ? "blocked" : (f.dob_conflict ? "blocked dob-conflict" : (p.linked ? "linked" : ""));
      const status = p.hard_block ? "hard-blocked" : (f.dob_conflict ? "dob-conflict" : (p.linked ? "linked" : "candidate"));
      const cells = [
        p.score.toFixed(3),
        p.observation_id_i, p.observation_id_j,
        f.first_name_sim.toFixed(2), f.last_name_sim.toFixed(2),
        f.dob_conflict ? "conflict" : f.dob_sim.toFixed(2),
        f.spatiotemporal_kernel.toFixed(2), f.cooccurrence.toFixed(2),
        f.velocity_kmh === null ? "–" : f.velocity_kmh,
        status,
      ];
      cells.forEach((c) => {
        const td = document.createElement("td");
        td.textContent = c;
        tr.appendChild(td);
      });
      frag.appendChild(tr);
    });
    body.appendChild(frag);
  }

  // --------------------------------------------------------- observations --
  function renderObservationsTable() {
    const body = $("#obsBody");
    body.innerHTML = "";
    const frag = document.createDocumentFragment();
    state.observations
      .slice()
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
      .forEach((o) => {
        const tr = document.createElement("tr");
        const cells = [
          o.observation_id, o.timestamp, o.first_name, o.last_name,
          o.dob || "–", o.city, o.household_id || "–", o.employer_id || "–",
          o.persistent_token ? o.persistent_token.slice(0, 8) : "–",
          state.showTruth ? o.entity_id_truth : "hidden",
        ];
        cells.forEach((c) => {
          const td = document.createElement("td");
          td.textContent = c;
          tr.appendChild(td);
        });
        frag.appendChild(tr);
      });
    body.appendChild(frag);
  }

  // ----------------------------------------------------------------- map --
  let currentEntityLatLngs = [];

  function initLeafletMap() {
    if (!window.L || state.map) return;
    const mapEl = $("#mapContainer");
    if (!mapEl) return;

    state.map = L.map("mapContainer", {
      center: [39.8283, -98.5795], // US Geographic center
      zoom: 4,
      minZoom: 3,
      maxZoom: 18,
    });

    updateMapTiles();

    state.backgroundLayerGroup = L.layerGroup().addTo(state.map);
    state.trajectoryLayerGroup = L.layerGroup().addTo(state.map);

    const fitBtn = $("#mapFitBtn");
    if (fitBtn) {
      fitBtn.addEventListener("click", fitCurrentTrajectory);
    }
  }

  function fitCurrentTrajectory() {
    if (!state.map || !currentEntityLatLngs.length) return;
    if (currentEntityLatLngs.length === 1) {
      state.map.setView(currentEntityLatLngs[0], 9);
    } else {
      state.map.fitBounds(L.latLngBounds(currentEntityLatLngs), {
        padding: [45, 45],
        maxZoom: 11,
      });
    }
  }

  function populateMapSelect() {
    const select = $("#mapEntitySelect");
    const prev = select.value;
    select.innerHTML = "";
    state.result.entities.forEach((e) => {
      const opt = document.createElement("option");
      opt.value = e.cluster_id;
      opt.textContent = `${e.cluster_id} — ${e.names_seen[0]}${e.names_seen.length > 1 ? " (+variants)" : ""} — ${e.size} obs`;
      select.appendChild(opt);
    });
    if (prev && state.result.entities.some((e) => e.cluster_id === prev)) {
      select.value = prev;
    }
  }

  function renderMap() {
    if (!window.L) return;
    if (!state.map) {
      initLeafletMap();
    }
    if (!state.map) return;

    state.backgroundLayerGroup.clearLayers();
    state.trajectoryLayerGroup.clearLayers();
    currentEntityLatLngs = [];

    // 1. Draw subtle background observation dots across the entire dataset
    state.observations.forEach((o) => {
      if (o.lat == null || o.lon == null) return;
      const marker = L.circleMarker([o.lat, o.lon], {
        radius: 3.5,
        fillColor: "#888888",
        fillOpacity: 0.25,
        stroke: false,
      });
      marker.bindTooltip(`<b>${o.first_name} ${o.last_name}</b><br>${o.city} · ${o.timestamp}`, {
        sticky: true,
      });
      state.backgroundLayerGroup.addLayer(marker);
    });

    const clusterId = $("#mapEntitySelect").value;
    const entity = state.result.entities.find((e) => e.cluster_id === clusterId);
    if (!entity) return;

    const obs = entity.observation_ids
      .map((id) => state.obsById.get(id))
      .filter((o) => o.lat != null && o.lon != null)
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp));

    const infoEl = $("#mapEntityInfo");
    if (infoEl) {
      infoEl.textContent = `${entity.cluster_id} · ${obs.length} mapped points · ${entity.cities_seen.join(" → ")}`;
    }

    if (obs.length === 0) return;

    currentEntityLatLngs = obs.map((o) => [o.lat, o.lon]);

    // 2. Chronological trajectory polyline connecting observations
    if (obs.length > 1) {
      const polyline = L.polyline(currentEntityLatLngs, {
        color: "#3b5bdb",
        weight: 3.5,
        opacity: 0.85,
        dashArray: "6, 6",
        lineCap: "round",
      });
      state.trajectoryLayerGroup.addLayer(polyline);
    }

    // 3. Chronologically colored waypoint markers with rich popups
    obs.forEach((o, idx) => {
      const t = obs.length > 1 ? idx / (obs.length - 1) : 1;
      const r = Math.round(59 + t * 165);
      const g = Math.round(91 - t * 42);
      const b = Math.round(219 - t * 170);
      const color = `rgb(${r}, ${g}, ${b})`;

      const marker = L.circleMarker([o.lat, o.lon], {
        radius: 7,
        fillColor: color,
        fillOpacity: 0.95,
        color: "#ffffff",
        weight: 2,
      });

      const popupHtml = `
        <div class="map-popup-body">
          <div style="font-weight:700;font-size:0.95rem;margin-bottom:4px;color:var(--text);">${o.first_name} ${o.last_name}</div>
          <div style="font-size:0.8rem;color:var(--muted);margin-bottom:6px;">Waypoint ${idx + 1} of ${obs.length}</div>
          <div style="display:grid;gap:2px;font-size:0.8rem;">
            <div><b>Date:</b> ${o.timestamp}</div>
            <div><b>Location:</b> ${o.city}</div>
            ${o.address ? `<div><b>Address:</b> ${o.address}</div>` : ""}
            ${o.dob ? `<div><b>DOB:</b> ${o.dob}</div>` : ""}
            ${o.household_id ? `<div><b>Household:</b> <code>${o.household_id}</code></div>` : ""}
            ${o.employer_id ? `<div><b>Employer:</b> <code>${o.employer_id}</code></div>` : ""}
            ${state.showTruth ? `<div style="margin-top:4px;border-top:1px dashed var(--border);padding-top:4px;color:var(--muted);"><b>Truth ID:</b> <code>${o.entity_id_truth}</code></div>` : ""}
          </div>
        </div>
      `;

      marker.bindPopup(popupHtml);
      marker.bindTooltip(`<b>#${idx + 1}</b> ${o.timestamp} — ${o.city}`, {
        direction: "top",
        offset: [0, -6],
      });

      state.trajectoryLayerGroup.addLayer(marker);
    });

    fitCurrentTrajectory();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
