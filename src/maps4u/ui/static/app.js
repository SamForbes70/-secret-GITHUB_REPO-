/* Maps4U Geofence, Viability, Pipeline & Proof Review Operator UI (Stage 2 S2.T3, hardened for BUG-014) */
(function () {
  const state = {
    projectId: null,
    currentRevisionId: null,
    currentJobId: null,
    currentJobStatus: null,
    vertices: [],
    polygonLayer: null,
    vertexMarkers: [],
    map: null,
    geometryVersion: 0,
    savedGeometryVersion: null,
    viabilityGeneration: 0,
    viable: false,
  };

  const MCY_PRESET_RING = [
    [153.085, -26.660],
    [153.105, -26.660],
    [153.105, -26.645],
    [153.085, -26.645],
    [153.085, -26.660],
  ];

  function getAuthHeaders(includeJson = true) {
    const headers = {};
    if (includeJson) {
      headers["Content-Type"] = "application/json";
    }
    const tokenEl = document.getElementById("auth-token");
    const identEl = document.getElementById("operator-identity");
    const token = tokenEl ? tokenEl.value.trim() : "";
    const ident = identEl ? identEl.value.trim() : "";
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    if (ident) {
      headers["X-Operator-Identity"] = ident;
    }
    return headers;
  }

  function showError(msg) {
    const banner = document.getElementById("error-banner");
    if (!banner) return;
    if (!msg) {
      banner.textContent = "";
      banner.classList.add("hidden");
      return;
    }
    banner.textContent = msg;
    banner.classList.remove("hidden");
  }

  async function extractErrorMessage(resp) {
    try {
      const payload = await resp.json();
      if (payload && payload.error) {
        return `[${payload.error.code || resp.status}] ${payload.error.message}`;
      }
      if (payload && payload.detail) {
        return `[${resp.status}] ${JSON.stringify(payload.detail)}`;
      }
    } catch (_e) {
      /* ignore parse error */
    }
    return `HTTP ${resp.status} ${resp.statusText || "Error"}`;
  }

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

  function updateJobSubmission() {
    document.getElementById("btn-submit-job").disabled = !(
      state.projectId &&
      state.currentRevisionId &&
      state.savedGeometryVersion === state.geometryVersion &&
      state.viable
    );
  }

  function invalidateGeometry() {
    state.geometryVersion += 1;
    state.viabilityGeneration += 1;
    state.currentRevisionId = null;
    state.savedGeometryVersion = null;
    state.viable = false;
    document.getElementById("btn-save-revision").disabled = true;
    updateJobSubmission();
  }

  function appendJobLine(parent, entries) {
    const row = document.createElement("div");
    for (const [tagName, value, className] of entries) {
      const node = document.createElement(tagName);
      node.textContent = String(value ?? "");
      if (className) node.className = className;
      row.appendChild(node);
    }
    parent.appendChild(row);
  }

  function updateJobUI(job) {
    const readout = document.getElementById("job-status-readout");
    const btnRun = document.getElementById("btn-run-job");
    const btnRefresh = document.getElementById("btn-refresh-job");
    const btnRepro = document.getElementById("btn-reproduce-job");
    const btnApprove = document.getElementById("btn-approve-job");
    const btnReject = document.getElementById("btn-reject-job");
    const btnCorr = document.getElementById("btn-submit-corrections");
    const linksDiv = document.getElementById("artifact-links");

    if (!job) {
      readout.textContent = "No active job selected.";
      btnRun.disabled = true;
      btnRefresh.disabled = true;
      btnRepro.disabled = true;
      btnApprove.disabled = true;
      btnReject.disabled = true;
      btnCorr.disabled = true;
      linksDiv.innerHTML = "";
      return;
    }

    state.currentJobId = job.job_id;
    state.currentJobStatus = job.status;

    readout.replaceChildren();
    appendJobLine(readout, [
      ["strong", "Job ID: "],
      ["code", job.job_id],
    ]);
    const safeStatus = String(job.status || "").replace(/[^a-z0-9_-]/gi, "");
    appendJobLine(readout, [
      ["strong", "Status: "],
      ["span", job.status, "job-state job-state-" + safeStatus],
    ]);
    appendJobLine(readout, [
      ["strong", "Style: "],
      ["span", job.style_ref],
      ["strong", " | Scale: "],
      ["span", job.scale_denominator ? "1:" + Math.round(job.scale_denominator) : "pending"],
    ]);
    if (job.error_code) {
      appendJobLine(readout, [
        ["strong", "Error: "],
        ["span", "[" + job.error_code + "] " + (job.error_detail || ""), "error-text"],
      ]);
    }

    btnRefresh.disabled = false;
    btnRun.disabled = !["created", "queued", "failed"].includes(job.status);
    btnRepro.disabled = !["proof_ready", "finalized"].includes(job.status);
    btnApprove.disabled = job.status !== "proof_ready";
    btnReject.disabled = job.status !== "proof_ready";
    btnCorr.disabled = false;

    if (["proof_ready", "finalized", "rejected"].includes(job.status)) {
      const artifacts = ["proof.pdf", "thumb.png", "qa-report.md", "qa-report.json", "manifest.json"];
      linksDiv.innerHTML = artifacts
        .map(
          (name) =>
            `<button type="button" class="artifact-btn" data-artifact="${name}">${name}</button>`
        )
        .join(" ");
      linksDiv.querySelectorAll(".artifact-btn").forEach((btn) => {
        btn.addEventListener("click", () => downloadOrPreviewArtifact(job.job_id, btn.dataset.artifact));
      });
    } else {
      linksDiv.innerHTML = "";
    }
  }

  async function downloadOrPreviewArtifact(jobId, artifactName) {
    showError(null);
    const resp = await fetch(`/api/jobs/${jobId}/artifacts/${artifactName}`, {
      method: "GET",
      headers: getAuthHeaders(false),
    });
    if (!resp.ok) {
      showError(await extractErrorMessage(resp));
      return;
    }
    const preview = document.getElementById("qa-preview");
    if (artifactName.endsWith(".md") || artifactName.endsWith(".json")) {
      const text = await resp.text();
      preview.textContent = text;
      preview.classList.remove("hidden");
    } else {
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
    }
  }

  async function evaluateViability() {
    const geom = currentGeoJSON();
    const badge = document.getElementById("viability-badge");
    const summary = document.getElementById("viability-summary");
    const msgList = document.getElementById("viability-messages");
    const btnSave = document.getElementById("btn-save-revision");
    const requestGeneration = ++state.viabilityGeneration;
    state.viable = false;
    btnSave.disabled = true;
    updateJobSubmission();
    msgList.replaceChildren();

    if (!geom) {
      badge.className = "badge badge-neutral";
      badge.textContent = "No Geofence Drawn";
      summary.innerHTML = "<p>Click at least 3 points on the map or load a preset.</p>";
      btnSave.disabled = true;
      return;
    }

    const paper = document.getElementById("paper-select").value;
    const orientation = document.getElementById("orientation-select").value;
    const styleRef = document.getElementById("style-ref").value.trim() || "mcy/v1";

    const resp = await fetch("/api/viability", {
      method: "POST",
      headers: getAuthHeaders(true),
      body: JSON.stringify({ geofence: geom, paper, orientation, style_ref: styleRef }),
    });
    if (!resp.ok) {
      const errMsg = await extractErrorMessage(resp);
      if (requestGeneration !== state.viabilityGeneration) return;
      badge.className = "badge badge-block";
      badge.textContent = "Viability Error";
      summary.textContent = errMsg;
      btnSave.disabled = true;
      showError(errMsg);
      return;
    }
    const data = await resp.json();
    if (requestGeneration !== state.viabilityGeneration) return;
    showError(null);
    state.viable = !!data.viable;
    btnSave.disabled = !state.projectId || !data.viable;
    updateJobSubmission();
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
    invalidateGeometry();
    if (!state.map) return;
    if (state.polygonLayer) {
      state.map.removeLayer(state.polygonLayer);
      state.polygonLayer = null;
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
    const resp = await fetch(`/api/projects/${state.projectId}/revisions`, {
      headers: getAuthHeaders(false),
    });
    if (!resp.ok) {
      showError(await extractErrorMessage(resp));
      return;
    }
    const list = await resp.json();
    const ul = document.getElementById("revisions-list");
    ul.innerHTML = "";
    list.forEach((rev) => {
      const li = document.createElement("li");
      li.textContent = `${rev.revision_id.slice(0, 12)}… (${rev.is_current ? "current" : "historical"}) — ${rev.created_at}`;
      ul.appendChild(li);
    });
  }

  async function refreshJobStatus() {
    if (!state.currentJobId) return;
    const resp = await fetch(`/api/jobs/${state.currentJobId}`, {
      headers: getAuthHeaders(false),
    });
    if (!resp.ok) {
      showError(await extractErrorMessage(resp));
      return;
    }
    const job = await resp.json();
    updateJobUI(job);
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
      showError(null);
      const areaName = document.getElementById("area-name").value.trim();
      const reference = document.getElementById("area-ref").value.trim();
      const resp = await fetch("/api/projects", {
        method: "POST",
        headers: getAuthHeaders(true),
        body: JSON.stringify({ area_name: areaName, reference }),
      });
      if (!resp.ok) {
        showError(await extractErrorMessage(resp));
        return;
      }
      const data = await resp.json();
      state.projectId = data.project_id;
      invalidateGeometry();
      state.currentJobId = null;
      state.currentJobStatus = null;
      updateJobUI(null);
      document.getElementById("revisions-list").replaceChildren();
      document.getElementById("project-status").textContent = `Active Project: ${data.project_id}`;
      evaluateViability();
      refreshRevisions();
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
    document.getElementById("style-ref").addEventListener("change", evaluateViability);

    document.getElementById("btn-save-revision").addEventListener("click", async () => {
      showError(null);
      const geom = currentGeoJSON();
      if (!state.projectId || !geom || !state.viable) return;
      const geometryVersion = state.geometryVersion;
      const projectId = state.projectId;
      document.getElementById("btn-save-revision").disabled = true;
      const resp = await fetch(`/api/projects/${projectId}/geofence`, {
        method: "POST",
        headers: getAuthHeaders(true),
        body: JSON.stringify(geom),
      });
      if (!resp.ok) {
        showError(await extractErrorMessage(resp));
        if (geometryVersion === state.geometryVersion && projectId === state.projectId) {
          document.getElementById("btn-save-revision").disabled = !state.viable;
        }
        return;
      }
      const rev = await resp.json();
      if (geometryVersion !== state.geometryVersion || projectId !== state.projectId) return;
      state.currentRevisionId = rev.revision_id;
      state.savedGeometryVersion = geometryVersion;
      updateJobSubmission();
      refreshRevisions();
    });

    document.getElementById("btn-submit-job").addEventListener("click", async () => {
      showError(null);
      if (!state.projectId || !state.currentRevisionId || !state.viable ||
          state.savedGeometryVersion !== state.geometryVersion) return;
      const paper = document.getElementById("paper-select").value;
      const orientation = document.getElementById("orientation-select").value;
      const styleRef = document.getElementById("style-ref").value.trim() || "mcy/v1";
      const edition = document.getElementById("edition-input").value.trim() || "2026-10";
      const resp = await fetch("/api/jobs", {
        method: "POST",
        headers: getAuthHeaders(true),
        body: JSON.stringify({
          project_id: state.projectId,
          geofence_revision: state.currentRevisionId,
          paper,
          orientation,
          style_ref: styleRef,
          edition,
        }),
      });
      if (!resp.ok) {
        showError(await extractErrorMessage(resp));
        return;
      }
      const job = await resp.json();
      updateJobUI(job);
    });

    document.getElementById("btn-run-job").addEventListener("click", async () => {
      showError(null);
      if (!state.currentJobId) return;
      const resp = await fetch(`/api/jobs/${state.currentJobId}/run`, {
        method: "POST",
        headers: getAuthHeaders(false),
      });
      if (!resp.ok) {
        showError(await extractErrorMessage(resp));
        await refreshJobStatus();
        return;
      }
      const job = await resp.json();
      updateJobUI(job);
    });

    document.getElementById("btn-refresh-job").addEventListener("click", async () => {
      showError(null);
      await refreshJobStatus();
    });

    document.getElementById("btn-reproduce-job").addEventListener("click", async () => {
      showError(null);
      if (!state.currentJobId) return;
      const resp = await fetch(`/api/jobs/${state.currentJobId}/reproduce`, {
        method: "POST",
        headers: getAuthHeaders(false),
      });
      if (!resp.ok) {
        showError(await extractErrorMessage(resp));
        return;
      }
      const data = await resp.json();
      const preview = document.getElementById("qa-preview");
      preview.textContent = JSON.stringify(data, null, 2);
      preview.classList.remove("hidden");
    });

    document.getElementById("btn-approve-job").addEventListener("click", async () => {
      showError(null);
      if (!state.currentJobId) return;
      const reviewer = document.getElementById("operator-identity").value.trim() || "reviewer";
      const comment = document.getElementById("review-comment").value.trim() || null;
      const resp = await fetch(`/api/jobs/${state.currentJobId}/approve`, {
        method: "POST",
        headers: getAuthHeaders(true),
        body: JSON.stringify({ reviewer, comment }),
      });
      if (!resp.ok) {
        showError(await extractErrorMessage(resp));
        return;
      }
      await refreshJobStatus();
    });

    document.getElementById("btn-reject-job").addEventListener("click", async () => {
      showError(null);
      if (!state.currentJobId) return;
      const reviewer = document.getElementById("operator-identity").value.trim() || "reviewer";
      const comment = document.getElementById("review-comment").value.trim();
      const resp = await fetch(`/api/jobs/${state.currentJobId}/reject`, {
        method: "POST",
        headers: getAuthHeaders(true),
        body: JSON.stringify({ reviewer, comment }),
      });
      if (!resp.ok) {
        showError(await extractErrorMessage(resp));
        return;
      }
      await refreshJobStatus();
    });

    document.getElementById("btn-submit-corrections").addEventListener("click", async () => {
      showError(null);
      if (!state.currentJobId) return;
      const yamlContent = document.getElementById("corrections-yaml").value;
      const author = document.getElementById("operator-identity").value.trim() || "operator";
      const resp = await fetch(`/api/jobs/${state.currentJobId}/corrections`, {
        method: "POST",
        headers: getAuthHeaders(true),
        body: JSON.stringify({ yaml_content: yamlContent, author }),
      });
      if (!resp.ok) {
        showError(await extractErrorMessage(resp));
        return;
      }
      const childJob = await resp.json();
      updateJobUI(childJob);
    });
  });
})();
