// Phase 22: replace the dashboard's illustrative demo sections with live API data.
// Each section keeps its demo content (and its "Illustrative demo" notice) unless the API answers.
(function () {
  var API_BASES = ["", "http://127.0.0.1:8000", "http://localhost:8000"];
  var apiBase = null;
  var FLAGSHIPS = [
    { id: "tiger", name: "Tiger", emoji: "🐯", col: "#ff6030", demoName: "Bengal Tiger" },
    { id: "elephant", name: "Asian Elephant", emoji: "🐘", col: "#6090d0", demoName: "Asian Elephant" },
    { id: "rhino", name: "Indian Rhinoceros", emoji: "🦏", col: "#4abaa8", demoName: "Indian Rhinoceros" },
    { id: "bear", name: "Sloth Bear", emoji: "🐻", col: "#c07830", demoName: "Sloth Bear" },
    { id: "croc", name: "Mugger Crocodile", emoji: "🐊", col: "#30a080", demoName: "Mugger Crocodile" }
  ];
  var NOTE_STYLE = "font-family:'EB Garamond',serif;font-style:italic;font-size:.88rem;line-height:1.6;color:rgba(168,196,216,.55);margin-top:10px";

  function esc(value) {
    return String(value == null ? "" : value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function pct(value) {
    return value == null ? "—" : Math.round(value * 100) + "%";
  }

  // Static hosting: API answers were exported to snapshot/ by scripts/export_static_site.py.
  // The file name must match snapshot_key() there.
  function snapshotKey(path, body) {
    var key = path.replace(/^\//, "");
    if (body) key += "__" + Object.keys(body).sort().map(function (k) { return k + "-" + body[k]; }).join("_");
    return key.replace(/[^A-Za-z0-9\/._-]/g, "_") + ".json";
  }

  async function request(path, options) {
    if (window.BIOINDIA_STATIC) {
      var body = options && options.body ? JSON.parse(options.body) : null;
      var response = await fetch("snapshot/v1/" + snapshotKey(path, body));
      if (!response.ok) throw new Error("Not included in this snapshot (" + response.status + ")");
      return response.json();
    }
    var bases = apiBase !== null ? [apiBase] : API_BASES;
    for (var i = 0; i < bases.length; i += 1) {
      try {
        var response = await fetch(bases[i] + "/api/v1" + path, Object.assign({ cache: "no-store" }, options || {}));
        if (response.status === 404 && bases[i] === "" && apiBase === null) continue;
        if (!response.ok) throw new Error(response.status + " " + (await response.text()));
        apiBase = bases[i];
        return await response.json();
      } catch (error) {
        if (apiBase !== null) throw error;
      }
    }
    throw new Error("API not reachable");
  }

  function post(path, body) {
    return request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  function markLive(sectionId, note) {
    var section = document.getElementById(sectionId);
    if (!section) return;
    var demo = section.querySelector(".demo-content-notice");
    if (demo) demo.remove();
    if (note && !section.querySelector(".live-data-notice")) {
      var badge = document.createElement("div");
      badge.className = "live-data-notice";
      badge.textContent = window.BIOINDIA_STATIC ? note.replace(/^Live /, "Snapshot " + window.BIOINDIA_STATIC.date + " · ") : note;
      badge.style.cssText = "margin:0 auto 18px;max-width:900px;padding:8px 14px;border:1px solid rgba(74,186,168,.45);" +
        "color:rgba(116,234,210,.9);font-family:'Cinzel',serif;font-size:.55rem;letter-spacing:.14em;text-transform:uppercase;text-align:center";
      section.insertBefore(badge, section.firstChild);
    }
  }

  function image(emoji, size) {
    var src = typeof SP_IMG !== "undefined" ? SP_IMG[emoji] : "";
    return src ? '<img src="' + src + '" style="width:' + size + "px;height:" + size + 'px;object-fit:cover;border-radius:2px;vertical-align:middle;margin-right:7px" alt="">' : "";
  }

  function shapBars(items, scale) {
    // Bars grow from the midline, so the largest value fills half the track.
    return items.slice().sort(function (a, b) { return Math.abs(b.shap_value) - Math.abs(a.shap_value); }).map(function (item) {
      var value = Number(item.shap_value);
      var width = Math.min(50, Math.round(Math.abs(value) / scale * 50));
      return '<div class="shap-bar"><div class="shap-label" style="flex:0 0 46%;line-height:1.3">' + esc(item.description || item.feature) + "</div>" +
        '<div class="shap-track" style="min-width:80px"><div class="shap-midline"></div>' +
        (value > 0 ? '<div class="shap-pos" style="width:' + width + '%"></div>' : '<div class="shap-neg" style="width:' + width + '%"></div>') +
        '</div><div class="shap-val">' + (value > 0 ? "+" : "") + value.toFixed(3) + "</div></div>";
    }).join("");
  }

  // ── AI risk: model predictions for species without a verified IUCN status ──
  async function liveRisk() {
    var grid = document.getElementById("aiRiskGrid");
    if (!grid) return;
    var data = await request("/prediction/ranking?limit=6&unlabelled_only=true");
    var perf = data.model_performance;
    grid.innerHTML = data.species.map(function (item) {
      var risk = Math.round(item.predicted_probability * 100);
      var level = risk >= 60 ? "risk-high" : risk >= 35 ? "risk-med" : "risk-low";
      var status = item.official_iucn_category ? "IUCN " + item.official_iucn_category : item.reported_category ? item.reported_category + " (unverified)" : "No verified status";
      var factors = item.top_contributions.slice(0, 3).map(function (f) {
        return '<span class="ai-factor">' + (f.shap_value > 0 ? "▲ " : "▼ ") + esc(f.description) + "</span>";
      }).join("");
      return '<div class="ai-card"><h3>' + image((FLAGSHIPS.find(function (f) { return f.id === item.species_id; }) || {}).emoji, 22) +
        esc(item.common_name || item.scientific_name) + "</h3>" +
        '<div class="risk-meter ' + level + '"><div class="risk-label"><span>Model-predicted probability of threatened status</span><span>' + esc(status) + "</span></div>" +
        '<div class="risk-track"><div class="risk-fill" style="width:' + risk + '%"></div></div><div class="risk-pct">' + risk + "%</div></div>" +
        '<div style="font-family:\'Cinzel\',serif;font-size:.5rem;letter-spacing:.2em;color:rgba(168,196,216,.4);margin:12px 0 6px">Main model drivers (SHAP)</div>' +
        '<div class="ai-factors">' + factors + "</div>" +
        '<div style="' + NOTE_STYLE + '">' + esc(item.prediction_type === "unlabelled" ? "Not used in training: Data Deficient or no verified assessment." : "Out-of-fold prediction.") + "</div>" +
        '<div style="margin-top:10px" class="confidence-badge">Model PR-AUC ' + perf.pr_auc.mean.toFixed(2) + " (chance " + perf.pr_auc_baseline.toFixed(2) + ")</div></div>";
    }).join("");
    markLive("ai-risk", "Live model output · " + data.model_version + " · model prediction, not IUCN status");
  }

  // ── Explainable AI: global importance and per-species SHAP ──
  async function liveXai() {
    var grid = document.getElementById("xaiGrid");
    if (!grid) return;
    var performance = await request("/model-performance");
    var ranking = await request("/prediction/ranking?limit=6");
    var labels = {};
    (await request("/model-info")).features.forEach(function (f) { labels[f.name] = f.description; });
    var importance = Object.entries(performance.global_importance_mean_abs_shap)
      .sort(function (a, b) { return b[1] - a[1]; }).slice(0, 8)
      .map(function (entry) { return { feature: entry[0], description: labels[entry[0]] || entry[0].replace(/_/g, " "), shap_value: entry[1] }; });
    var maxImportance = Math.max.apply(null, importance.map(function (i) { return i.shap_value; }).concat([1e-6]));
    grid.innerHTML =
      '<div class="xai-card"><h3>Global feature importance</h3><div style="' + NOTE_STYLE + '">Mean absolute SHAP value across training species (' + esc(performance.selected_model.replace(/_/g, " ")) + ").</div>" +
      '<div style="margin-top:14px">' + shapBars(importance, maxImportance) + "</div></div>" +
      '<div class="xai-card"><h3>Why the model rates a species</h3><div class="xai-species-sel" id="liveXaiSel">' +
      ranking.species.map(function (item, index) {
        return '<button class="xai-sp-btn' + (index === 0 ? " active" : "") + '" data-id="' + esc(item.species_id) + '">' + esc(item.common_name || item.scientific_name) + "</button>";
      }).join("") + '</div><div id="liveShap" style="margin-top:14px"></div><div style="' + NOTE_STYLE + '">SHAP shows how features moved this model\'s prediction; it does not establish ecological causes.</div></div>';
    async function show(speciesId) {
      var data = await request("/prediction/species/" + encodeURIComponent(speciesId) + "/explanation");
      var scale = Math.max.apply(null, data.top_contributions.map(function (c) { return Math.abs(c.shap_value); }).concat([1e-6]));
      document.getElementById("liveShap").innerHTML = '<div style="' + NOTE_STYLE + ';margin:0 0 10px">Predicted probability ' + pct(data.predicted_threatened_probability) +
        (data.official_iucn_category ? " · official IUCN " + esc(data.official_iucn_category) : "") + "</div>" + shapBars(data.top_contributions, scale);
    }
    grid.querySelectorAll("#liveXaiSel .xai-sp-btn").forEach(function (button) {
      button.addEventListener("click", function () {
        grid.querySelectorAll("#liveXaiSel .xai-sp-btn").forEach(function (b) { b.classList.remove("active"); });
        button.classList.add("active");
        show(button.dataset.id);
      });
    });
    if (ranking.species.length) await show(ranking.species[0].species_id);
    markLive("xai", "Live SHAP explanations · " + performance.model_version);
  }

  // ── Species intelligence: a browsable profile for every species with records ──
  var GROUPS = [
    ["Mammals", ["Mammalia"]], ["Birds", ["Aves"]], ["Reptiles", ["Reptilia", "Squamata", "Testudines", "Crocodylia"]],
    ["Amphibians", ["Amphibia"]], ["Fishes", ["Actinopterygii", "Chondrichthyes", "Elasmobranchii"]],
    ["Plants", ["Magnoliopsida", "Liliopsida", "Pinopsida", "Polypodiopsida", "Cycadopsida", "Gnetopsida"]]
  ];

  function groupOf(className) {
    var match = GROUPS.find(function (g) { return g[1].indexOf(className) >= 0; });
    return match ? match[0] : "Other";
  }

  function kv(label, value, share) {
    return '<div class="si-kv"><label>' + esc(label) + "</label><b>" + esc(value) + "</b>" +
      (share == null ? "" : '<i><em style="width:' + Math.max(1, Math.min(100, Math.round(share * 100))) + '%"></em></i>') + "</div>";
  }

  function fmt(value, digits, unit) {
    return value == null ? "—" : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits || 0 }) + (unit || "");
  }

  async function liveSpeciesIntel() {
    var tabs = document.getElementById("siTabs");
    if (!tabs) return;
    var host = tabs.parentElement;
    var listing = await request("/species");
    var flagshipOrder = FLAGSHIPS.map(function (f) { return f.id; });
    var species = listing.species.filter(function (s) { return s.observation_record_count > 0; }).sort(function (a, b) {
      var fa = flagshipOrder.indexOf(a.species_id), fb = flagshipOrder.indexOf(b.species_id);
      if (fa >= 0 || fb >= 0) return (fa < 0 ? 99 : fa) - (fb < 0 ? 99 : fb);
      return b.observation_record_count - a.observation_record_count;
    });
    var counts = {};
    species.forEach(function (s) { var g = groupOf(s.taxonomic_group); counts[g] = (counts[g] || 0) + 1; });
    var groups = ["All"].concat(GROUPS.map(function (g) { return g[0]; }), ["Other"]).filter(function (g) { return g === "All" || counts[g]; });

    host.innerHTML =
      '<div class="si-browser"><aside class="si-rail">' +
      '<input class="si-search" id="siSearch" type="search" placeholder="Search ' + species.length + ' species…" aria-label="Search species">' +
      '<div class="si-groups" id="siGroups">' + groups.map(function (g, i) {
        return '<button class="si-chip' + (i === 0 ? " active" : "") + '" data-group="' + g + '">' + g + (g === "All" ? "" : " " + counts[g]) + "</button>";
      }).join("") + "</div>" +
      '<div class="si-count" id="siCount"></div><div class="si-list" id="siList"></div></aside>' +
      '<div class="si-detail" id="siDetail"><div class="si-loading">Choose a species</div></div></div>';

    var state = { group: "All", query: "", selected: species[0].species_id };
    function renderList() {
      var q = state.query.toLowerCase();
      var shown = species.filter(function (s) {
        return (state.group === "All" || groupOf(s.taxonomic_group) === state.group) &&
          (!q || (s.common_name || "").toLowerCase().indexOf(q) >= 0 || s.scientific_name.toLowerCase().indexOf(q) >= 0);
      });
      document.getElementById("siCount").textContent = shown.length + " of " + species.length + " species";
      document.getElementById("siList").innerHTML = shown.map(function (s) {
        return '<button class="si-row' + (s.species_id === state.selected ? " active" : "") + '" data-id="' + esc(s.species_id) + '">' +
          '<span class="si-row-name">' + esc(s.common_name || s.scientific_name) + (flagshipOrder.indexOf(s.species_id) >= 0 ? '<span class="si-row-flag">FLAGSHIP</span>' : "") + "</span>" +
          '<span class="si-row-n">' + fmt(s.observation_record_count) + "</span>" +
          '<span class="si-row-sci">' + esc(s.scientific_name) + "</span></button>";
      }).join("") || '<div class="si-loading">No species match</div>';
    }
    document.getElementById("siSearch").addEventListener("input", function (e) { state.query = e.target.value.trim(); renderList(); });
    document.getElementById("siGroups").addEventListener("click", function (e) {
      var chip = e.target.closest(".si-chip");
      if (!chip) return;
      state.group = chip.dataset.group;
      document.querySelectorAll("#siGroups .si-chip").forEach(function (c) { c.classList.toggle("active", c === chip); });
      renderList();
    });
    document.getElementById("siList").addEventListener("click", function (e) {
      var row = e.target.closest(".si-row");
      if (!row) return;
      state.selected = row.dataset.id;
      document.querySelectorAll("#siList .si-row").forEach(function (r) { r.classList.toggle("active", r === row); });
      showSpecies(row.dataset.id);
    });
    renderList();
    await showSpecies(state.selected);
    markLive("species-intel", "Live profiles for " + species.length + " species from GBIF, IUCN, the risk model, land use and GloBI");

    async function showSpecies(speciesId) {
      var detail = document.getElementById("siDetail");
      detail.innerHTML = '<div class="si-loading">Loading profile…</div>';
      function optional(path) { return request(path).catch(function () { return null; }); }
      var results = await Promise.all([request("/species/" + speciesId + "/intelligence"), optional("/species/" + speciesId + "/environment"),
        optional("/prediction/species/" + speciesId + "/explanation"), optional("/network/species/" + speciesId), optional("/indices/ibvci/" + speciesId)]);
      if (speciesId !== state.selected) return;  // a newer selection arrived while loading
      detail.innerHTML = profileHtml(speciesId, results[0], results[1], results[2], results[3], results[4]);
    }
  }

  function profileHtml(speciesId, intel, env, explanation, network, ibvci) {
    var sp = intel.species, taxo = intel.taxonomy, cons = intel.conservation_assessment;
    var flag = FLAGSHIPS.find(function (f) { return f.id === speciesId; });
    var trend = intel.occurrence_history.trend;
    var states = intel.geographic_distribution.states_with_records;
    var protection = intel.protected_area_coverage;
    var land = intel.land_pressure && intel.land_pressure.profile;
    var risk = intel.derived_watchlist_signal || {};
    var rankItem = ibvci && ibvci.species && ibvci.species[0];
    var name = sp.common_name || sp.scientific_name;
    var initials = name.split(/[\s-]+/).filter(Boolean).slice(0, 2).map(function (w) { return w[0].toUpperCase(); }).join("");
    var category = cons.category;
    var status = category ? category + (cons.official_assessment_verified ? "" : " (unverified)")
      : (window.BIOINDIA_STATIC ? "Withheld in public snapshot" : "Not assessed");
    var pa = protection && protection.wildlife_protected_areas.record_intersection_percent;
    var image = flag && typeof SP_IMG !== "undefined" ? SP_IMG[flag.emoji] : "";
    var maxTrend = Math.max.apply(null, trend.normalized_observation_index.concat([1]));
    var bars = trend.normalized_observation_index.map(function (value, i) {
      return '<div class="si-bar" style="height:' + Math.max(1, Math.round(value / maxTrend * 100)) + '%;background:linear-gradient(to top,#277a73,#4abaa8);flex:1" data-tip="' +
        trend.years[i] + ": " + trend.record_counts[i] + ' records"></div>';
    }).join("");

    var climate = env && env.profile;
    var climateRows = climate ? [
      kv("Mean temperature", fmt(climate.annual_mean_temperature_c, 1, " °C"), climate.annual_mean_temperature_c / 30),
      kv("Annual rainfall", fmt(climate.annual_precipitation_mm, 0, " mm"), climate.annual_precipitation_mm / 4000),
      kv("Mean elevation", fmt(climate.elevation_m, 0, " m"), climate.elevation_m / 4000)
    ].join("") : "";
    var landRows = land ? [
      kv("Tree cover (2000)", fmt(100 * land.forest_2000_share, 0, "%"), land.forest_2000_share),
      kv("Tree-cover loss 2015–24", fmt(100 * land.recent_forest_loss_share, 2, "%"), land.recent_forest_loss_share * 20),
      kv("Built-up land", fmt(100 * land.built_up_share, 1, "%"), land.built_up_share * 5)
    ].join("") : "";
    var drivers = explanation && explanation.top_contributions ? explanation.top_contributions.slice()
      .sort(function (a, b) { return Math.abs(b.shap_value) - Math.abs(a.shap_value); }).slice(0, 5) : [];
    var driverScale = Math.max.apply(null, drivers.map(function (d) { return Math.abs(d.shap_value); }).concat([1e-6]));
    var types = network && network.documented_links_by_type ? Object.entries(network.documented_links_by_type).sort(function (a, b) { return b[1] - a[1]; }).slice(0, 3) : [];

    return '<div class="si-head"><div class="si-pic">' +
      (image ? '<img src="' + image + '" alt="' + esc(name) + '">' : '<div class="si-mono"><b>' + esc(initials) + "</b><span>" + esc(groupOf(sp.taxonomic_group)) + "</span></div>") +
      "</div><div>" +
      '<div class="si-title">' + esc(name) + '</div><div class="si-sub">' + esc(sp.scientific_name) + "</div>" +
      '<div class="si-taxo">' + [taxo.class_name, taxo.order_name, taxo.family].filter(Boolean).map(esc).join(" · ") + "</div>" +
      '<span class="sp-st s-' + esc(String(category || "-").toLowerCase()) + '" style="margin-top:10px;display:inline-block">' + esc(status) + "</span>" +
      '<div class="si-kpis">' +
      '<div class="si-kpi"><b>' + fmt(intel.occurrence_history.record_count) + "</b><span>GBIF records</span></div>" +
      '<div class="si-kpi"><b>' + states.length + "</b><span>States with records</span></div>" +
      '<div class="si-kpi"><b>' + (pa == null ? "—" : pa + "%") + "</b><span>Records in wildlife PAs</span></div>" +
      '<div class="si-kpi"><b>' + (risk.available ? pct(risk.predicted_threatened_probability) : "—") + "</b><span>Model-predicted risk</span></div>" +
      '<div class="si-kpi"><b>' + (rankItem && rankItem.rank ? rankItem.rank + " / " + ibvci.items_ranked : "—") + "</b><span>Vulnerability index rank</span></div>" +
      '<div class="si-kpi"><b>' + (network ? fmt(network.documented_partner_count) : "—") + "</b><span>Documented partners</span></div>" +
      "</div></div></div>" +

      '<div class="si-mid"><div class="si-panel"><h5>Records per year, ' + trend.years[0] + "–" + trend.years[trend.years.length - 1] + " (peak = 100)</h5>" +
      (trend.record_counts.some(function (n) { return n > 0; }) ? '<div class="si-bars" style="height:110px">' + bars + "</div>"
        : '<div class="si-note" style="height:110px">No records between ' + trend.years[0] + " and " + trend.years[trend.years.length - 1] + ".</div>") +
      '<div class="si-note">Recording effort as much as presence; not a population estimate.</div></div>' +
      '<div class="si-panel"><h5>States with records (most first)</h5><div class="si-state-tags">' +
      states.slice(0, 18).map(function (s) { return '<span class="si-state-tag">' + esc(s) + "</span>"; }).join("") +
      (states.length > 18 ? '<span class="si-state-tag">+' + (states.length - 18) + " more</span>" : "") + "</div>" +
      (protection && protection.records_used.count ? '<div class="si-note">' + fmt(protection.records_used.count) + " records located within 10 km were used for protection figures" +
        (protection.records_used.small_sample_warning ? " — a small sample, so treat percentages with caution" : "") + ".</div>"
        : '<div class="si-note">No records are located within 10 km, so protected-area coverage cannot be assessed.</div>') + "</div></div>" +

      '<div class="si-cards">' +
      '<div class="si-panel"><h5>Where it is recorded</h5>' + (climateRows || landRows ? climateRows + landRows :
        '<div class="si-note">No records located within 10 km, so climate and land use cannot be described.</div>') +
      '<div class="si-note">Conditions at records within 10 km (WorldClim 1970–2000, Hansen 2024, GHSL 2020). Associations, not causes.</div></div>' +

      '<div class="si-panel"><h5>Why the model rates it</h5>' + (drivers.length ? drivers.map(function (d) {
        return kv((d.shap_value > 0 ? "▲ " : "▼ ") + d.description, (d.shap_value > 0 ? "+" : "") + d.shap_value.toFixed(3), Math.abs(d.shap_value) / driverScale);
      }).join("") + '<div class="si-note">▲ raises, ▼ lowers the predicted risk. SHAP explains the model, not ecology.</div>' :
        '<div class="si-note">No model explanation is available for this species.</div>') + "</div>" +

      '<div class="si-panel"><h5>Ecological connections</h5>' + (network && network.documented_partner_count ?
        types.map(function (t) { return kv(t[0].replace(/([A-Z])/g, " $1").toLowerCase(), t[1] + " links", null); }).join("") +
        (network.top_partners || []).slice(0, 6).map(function (p) {
          return '<div class="si-partner"><span>' + esc(p.name) + "</span><span>" + esc(p.types.join(", ").replace(/([A-Z])/g, " $1").toLowerCase()) + "</span></div>";
        }).join("") + '<div class="si-note">Documented in the Global Biotic Interactions database; coverage favours well-studied taxa.</div>' :
        '<div class="si-note">No documented interactions were found in GloBI for this species.</div>') + "</div>" +
      "</div>" +
      '<div class="si-note" style="margin-top:16px">' + esc(cons.note) + "</div>";
  }

  // ── Time series: real record index for the five flagships ──
  async function liveTimeSeries() {
    if (typeof TS_DATA === "undefined" || typeof drawTSChart !== "function") return;
    var trends = await Promise.all(FLAGSHIPS.map(function (sp) { return request("/species/" + sp.id + "/trend"); }));
    FLAGSHIPS.forEach(function (sp, index) {
      var series = TS_DATA.find(function (s) { return s.name === sp.demoName; });
      if (series) {
        series.data = trends[index].normalized_observation_index.slice(-TS_YEARS.length);
        series.records = trends[index].record_counts.slice(-TS_YEARS.length);
      }
    });
    // The demo stats summed index values; report actual record counts instead.
    window.updateTSStats = function () {
      var stats = document.getElementById("tsStats");
      var active = TS_DATA.filter(function (s) { return s.active && s.records; });
      var perYear = TS_YEARS.map(function (_, i) { return active.reduce(function (sum, s) { return sum + (s.records[i] || 0); }, 0); });
      var total = perYear.reduce(function (a, b) { return a + b; }, 0);
      var peak = perYear.indexOf(Math.max.apply(null, perYear));
      var recent = perYear.slice(-5).reduce(function (a, b) { return a + b; }, 0);
      var earlier = perYear.slice(-10, -5).reduce(function (a, b) { return a + b; }, 0);
      var change = earlier ? Math.round((recent / earlier - 1) * 100) : null;
      stats.innerHTML = [
        { v: total.toLocaleString(), l: "GBIF records, selected species" },
        { v: active.length, l: "Species shown" },
        { v: total ? TS_YEARS[peak] : "—", l: "Year with most records" },
        { v: change == null ? "—" : (change >= 0 ? "+" : "") + change + "%", l: "Records, last 5 yrs vs previous 5 (effort, not population)" }
      ].map(function (s) { return '<div class="ts-stat-box"><span class="ts-stat-val">' + esc(s.v) + '</span><div class="ts-stat-label">' + esc(s.l) + "</div></div>"; }).join("");
    };
    drawTSChart();
    window.updateTSStats();
    markLive("timeseries", "Live GBIF record index (peak year = 100) · recording effort, not population size");
  }

  // ── Environment: baseline climate at records ──
  async function liveEnvironment() {
    var grid = document.getElementById("envGrid");
    if (!grid) return;
    var profiles = await Promise.all(FLAGSHIPS.map(function (sp) { return request("/species/" + sp.id + "/environment").catch(function () { return null; }); }));
    var land = await Promise.all(FLAGSHIPS.map(function (sp) { return request("/species/" + sp.id + "/land-pressure").catch(function () { return null; }); }));
    var temps = profiles.filter(Boolean).map(function (p) { return p.profile.annual_mean_temperature_c_p90 || p.profile.annual_mean_temperature_c; });
    var maxTemp = Math.max.apply(null, temps.concat([1]));
    grid.innerHTML = profiles.map(function (data, index) {
      var sp = FLAGSHIPS[index];
      if (!data) return "";
      var p = data.profile;
      function bar(label, value, max, text) {
        var width = Math.max(2, Math.min(100, Math.round(value / max * 100)));
        return '<div class="env-impact-bar"><div class="env-impact-label">' + esc(label) + '</div><div class="env-impact-track"><div class="env-impact-fill" style="width:' + width + "%;background:" + sp.col + '"></div></div><div class="env-corr-val" style="font-size:.8rem">' + esc(text) + "</div></div>";
      }
      var spread = (p.annual_mean_temperature_c_p90 || 0) - (p.annual_mean_temperature_c_p10 || 0);
      return '<div class="env-card"><h3>' + image(sp.emoji, 22) + esc(sp.name) + "</h3>" +
        bar("Annual mean temperature", p.annual_mean_temperature_c, maxTemp, p.annual_mean_temperature_c.toFixed(1) + " °C") +
        bar("Temperature range at records (10th–90th pct)", spread, 12, spread.toFixed(1) + " °C") +
        bar("Annual precipitation", p.annual_precipitation_mm, 4000, Math.round(p.annual_precipitation_mm).toLocaleString() + " mm") +
        bar("Mean elevation", p.elevation_m, 3000, Math.round(p.elevation_m).toLocaleString() + " m") +
        (land[index] ? landBars(land[index].profile, bar) : "") +
        '<div style="' + NOTE_STYLE + '">' + Number(p.sampled_occurrence_count).toLocaleString() + " records within 10 km sampled · WorldClim 2.1, " + esc(data.metadata.reference_period) +
        (land[index] ? " · land use over " + land[index].profile.occupied_cells + " occupied ~5 km cells (Hansen GFC 2024, GHSL 2020)" : "") + "</div></div>";
    }).join("");
    markLive("env-impact", "Live climate and land-use conditions where species are recorded · associations, not causes");
  }

  function landBars(l, bar) {
    function share(v) { return v == null ? 0 : v * 100; }
    return '<div style="font-family:\'Cinzel\',serif;font-size:.5rem;letter-spacing:.2em;color:rgba(168,196,216,.4);margin:12px 0 6px">Land use in occupied cells</div>' +
      bar("Tree cover in 2000", share(l.forest_2000_share), 100, share(l.forest_2000_share).toFixed(0) + "%") +
      bar("Tree-cover loss 2015–2024 (of 2000 cover)", share(l.recent_forest_loss_share), 5, share(l.recent_forest_loss_share).toFixed(2) + "%") +
      bar("Built-up land (2020)", share(l.built_up_share), 20, share(l.built_up_share).toFixed(1) + "%");
  }

  // ── Ecosystem: extinction cascade scenario simulator ──
  function liveEcosystem() {
    var section = document.getElementById("ecosystem");
    var canvas = document.getElementById("ecoCanvas");
    if (!section || !canvas) return;
    var host = canvas.parentElement;
    // Stop the demo food-web animation before its canvas is removed.
    if (typeof eAnim !== "undefined" && eAnim) cancelAnimationFrame(eAnim);
    host.innerHTML =
      '<div style="max-width:1000px;margin:0 auto;padding:28px 32px;text-align:left;background:linear-gradient(135deg,rgba(6,12,20,.96),rgba(8,16,32,.96));' +
      'border:1px solid rgba(42,138,122,.25);box-shadow:0 20px 60px rgba(0,0,0,.5)">' +
      '<div class="report-controls">' +
      '<div class="gis-filter-group"><label>Remove species</label><select class="gis-select" id="cascadeSpecies">' +
      FLAGSHIPS.map(function (sp) { return '<option value="' + sp.id + '">' + esc(sp.name) + "</option>"; }).join("") +
      '<option value="ardeola_grayii">Indian Pond-heron</option><option value="pavo_cristatus">Indian Peafowl</option></select></div>' +
      '<div class="gis-filter-group"><label>Loss threshold</label><select class="gis-select" id="cascadeThreshold">' +
      '<option value="0.25">25% of resources</option><option value="0.5" selected>50% of resources</option><option value="0.75">75% of resources</option></select></div>' +
      '<button class="gen-report-btn" id="cascadeRun">Run scenario</button></div><div id="cascadeOutput"></div></div>';
    async function run() {
      var output = document.getElementById("cascadeOutput");
      output.innerHTML = '<div style="' + NOTE_STYLE + '">Running scenario…</div>';
      try {
        var data = await post("/simulation/extinction-cascade", {
          species_id: document.getElementById("cascadeSpecies").value,
          threshold: Number(document.getElementById("cascadeThreshold").value)
        });
        if (!data.summary) {
          output.innerHTML = '<div style="' + NOTE_STYLE + '">' + esc(data.result) + "</div>";
          return;
        }
        var s = data.summary, change = data.connectivity_change;
        function kpi(value, label) { return '<div class="report-kpi"><div class="report-kpi-val">' + esc(value) + '</div><div class="report-kpi-label">' + esc(label) + "</div></div>"; }
        output.innerHTML =
          '<div class="report-badge">SCENARIO SIMULATION — not a prediction</div><div class="report-kpis">' +
          kpi(s.directly_dependent_taxa, "Directly dependent taxa") + kpi(s.potentially_secondarily_lost, "Potentially secondarily lost") +
          kpi(s.of_which_low_confidence_single_resource, "Low-confidence (single resource)") + kpi(change.dependency_links_lost, "Dependency links lost") + "</div>" +
          '<div class="report-section"><h4>Sensitivity to the threshold</h4><div style="' + NOTE_STYLE + '">' +
          Object.entries(data.sensitivity).map(function (e) { return e[0].replace("threshold_", "") + " → " + e[1] + " taxa"; }).join(" · ") + "</div></div>" +
          '<div class="report-section"><h4>Most affected dependent taxa</h4><div class="report-risk-list">' +
          data.directly_dependent_taxa.slice(0, 8).map(function (t) {
            return '<div class="report-risk-item"><span class="risk-item-name">' + esc(t.taxon) + (t.low_confidence_single_resource ? " (single documented resource)" : "") +
              '</span><span class="risk-item-score">' + pct(t.share_of_resources_lost) + " lost</span></div>";
          }).join("") + "</div></div>" +
          '<div style="' + NOTE_STYLE + '">' + esc(data.assumptions[0]) + " " + esc(data.uncertainty) + "</div>";
      } catch (error) {
        output.innerHTML = '<div style="' + NOTE_STYLE + '">Scenario could not be run: ' + esc(error.message) + "</div>";
      }
    }
    document.getElementById("cascadeRun").addEventListener("click", run);
    markLive("ecosystem", "Live cascade scenarios on documented GloBI interactions · scenario, not prediction");
    run();
  }

  // ── Regional reports: data-derived state reports ──
  function liveReports() {
    var output = document.getElementById("reportOutput");
    if (!output) return;
    window.generateReport = async function () {
      var state = (document.getElementById("reportState") || {}).value;
      if (!state) return;
      output.innerHTML = '<div style="' + NOTE_STYLE + '">Building report for ' + esc(state) + " from the database…</div>";
      try {
        var report = await post("/reports/regional", { region: state });
        output.innerHTML = '<div class="report-header"><div class="report-title-block"><h3>' + esc(report.region) + '</h3><div class="report-badge">Data-derived report · every figure traceable</div></div></div>' +
          Object.entries(report.sections).map(function (entry) {
            return '<div class="report-section"><h4>' + esc(entry[0].replace(/_/g, " ")) + "</h4>" +
              entry[1].map(function (statement) { return '<div class="report-rec">' + esc(statement.text) + "</div>"; }).join("") + "</div>";
          }).join("") +
          '<div style="' + NOTE_STYLE + '">Sources: ' + report.sources.map(esc).join(" · ") + "</div>";
      } catch (error) {
        output.innerHTML = '<div style="' + NOTE_STYLE + '">Report could not be built: ' + esc(error.message) + "</div>";
      }
    };
    markLive("reports", "Live reports built from database queries · no generated text");
  }

  async function bootstrap() {
    var steps = [liveRisk, liveXai, liveSpeciesIntel, liveTimeSeries, liveEnvironment];
    try {
      await request("/model-info");
    } catch (error) {
      return; // API not reachable: keep the labelled demo content.
    }
    for (var i = 0; i < steps.length; i += 1) {
      try { await steps[i](); } catch (error) { console.warn("[BioIndia live]", steps[i].name, error.message); }
    }
    liveEcosystem();
    liveReports();
    window.BioIndiaLive = { apiBase: apiBase };
  }

  if (document.readyState === "complete") bootstrap(); else window.addEventListener("load", bootstrap);
}());
