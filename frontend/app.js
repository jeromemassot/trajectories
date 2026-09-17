(() => {
  "use strict";

  const DEFAULT_WEIGHTS = {
    name: 3.0, dob: 1.5, email: 2.0, phone: 1.8,
    spatial_locality: 1.2, relocation_plausibility: 1.5,
    cooccurrence: 2.2, dob_conflict_penalty: 5.0,
  };
  const DEFAULT_THRESHOLD = 0.65;

  const state = {
    observations: [],
    obsById: new Map(),
    result: null,
    weights: { ...DEFAULT_WEIGHTS },
    threshold: DEFAULT_THRESHOLD,
    showTruth: true,
    usePersistentTokens: true,
    pairOnlyToken: false,
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
    initTimelineControls();
    bindGeneratorControls();
    const health = await fetchJSON("/api/health");
    $("#statusBadge").textContent = `${health.n_observations} observations loaded`;

    const ds = await fetchJSON("/api/dataset");
    state.observations = ds.observations;
    state.observations.forEach((o) => state.obsById.set(o.observation_id, o));
    renderObservationsTable();

    await runResolve();

    window.addEventListener("resize", () => {
      if (state.map) {
        state.map.invalidateSize();
      }
    });
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

    const tileUrl = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
    const attribution = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors';

    state.tileLayer = L.tileLayer(tileUrl, {
      attribution: attribution,
      subdomains: ["a", "b", "c"],
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
      $("#thresholdVal").textContent = state.threshold.toFixed(3);
      debouncedResolve();
    });
    $("#thresholdVal").textContent = state.threshold.toFixed(3);

    document.querySelectorAll(".weight").forEach((input) => {
      const key = input.dataset.key;
      input.value = state.weights[key];
      const label = $(`#w_${key}_val`);
      if (label) {
        label.textContent = Number(input.value).toFixed(1);
      }
      input.addEventListener("input", () => {
        state.weights[key] = parseFloat(input.value);
        if (label) label.textContent = input.value;
        debouncedResolve();
      });
    });

    $("#resetBtn").addEventListener("click", () => {
      state.weights = { ...DEFAULT_WEIGHTS };
      state.threshold = DEFAULT_THRESHOLD;
      thresholdInput.value = state.threshold;
      $("#thresholdVal").textContent = state.threshold.toFixed(3);
      state.usePersistentTokens = true;
      const tokenToggle = $("#tokenToggle");
      if (tokenToggle) tokenToggle.checked = true;
      document.querySelectorAll(".weight").forEach((input) => {
        input.value = state.weights[input.dataset.key];
        const label = $(`#w_${input.dataset.key}_val`);
        if (label) label.textContent = input.value;
      });
      runResolve();
    });

    const tokenToggle = $("#tokenToggle");
    if (tokenToggle) {
      tokenToggle.addEventListener("change", (e) => {
        state.usePersistentTokens = e.target.checked;
        debouncedResolve();
      });
    }

    $("#truthToggle").addEventListener("change", (e) => {
      state.showTruth = e.target.checked;
      renderEntities();
      renderObservationsTable();
      renderMapObservationsTable();
    });

    $("#pairMinScore").addEventListener("input", renderPairs);
    $("#pairOnlyLinked").addEventListener("change", renderPairs);
    $("#pairOnlyBlocked").addEventListener("change", renderPairs);
    const pairOnlyToken = $("#pairOnlyToken");
    if (pairOnlyToken) {
      pairOnlyToken.addEventListener("change", (e) => {
        state.pairOnlyToken = e.target.checked;
        renderPairs();
      });
    }
    $("#mapEntitySelect").addEventListener("change", renderMap);

    const mapObsFilter = $("#mapObsFilterEntity");
    if (mapObsFilter) {
      mapObsFilter.addEventListener("change", () => {
        renderMapObservationsTable();
      });
    }
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
      body: JSON.stringify({
        threshold: state.threshold,
        weights: state.weights,
        use_persistent_tokens: state.usePersistentTokens,
      }),
    });
    state.result = result;
    buildPairMap();
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

    const tb = $("#tokenCountBadge");
    if (tb) {
      const cnt = m.token_anchored_pairs !== undefined ? m.token_anchored_pairs : 0;
      tb.textContent = state.usePersistentTokens
        ? `(${cnt} pairs anchored)`
        : `(${cnt} pairs present, disabled)`;
      tb.style.color = state.usePersistentTokens ? "var(--color-accent, #2563eb)" : "var(--color-muted, #888)";
    }
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
      if (e.emails_seen && e.emails_seen.length) addRow(dl, "Emails", e.emails_seen.join(", "));
      if (e.phones_seen && e.phones_seen.length) addRow(dl, "Phones", e.phones_seen.join(", "));
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
    const onlyToken = state.pairOnlyToken;

    const rows = state.result.pairs.filter((p) => {
      if (p.score < minScore) return false;
      if (onlyLinked && !p.linked) return false;
      if (onlyBlocked && !p.hard_block) return false;
      if (onlyToken && !p.features.token_shared) return false;
      return true;
    }).sort((a, b) => b.score - a.score);

    $("#pairCount").textContent = `${rows.length} / ${state.result.pairs.length} pairs shown`;

    const frag = document.createDocumentFragment();
    rows.slice(0, 500).forEach((p) => {
      const tr = document.createElement("tr");
      const f = p.features;
      const isBlocked = p.hard_block || f.dob_conflict;
      tr.className = p.hard_block ? "blocked" : (f.dob_conflict ? "blocked dob-conflict" : (p.linked ? "linked" : ""));
      let status = p.hard_block ? "hard-blocked" : (f.dob_conflict ? "dob-conflict" : (p.linked ? "linked" : "candidate"));
      if (p.linked && f.token_shared) {
        status = state.usePersistentTokens ? "linked (token)" : "linked";
      }

      if (f.token_shared) {
        tr.title = state.usePersistentTokens
          ? "Anchored by persistent hardware/ad digital token"
          : "Persistent digital token present on observations, but disabled by controls";
      }

      const coocText = f.token_shared
        ? (state.usePersistentTokens ? `${f.cooccurrence.toFixed(2)} 🔑` : `${f.cooccurrence.toFixed(2)} (no token)`)
        : f.cooccurrence.toFixed(2);

      const cells = [
        p.score.toFixed(3),
        p.observation_id_i, p.observation_id_j,
        f.first_name_sim.toFixed(2), f.last_name_sim.toFixed(2),
        f.dob_conflict ? "conflict" : f.dob_sim.toFixed(2),
        f.email_sim !== undefined ? f.email_sim.toFixed(2) : "–",
        f.phone_sim !== undefined ? f.phone_sim.toFixed(2) : "–",
        f.spatial_locality !== undefined ? f.spatial_locality.toFixed(2) : (f.spatiotemporal_kernel !== undefined ? f.spatiotemporal_kernel.toFixed(2) : "–"),
        coocText,
        f.relocation_plausibility !== undefined ? f.relocation_plausibility.toFixed(2) : "–",
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
        const emailsStr = (o.emails && o.emails.length) ? o.emails.join(", ") : "–";
        const phonesStr = (o.phones && o.phones.length) ? o.phones.join(", ") : "–";
        const cells = [
          o.observation_id, o.timestamp, o.first_name, o.last_name,
          o.dob || "–", o.city, emailsStr, phonesStr,
          o.household_id || "–", o.employer_id || "–",
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

  const timelineState = {
    obsList: [],
    step: 0,
    isPlaying: false,
    timer: null,
    speedMs: 1200,
    markers: [],
    segments: [],
  };

  function buildPairMap() {
    state.pairMap = new Map();
    if (!state.result || !state.result.pairs) return;
    state.result.pairs.forEach((p) => {
      state.pairMap.set(`${p.observation_id_i}:${p.observation_id_j}`, p);
      state.pairMap.set(`${p.observation_id_j}:${p.observation_id_i}`, p);
    });
  }

  function getPairBetween(id1, id2) {
    if (!state.pairMap) return null;
    return state.pairMap.get(`${id1}:${id2}`) || null;
  }

  function haversineKm(lat1, lon1, lat2, lon2) {
    if (lat1 == null || lon1 == null || lat2 == null || lon2 == null) return null;
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.sin(dLon / 2) *
        Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return Math.round(R * c);
  }

  function generateConnectionExplanation(o1, o2, pair) {
    const f = (pair && pair.features) || {};
    const scoreVal = pair ? pair.score.toFixed(3) : "–";
    const scorePct = pair ? (pair.score * 100).toFixed(1) + "%" : "–";
    const isHigh = pair && pair.score >= state.threshold;

    // 1. Name continuity
    let nameText = "";
    let namePill = "";
    if (o1.first_name === o2.first_name && o1.last_name === o2.last_name) {
      nameText = "identical full name";
      namePill = `${o1.first_name} ${o1.last_name} (100% Match)`;
    } else if (o1.first_name === o2.first_name && o1.last_name !== o2.last_name) {
      nameText = `same first name with surname transition (${o1.last_name} → ${o2.last_name})`;
      namePill = `First: ${o1.first_name} | ${o1.last_name} → ${o2.last_name}`;
    } else {
      const sim = ((f.name_sim || 0) * 100).toFixed(0);
      nameText = `high name similarity (${sim}%)`;
      namePill = `${o1.first_name} ${o1.last_name} ↔ ${o2.first_name} ${o2.last_name} (${sim}%)`;
    }

    // 2. Date of birth agreement
    let dobText = "";
    let dobPill = "";
    if (o1.dob && o2.dob && o1.dob === o2.dob) {
      dobText = `identical confirmed DOB (${o1.dob})`;
      dobPill = `Verified: ${o1.dob}`;
    } else if (!o1.dob || !o2.dob) {
      dobText = "uninformative neutral DOB (missing on one record)";
      dobPill = o1.dob || o2.dob ? `Known: ${o1.dob || o2.dob} (Partial)` : "Unknown";
    } else {
      dobText = `DOB mismatch (${o1.dob} vs ${o2.dob})`;
      dobPill = `Conflict: ${o1.dob} vs ${o2.dob}`;
    }

    // 3. Email anchor & evolution
    const sharedEmails = (o1.emails || []).filter((e) => (o2.emails || []).includes(e));
    let emailText = "";
    let emailPill = "";
    if (sharedEmails.length) {
      emailText = `shared email address (${sharedEmails.join(", ")})`;
      emailPill = sharedEmails.join(", ");
    } else if (f.email_sim >= 0.85 && o1.emails?.length && o2.emails?.length) {
      const evolutionType = f.email_sim >= 0.88 ? "Personal/Work Pair" : "Provider Migration";
      emailText = `logical email evolution (${evolutionType}: ${o1.emails[0]} ↔ ${o2.emails[0]})`;
      emailPill = `${evolutionType} (${(f.email_sim * 100).toFixed(0)}%)`;
    } else if (o1.emails?.length && o2.emails?.length) {
      emailText = "different email addresses";
      emailPill = "Disjoint aliases";
    } else {
      emailPill = (o1.emails?.length || o2.emails?.length) ? "Partial email record" : "No email logged";
    }

    // 4. Phone active snapshot & reallocation
    const sharedPhones = (o1.phones || []).filter((p) => (o2.phones || []).includes(p));
    let phoneText = "";
    let phonePill = "";
    if (sharedPhones.length) {
      phoneText = `shared active phone number (${sharedPhones.join(", ")})`;
      phonePill = `${sharedPhones.join(", ")} (sim: ${(f.phone_sim || 1).toFixed(2)})`;
    } else if (o1.phones?.length && o2.phones?.length) {
      phonePill = "Different active lines (churn)";
    } else {
      phonePill = (o1.phones?.length || o2.phones?.length) ? "Partial phone record" : "No phone logged";
    }

    // 5. Spatial locality & relocation transition
    const d1 = new Date(o1.timestamp);
    const d2 = new Date(o2.timestamp);
    const dtDays = Math.abs(Math.round((d2 - d1) / (1000 * 60 * 60 * 24)));
    const distKm = haversineKm(o1.lat, o1.lon, o2.lat, o2.lon);
    let mobilityText = "";
    let mobilityPill = "";

    if (f.mobility_explanation) {
      mobilityText = f.mobility_explanation;
      if (f.hard_block) {
        mobilityPill = "Simultaneous Conflict";
      } else if (distKm != null && distKm <= 50) {
        mobilityPill = `Local Area (${distKm.toFixed(1)} km · ${dtDays}d)`;
      } else if (distKm != null) {
        mobilityPill = `Relocation (${distKm.toFixed(0)} km · ${dtDays}d)`;
      } else {
        mobilityPill = "Location Missing";
      }
    } else if (distKm != null) {
      if (distKm <= 50) {
        mobilityText = `Local area: ${distKm.toFixed(1)} km apart over ${dtDays} days (habitual activity zone)`;
        mobilityPill = `Local Area (${distKm.toFixed(1)} km · ${dtDays}d)`;
      } else {
        mobilityText = `Inter-city distance: ${distKm.toFixed(0)} km apart across ${dtDays} days`;
        mobilityPill = `Relocation (${distKm.toFixed(0)} km · ${dtDays}d)`;
      }
    } else {
      mobilityText = `${dtDays} days elapsed (location coordinates missing)`;
      mobilityPill = `${dtDays} days elapsed`;
    }

    // 6. Context continuity
    const contextParts = [];
    if (o1.household_id && o1.household_id === o2.household_id) contextParts.push(`Household ${o1.household_id}`);
    if (o1.employer_id && o1.employer_id === o2.employer_id) contextParts.push(`Employer ${o1.employer_id}`);
    if (o1.persistent_token && o1.persistent_token === o2.persistent_token) contextParts.push("Shared Device Token");
    const contextPill = contextParts.length ? contextParts.join(", ") : "Independent context";

    // Synthesized narrative
    const highlights = [];
    if (nameText) highlights.push(nameText);
    if (dobText && !dobText.includes("neutral")) highlights.push(dobText);
    if (sharedEmails.length) highlights.push(emailText);
    if (sharedPhones.length) highlights.push(phoneText);
    if (contextParts.length) highlights.push(contextParts.join(" and "));
    highlights.push(mobilityText);

    const narrative = `The algorithm connects these observations with <b>${scorePct} resolution probability</b> based on ${highlights.join(", ")}.`;

    return {
      scorePct,
      scoreVal,
      isHigh,
      narrative,
      pills: [
        { label: "Name Match", val: namePill },
        { label: "Date of Birth", val: dobPill },
        { label: "Email Anchor", val: emailPill },
        { label: "Phone Line", val: phonePill },
        { label: "Mobility & Relocation", val: mobilityPill },
        { label: "Context Continuity", val: contextPill },
      ],
    };
  }

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

  function initTimelineControls() {
    const playBtn = $("#timelinePlayBtn");
    const prevBtn = $("#timelinePrevBtn");
    const nextBtn = $("#timelineNextBtn");
    const replayBtn = $("#timelineReplayBtn");
    const scrubber = $("#timelineScrubber");
    const speedSelect = $("#timelineSpeedSelect");
    const closeBtn = $("#explanationCloseBtn");

    if (playBtn) playBtn.addEventListener("click", togglePlayTimeline);
    if (prevBtn) prevBtn.addEventListener("click", () => stepTimeline(-1));
    if (nextBtn) nextBtn.addEventListener("click", () => stepTimeline(1));
    if (replayBtn) replayBtn.addEventListener("click", replayTimeline);

    if (scrubber) {
      scrubber.addEventListener("input", (e) => {
        seekTimeline(parseInt(e.target.value, 10));
      });
    }

    if (speedSelect) {
      speedSelect.addEventListener("change", (e) => {
        timelineState.speedMs = parseInt(e.target.value, 10);
        if (timelineState.isPlaying) {
          pauseTimeline();
          playTimeline();
        }
      });
    }

    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        const card = $("#mapExplanationCard");
        if (card) card.hidden = true;
      });
    }
  }

  function togglePlayTimeline() {
    if (timelineState.isPlaying) {
      pauseTimeline();
    } else {
      if (timelineState.step >= timelineState.obsList.length - 1) {
        timelineState.step = 0;
        applyTimelineStep(0, true);
      }
      playTimeline();
    }
  }

  function playTimeline() {
    if (timelineState.obsList.length <= 1) return;
    timelineState.isPlaying = true;
    const playBtn = $("#timelinePlayBtn");
    if (playBtn) {
      playBtn.textContent = "⏸ Pause";
      playBtn.classList.add("playing");
    }
    clearInterval(timelineState.timer);
    timelineState.timer = setInterval(() => {
      if (timelineState.step < timelineState.obsList.length - 1) {
        timelineState.step++;
        applyTimelineStep(timelineState.step, true);
      } else {
        pauseTimeline();
      }
    }, timelineState.speedMs);
  }

  function pauseTimeline() {
    timelineState.isPlaying = false;
    clearInterval(timelineState.timer);
    timelineState.timer = null;
    const playBtn = $("#timelinePlayBtn");
    if (playBtn) {
      playBtn.textContent = "▶ Play";
      playBtn.classList.remove("playing");
    }
  }

  function replayTimeline() {
    pauseTimeline();
    timelineState.step = 0;
    applyTimelineStep(0, true);
    playTimeline();
  }

  function stepTimeline(delta) {
    pauseTimeline();
    const newStep = Math.max(0, Math.min(timelineState.obsList.length - 1, timelineState.step + delta));
    timelineState.step = newStep;
    applyTimelineStep(newStep, true);
  }

  function seekTimeline(newStep) {
    pauseTimeline();
    timelineState.step = Math.max(0, Math.min(timelineState.obsList.length - 1, newStep));
    applyTimelineStep(timelineState.step, true);
  }

  function applyTimelineStep(stepIdx, centerMap = false) {
    const obs = timelineState.obsList;
    if (!obs || obs.length === 0) return;

    // 1. Manage marker visibility and active emphasis
    timelineState.markers.forEach((m, idx) => {
      if (idx <= stepIdx) {
        if (!state.trajectoryLayerGroup.hasLayer(m)) {
          state.trajectoryLayerGroup.addLayer(m);
        }
        if (idx === stepIdx) {
          m.setRadius(9);
          m.setStyle({ weight: 3 });
        } else {
          m.setRadius(7);
          m.setStyle({ weight: 2 });
        }
      } else {
        if (state.trajectoryLayerGroup.hasLayer(m)) {
          state.trajectoryLayerGroup.removeLayer(m);
        }
      }
    });

    // 2. Manage segment visibility and styling
    timelineState.segments.forEach((seg, idx) => {
      if (idx < stepIdx) {
        if (!state.trajectoryLayerGroup.hasLayer(seg.line)) {
          state.trajectoryLayerGroup.addLayer(seg.line);
        }
        if (idx === stepIdx - 1) {
          seg.line.setStyle({
            color: "#ff6b6b",
            weight: 5.5,
            opacity: 1.0,
            dashArray: null,
          });
        } else {
          seg.line.setStyle({
            color: "#3b5bdb",
            weight: 3.5,
            opacity: 0.85,
            dashArray: "6, 6",
          });
        }
      } else {
        if (state.trajectoryLayerGroup.hasLayer(seg.line)) {
          state.trajectoryLayerGroup.removeLayer(seg.line);
        }
      }
    });

    // 3. Update scrubber and status badge
    const activeObs = obs[stepIdx];
    const scrubber = $("#timelineScrubber");
    if (scrubber) scrubber.value = stepIdx;
    const statusBadge = $("#timelineStatus");
    if (statusBadge && activeObs) {
      statusBadge.textContent = `Waypoint ${stepIdx + 1} of ${obs.length} · ${activeObs.timestamp} · ${activeObs.city}`;
    }

    // 5. Update and show Connection Explanation Card
    const card = $("#mapExplanationCard");
    const titleText = $("#explanationTitleText");
    const scoreBadge = $("#explanationScoreBadge");
    const bodyEl = $("#explanationBody");

    if (card && titleText && scoreBadge && bodyEl) {
      card.hidden = false;
      if (stepIdx > 0) {
        const prevObs = obs[stepIdx - 1];
        const pair = getPairBetween(prevObs.observation_id, activeObs.observation_id);
        const exp = generateConnectionExplanation(prevObs, activeObs, pair);

        titleText.textContent = `Link #${stepIdx} ➔ #${stepIdx + 1}: ${prevObs.city} → ${activeObs.city}`;
        scoreBadge.textContent = `P = ${exp.scoreVal} (${exp.scorePct})`;
        scoreBadge.className = "explanation-score-badge" + (exp.isHigh ? " high" : "");

        bodyEl.innerHTML = `
          <div class="explanation-narrative">${exp.narrative}</div>
          <div class="explanation-pill-grid">
            ${exp.pills.map((p) => `
              <div class="explanation-pill">
                <span class="explanation-pill-label">${p.label}</span>
                <span class="explanation-pill-val">${p.val}</span>
              </div>
            `).join("")}
          </div>
        `;
      } else {
        titleText.textContent = `Initial Sighting: ${activeObs.city}`;
        scoreBadge.textContent = "Start Point";
        scoreBadge.className = "explanation-score-badge";
        bodyEl.innerHTML = `
          <div class="explanation-narrative">
            Reconstructed timeline starts here on <b>${activeObs.timestamp}</b> for <b>${activeObs.first_name} ${activeObs.last_name}</b>.
            Click <b>Play (▶)</b> or <b>Next (⏭)</b> to advance the trajectory and inspect why the algorithm connects each subsequent sighting.
          </div>
        `;
      }
    }

    // 6. Intelligent adaptive camera framing (re-evaluated at each time step)
    if (centerMap && state.map && activeObs) {
      updateMapCameraForStep(stepIdx);
    }

    // 7. Synchronize active observation row in observations table below map
    highlightActiveMapObsRow(stepIdx);
  }

  const RELOCATION_THRESHOLD_KM = 80;

  function updateMapCameraForStep(stepIdx) {
    if (!state.map) return;
    const obs = timelineState.obsList;
    if (!obs || obs.length === 0 || stepIdx < 0 || stepIdx >= obs.length) return;

    const activeObs = obs[stepIdx];
    if (activeObs.lat == null || activeObs.lon == null) return;

    // Step 0: Initial observation
    if (stepIdx === 0) {
      state.map.setView([activeObs.lat, activeObs.lon], 13, { animate: true, duration: 0.5 });
      return;
    }

    // Determine the current local cluster start index (most recent relocation > RELOCATION_THRESHOLD_KM)
    let clusterStartIdx = 0;
    for (let i = 1; i <= stepIdx; i++) {
      const prev = obs[i - 1];
      const curr = obs[i];
      if (prev.lat != null && prev.lon != null && curr.lat != null && curr.lon != null) {
        const d = haversineKm(prev.lat, prev.lon, curr.lat, curr.lon);
        if (d != null && d > RELOCATION_THRESHOLD_KM) {
          clusterStartIdx = i;
        }
      }
    }

    // Case 1: The current step is itself a large relocation from the previous observation
    if (stepIdx === clusterStartIdx) {
      // If relocation distance is too large: show current location with the same zoom level as previous time step
      const previousZoom = state.map.getZoom() || 13;
      state.map.setView([activeObs.lat, activeObs.lon], previousZoom, {
        animate: true,
        duration: 0.6,
      });
      return;
    }

    // Case 2: Local movement within the same area
    // Re-evaluate zoom to appropriately frame all past observations in the current local journey
    const localPastObs = obs.slice(clusterStartIdx, stepIdx + 1).filter((o) => o.lat != null && o.lon != null);
    if (localPastObs.length <= 1) {
      const previousZoom = state.map.getZoom() || 13;
      state.map.setView([activeObs.lat, activeObs.lon], previousZoom, {
        animate: true,
        duration: 0.5,
      });
    } else {
      const latLngs = localPastObs.map((o) => [o.lat, o.lon]);
      const bounds = L.latLngBounds(latLngs);
      state.map.fitBounds(bounds, {
        padding: [60, 60],
        maxZoom: 14,
        animate: true,
        duration: 0.5,
      });
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

  function renderMapObservationsTable() {
    const body = $("#mapObsBody");
    if (!body) return;
    body.innerHTML = "";

    const clusterId = $("#mapEntitySelect") ? $("#mapEntitySelect").value : null;
    const entity = state.result && state.result.entities
      ? state.result.entities.find((e) => e.cluster_id === clusterId)
      : null;

    const filterEntity = $("#mapObsFilterEntity") ? $("#mapObsFilterEntity").checked : true;
    const countBadge = $("#mapObsCountBadge");
    const titleEl = $("#mapObsTableTitle");

    const trajectoryObs = timelineState.obsList || [];
    const obsIdToWaypoint = new Map();
    trajectoryObs.forEach((o, idx) => {
      obsIdToWaypoint.set(o.observation_id, idx);
    });

    let displayList = [];
    if (filterEntity) {
      displayList = trajectoryObs;
      if (titleEl && entity) {
        titleEl.textContent = `${entity.cluster_id} — Observations Data`;
      }
      if (countBadge) {
        countBadge.textContent = `${displayList.length} observations`;
      }
    } else {
      displayList = state.observations
        .slice()
        .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
      if (titleEl) {
        titleEl.textContent = "All Observations Feed (Filtered by Map Entity)";
      }
      if (countBadge) {
        countBadge.textContent = `${displayList.length} total (${trajectoryObs.length} in route)`;
      }
    }

    if (displayList.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 12;
      td.style.textAlign = "center";
      td.style.color = "var(--muted)";
      td.style.padding = "16px";
      td.textContent = "No observations to display for this selection.";
      tr.appendChild(td);
      body.appendChild(tr);
      return;
    }

    const frag = document.createDocumentFragment();
    displayList.forEach((o) => {
      const tr = document.createElement("tr");
      tr.dataset.obsId = o.observation_id;

      const wpIdx = obsIdToWaypoint.get(o.observation_id);
      const isEntityObs = wpIdx !== undefined;

      if (isEntityObs) {
        tr.dataset.stepIdx = wpIdx;
        tr.title = `Waypoint #${wpIdx + 1} — Click to focus on map`;
      } else {
        tr.style.opacity = "0.55";
        tr.title = `External observation (Entity: ${o.entity_id_truth || "other"})`;
      }

      const emailsStr = o.emails && o.emails.length ? o.emails.join(", ") : "–";
      const phonesStr = o.phones && o.phones.length ? o.phones.join(", ") : "–";
      const locationStr = o.address ? `${o.city} · ${o.address}` : (o.city || "–");

      const cells = [
        isEntityObs ? `#${wpIdx + 1}` : "–",
        o.observation_id,
        o.timestamp,
        locationStr,
        `${o.first_name} ${o.last_name}`,
        o.dob || "–",
        emailsStr,
        phonesStr,
        o.household_id || "–",
        o.employer_id || "–",
        o.persistent_token ? o.persistent_token.slice(0, 8) : "–",
        state.showTruth ? o.entity_id_truth : "hidden",
      ];

      cells.forEach((c) => {
        const td = document.createElement("td");
        td.textContent = c;
        tr.appendChild(td);
      });

      if (isEntityObs) {
        tr.addEventListener("click", () => {
          seekTimeline(wpIdx);
        });
      }

      frag.appendChild(tr);
    });

    body.appendChild(frag);
    highlightActiveMapObsRow(timelineState.step);
  }

  function highlightActiveMapObsRow(stepIdx) {
    const body = $("#mapObsBody");
    if (!body) return;

    const rows = body.querySelectorAll("tr");
    rows.forEach((r) => r.classList.remove("active-obs-row"));

    const activeObs = timelineState.obsList && timelineState.obsList[stepIdx];
    if (!activeObs) return;

    const targetRow = body.querySelector(`tr[data-obs-id="${activeObs.observation_id}"]`);
    if (targetRow) {
      targetRow.classList.add("active-obs-row");
      targetRow.scrollIntoView({ block: "nearest", behavior: "smooth" });
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

    pauseTimeline();
    state.backgroundLayerGroup.clearLayers();
    state.trajectoryLayerGroup.clearLayers();
    currentEntityLatLngs = [];
    timelineState.markers = [];
    timelineState.segments = [];

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

    if (obs.length === 0) {
      const timelineBar = $("#mapTimelineBar");
      if (timelineBar) {
        timelineBar.style.opacity = "0.5";
        timelineBar.style.pointerEvents = "none";
      }
      const card = $("#mapExplanationCard");
      if (card) card.hidden = true;
      timelineState.obsList = [];
      currentEntityLatLngs = [];
      renderMapObservationsTable();
      return;
    }

    const timelineBar = $("#mapTimelineBar");
    if (timelineBar) {
      timelineBar.style.opacity = "1";
      timelineBar.style.pointerEvents = "auto";
    }
    timelineState.obsList = obs;
    currentEntityLatLngs = obs.map((o) => [o.lat, o.lon]);
    renderMapObservationsTable();

    // 2. Build individual consecutive line segments with explainability tooltips
    for (let k = 0; k < obs.length - 1; k++) {
      const o1 = obs[k];
      const o2 = obs[k + 1];
      const pair = getPairBetween(o1.observation_id, o2.observation_id);
      const exp = generateConnectionExplanation(o1, o2, pair);

      const segLine = L.polyline(
        [[o1.lat, o1.lon], [o2.lat, o2.lon]],
        {
          color: "#3b5bdb",
          weight: 3.5,
          opacity: 0.85,
          dashArray: "6, 6",
          lineCap: "round",
        }
      );

      const tooltipContent = `
        <div style="font-weight:700;color:var(--accent);margin-bottom:3px;">
          Link #${k + 1} ➔ #${k + 2}: ${o1.city} → ${o2.city}
        </div>
        <div style="font-size:0.8rem;margin-bottom:4px;">
          <b>Resolution Confidence:</b> <span style="font-weight:700;color:${exp.isHigh ? "var(--good)" : "var(--warn)"};">${exp.scorePct}</span> (P = ${exp.scoreVal})
        </div>
        <div style="font-size:0.75rem;color:var(--muted);max-width:280px;line-height:1.4;">
          ${exp.narrative}
        </div>
      `;

      segLine.bindTooltip(tooltipContent, {
        sticky: true,
        className: "trajectory-segment-tooltip",
      });

      segLine.on("click", () => {
        seekTimeline(k + 1);
      });

      segLine.on("mouseover", () => {
        segLine.setStyle({ weight: 5.5, opacity: 1.0 });
      });

      segLine.on("mouseout", () => {
        if (timelineState.step - 1 !== k) {
          segLine.setStyle({ weight: 3.5, opacity: 0.85 });
        }
      });

      timelineState.segments.push({
        line: segLine,
        fromIdx: k,
        toIdx: k + 1,
        pair,
        explanation: exp,
      });
    }

    // 3. Build waypoint markers with rich popups
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

      const emailsStr = (o.emails && o.emails.length) ? o.emails.join(", ") : "None";
      const phonesStr = (o.phones && o.phones.length) ? o.phones.join(", ") : "None";

      const popupHtml = `
        <div class="map-popup-body">
          <div style="font-weight:700;font-size:0.95rem;margin-bottom:4px;color:var(--text);">${o.first_name} ${o.last_name}</div>
          <div style="font-size:0.8rem;color:var(--muted);margin-bottom:6px;">Waypoint ${idx + 1} of ${obs.length}</div>
          <div style="display:grid;gap:2px;font-size:0.8rem;">
            <div><b>Date:</b> ${o.timestamp}</div>
            <div><b>Location:</b> ${o.city}</div>
            ${o.address ? `<div><b>Address:</b> ${o.address}</div>` : ""}
            ${o.dob ? `<div><b>DOB:</b> ${o.dob}</div>` : ""}
            <div><b>Email:</b> ${emailsStr}</div>
            <div><b>Phone:</b> ${phonesStr}</div>
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

      marker.on("click", () => {
        seekTimeline(idx);
      });

      timelineState.markers.push(marker);
    });

    // 4. Initialize Scrubber
    const scrubber = $("#timelineScrubber");
    if (scrubber) {
      scrubber.min = 0;
      scrubber.max = obs.length - 1;
      scrubber.value = obs.length - 1;
    }

    // Default: show full trajectory at final step
    timelineState.step = obs.length - 1;
    applyTimelineStep(timelineState.step, false);
    fitCurrentTrajectory();
  }

  // ---------------------------------------------------- data generator --
  function formatCount(num) {
    if (num >= 1e9) return (num / 1e9).toFixed(1) + "B";
    if (num >= 1e6) return (num / 1e6).toFixed(1) + "M";
    if (num >= 1e3) return (num / 1e3).toFixed(1) + "k";
    return (num || 0).toLocaleString();
  }

  function formatBytes(bytes) {
    if (!bytes || isNaN(bytes)) return "0 B";
    if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(1) + " GB";
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MB";
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + " KB";
    return bytes + " B";
  }

  const generatorState = {
    mode: "live", // "live" or "batch"
    batchPollTimer: null,
  };

  const GENERATOR_PRESETS = {
    benchmark: {
      seed: 42,
      n_individuals: 30,
      obs_dist: "gaussian",
      mean_obs: 10.2,
      std_obs: 3.5,
      min_obs: 2,
      max_obs: 80,
      pct_never: 50,
      pct_county: 30,
      pct_state: 15,
      pct_cross_us: 5,
      mean_county_moves: 1.8,
      std_county_moves: 0.8,
      mean_state_moves: 2.2,
      std_state_moves: 0.9,
      mean_cross_moves: 3.1,
      std_cross_moves: 1.2,
      pct_household: 5.0,
      pct_collision: 2.0,
      include_phone_reallocation: true,
      enable_dob_noise: true,
      rate_dob_year_only: 0.10,
      rate_dob_year_month: 0.10,
      rate_dob_shift: 0.12,
      drop_dob_rate: 0.12,
      enable_name_noise: true,
      rate_first_noise: 0.35,
      rate_last_noise: 0.15,
      drop_address_rate: 0.10,
      drop_phone_rate: 0.08,
      drop_email_rate: 0.08,
      token_rate: 0.60,
      employer_rate: 0.70,
    },
    clean: {
      seed: 42,
      n_individuals: 30,
      obs_dist: "gaussian",
      mean_obs: 10.2,
      std_obs: 3.5,
      min_obs: 2,
      max_obs: 80,
      pct_never: 50,
      pct_county: 30,
      pct_state: 15,
      pct_cross_us: 5,
      mean_county_moves: 1.8,
      std_county_moves: 0.8,
      mean_state_moves: 2.2,
      std_state_moves: 0.9,
      mean_cross_moves: 3.1,
      std_cross_moves: 1.2,
      pct_household: 5.0,
      pct_collision: 2.0,
      include_phone_reallocation: true,
      enable_dob_noise: false,
      rate_dob_year_only: 0.0,
      rate_dob_year_month: 0.0,
      rate_dob_shift: 0.0,
      drop_dob_rate: 0.0,
      enable_name_noise: false,
      rate_first_noise: 0.0,
      rate_last_noise: 0.0,
      drop_address_rate: 0.0,
      drop_phone_rate: 0.0,
      drop_email_rate: 0.0,
      token_rate: 0.80,
      employer_rate: 0.80,
    },
    challenging: {
      seed: 42,
      n_individuals: 30,
      obs_dist: "negbinom",
      mean_obs: 12.0,
      std_obs: 6.0,
      min_obs: 1,
      max_obs: 100,
      pct_never: 35,
      pct_county: 35,
      pct_state: 20,
      pct_cross_us: 10,
      mean_county_moves: 2.2,
      std_county_moves: 1.0,
      mean_state_moves: 2.8,
      std_state_moves: 1.2,
      mean_cross_moves: 4.0,
      std_cross_moves: 1.5,
      pct_household: 8.0,
      pct_collision: 4.0,
      include_phone_reallocation: true,
      enable_dob_noise: true,
      rate_dob_year_only: 0.20,
      rate_dob_year_month: 0.20,
      rate_dob_shift: 0.24,
      drop_dob_rate: 0.20,
      enable_name_noise: true,
      rate_first_noise: 0.50,
      rate_last_noise: 0.30,
      drop_address_rate: 0.20,
      drop_phone_rate: 0.18,
      drop_email_rate: 0.18,
      token_rate: 0.40,
      employer_rate: 0.50,
    },
    high_mobility: {
      seed: 42,
      n_individuals: 30,
      obs_dist: "gaussian",
      mean_obs: 12.0,
      std_obs: 4.0,
      min_obs: 3,
      max_obs: 80,
      pct_never: 15,
      pct_county: 35,
      pct_state: 30,
      pct_cross_us: 20,
      mean_county_moves: 2.0,
      std_county_moves: 0.9,
      mean_state_moves: 3.0,
      std_state_moves: 1.1,
      mean_cross_moves: 4.5,
      std_cross_moves: 1.5,
      pct_household: 5.0,
      pct_collision: 3.0,
      include_phone_reallocation: true,
      enable_dob_noise: true,
      rate_dob_year_only: 0.10,
      rate_dob_year_month: 0.10,
      rate_dob_shift: 0.12,
      drop_dob_rate: 0.12,
      enable_name_noise: true,
      rate_first_noise: 0.35,
      rate_last_noise: 0.15,
      drop_address_rate: 0.10,
      drop_phone_rate: 0.08,
      drop_email_rate: 0.08,
      token_rate: 0.60,
      employer_rate: 0.70,
    },
    massive_100k: {
      seed: 42,
      n_individuals: 100000,
      obs_dist: "gaussian",
      mean_obs: 10.0,
      std_obs: 3.5,
      min_obs: 2,
      max_obs: 80,
      pct_never: 50,
      pct_county: 30,
      pct_state: 15,
      pct_cross_us: 5,
      mean_county_moves: 1.8,
      std_county_moves: 0.8,
      mean_state_moves: 2.2,
      std_state_moves: 0.9,
      mean_cross_moves: 3.1,
      std_cross_moves: 1.2,
      pct_household: 5.0,
      pct_collision: 2.0,
      include_phone_reallocation: true,
      enable_dob_noise: true,
      rate_dob_year_only: 0.10,
      rate_dob_year_month: 0.10,
      rate_dob_shift: 0.12,
      drop_dob_rate: 0.12,
      enable_name_noise: true,
      rate_first_noise: 0.35,
      rate_last_noise: 0.15,
      drop_address_rate: 0.10,
      drop_phone_rate: 0.08,
      drop_email_rate: 0.08,
      token_rate: 0.60,
      employer_rate: 0.70,
    },
    small: {
      seed: 42,
      n_individuals: 15,
      obs_dist: "gaussian",
      mean_obs: 10.0,
      std_obs: 3.0,
      min_obs: 2,
      max_obs: 40,
      pct_never: 50,
      pct_county: 30,
      pct_state: 15,
      pct_cross_us: 5,
      mean_county_moves: 1.5,
      std_county_moves: 0.6,
      mean_state_moves: 2.0,
      std_state_moves: 0.8,
      mean_cross_moves: 2.5,
      std_cross_moves: 1.0,
      pct_household: 6.0,
      pct_collision: 3.0,
      include_phone_reallocation: true,
      enable_dob_noise: true,
      rate_dob_year_only: 0.10,
      rate_dob_year_month: 0.10,
      rate_dob_shift: 0.12,
      drop_dob_rate: 0.12,
      enable_name_noise: true,
      rate_first_noise: 0.35,
      rate_last_noise: 0.15,
      drop_address_rate: 0.10,
      drop_phone_rate: 0.08,
      drop_email_rate: 0.08,
      token_rate: 0.60,
      employer_rate: 0.70,
    },
  };

  function balanceRelocationTiers(changedKey) {
    const keys = ["pct_never", "pct_county", "pct_state", "pct_cross_us"];
    const sliderChanged = $(`#gen_${changedKey}`);
    if (!sliderChanged) return;

    let v = Math.max(0, Math.min(100, parseInt(sliderChanged.value, 10) || 0));
    sliderChanged.value = v;

    const otherKeys = keys.filter((k) => k !== changedKey);
    let rem = 100 - v;
    let otherSum = otherKeys.reduce((acc, k) => acc + (parseInt($(`#gen_${k}`)?.value, 10) || 0), 0);

    if (otherSum <= 0) {
      const each = Math.floor(rem / otherKeys.length);
      otherKeys.forEach((k, idx) => {
        const el = $(`#gen_${k}`);
        if (el) el.value = idx === otherKeys.length - 1 ? rem - each * (otherKeys.length - 1) : each;
      });
    } else {
      let allocated = 0;
      otherKeys.forEach((k, idx) => {
        const el = $(`#gen_${k}`);
        if (!el) return;
        if (idx === otherKeys.length - 1) {
          el.value = Math.max(0, rem - allocated);
        } else {
          const current = parseInt(el.value, 10) || 0;
          const share = Math.round((current / otherSum) * rem);
          el.value = Math.max(0, Math.min(rem, share));
          allocated += parseInt(el.value, 10);
        }
      });
    }
    updateGeneratorLabels();
  }

  function logGamma(z) {
    if (z <= 0) return 0;
    const c = [
      57.1562356658629235,
      -59.5979603554754912,
      14.1360979747417471,
      -0.491913816097620199,
      0.339946499848118887e-4,
      0.465236289270485756e-4,
      -0.983744753048795646e-4,
      0.158088703224378388e-3,
      -0.210264441724104883e-3,
      0.217439618115212643e-3,
      -0.164318106536763890e-3,
      0.844182239838527433e-4,
      -0.261908384015814087e-4,
      0.368991826595316234e-5,
    ];
    let y = z;
    let x = 0.99999999999999709182;
    for (let i = 0; i < c.length; i++) {
      x += c[i] / (z + i + 1);
    }
    const t = z + c.length - 0.5;
    return 0.91893853320467274178 + (z + 0.5) * Math.log(t) - t + Math.log(x) - Math.log(z);
  }

  function computeDistributionPMF(distType, mean, std, kMin, kMax) {
    let maxK = Math.max(25, Math.ceil(mean + 3.2 * Math.max(1, std)));
    if (kMax < 150) {
      maxK = Math.max(maxK, Math.min(100, kMax + 2));
    }
    maxK = Math.min(120, Math.max(maxK, kMin + 15));

    const pmf = [];
    let sum = 0;

    for (let k = 0; k <= maxK; k++) {
      let p = 0;
      if (k >= kMin && k <= kMax) {
        if (distType === "gaussian") {
          const s = Math.max(0.1, std);
          const z = (k - mean) / s;
          p = Math.exp(-0.5 * z * z);
        } else if (distType === "negbinom") {
          const variance = Math.max(mean * 1.05, std * std);
          const p_succ = mean / variance;
          const r = (mean * mean) / (variance - mean);
          p = Math.exp(logGamma(k + r) - logGamma(k + 1) - logGamma(r) + r * Math.log(p_succ) + k * Math.log(1 - p_succ));
        } else if (distType === "lognormal") {
          if (k > 0) {
            const v = std * std;
            const m = Math.max(0.1, mean);
            const sigmaL = Math.sqrt(Math.log(1 + v / (m * m)));
            const muL = Math.log(m) - 0.5 * sigmaL * sigmaL;
            const z = (Math.log(k) - muL) / sigmaL;
            p = (1 / (k * sigmaL)) * Math.exp(-0.5 * z * z);
          }
        } else if (distType === "uniform") {
          p = 1.0;
        } else if (distType === "fixed") {
          p = (k === Math.round(mean)) ? 1.0 : 0.0;
        }
      }
      if (isNaN(p) || !isFinite(p) || p < 0) p = 0;
      pmf.push({ k, p });
      sum += p;
    }

    if (sum > 0) {
      for (const d of pmf) d.p /= sum;
    }

    return { pmf, maxK };
  }

  function renderDistributionViewer() {
    const svg = $("#distViewerSvg");
    if (!svg) return;

    const distType = $("#gen_obs_dist")?.value || "gaussian";
    const mean = parseFloat($("#gen_mean_obs")?.value || 10.2);
    const std = parseFloat($("#gen_std_obs")?.value || 3.5);
    const kMin = parseInt($("#gen_min_obs")?.value || 2, 10);
    const kMax = parseInt($("#gen_max_obs")?.value || 80, 10);

    const { pmf, maxK } = computeDistributionPMF(distType, mean, std, kMin, kMax);

    // Compute stats: Mode, 95% interval
    let modeK = kMin;
    let maxP = 0;
    pmf.forEach((d) => {
      if (d.p > maxP) {
        maxP = d.p;
        modeK = d.k;
      }
    });

    let cum = 0;
    let ciLow = kMin;
    let ciHigh = maxK;
    let foundLow = false;
    for (const d of pmf) {
      cum += d.p;
      if (!foundLow && cum >= 0.025) {
        ciLow = d.k;
        foundLow = true;
      }
      if (cum >= 0.975) {
        ciHigh = d.k;
        break;
      }
    }

    const statsEl = $("#distViewerStats");
    if (statsEl) {
      if (distType === "fixed") {
        statsEl.textContent = `Fixed: k = ${Math.round(mean)} obs`;
      } else if (distType === "uniform") {
        statsEl.textContent = `Uniform: [${kMin}, ${kMax}] · E[K] = ${mean.toFixed(1)}`;
      } else {
        statsEl.textContent = `Mode: ${modeK} · 95% CI: [${ciLow}, ${ciHigh}]`;
      }
    }

    // Drawing coordinates
    const vbW = 340;
    const vbH = 140;
    const padL = 28;
    const padR = 14;
    const padT = 20;
    const padB = 22;
    const plotW = vbW - padL - padR;
    const plotH = vbH - padT - padB;

    const yMax = Math.max(0.05, maxP * 1.25);
    const xCoord = (k) => padL + (k / maxK) * plotW;
    const yCoord = (p) => padT + plotH - (Math.min(yMax, p) / yMax) * plotH;

    // Build SVG Path
    let areaPath = `M ${xCoord(0)} ${padT + plotH}`;
    let strokePath = `M ${xCoord(0)} ${yCoord(pmf[0].p)}`;
    for (let i = 0; i < pmf.length; i++) {
      const x = xCoord(pmf[i].k);
      const y = yCoord(pmf[i].p);
      areaPath += ` L ${x} ${y}`;
      if (i > 0) strokePath += ` L ${x} ${y}`;
    }
    areaPath += ` L ${xCoord(pmf[pmf.length - 1].k)} ${padT + plotH} Z`;

    // Discrete bars
    const barW = Math.max(2, Math.min(8, (plotW / (maxK + 1)) * 0.75));
    let barsHtml = "";
    pmf.forEach((d) => {
      if (d.p > 0.002) {
        const x = xCoord(d.k) - barW / 2;
        const y = yCoord(d.p);
        const h = padT + plotH - y;
        barsHtml += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" rx="1.5" fill="var(--accent)" opacity="0.32" />`;
      }
    });

    // Mean indicator
    const meanX = xCoord(Math.min(maxK, Math.max(0, mean)));
    const meanMarkerHtml = `
      <line x1="${meanX.toFixed(1)}" y1="${padT}" x2="${meanX.toFixed(1)}" y2="${padT + plotH}" stroke="var(--warn)" stroke-width="1.6" stroke-dasharray="3,3" />
      <text x="${meanX.toFixed(1)}" y="${padT - 5}" fill="var(--warn)" font-size="9" font-weight="700" text-anchor="middle">&mu;=${mean.toFixed(1)}</text>
    `;

    // Truncation markers
    let truncHtml = "";
    if (kMin > 0) {
      const minX = xCoord(kMin);
      truncHtml += `<line x1="${minX.toFixed(1)}" y1="${padT + 8}" x2="${minX.toFixed(1)}" y2="${padT + plotH}" stroke="var(--bad)" stroke-width="1.2" stroke-dasharray="2,2" opacity="0.85" />
      <text x="${minX.toFixed(1)}" y="${padT + 6}" fill="var(--bad)" font-size="8" font-weight="600" text-anchor="middle">k_min</text>`;
    }
    if (kMax < maxK) {
      const maxX = xCoord(kMax);
      truncHtml += `<line x1="${maxX.toFixed(1)}" y1="${padT + 8}" x2="${maxX.toFixed(1)}" y2="${padT + plotH}" stroke="var(--bad)" stroke-width="1.2" stroke-dasharray="2,2" opacity="0.85" />
      <text x="${maxX.toFixed(1)}" y="${padT + 6}" fill="var(--bad)" font-size="8" font-weight="600" text-anchor="middle">k_max</text>`;
    }

    // Grid & Axis Ticks
    const tickStep = maxK <= 30 ? 5 : maxK <= 60 ? 10 : 20;
    let ticksHtml = "";
    for (let k = 0; k <= maxK; k += tickStep) {
      const x = xCoord(k);
      ticksHtml += `
        <line x1="${x.toFixed(1)}" y1="${padT + plotH}" x2="${x.toFixed(1)}" y2="${padT + plotH + 4}" stroke="var(--border)" stroke-width="1" />
        <text x="${x.toFixed(1)}" y="${padT + plotH + 14}" fill="var(--muted)" font-size="8" text-anchor="middle">${k}</text>
      `;
    }

    svg.innerHTML = `
      <defs>
        <linearGradient id="distGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.4" />
          <stop offset="100%" stop-color="var(--accent)" stop-opacity="0.03" />
        </linearGradient>
      </defs>
      <!-- Baseline -->
      <line x1="${padL}" y1="${padT + plotH}" x2="${padL + plotW}" y2="${padT + plotH}" stroke="var(--border)" stroke-width="1.2" />
      <!-- Grid Ticks -->
      ${ticksHtml}
      <!-- Bars -->
      ${barsHtml}
      <!-- Filled Density Area -->
      <path d="${areaPath}" fill="url(#distGrad)" />
      <!-- Density Stroke -->
      <path d="${strokePath}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
      <!-- Truncation lines -->
      ${truncHtml}
      <!-- Mean Line -->
      ${meanMarkerHtml}
    `;

    // Interactive hover
    svg.onmousemove = (e) => {
      const rect = svg.getBoundingClientRect();
      const relX = ((e.clientX - rect.left) / rect.width) * vbW;
      const k = Math.round(((relX - padL) / plotW) * maxK);
      const tt = $("#distViewerTooltip");
      if (tt && k >= 0 && k < pmf.length) {
        const item = pmf[k];
        const pct = item ? (item.p * 100).toFixed(1) : "0.0";
        tt.textContent = `k = ${k} obs: ${pct}%`;
        tt.hidden = false;
      }
    };
    svg.onmouseleave = () => {
      const tt = $("#distViewerTooltip");
      if (tt) tt.hidden = true;
    };
  }

  function updateGeneratorLabels() {
    const setVal = (id, val) => {
      const el = $(`#${id}`);
      if (el) el.textContent = val;
    };
    const getNum = (id) => parseFloat($(`#${id}`)?.value || 0);

    const n = parseInt($("#gen_n_individuals")?.value || 30, 10);
    setVal("gen_n_individuals_val", n.toLocaleString());

    // Highlight active pill if matches
    document.querySelectorAll(".gen-pill-btn").forEach((pill) => {
      pill.classList.toggle("active", parseInt(pill.dataset.n, 10) === n);
    });

    const meanObs = getNum("gen_mean_obs");
    setVal("gen_mean_obs_val", meanObs.toFixed(1));
    setVal("gen_std_obs_val", getNum("gen_std_obs").toFixed(1));

    // Tiers
    const pNever = getNum("gen_pct_never");
    const pCounty = getNum("gen_pct_county");
    const pState = getNum("gen_pct_state");
    const pCross = getNum("gen_pct_cross_us");

    setVal("gen_pct_never_val", `${pNever}%`);
    setVal("gen_pct_county_val", `${pCounty}%`);
    setVal("gen_pct_state_val", `${pState}%`);
    setVal("gen_pct_cross_us_val", `${pCross}%`);

    // Update stacked bar
    const barNever = $("#relocBarNever");
    if (barNever) {
      barNever.style.width = `${pNever}%`;
      barNever.textContent = pNever > 5 ? `${pNever}%` : "";
      barNever.title = `Tier 0: Non-Movers (${pNever}%)`;
    }
    const barCounty = $("#relocBarCounty");
    if (barCounty) {
      barCounty.style.width = `${pCounty}%`;
      barCounty.textContent = pCounty > 5 ? `${pCounty}%` : "";
      barCounty.title = `Tier 1: Intra-County (${pCounty}%)`;
    }
    const barState = $("#relocBarState");
    if (barState) {
      barState.style.width = `${pState}%`;
      barState.textContent = pState > 5 ? `${pState}%` : "";
      barState.title = `Tier 2: Intra-State (${pState}%)`;
    }
    const barCross = $("#relocBarCross");
    if (barCross) {
      barCross.style.width = `${pCross}%`;
      barCross.textContent = pCross > 5 ? `${pCross}%` : "";
      barCross.title = `Tier 3: Cross-US (${pCross}%)`;
    }

    // Confounders
    const pctHh = getNum("gen_pct_household");
    const hhCount = Math.round(n * (pctHh / 100));
    setVal("gen_pct_household_val", `${pctHh.toFixed(1)}% (~${Math.max(2, hhCount + (hhCount % 2))} entities)`);

    const pctColl = getNum("gen_pct_collision");
    const collCount = Math.round(n * (pctColl / 100));
    setVal("gen_pct_collision_val", `${pctColl.toFixed(1)}% (~${Math.max(2, collCount + (collCount % 2))} entities)`);

    // Noise
    const pct = (id) => `${Math.round(getNum(id) * 100)}%`;
    setVal("gen_rate_dob_year_only_val", pct("gen_rate_dob_year_only"));
    setVal("gen_rate_dob_year_month_val", pct("gen_rate_dob_year_month"));
    setVal("gen_rate_dob_shift_val", pct("gen_rate_dob_shift"));
    setVal("gen_drop_dob_rate_val", pct("gen_drop_dob_rate"));

    setVal("gen_rate_first_noise_val", pct("gen_rate_first_noise"));
    setVal("gen_rate_last_noise_val", pct("gen_rate_last_noise"));
    setVal("gen_drop_address_rate_val", pct("gen_drop_address_rate"));
    setVal("gen_drop_phone_rate_val", pct("gen_drop_phone_rate"));
    setVal("gen_drop_email_rate_val", pct("gen_drop_email_rate"));

    setVal("gen_token_rate_val", pct("gen_token_rate"));
    setVal("gen_employer_rate_val", pct("gen_employer_rate"));

    // Expected output calculation
    const totalEstObs = Math.round(n * meanObs);
    const isCsv = $("#gen_batch_format")?.value === "csv";
    const bytesPerRow = isCsv ? 85 : 190;
    const estBytes = totalEstObs * bytesPerRow;
    const estTimeSec = totalEstObs / 700000;
    const estTimeStr = estTimeSec < 0.1 ? "< 0.1s" : estTimeSec < 60 ? `${estTimeSec.toFixed(1)}s` : `${Math.floor(estTimeSec / 60)}m ${Math.round(estTimeSec % 60)}s`;

    setVal("genEstObsCount", `~${formatCount(totalEstObs)} obs`);
    setVal("genEstFileSize", `· ~${formatBytes(estBytes)}`);

    setVal("batchEstEntities", n.toLocaleString());
    setVal("batchEstObs", `~${formatCount(totalEstObs)} obs`);
    setVal("batchEstSize", `~${formatBytes(estBytes)}`);
    setVal("batchEstTime", estTimeStr);

    const warnEl = $("#genLiveScaleWarning");
    if (warnEl) {
      warnEl.hidden = (n <= 500 || generatorState.mode === "batch");
    }

    renderDistributionViewer();
  }

  function switchGeneratorMode(mode) {
    generatorState.mode = mode;
    const liveBtn = $("#genModeLiveBtn");
    const batchBtn = $("#genModeBatchBtn");
    const livePanel = $("#genLivePanel");
    const batchPanel = $("#genBatchPanel");

    if (liveBtn) liveBtn.classList.toggle("active", mode === "live");
    if (batchBtn) batchBtn.classList.toggle("active", mode === "batch");
    if (livePanel) livePanel.hidden = mode !== "live";
    if (batchPanel) batchPanel.hidden = mode !== "batch";
    updateGeneratorLabels();
  }

  function applyGeneratorPreset(presetKey) {
    const p = GENERATOR_PRESETS[presetKey];
    if (!p) return;

    for (const [key, val] of Object.entries(p)) {
      const el = $(`#gen_${key}`);
      if (!el) continue;
      if (el.type === "checkbox") {
        el.checked = Boolean(val);
      } else {
        el.value = val;
      }
    }

    document.querySelectorAll(".gen-preset-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.preset === presetKey);
    });

    if (presetKey === "massive_100k") {
      switchGeneratorMode("batch");
    }

    updateGeneratorLabels();
  }

  function gatherGeneratorPayload() {
    const isBenchmark = document.querySelector('.gen-preset-btn.active[data-preset="benchmark"]') !== null;
    const n = parseInt($("#gen_n_individuals")?.value || 30, 10);
    const meanObs = parseFloat($("#gen_mean_obs")?.value || 10.2);

    return {
      seed: parseInt($("#gen_seed")?.value || 42, 10),
      n_individuals: n,
      target_obs: (isBenchmark && n === 30) ? 306 : Math.round(n * meanObs),
      obs_distribution: $("#gen_obs_dist")?.value || "gaussian",
      mean_obs_per_person: meanObs,
      std_obs_per_person: parseFloat($("#gen_std_obs")?.value || 3.5),
      min_obs_per_person: parseInt($("#gen_min_obs")?.value || 2, 10),
      max_obs_per_person: parseInt($("#gen_max_obs")?.value || 80, 10),
      pct_never_moved: parseFloat($("#gen_pct_never")?.value || 50),
      pct_county_moved: parseFloat($("#gen_pct_county")?.value || 30),
      pct_state_moved: parseFloat($("#gen_pct_state")?.value || 15),
      pct_cross_us_moved: parseFloat($("#gen_pct_cross_us")?.value || 5),
      mean_county_moves: parseFloat($("#gen_mean_county_moves")?.value || 1.8),
      std_county_moves: parseFloat($("#gen_std_county_moves")?.value || 0.8),
      mean_state_moves: parseFloat($("#gen_mean_state_moves")?.value || 2.2),
      std_state_moves: parseFloat($("#gen_std_state_moves")?.value || 0.9),
      mean_cross_moves: parseFloat($("#gen_mean_cross_moves")?.value || 3.1),
      std_cross_moves: parseFloat($("#gen_std_cross_moves")?.value || 1.2),
      pct_household: parseFloat($("#gen_pct_household")?.value || 5.0),
      pct_collision: parseFloat($("#gen_pct_collision")?.value || 2.0),
      include_phone_reallocation: $("#gen_include_phone_reallocation")?.checked ?? true,
      enable_dob_noise: $("#gen_enable_dob_noise")?.checked ?? true,
      rate_dob_year_only: parseFloat($("#gen_rate_dob_year_only")?.value || 0.10),
      rate_dob_year_month: parseFloat($("#gen_rate_dob_year_month")?.value || 0.10),
      rate_dob_shift: parseFloat($("#gen_rate_dob_shift")?.value || 0.12),
      drop_dob_rate: parseFloat($("#gen_drop_dob_rate")?.value || 0.12),
      enable_name_noise: $("#gen_enable_name_noise")?.checked ?? true,
      rate_first_noise: parseFloat($("#gen_rate_first_noise")?.value || 0.35),
      rate_last_noise: parseFloat($("#gen_rate_last_noise")?.value || 0.15),
      drop_address_rate: parseFloat($("#gen_drop_address_rate")?.value || 0.10),
      drop_phone_rate: parseFloat($("#gen_drop_phone_rate")?.value || 0.08),
      drop_email_rate: parseFloat($("#gen_drop_email_rate")?.value || 0.08),
      token_rate: parseFloat($("#gen_token_rate")?.value || 0.60),
      employer_rate: parseFloat($("#gen_employer_rate")?.value || 0.70),
      threshold: state.threshold,
      weights: state.weights,
      use_persistent_tokens: state.usePersistentTokens,
    };
  }

  async function pollBatchStatus() {
    try {
      const status = await fetchJSON("/api/generate/batch/status");
      if (!status) return;

      const progressWrap = $("#genBatchProgressWrap");
      const progressBar = $("#genBatchProgressBar");
      const progressPct = $("#batchProgressPct");
      const badge = $("#genBatchStatusBadge");
      const cancelBtn = $("#genBatchCancelBtn");
      const startBtn = $("#genBatchStartBtn");

      if (progressWrap) progressWrap.hidden = false;
      const pct = Math.min(100, Math.round(status.pct_complete || 0));
      if (progressBar) progressBar.style.width = `${pct}%`;
      if (progressPct) progressPct.textContent = `${pct}%`;

      const setVal = (id, val) => {
        const el = $(`#${id}`);
        if (el) el.textContent = val;
      };

      setVal("batchProgEntities", `${(status.generated_individuals || 0).toLocaleString()} / ${(status.total_individuals || 0).toLocaleString()}`);
      setVal("batchProgObs", (status.generated_observations || 0).toLocaleString());
      setVal("batchProgRate", `${Math.round(status.rows_per_second || 0).toLocaleString()} rows/s`);
      setVal("batchProgElapsed", `${(status.elapsed_seconds || 0).toFixed(1)}s`);
      setVal("batchProgEta", (status.eta_seconds !== null && status.eta_seconds !== undefined) ? `${status.eta_seconds.toFixed(1)}s` : "--");

      if (status.status === "running") {
        if (badge) {
          badge.className = "gen-status-badge loading";
          badge.innerHTML = '<span class="pulse-indicator"></span> Streaming records…';
        }
        if (cancelBtn) cancelBtn.hidden = false;
        if (startBtn) startBtn.disabled = true;
      } else if (status.status === "completed") {
        clearInterval(generatorState.batchPollTimer);
        generatorState.batchPollTimer = null;
        if (badge) {
          badge.className = "gen-status-badge success";
          badge.textContent = `✓ Done (${(status.generated_observations || 0).toLocaleString()} rows)`;
        }
        if (cancelBtn) cancelBtn.hidden = true;
        if (startBtn) startBtn.disabled = false;

        const alertEl = $("#batchCompleteAlert");
        if (alertEl) {
          alertEl.hidden = false;
          alertEl.innerHTML = `✓ <strong>Streaming complete!</strong> Exported ${(status.generated_observations || 0).toLocaleString()} rows (${formatBytes(status.file_size_bytes || 0)}) to <code>${status.output_file}</code> in ${(status.elapsed_seconds || 0).toFixed(2)}s (${Math.round(status.rows_per_second || 0).toLocaleString()} rows/sec).`;
        }
      } else if (status.status === "cancelled" || status.status === "failed") {
        clearInterval(generatorState.batchPollTimer);
        generatorState.batchPollTimer = null;
        if (badge) {
          badge.className = "gen-status-badge error";
          badge.textContent = status.status === "cancelled" ? "Cancelled" : `Error: ${status.error}`;
        }
        if (cancelBtn) cancelBtn.hidden = true;
        if (startBtn) startBtn.disabled = false;
      }
    } catch (err) {
      console.warn("pollBatchStatus error:", err);
    }
  }

  function bindGeneratorControls() {
    const genPanel = $("#tab-generator");
    if (!genPanel) return;

    // Mode switch buttons
    $("#genModeLiveBtn")?.addEventListener("click", () => switchGeneratorMode("live"));
    $("#genModeBatchBtn")?.addEventListener("click", () => switchGeneratorMode("batch"));

    // Attach input listeners for real-time label updates
    genPanel.querySelectorAll("input[type=range], input[type=number], select").forEach((input) => {
      input.addEventListener("input", updateGeneratorLabels);
    });

    // Quick scale pills
    genPanel.querySelectorAll(".gen-pill-btn").forEach((pill) => {
      pill.addEventListener("click", () => {
        const n = parseInt(pill.dataset.n, 10);
        const input = $("#gen_n_individuals");
        if (input) input.value = n;
        if (n > 1000 && generatorState.mode === "live") {
          switchGeneratorMode("batch");
        } else {
          updateGeneratorLabels();
        }
      });
    });

    // Auto-balancing 4 relocation sliders
    ["pct_never", "pct_county", "pct_state", "pct_cross_us"].forEach((key) => {
      const el = $(`#gen_${key}`);
      if (el) {
        el.addEventListener("input", () => balanceRelocationTiers(key));
      }
    });

    // Reset relocation proportions
    $("#genResetRelocBtn")?.addEventListener("click", () => {
      const setV = (k, v) => {
        const el = $(`#gen_${k}`);
        if (el) el.value = v;
      };
      setV("pct_never", 50);
      setV("pct_county", 30);
      setV("pct_state", 15);
      setV("pct_cross_us", 5);
      updateGeneratorLabels();
    });

    // Distribution selector change
    $("#gen_obs_dist")?.addEventListener("change", (e) => {
      const wrap = $("#gen_std_obs_wrap");
      if (wrap) {
        wrap.style.opacity = e.target.value === "fixed" ? "0.3" : "1.0";
        wrap.style.pointerEvents = e.target.value === "fixed" ? "none" : "auto";
      }
      updateGeneratorLabels();
    });

    // Preset buttons
    genPanel.querySelectorAll(".gen-preset-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        applyGeneratorPreset(btn.dataset.preset);
      });
    });

    // Randomize seed button
    const randSeedBtn = $("#genRandomSeedBtn");
    if (randSeedBtn) {
      randSeedBtn.addEventListener("click", () => {
        const seedInput = $("#gen_seed");
        if (seedInput) {
          seedInput.value = Math.floor(Math.random() * 90000) + 10000;
        }
      });
    }

    // Reset button
    const resetBtn = $("#genResetBtn");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        applyGeneratorPreset("benchmark");
      });
    }

    // Save dataset as JSON file with native "Save As..." dialog
    async function saveDatasetAsJSON() {
      const data = state.observations;
      if (!data || !data.length) {
        alert("No observations available to export.");
        return;
      }
      const seed = $("#gen_seed")?.value || 42;
      const count = data.length;
      const filename = `trajectories_dataset_seed${seed}_${count}obs.json`;
      const jsonStr = JSON.stringify(data, null, 2);

      if (typeof window.showSaveFilePicker === "function") {
        try {
          const handle = await window.showSaveFilePicker({
            suggestedName: filename,
            types: [
              {
                description: "JSON Dataset (*.json)",
                accept: { "application/json": [".json"] },
              },
            ],
          });
          const writable = await handle.createWritable();
          await writable.write(jsonStr);
          await writable.close();
          return;
        } catch (err) {
          if (err && err.name === "AbortError") {
            return;
          }
          console.warn("showSaveFilePicker failed, falling back to download link:", err);
        }
      }

      const blob = new Blob([jsonStr], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }

    const saveBtn = $("#genSaveJsonBtn");
    if (saveBtn) {
      saveBtn.addEventListener("click", saveDatasetAsJSON);
    }
    const summarySaveBtn = $("#genSummarySaveBtn");
    if (summarySaveBtn) {
      summarySaveBtn.addEventListener("click", saveDatasetAsJSON);
    }

    // Quick navigation buttons from summary
    const goEntities = $("#genGoEntitiesBtn");
    if (goEntities) {
      goEntities.addEventListener("click", () => {
        const tab = document.querySelector('.tab[data-tab="entities"]');
        if (tab) tab.click();
      });
    }
    const goMap = $("#genGoMapBtn");
    if (goMap) {
      goMap.addEventListener("click", () => {
        const tab = document.querySelector('.tab[data-tab="map"]');
        if (tab) tab.click();
      });
    }

    // Primary Live generate button
    const genBtn = $("#genGenerateBtn");
    const statusBadge = $("#genStatusBadge");

    if (genBtn) {
      genBtn.addEventListener("click", async () => {
        const payload = gatherGeneratorPayload();

        genBtn.disabled = true;
        genBtn.textContent = "Generating dataset…";
        if (statusBadge) {
          statusBadge.className = "gen-status-badge loading";
          statusBadge.innerHTML = '<span class="pulse-indicator"></span> Generating dataset…';
        }

        try {
          const res = await fetchJSON("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });

          if (res.error) throw new Error(res.error);

          // Update application state
          state.observations = res.observations;
          state.obsById.clear();
          state.observations.forEach((o) => state.obsById.set(o.observation_id, o));
          state.result = res.result;

          buildPairMap();
          $("#statusBadge").textContent = `${state.observations.length} observations · ` +
            `${res.result.entities.length} resolved entities`;
          renderMetrics();
          renderEntities();
          renderPairs();
          populateMapSelect();
          renderMap();
          renderObservationsTable();
          renderMapObservationsTable();

          if (statusBadge) {
            statusBadge.className = "gen-status-badge success";
            statusBadge.textContent = `✓ Generated ${res.observations.length} observations (${res.summary.total_entities} entities)`;
          }

          renderGenSummary(res.summary, payload);
        } catch (err) {
          if (statusBadge) {
            statusBadge.className = "gen-status-badge error";
            statusBadge.textContent = `Error: ${err.message}`;
          }
        } finally {
          genBtn.disabled = false;
          genBtn.textContent = "⚡ Generate & Reload Dataset";
        }
      });
    }

    // Batch Preview in Map button
    const previewBtn = $("#genBatchPreviewBtn");
    if (previewBtn) {
      previewBtn.addEventListener("click", async () => {
        const payload = gatherGeneratorPayload();
        payload.target_preview_obs = 300;
        previewBtn.disabled = true;
        previewBtn.textContent = "Sampling preview…";
        const badge = $("#genBatchStatusBadge");
        if (badge) {
          badge.className = "gen-status-badge loading";
          badge.innerHTML = '<span class="pulse-indicator"></span> Sampling preview…';
        }

        try {
          const res = await fetchJSON("/api/generate/preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          if (res.error) throw new Error(res.error);

          state.observations = res.observations;
          state.obsById.clear();
          state.observations.forEach((o) => state.obsById.set(o.observation_id, o));
          state.result = res.result;

          buildPairMap();
          $("#statusBadge").textContent = `${state.observations.length} observations (stratified preview) · ` +
            `${res.result.entities.length} resolved entities`;
          renderMetrics();
          renderEntities();
          renderPairs();
          populateMapSelect();
          renderMap();
          renderObservationsTable();
          renderMapObservationsTable();

          if (badge) {
            badge.className = "gen-status-badge success";
            badge.textContent = `✓ Sampled ${res.observations.length} obs & mapped`;
          }

          // Switch to Map tab
          const mapTab = document.querySelector('.tab[data-tab="map"]');
          if (mapTab) mapTab.click();
        } catch (err) {
          if (badge) {
            badge.className = "gen-status-badge error";
            badge.textContent = `Error: ${err.message}`;
          }
        } finally {
          previewBtn.disabled = false;
          previewBtn.textContent = "👁 Sample & Preview in Map";
        }
      });
    }

    // Batch Start Export button
    const batchStartBtn = $("#genBatchStartBtn");
    if (batchStartBtn) {
      batchStartBtn.addEventListener("click", async () => {
        const payload = gatherGeneratorPayload();
        payload.output_path = $("#gen_batch_path")?.value || "backend/data/massive_synthetic.jsonl";
        payload.format = $("#gen_batch_format")?.value || "jsonl";

        batchStartBtn.disabled = true;
        const cancelBtn = $("#genBatchCancelBtn");
        if (cancelBtn) cancelBtn.hidden = false;
        const alertEl = $("#batchCompleteAlert");
        if (alertEl) alertEl.hidden = true;

        const badge = $("#genBatchStatusBadge");
        if (badge) {
          badge.className = "gen-status-badge loading";
          badge.innerHTML = '<span class="pulse-indicator"></span> Starting streaming job…';
        }

        try {
          const res = await fetchJSON("/api/generate/batch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          if (res.error) throw new Error(res.error);

          if (generatorState.batchPollTimer) clearInterval(generatorState.batchPollTimer);
          generatorState.batchPollTimer = setInterval(pollBatchStatus, 350);
          pollBatchStatus();
        } catch (err) {
          if (badge) {
            badge.className = "gen-status-badge error";
            badge.textContent = `Error: ${err.message}`;
          }
          batchStartBtn.disabled = false;
          if (cancelBtn) cancelBtn.hidden = true;
        }
      });
    }

    // Batch Cancel Export button
    const batchCancelBtn = $("#genBatchCancelBtn");
    if (batchCancelBtn) {
      batchCancelBtn.addEventListener("click", async () => {
        try {
          await fetchJSON("/api/generate/batch/cancel", { method: "POST", body: "{}" });
          if (generatorState.batchPollTimer) clearInterval(generatorState.batchPollTimer);
          generatorState.batchPollTimer = null;
          pollBatchStatus();
        } catch (err) {
          console.warn("Cancel failed:", err);
        }
      });
    }

    updateGeneratorLabels();
  }

  function renderGenSummary(summary, payload) {
    const section = $("#genSummarySection");
    const container = $("#genSummaryContent");
    if (!section || !container || !summary) return;

    const totalObs = summary.total_observations || 0;
    const totalEnt = summary.total_entities || 0;
    const dob = summary.dob_stats || {};
    const cov = summary.coverage || {};
    const tiers = summary.relocation_tiers || {};

    const pct = (cnt) => totalObs > 0 ? `${Math.round((cnt / totalObs) * 100)}%` : "0%";

    const tierBreakdown = (tiers.never !== undefined)
      ? `Stayers: ${tiers.never} · County: ${tiers.county} · State: ${tiers.state} · Cross-US: ${tiers.cross_us}`
      : `Cat 1: ${payload?.n_neighborhood || 0} · Cat 2: ${payload?.n_intrastate || 0} · Cat 3: ${payload?.n_interstate || 0}`;

    const confounderText = payload?.pct_household !== undefined
      ? `HH: ${payload.pct_household}% · Coll: ${payload.pct_collision}% · Recycled Phone: ${payload.include_phone_reallocation ? "Yes" : "No"}`
      : `HH: ${payload?.n_household_pairs || 0}p · Name: ${payload?.n_name_collision_pairs || 0}p · Phone: ${payload?.include_phone_reallocation ? "Yes" : "No"}`;

    container.innerHTML = `
      <div class="gen-summary-grid">
        <div class="gen-stat-card">
          <span class="gen-stat-label">Total Observations</span>
          <span class="gen-stat-value">${totalObs.toLocaleString()}</span>
          <span class="gen-stat-sub">Across ${totalEnt.toLocaleString()} latent individuals</span>
        </div>
        <div class="gen-stat-card">
          <span class="gen-stat-label">Mobility Breakdown</span>
          <span class="gen-stat-value">${totalEnt.toLocaleString()} Entities</span>
          <span class="gen-stat-sub">${tierBreakdown}</span>
        </div>
        <div class="gen-stat-card">
          <span class="gen-stat-label">Confounder Footprint</span>
          <span class="gen-stat-value">${payload?.include_phone_reallocation ? "Adversarial Stress Active" : "Clean Pairs"}</span>
          <span class="gen-stat-sub">${confounderText}</span>
        </div>
        <div class="gen-stat-card">
          <span class="gen-stat-label">DOB Quality Mix</span>
          <span class="gen-stat-value">${pct(dob.full)} Full Dates</span>
          <span class="gen-stat-sub">${pct(dob.year_only)} Y · ${pct(dob.year_month)} YM · ${pct(dob.missing)} None</span>
        </div>
        <div class="gen-stat-card">
          <span class="gen-stat-label">Token Footprints</span>
          <span class="gen-stat-value">${pct(cov.persistent_token_obs)}</span>
          <span class="gen-stat-sub">${(cov.persistent_token_obs || 0).toLocaleString()} sightings with token</span>
        </div>
        <div class="gen-stat-card">
          <span class="gen-stat-label">Employer Anchors</span>
          <span class="gen-stat-value">${pct(cov.employer_obs)}</span>
          <span class="gen-stat-sub">${(cov.employer_obs || 0).toLocaleString()} sightings with employer ID</span>
        </div>
      </div>
    `;
    section.hidden = false;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
