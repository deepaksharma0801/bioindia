(function () {
  var OCCURRENCE_FILE = "occurrence_points.json";

  function uniqueValues(list) {
    return Array.from(new Set(list));
  }

  function buildCandidates() {
    var urls = [];
    var apiBases = [];

    urls.push("/api/v1/species/occurrences");
    urls.push("http://127.0.0.1:8000/api/v1/species/occurrences");
    urls.push("http://localhost:8000/api/v1/species/occurrences");

    if (window.location.protocol.indexOf("http") === 0) {
      apiBases.push(window.location.origin + "/api/datasets/outputs/");
    }

    apiBases.push("http://127.0.0.1:8000/api/datasets/outputs/");
    apiBases.push("http://localhost:8000/api/datasets/outputs/");

    apiBases.forEach(function (base) {
      urls.push(base + OCCURRENCE_FILE);
    });

    urls.push("data/processed/" + OCCURRENCE_FILE);
    urls.push("data/" + OCCURRENCE_FILE);
    return uniqueValues(urls);
  }

  async function loadOccurrencePayload() {
    var candidates = buildCandidates();
    for (var i = 0; i < candidates.length; i += 1) {
      try {
        var response = await fetch(candidates[i], { cache: "no-store" });
        if (!response.ok) continue;
        var payload = await response.json();
        payload.__source = candidates[i];
        return payload;
      } catch (error) {
        continue;
      }
    }
    return null;
  }

  function updateBadge(message) {
    var badge = document.getElementById("phase2DataBadge");
    if (!badge) return;
    badge.textContent = message;
    badge.style.borderColor = "rgba(74,186,168,0.55)";
    badge.style.color = "rgba(116,234,210,0.92)";
  }

  function replaceOccurrenceData(speciesList) {
    if (!Array.isArray(speciesList) || typeof GIS_OCCURRENCES === "undefined" || !Array.isArray(GIS_OCCURRENCES)) {
      return false;
    }

    GIS_OCCURRENCES.splice(0, GIS_OCCURRENCES.length);
    speciesList.forEach(function (species) {
      GIS_OCCURRENCES.push(species);
    });
    return true;
  }

  function refreshSpeciesFilter(speciesList) {
    var select = document.getElementById("gisSpeciesFilter");
    if (!select) return;
    var current = select.value;
    select.innerHTML = '<option value="all">All Species</option>' + speciesList.map(function (species) {
      return '<option value="' + species.id + '">' + species.name + "</option>";
    }).join("");
    if (speciesList.some(function (species) { return species.id === current; })) {
      select.value = current;
    }
  }

  function refreshLegend(speciesList) {
    var legend = document.getElementById("gisLegend");
    if (!legend) return;
    legend.innerHTML = speciesList.map(function (species) {
      return '<div class="gis-leg-item"><div class="gis-leg-dot" style="background:' +
        species.col + '"></div>' + species.name + "</div>";
    }).join("");
  }

  function normalizeYearFilter(select) {
    if (!select) return;
    select.innerHTML =
      '<option value="all">All Years (1999–2026)</option>' +
      '<option value="recent">Recent (2020–2026)</option>' +
      '<option value="2010s">2010–2019</option>' +
      '<option value="2000s">2000–2009</option>';
  }

  function tweakMapSectionCopy(sourceMode, totalPoints) {
    var statBar = document.getElementById("gisStatBar");
    if (statBar && !document.getElementById("phase3MapNote")) {
      var note = document.createElement("div");
      note.id = "phase3MapNote";
      note.style.cssText = "margin-top:12px;font-family:'EB Garamond',serif;font-style:italic;font-size:.95rem;color:rgba(168,196,216,.52);";
      note.textContent = "Phase 3 loaded " + totalPoints.toLocaleString() + " grouped occurrence points from " + sourceMode.replace(/_/g, " ") + ".";
      statBar.parentNode.insertBefore(note, statBar.nextSibling);
    }
  }

  function refreshMap(payload) {
    var speciesList = Array.isArray(payload.species) ? payload.species : Array.isArray(payload) ? payload : [];
    if (!speciesList.length) return false;
    if (!replaceOccurrenceData(speciesList)) return false;

    refreshSpeciesFilter(speciesList);
    refreshLegend(speciesList);
    normalizeYearFilter(document.getElementById("gisYearFilter"));

    if (typeof updateGISMap === "function") {
      updateGISMap();
    }

    var totalPoints = speciesList.reduce(function (sum, species) {
      return sum + ((species.points && species.points.length) || 0);
    }, 0);

    tweakMapSectionCopy(payload.sourceMode || "occurrence exports", totalPoints);
    updateBadge("Phase 3 real occurrence map");
    window.BioIndiaPhase3 = payload;
    return true;
  }

  async function bootstrapPhase3() {
    var payload = await loadOccurrencePayload();
    if (!payload) return;
    refreshMap(payload);
  }

  if (document.readyState === "complete") {
    bootstrapPhase3();
  } else {
    window.addEventListener("load", bootstrapPhase3);
  }
}());
