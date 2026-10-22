/* Maps4U Geofence & Viability Operator UI (Stage 2 S2.T3) */
(function () {
  const state = {
    projectId: null,
    currentRevisionId: null,
    vertices: [],
    polygonLayer: null,
    vertexMarkers: [],
    map: null,
  };

  const MCY_PRESET_RING = [
    [153.085, -26.660],
    [153.105, -26.660],
    [153.105, -26.645],
    [153.085, -26.645],
    [153.085, -26.660],
  ];

  function currentGeoJSON() {
    if (state.vertices.length < 3) {
      return null;
    }
    const ring = state.vertices.map((pt) => [pt.lng, pt.lat]);
    const first = ring[0];
    const last = ring[ring.length - 1];
    if (first[0] !== last[0] || first[1] !== last[1]) {
      ring.push([first[0], first[1]]);
    }
    return {
      type: "Polygon",
      coordinates: [ring],
    };
  }

  async function evaluateViability() {
    const geom = currentGeoJSON();
    const badge = document.getElementById("viability-badge");
    const summary = document.getElementById("viability-summary");
    const msgList = document.getElementById("viability-messages");
    const btnSave = document.getElementById("btn-save-revision");
    msgList.innerHTML = "";

    if (!geom) {
      badge.className = "badge badge-neutral";
      badge.textContent = "No Geofence Drawn";
      summary.innerHTML = "<p>Click at least 3 points on the map or load a preset.</p>";
      btnSave.disabled = true;
      return;
    }

    const paper = document.getElementById("paper-select").value;
    const orientation = document.getElementById("orientation-select").value;

    const resp = await fetch("/api/viability", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ geofence: geom, paper, orientation }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      badge.className = "badge badge-block";
      badge.textContent = "Invalid Geometry";
      summary.textContent = data.error ? data.error.message : "Validation error";
      btnSave.disabled = true;
      return;
    }

    btnSave.disabled = !state.projectId;
    if (!data.viable) {
      badge.className = "badge badge-block";
      badge.textContent = `Blocked — 1:${Math.round(data.scale_denominator)}`;
    } else if (data.warnings && data.warnings.length > 0) {
      badge.className = "badge badge-warn";
      badge.textContent = `Viable (Warning) — 1:${Math.round(data.scale_denominator)}`;
    } else {
      badge.className = "badge badge-pass";
      badge.textContent = `Viable — 1:${Math.round(data.scale_denominator)}`;
    }

    summary.innerHTML = `
      <div><strong>Scale:</strong> 1:${Math.round(data.scale_denominator)} (natural 1:${Math.round(data.natural_scale_denominator)})</div>
      <div><strong>Extent:</strong> ${data.extent_width_m} m × ${data.extent_height_m} m (${data.area_km2} km²)</div>
      <div><strong>Min Printed Font:</strong> ${data.min_printed_mm} mm (floor ${data.configured_min_font_mm} mm)</div>
      <div><strong>Label Density Ratio:</strong> ${data.label_density_ratio}</div>
    `;

    (data.blockers || []).forEach((b) => {
      const li = document.createElement("li");
      li.textContent = `[BLOCKER] ${b.code}: ${b.message}`;
      msgList.appendChild(li);
    });
    (data.warnings || []).forEach((w) => {
      const li = document.createElement("li");
      li.textContent = `[WARNING] ${w.code}: ${w.message}`;
      msgList.appendChild(li);
    });
  }

  function redrawPolygon() {
    if (!state.map) return;
    if (state.polygonLayer) {
      state.map.removeLayer(state.polygonLayer);
    }
    if (state.vertices.length >= 3) {
      state.polygonLayer = L.polygon(
        state.vertices.map((v) => [v.lat, v.lng]),
        { color: "#2563eb", weight: 2, fillOpacity: 0.2 }
      ).addTo(state.map);
    }
    evaluateViability();
  }

  async function refreshRevisions() {
    if (!state.projectId) return;
    const resp = await fetch(`/api/projects/${state.projectId}/revisions`);
    if (!resp.ok) return;
    const list = await resp.json();
    const ul = document.getElementById("revisions-list");
    ul.innerHTML = "";
    list.forEach((rev) => {
      const li = document.createElement("li");
      li.textContent = `${rev.revision_id.slice(0, 12)}… (${rev.is_current ? "current" : "historical"}) — ${rev.created_at}`;
      ul.appendChild(li);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (typeof L !== "undefined") {
      state.map = L.map("map").setView([-26.652, 153.095], 14);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors (ODbL)",
      }).addTo(state.map);

      state.map.on("click", (ev) => {
        state.vertices.push({ lat: ev.latlng.lat, lng: ev.latlng.lng });
        redrawPolygon();
      });
    }

    document.getElementById("btn-create-project").addEventListener("click", async () => {
      const areaName = document.getElementById("area-name").value.trim();
      const reference = document.getElementById("area-ref").value.trim();
      const resp = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ area_name: areaName, reference }),
      });
      if (resp.ok) {
        const data = await resp.json();
        state.projectId = data.project_id;
        document.getElementById("project-status").textContent = `Active Project: ${data.project_id}`;
        evaluateViability();
        refreshRevisions();
      }
    });

    document.getElementById("btn-preset-mcy").addEventListener("click", () => {
      state.vertices = MCY_PRESET_RING.slice(0, 4).map((c) => ({ lng: c[0], lat: c[1] }));
      redrawPolygon();
    });

    document.getElementById("btn-clear-poly").addEventListener("click", () => {
      state.vertices = [];
      redrawPolygon();
    });

    document.getElementById("paper-select").addEventListener("change", evaluateViability);
    document.getElementById("orientation-select").addEventListener("change", evaluateViability);

    document.getElementById("btn-save-revision").addEventListener("click", async () => {
      const geom = currentGeoJSON();
      if (!state.projectId || !geom) return;
      const resp = await fetch(`/api/projects/${state.projectId}/geofence`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(geom),
      });
      if (resp.ok) {
        const rev = await resp.json();
        state.currentRevisionId = rev.revision_id;
        document.getElementById("btn-submit-job").disabled = false;
        refreshRevisions();
      }
    });

    document.getElementById("btn-submit-job").addEventListener("click", async () => {
      if (!state.projectId || !state.currentRevisionId) return;
      const paper = document.getElementById("paper-select").value;
      const orientation = document.getElementById("orientation-select").value;
      await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: state.projectId,
          geofence_revision: state.currentRevisionId,
          paper,
          orientation,
        }),
      });
    });
  });
})();
