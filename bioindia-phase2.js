(function () {
  var DATA_FILE_NAMES = {
    stateSpecies: "state_species.json",
    hotspots: "hotspots.geojson",
    watchlist: "watchlist.json"
  };

  var PHASE2 = {
    connected: false,
    sources: {},
    stateSpecies: null,
    hotspots: null,
    watchlist: null
  };

  var STATUS_COLORS = {
    cr: "#ff6060",
    en: "#ff8a3a",
    vu: "#4abaa8",
    nt: "#70a6ff",
    lc: "#9bb4c8"
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function uniqueValues(list) {
    return Array.from(new Set(list));
  }

  function safeNumber(value, fallback) {
    var num = Number(value);
    return Number.isFinite(num) ? num : fallback;
  }

  function severityRank(status) {
    var ranks = { cr: 5, en: 4, vu: 3, nt: 2, lc: 1 };
    return ranks[String(status || "").toLowerCase()] || 0;
  }

  function average(list) {
    if (!list.length) return 0;
    return list.reduce(function (sum, value) { return sum + value; }, 0) / list.length;
  }

  function phase2Badge() {
    var badge = document.getElementById("phase2DataBadge");
    if (badge) return badge;

    badge = document.createElement("div");
    badge.id = "phase2DataBadge";
    badge.style.cssText = [
      "position:fixed",
      "right:16px",
      "bottom:16px",
      "z-index:10002",
      "padding:10px 14px",
      "background:rgba(6,12,20,0.92)",
      "border:1px solid rgba(42,138,122,0.35)",
      "color:rgba(221,234,245,0.85)",
      "font-family:'Cinzel',serif",
      "font-size:0.55rem",
      "letter-spacing:0.16em",
      "text-transform:uppercase",
      "box-shadow:0 12px 28px rgba(0,0,0,0.35)"
    ].join(";");
    document.body.appendChild(badge);
    return badge;
  }

  function setBadge(text, connected) {
    var badge = phase2Badge();
    badge.textContent = text;
    badge.style.borderColor = connected ? "rgba(74,186,168,0.55)" : "rgba(168,196,216,0.25)";
    badge.style.color = connected ? "rgba(116,234,210,0.92)" : "rgba(221,234,245,0.72)";
  }

  function buildFetchCandidates(fileName) {
    var urls = [];
    var apiBases = [];

    if (fileName === DATA_FILE_NAMES.stateSpecies) {
      urls.push("/api/v1/species/state-profiles");
      urls.push("http://127.0.0.1:8000/api/v1/species/state-profiles");
      urls.push("http://localhost:8000/api/v1/species/state-profiles");
    }

    if (window.location.protocol.indexOf("http") === 0) {
      apiBases.push(window.location.origin + "/api/datasets/outputs/");
    }

    apiBases.push("http://127.0.0.1:8000/api/datasets/outputs/");
    apiBases.push("http://localhost:8000/api/datasets/outputs/");

    apiBases.forEach(function (base) {
      urls.push(base + fileName);
    });

    urls.push("data/processed/" + fileName);
    urls.push("data/" + fileName);

    return uniqueValues(urls);
  }

  async function loadJsonWithFallback(fileName) {
    var candidates = buildFetchCandidates(fileName);
    for (var i = 0; i < candidates.length; i += 1) {
      var url = candidates[i];
      try {
        var response = await fetch(url, { cache: "no-store" });
        if (!response.ok) continue;
        var payload = await response.json();
        PHASE2.sources[fileName] = url;
        return payload;
      } catch (error) {
        continue;
      }
    }
    return null;
  }

  function resetStateDb(nextStateDb) {
    if (typeof STATE_DB === "undefined" || !nextStateDb || Array.isArray(nextStateDb)) {
      return false;
    }

    Object.keys(STATE_DB).forEach(function (key) {
      delete STATE_DB[key];
    });
    Object.keys(nextStateDb).forEach(function (key) {
      STATE_DB[key] = nextStateDb[key];
    });
    return true;
  }

  function buildSpeciesSummaries() {
    var summaries = new Map();

    Object.entries(STATE_DB).forEach(function (entry) {
      var state = entry[0];
      var speciesList = Array.isArray(entry[1]) ? entry[1] : [];
      speciesList.forEach(function (species) {
        var key = species.s || species.n;
        if (!summaries.has(key)) {
          summaries.set(key, {
            key: key,
            name: species.n || key,
            scientificName: species.s || key,
            emoji: species.e || "",
            status: species.st || "lc",
            trend: Array.isArray(species.trend) ? species.trend.slice() : [],
            totalObs: 0,
            topState: null,
            topObs: -1,
            eriValues: [],
            states: [],
            taxonomicGroup: species.taxonomic_group || ""
          });
        }

        var summary = summaries.get(key);
        var obs = safeNumber(species.obs, 0);
        summary.totalObs += obs;
        summary.states.push({ state: state, obs: obs });

        if ((!summary.trend || !summary.trend.length) && Array.isArray(species.trend)) {
          summary.trend = species.trend.slice();
        }

        if (severityRank(species.st) > severityRank(summary.status)) {
          summary.status = species.st;
        }

        if (obs > summary.topObs) {
          summary.topObs = obs;
          summary.topState = state;
        }

        if (Number.isFinite(Number(species.eri))) {
          summary.eriValues.push(Number(species.eri));
        }
      });
    });

    return Array.from(summaries.values())
      .map(function (summary) {
        summary.avgEri = summary.eriValues.length ? average(summary.eriValues) : null;
        return summary;
      })
      .sort(function (a, b) { return b.totalObs - a.totalObs; });
  }

  function refreshStatsFromState() {
    var statEls = document.querySelectorAll("#stats .sn");
    var labelEls = document.querySelectorAll("#stats .sl");
    if (!statEls.length) return;

    var summaries = buildSpeciesSummaries();
    var totalObs = summaries.reduce(function (sum, item) { return sum + item.totalObs; }, 0);
    var totalStates = Object.keys(STATE_DB).length;
    var yearCount = 0;

    summaries.forEach(function (summary) {
      yearCount = Math.max(yearCount, Array.isArray(summary.trend) ? summary.trend.length : 0);
    });

    var values = [totalObs, summaries.length, totalStates, yearCount || 26];
    statEls.forEach(function (el, index) {
      if (index < values.length) {
        el.setAttribute("data-target", String(values[index]));
        el.textContent = Number(values[index]).toLocaleString();
      }
    });

    if (labelEls[1]) labelEls[1].textContent = "Species In Active Dataset";
    if (labelEls[3]) labelEls[3].textContent = "Observation Years (2000-2025)";
  }

  function rerenderHeatmap() {
    var grid = document.getElementById("hmGrid");
    if (!grid || typeof initHeatmap !== "function") return;
    grid.innerHTML = "";
    initHeatmap();
  }

  function renderDynamicDataCharts() {
    var grid = document.getElementById("dataGrid");
    if (!grid) return;

    var summaries = buildSpeciesSummaries().slice(0, 6);
    if (!summaries.length) return;

    grid.innerHTML = "";

    summaries.forEach(function (summary) {
      var trend = Array.isArray(summary.trend) && summary.trend.length ? summary.trend : [0];
      var maxTrend = Math.max.apply(null, trend.concat([1]));
      var color = STATUS_COLORS[String(summary.status || "").toLowerCase()] || "#4abaa8";
      var bars = trend.map(function (value) {
        var height = Math.round((safeNumber(value, 0) / maxTrend) * 100);
        return '<div class="tc-bar" style="height:' + height + '%;background:linear-gradient(to top,' +
          color + '88,' + color + ');min-width:4px;" title="' + safeNumber(value, 0) + '"></div>';
      }).join("");

      var card = document.createElement("div");
      card.className = "data-card";
      card.innerHTML =
        "<h3>" + spImgFixed(summary.emoji, 28, 28, "vertical-align:middle;border-radius:2px;margin-right:8px;border:1px solid rgba(42,138,122,.25);") +
        " " + escapeHtml(summary.name) +
        ' <span class="sp-st s-' + escapeHtml(String(summary.status).toLowerCase()) + '" style="margin-left:8px">' +
        escapeHtml(String(summary.status).toUpperCase()) + "</span></h3>" +
        "<div style=\"font-family:'EB Garamond',serif;font-style:italic;font-size:.88rem;color:rgba(168,196,216,.45);margin-bottom:12px\">" +
        Number(summary.totalObs).toLocaleString() + " total occurrence summaries · 2000-2025</div>" +
        '<div class="trend-chart">' + bars + '</div>' +
        '<div class="tc-labels"><span>2000</span><span>2005</span><span>2010</span><span>2015</span><span>2020</span><span>2025</span></div>';
      grid.appendChild(card);
    });

    var tableCard = document.createElement("div");
    tableCard.className = "data-card";
    tableCard.innerHTML =
      "<h3>Species Summary — Loaded Dataset</h3>" +
      '<table class="sp-table"><thead><tr><th>Species</th><th>Status</th><th>Records</th><th>Top State</th></tr></thead><tbody>' +
      summaries.map(function (summary) {
        return "<tr><td>" + spImgFixed(summary.emoji, 22, 22, "vertical-align:middle;border-radius:2px;margin-right:6px;") +
          " " + escapeHtml(summary.name) + "</td><td><span class=\"sp-st s-" +
          escapeHtml(String(summary.status).toLowerCase()) + "\">" +
          escapeHtml(String(summary.status).toUpperCase()) + "</span></td><td>" +
          Number(summary.totalObs).toLocaleString() + "</td><td>" +
          escapeHtml(summary.topState || "—") + "</td></tr>";
      }).join("") +
      "</tbody></table>";
    grid.appendChild(tableCard);
  }

  function renderDynamicHotspots() {
    var grid = document.getElementById("hotspotGrid");
    if (!grid || !PHASE2.hotspots || !Array.isArray(PHASE2.hotspots.features)) return;

    var features = PHASE2.hotspots.features.slice().sort(function (a, b) {
      var rankA = safeNumber(a.properties && a.properties.rank, 999);
      var rankB = safeNumber(b.properties && b.properties.rank, 999);
      if (rankA !== rankB) return rankA - rankB;
      return safeNumber((b.properties || {}).hotspot_score_norm, 0) - safeNumber((a.properties || {}).hotspot_score_norm, 0);
    }).slice(0, 9);

    if (!features.length) return;

    grid.innerHTML = "";

    features.forEach(function (feature, index) {
      var props = feature.properties || {};
      var paCoverage = Number.isFinite(Number(props.pa_coverage_pct)) ? Math.round(Number(props.pa_coverage_pct)) : null;
      var rank = safeNumber(props.rank, index + 1);
      var score = Math.round(safeNumber(props.hotspot_score_norm, safeNumber(props.hotspot_score, 0)));
      var richness = Math.round(safeNumber(props.species_richness, 0));
      var records = Math.round(safeNumber(props.record_count, 0));
      var status = String(props.gap_status || "hotspot").replace(/_/g, " ");
      var desc = props.summary || "Loaded hotspot cell from the generated spatial dataset.";
      if (!props.summary && paCoverage != null) {
        desc = "Protected-area coverage: " + paCoverage + "% of the hotspot cell footprint.";
      }

      var card = document.createElement("div");
      card.className = "hotspot-card";
      // Grid cells are data-derived, so no landscape photo is shown (a stock image would misrepresent the place).
      var coordinates = Number.isFinite(Number(props.centroid_lat)) ?
        Number(props.centroid_lat).toFixed(2) + "°N, " + Number(props.centroid_lon).toFixed(2) + "°E" : "";
      card.innerHTML =
        '<div class="hotspot-img-wrap" style="background:linear-gradient(135deg,rgba(42,138,122,.35),rgba(6,12,20,.95));display:flex;align-items:flex-end;justify-content:flex-start;">' +
        '<div style="padding:12px 16px;font-family:\'Cinzel\',serif;font-size:.6rem;letter-spacing:.18em;color:rgba(168,196,216,.7)">Grid cell · ' + escapeHtml(coordinates) + "</div>" +
        '<div class="hotspot-rank">' + rank + "</div></div>" +
        '<div class="hotspot-body"><div class="hotspot-name">' + escapeHtml(props.region_name || ("Hotspot " + rank)) + "</div>" +
        '<div class="hotspot-region">&#9652; ' + escapeHtml(status) + "</div>" +
        '<div style="font-family:\'EB Garamond\',serif;font-style:italic;font-size:.85rem;color:rgba(168,196,216,.5);line-height:1.6;margin-top:8px">' +
        escapeHtml(desc) + "</div>" +
        '<div class="hotspot-metrics">' +
        '<div class="hm-metric"><span class="hm-metric-val">' + richness + '</span><div class="hm-metric-label">Richness</div></div>' +
        '<div class="hm-metric"><span class="hm-metric-val">' + records + '</span><div class="hm-metric-label">Records</div></div>' +
        '<div class="hm-metric"><span class="hm-metric-val">' + (paCoverage == null ? "—" : paCoverage + "%") + '</span><div class="hm-metric-label">PA Cover</div></div>' +
        '<div class="hm-metric"><span class="hm-metric-val">' + score + '</span><div class="hm-metric-label">Score</div></div>' +
        "</div>" +
        '<div class="biodiversity-index"><div class="bi-fill" style="width:' + score + '%"></div></div></div>';
      grid.appendChild(card);
    });
  }

  function renderDynamicRiskCards() {
    var grid = document.getElementById("aiRiskGrid");
    if (!grid || !Array.isArray(PHASE2.watchlist) || !PHASE2.watchlist.length) return;

    grid.innerHTML = "";

    PHASE2.watchlist.slice(0, 6).forEach(function (item) {
      var risk = Math.round(safeNumber(item.predicted_worsening_prob, 0) * 100);
      var level = risk >= 70 ? "high" : (risk >= 45 ? "med" : "low");
      var riskClass = level === "high" ? "risk-high" : (level === "med" ? "risk-med" : "risk-low");
      var confidence = Math.round(safeNumber(item.priority_score, 0) * 100);
      var factors = Array.isArray(item.key_drivers) ? item.key_drivers : ["High composite extinction risk"];
      var note = item.note ? (
        '<div style="margin-top:12px;font-family:\'EB Garamond\',serif;font-style:italic;font-size:.88rem;line-height:1.6;color:rgba(168,196,216,.55)">' +
        escapeHtml(item.note) +
        "</div>"
      ) : "";
      var card = document.createElement("div");
      card.className = "ai-card";
      card.innerHTML =
        "<h3>" + spImgFixed(item.emoji || "", 22, 22, "vertical-align:middle;border-radius:2px;margin-right:7px;border:1px solid rgba(42,138,122,.25);") +
        " " + escapeHtml(item.common_name || item.scientific_name || "Watchlist Species") + " — Watchlist Signal</h3>" +
        '<div class="risk-meter ' + riskClass + '">' +
        '<div class="risk-label"><span>Predicted Worsening Probability</span><span>' + escapeHtml(item.iucn_category || "Tracked") + "</span></div>" +
        '<div class="risk-track"><div class="risk-fill" style="width:0%" data-w="' + risk + '"></div></div>' +
        '<div class="risk-pct">' + risk + "%</div></div>" +
        '<div style="font-family:\'Cinzel\',serif;font-size:.5rem;letter-spacing:.2em;color:rgba(168,196,216,.4);margin:12px 0 6px">Key Drivers</div>' +
        '<div class="ai-factors">' + factors.map(function (factor) {
          return '<span class="ai-factor">' + escapeHtml(factor) + "</span>";
        }).join("") + "</div>" +
        note +
        '<div style="margin-top:12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">' +
        '<div class="confidence-badge">Priority score: ' + confidence + "%</div>" +
        '<div style="font-family:\'Cinzel\',serif;font-size:.48rem;color:rgba(168,196,216,.3);letter-spacing:.1em">Generated watchlist</div></div>';
      grid.appendChild(card);
    });

    setTimeout(function () {
      document.querySelectorAll(".risk-fill[data-w]").forEach(function (el) {
        el.style.width = el.dataset.w + "%";
      });
    }, 250);
  }

  function deriveReportRecommendations(entries, risk) {
    var recommendations = [];
    if (risk >= 70) recommendations.push("Prioritize rapid risk monitoring for the highest-pressure habitats.");
    if (entries.some(function (entry) { return severityRank(entry.st) >= 4; })) {
      recommendations.push("Focus field verification on endangered species with the sharpest observed pressure.");
    }
    if (entries.length >= 5) {
      recommendations.push("Coordinate protected-area management with corridor-level restoration planning.");
    }
    if (!recommendations.length) {
      recommendations.push("Continue baseline monitoring and strengthen data coverage for under-observed species.");
    }
    return recommendations.slice(0, 3);
  }

  function updateReportDataFromState() {
    if (typeof REPORT_DATA === "undefined") return;

    Object.keys(REPORT_DATA).forEach(function (key) {
      delete REPORT_DATA[key];
    });

    Object.entries(STATE_DB).forEach(function (entry) {
      var state = entry[0];
      var speciesList = Array.isArray(entry[1]) ? entry[1] : [];
      var withObs = speciesList.filter(function (species) { return safeNumber(species.obs, 0) > 0; });
      if (!withObs.length) return;

      var riskValues = withObs.map(function (species) {
        if (Number.isFinite(Number(species.eri))) return Number(species.eri);
        return severityRank(species.st) * 15;
      });

      var trendSignals = withObs.map(function (species) {
        var trend = Array.isArray(species.trend) ? species.trend : [];
        if (trend.length < 2) return 0;
        return safeNumber(trend[trend.length - 1], 0) - safeNumber(trend[0], 0);
      });

      var avgRisk = Math.max(15, Math.min(95, Math.round(average(riskValues))));
      var avgTrend = average(trendSignals);
      var trendLabel = avgTrend > 8 ? "Rising" : (avgTrend < -8 ? "Declining" : "Stable");
      var topSpecies = withObs.slice().sort(function (a, b) {
        return safeNumber(b.obs, 0) - safeNumber(a.obs, 0);
      }).slice(0, 3).map(function (species) {
        return species.n || species.s || "Tracked species";
      });

      REPORT_DATA[state] = {
        species: withObs.length,
        endangered: withObs.filter(function (species) { return severityRank(species.st) >= 3; }).length,
        endemic: "Data pending",
        risk: avgRisk,
        trend: trendLabel,
        topSp: topSpecies,
        recs: deriveReportRecommendations(withObs, avgRisk)
      };
    });
  }

  function refreshReportStateOptions() {
    var select = document.getElementById("reportState");
    if (!select) return;

    var currentValue = select.value;
    var states = Object.keys(STATE_DB).sort();
    select.innerHTML = '<option value="">— Choose a State —</option>' +
      states.map(function (state) {
        return "<option>" + escapeHtml(state) + "</option>";
      }).join("");
    if (states.indexOf(currentValue) !== -1) {
      select.value = currentValue;
    }
  }

  function refreshMapStateIfNeeded() {
    var active = document.querySelector("#indiaMap .sp.active");
    if (active && typeof showState === "function") {
      showState(active.dataset.state);
    }
  }

  function wrapGlobalFunctions() {
    if (typeof showState === "function" && !showState.__phase2Wrapped) {
      var originalShowState = showState;
      window.showState = function (stateName) {
        originalShowState(stateName);
        if (!PHASE2.connected) return;
        // Replace the hand-written state blurb with a summary of the loaded records.
        var info = document.getElementById("stateInfo");
        var entries = Array.isArray(STATE_DB[stateName]) ? STATE_DB[stateName] : [];
        if (info) {
          var total = entries.reduce(function (sum, entry) { return sum + safeNumber(entry.obs, 0); }, 0);
          info.textContent = entries.length ?
            stateName + ": " + total.toLocaleString() + " GBIF occurrence records for " + entries.length +
              " tracked species. Records are observations, not population counts." :
            stateName + ": no occurrence records for the tracked species in the loaded data.";
        }
      };
      window.showState.__phase2Wrapped = true;
    }

    if (typeof openModal === "function" && !openModal.__phase2Wrapped) {
      var originalOpenModal = openModal;
      window.openModal = function (species, stateName) {
        originalOpenModal(species, stateName);
        if (!PHASE2.connected) return;
        var title = document.querySelector("#mChart .yr-title");
        if (title) {
          title.textContent = "Observation Trend 2000–2025 (Normalized GBIF records)";
        }
      };
      window.openModal.__phase2Wrapped = true;
    }
  }

  // Sections whose content is still hard-coded in the HTML, not produced by the backend.
  var DEMO_SECTIONS = {
    "ai-risk": "Illustrative demo — these risk figures are placeholders, not output of a trained model.",
    "ecosystem": "Illustrative demo — the food web and cascade are not built from documented interaction data yet.",
    "species-intel": "Illustrative demo — species profiles here are placeholder text; see the API for data-derived profiles.",
    "timeseries": "Illustrative demo — these series are placeholders, not the loaded occurrence records.",
    "env-impact": "Illustrative demo — these correlations are placeholders, not computed from the loaded data.",
    "xai": "Illustrative demo — these feature contributions are placeholders, not SHAP values from a trained model.",
    "timeline": "Background history from published sources; not computed from the platform's data."
  };

  function markDemoSections() {
    Object.keys(DEMO_SECTIONS).forEach(function (id) {
      var section = document.getElementById(id);
      if (!section || section.querySelector(".demo-content-notice")) return;
      var notice = document.createElement("div");
      notice.className = "demo-content-notice";
      notice.textContent = DEMO_SECTIONS[id];
      notice.style.cssText = "margin:0 auto 18px;max-width:900px;padding:8px 14px;border:1px dashed rgba(255,170,64,.55);" +
        "color:rgba(255,200,140,.9);font-family:'Cinzel',serif;font-size:.55rem;letter-spacing:.14em;text-transform:uppercase;text-align:center";
      section.insertBefore(notice, section.firstChild);
    });
  }

  function rerenderLoadedSections() {
    refreshStatsFromState();
    rerenderHeatmap();
    renderDynamicDataCharts();
    renderDynamicHotspots();
    renderDynamicRiskCards();
    updateReportDataFromState();
    refreshReportStateOptions();
    refreshMapStateIfNeeded();
  }

  async function bootstrapPhase2() {
    setBadge("Demo fallback data", false);
    wrapGlobalFunctions();
    markDemoSections();

    var stateSpecies = await loadJsonWithFallback(DATA_FILE_NAMES.stateSpecies);
    var hotspots = await loadJsonWithFallback(DATA_FILE_NAMES.hotspots);
    var watchlist = await loadJsonWithFallback(DATA_FILE_NAMES.watchlist);

    PHASE2.hotspots = hotspots;
    PHASE2.watchlist = watchlist;

    if (stateSpecies && resetStateDb(stateSpecies)) {
      PHASE2.connected = true;
      PHASE2.stateSpecies = stateSpecies;
      rerenderLoadedSections();
      setBadge("Live data: GBIF occurrences (PostGIS)", true);
    } else if (hotspots || watchlist) {
      renderDynamicHotspots();
      renderDynamicRiskCards();
      setBadge("Partial live data", true);
    }

    window.BioIndiaPhase2 = PHASE2;
  }

  if (document.readyState === "complete") {
    bootstrapPhase2();
  } else {
    window.addEventListener("load", bootstrapPhase2);
  }
}());
