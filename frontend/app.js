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
    bindControls();
    bindTabs();
    const health = await fetchJSON("/api/health");
    $("#statusBadge").textContent = `${health.n_observations} observations loaded`;

    const ds = await fetchJSON("/api/dataset");
    state.observations = ds.observations;
    state.observations.forEach((o) => state.obsById.set(o.observation_id, o));
    updateBounds();
    renderObservationsTable();

    await runResolve();
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
  const SVG_W = 900, SVG_H = 480, PAD = 20;
  let bounds = { lonMin: -125, lonMax: -66, latMin: 24, latMax: 49 };

  function updateBounds() {
    const lats = state.observations.filter((o) => o.lat != null).map((o) => o.lat);
    const lons = state.observations.filter((o) => o.lon != null).map((o) => o.lon);
    if (lats.length && lons.length) {
      const minLat = Math.min(...lats), maxLat = Math.max(...lats);
      const minLon = Math.min(...lons), maxLon = Math.max(...lons);
      const padLat = Math.max((maxLat - minLat) * 0.08, 1.0);
      const padLon = Math.max((maxLon - minLon) * 0.08, 1.0);
      bounds = {
        latMin: minLat - padLat,
        latMax: maxLat + padLat,
        lonMin: minLon - padLon,
        lonMax: maxLon + padLon,
      };
    }
  }

  function project(lat, lon) {
    const x = PAD + ((lon - bounds.lonMin) / (bounds.lonMax - bounds.lonMin)) * (SVG_W - 2 * PAD);
    const y = PAD + (1 - (lat - bounds.latMin) / (bounds.latMax - bounds.latMin)) * (SVG_H - 2 * PAD);
    return [x, y];
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
    const svg = $("#mapSvg");
    svg.innerHTML = "";
    const clusterId = $("#mapEntitySelect").value;
    const entity = state.result.entities.find((e) => e.cluster_id === clusterId);
    if (!entity) return;

    // background: faint dots for every observation with known coordinates
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "g");
    bg.setAttribute("opacity", "0.15");
    state.observations.forEach((o) => {
      if (o.lat == null) return;
      const [x, y] = project(o.lat, o.lon);
      bg.appendChild(circle(x, y, 2, "currentColor"));
    });
    svg.appendChild(bg);

    const obs = entity.observation_ids
      .map((id) => state.obsById.get(id))
      .filter((o) => o.lat != null)
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp));

    const path = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    const pts = obs.map((o) => project(o.lat, o.lon).join(",")).join(" ");
    path.setAttribute("points", pts);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "#3b5bdb");
    path.setAttribute("stroke-width", "2");
    path.setAttribute("stroke-dasharray", "5,4");
    svg.appendChild(path);

    obs.forEach((o, idx) => {
      const [x, y] = project(o.lat, o.lon);
      const t = obs.length > 1 ? idx / (obs.length - 1) : 1;
      const color = `rgb(${Math.round(59 + t * 100)}, ${Math.round(91 - t * 40)}, ${Math.round(219 - t * 100)})`;
      const c = circle(x, y, 6, color);
      c.style.cursor = "pointer";
      c.addEventListener("mousemove", (ev) => showTooltip(ev, o));
      c.addEventListener("mouseleave", hideTooltip);
      svg.appendChild(c);
    });

    // city labels for context
    const seenCities = new Set();
    obs.forEach((o) => {
      if (seenCities.has(o.city)) return;
      seenCities.add(o.city);
      const [x, y] = project(o.lat, o.lon);
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", x + 8);
      label.setAttribute("y", y - 8);
      label.setAttribute("font-size", "10");
      label.setAttribute("fill", "currentColor");
      label.textContent = o.city;
      svg.appendChild(label);
    });
  }

  function circle(x, y, r, fill) {
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", x); c.setAttribute("cy", y); c.setAttribute("r", r);
    c.setAttribute("fill", fill);
    c.setAttribute("stroke", "white");
    c.setAttribute("stroke-width", "1");
    return c;
  }

  function showTooltip(ev, o) {
    const tip = $("#mapTooltip");
    tip.hidden = false;
    tip.style.left = ev.clientX + 14 + "px";
    tip.style.top = ev.clientY + 10 + "px";
    tip.innerHTML = `<b>${o.first_name} ${o.last_name}</b><br>${o.timestamp} — ${o.city}` +
      (state.showTruth ? `<br>truth: ${o.entity_id_truth}` : "");
  }
  function hideTooltip() { $("#mapTooltip").hidden = true; }

  document.addEventListener("DOMContentLoaded", init);
})();
