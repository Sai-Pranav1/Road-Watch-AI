// =============================================================================
// RoadGuard AI - Authority Admin Dashboard Logic
// Geospatial map rendering, real-time triage queue, status transitions,
// and KPI analytics monitoring.
// =============================================================================

let adminMap = null;
let mapMarkers = [];
let allReports = [];
let activeStatusFilter = "ALL";
let activeReportForModal = null;
let inspectMap = null;
let inspectMarker = null;
let hasFittedBounds = false;

// Any 401 from the API (session expired / not logged in) -> back to the citizen page password prompt
const _origFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const res = await _origFetch(...args);
  if (res.status === 401) window.location.href = "/admin";
  return res;
};

const OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTRIB = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) window.lucide.createIcons();
  initAdminMap();
  fetchReportsAndRefresh();

  // Keep Leaflet in sync whenever the window / containers change size
  window.addEventListener("resize", () => {
    if (adminMap) adminMap.invalidateSize();
    if (inspectMap) inspectMap.invalidateSize();
  });

  // Auto-refresh feed every 15 seconds for live hackathon presentation
  setInterval(() => {
    fetchReportsAndRefresh(false);
  }, 15000);
});

// Initialize Leaflet map
function initAdminMap() {
  const mapEl = document.getElementById("adminMap");
  if (!mapEl) return;

  adminMap = L.map("adminMap", {
    zoomControl: true,
  }).setView([37.7749, -122.4194], 13);

  L.tileLayer(OSM_TILE_URL, { maxZoom: 19, attribution: OSM_ATTRIB }).addTo(adminMap);

  // Auto-fix size whenever the container itself changes (minimize/expand, layout shifts)
  if (window.ResizeObserver) {
    new ResizeObserver(() => adminMap && adminMap.invalidateSize()).observe(mapEl);
  }
  setTimeout(() => adminMap.invalidateSize(), 200);
}

// Minimize / expand the main hazard map
function toggleMainMap() {
  const wrap = document.getElementById("mainMapWrap");
  const label = document.getElementById("mapToggleLabel");
  const icon = document.getElementById("mapToggleIcon");
  const collapsed = wrap.classList.toggle("hidden");
  label.textContent = collapsed ? "Expand" : "Minimize";
  icon.setAttribute("data-lucide", collapsed ? "chevrons-down" : "chevrons-up");
  if (window.lucide) window.lucide.createIcons();
  if (!collapsed) {
    setTimeout(() => adminMap && adminMap.invalidateSize(), 50);
  }
}

// Lock dashboard
async function adminLogout() {
  try { await _origFetch("/api/v1/admin/logout", { method: "POST" }); } catch (_) {}
  window.location.href = "/admin";
}

// Fetch all reports & KPI stats
async function fetchReportsAndRefresh(showFeedback = true) {
  const refreshIcon = document.getElementById("refreshIcon");
  if (refreshIcon && showFeedback) refreshIcon.classList.add("animate-spin");

  try {
    const [reportsRes, statsRes] = await Promise.all([
      fetch("/api/v1/reports?limit=200"),
      fetch("/api/v1/stats")
    ]);

    if (reportsRes.ok) {
      const data = await reportsRes.json();
      allReports = data.reports || [];
      renderMapMarkers(allReports);
      applyFilters();
    }

    if (statsRes.ok) {
      const stats = await statsRes.json();
      renderStats(stats);
    }
  } catch (err) {
    console.error("Error fetching live dashboard feeds:", err);
  } finally {
    if (refreshIcon) refreshIcon.classList.remove("animate-spin");
  }
}

// Render KPI Stats
function renderStats(stats) {
  document.getElementById("kpiTotal").textContent = stats.total_reports || 0;
  document.getElementById("kpiPending").textContent = stats.pending_triage || 0;
  document.getElementById("kpiInProgress").textContent = (stats.assigned || 0) + (stats.in_progress || 0);
  document.getElementById("kpiResolved").textContent = stats.resolved || 0;
  document.getElementById("kpiCritical").textContent = stats.high_priority_count || 0;
  document.getElementById("kpiAvgScore").textContent = (stats.avg_priority_score || 0).toFixed(1);
}

// Render Map Markers Color-Coded by Priority Score
function renderMapMarkers(reports) {
  if (!adminMap) return;

  // Remember which popup is open so the 15s refresh doesn't close it
  let reopenId = null;
  mapMarkers.forEach(m => { if (m.isPopupOpen && m.isPopupOpen()) reopenId = m._reportId; });

  // Clear existing markers
  mapMarkers.forEach(m => adminMap.removeLayer(m));
  mapMarkers = [];

  const bounds = [];

  reports.forEach(r => {
    const lat = parseFloat(r.latitude);
    const lng = parseFloat(r.longitude);
    if (isNaN(lat) || isNaN(lng)) return;

    bounds.push([lat, lng]);

    const score = r.priority_score || 0;
    const isResolved = r.status === "Resolved";

    let color = "#10b981"; // Emerald (<45)
    let pulseClass = "";

    if (isResolved) {
      color = "#64748b"; // Slate / resolved
    } else if (score >= 75) {
      color = "#ef4444"; // Red (Critical)
      pulseClass = "marker-critical";
    } else if (score >= 45) {
      color = "#f59e0b"; // Amber (Medium)
    }

    const iconHtml = `
      <div class="${pulseClass}" style="
        background-color: ${color};
        width: ${score >= 75 ? '20px' : '16px'};
        height: ${score >= 75 ? '20px' : '16px'};
        border-radius: 50%;
        border: 2px solid white;
        box-shadow: 0 0 10px ${color};
        display: flex;
        align-items: center;
        justify-content: center;
      ">
        <span style="font-size: 8px; font-weight: 800; color: white;">${score}</span>
      </div>
    `;

    const markerIcon = L.divIcon({
      className: "custom-leaflet-marker",
      html: iconHtml,
      iconSize: [20, 20],
      iconAnchor: [10, 10]
    });

    const marker = L.marker([lat, lng], { icon: markerIcon }).addTo(adminMap);

    // Popup Content with thumbnail and quick status dropdown
    const popupHtml = `
      <div style="width: 210px; font-family: sans-serif;">
        <div style="position: relative; border-radius: 8px; overflow: hidden; height: 110px; background: #020617;">
          <img src="${r.image_url}" alt="Damage" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.src='https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?auto=format&fit=crop&w=400&q=80'" />
          <span style="position: absolute; top: 6px; right: 6px; background: ${color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold;">
            Score: ${score}
          </span>
        </div>
        <div style="padding-top: 8px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <strong style="text-transform: capitalize; color: #f8fafc; font-size: 13px;">${r.damage_type}</strong>
            <span style="font-size: 11px; color: ${color}; font-weight: 600;">${r.severity}</span>
          </div>
          <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">${r.road_class}</div>
          <div style="margin-top: 8px; padding-top: 6px; border-top: 1px solid #334155; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 10px; color: #cbd5e1;">Status:</span>
            <select onchange="handlePopupStatusChange('${r.id}', this.value)" style="background: #1e293b; color: #f1f5f9; border: 1px solid #475569; border-radius: 4px; font-size: 10px; padding: 2px 4px;">
              <option value="Reported" ${r.status === 'Reported' ? 'selected' : ''}>Reported</option>
              <option value="Assigned" ${r.status === 'Assigned' ? 'selected' : ''}>Assigned</option>
              <option value="In Progress" ${r.status === 'In Progress' ? 'selected' : ''}>In Progress</option>
              <option value="Resolved" ${r.status === 'Resolved' ? 'selected' : ''}>Resolved</option>
            </select>
          </div>
        </div>
      </div>
    `;

    marker.bindPopup(popupHtml);
    marker._reportId = r.id;
    mapMarkers.push(marker);
    if (reopenId && r.id === reopenId) marker.openPopup();
  });

  // Fit bounds only on first load - re-fitting every refresh made the map feel frozen/stuck
  if (bounds.length > 0 && !hasFittedBounds) {
    adminMap.invalidateSize();
    adminMap.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 });
    hasFittedBounds = true;
  }
}

// Filter Triage Queue
function setStatusFilter(status) {
  activeStatusFilter = status;
  
  // Highlight tab
  document.querySelectorAll(".status-tab").forEach(tab => {
    if (tab.getAttribute("data-filter") === status) {
      tab.className = "status-tab px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600 text-white transition";
    } else {
      tab.className = "status-tab px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-slate-300 hover:bg-slate-700 transition";
    }
  });

  applyFilters();
}

function applyFilters() {
  const searchTerm = (document.getElementById("searchInput").value || "").toLowerCase();
  
  const filtered = allReports.filter(r => {
    const matchesStatus = activeStatusFilter === "ALL" || r.status === activeStatusFilter;
    const matchesSearch = !searchTerm || 
      (r.damage_type && r.damage_type.toLowerCase().includes(searchTerm)) ||
      (r.severity && r.severity.toLowerCase().includes(searchTerm)) ||
      (r.road_class && r.road_class.toLowerCase().includes(searchTerm)) ||
      (r.notes && r.notes.toLowerCase().includes(searchTerm)) ||
      (r.id && r.id.toLowerCase().includes(searchTerm));
    
    return matchesStatus && matchesSearch;
  });

  renderTable(filtered);
}

// Render Table Rows
function renderTable(reports) {
  const tbody = document.getElementById("triageTableBody");
  const countBadge = document.getElementById("queueCountBadge");
  countBadge.textContent = `${reports.length} records`;

  if (reports.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="text-center py-10 text-slate-500">
          No road hazard reports found matching this criteria.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = reports.map(r => {
    const score = r.priority_score || 0;
    let scoreBadge = `<span class="px-2 py-0.5 rounded text-[11px] font-extrabold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">${score}</span>`;
    if (score >= 75) {
      scoreBadge = `<span class="px-2 py-0.5 rounded text-[11px] font-extrabold bg-red-500/10 text-red-400 border border-red-500/30">${score}</span>`;
    } else if (score >= 45) {
      scoreBadge = `<span class="px-2 py-0.5 rounded text-[11px] font-extrabold bg-amber-500/10 text-amber-400 border border-amber-500/30">${score}</span>`;
    }

    let statusPill = `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">${r.status}</span>`;
    if (r.status === "Assigned") statusPill = `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">${r.status}</span>`;
    if (r.status === "In Progress") statusPill = `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">${r.status}</span>`;
    if (r.status === "Resolved") statusPill = `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">${r.status}</span>`;

    return `
      <tr class="hover:bg-slate-800/40 transition">
        <td class="py-2.5 px-3 whitespace-nowrap">
          ${scoreBadge}
        </td>
        <td class="py-2.5 px-3">
          <div class="flex items-center gap-2.5">
            <img src="${r.image_url}" alt="Hazard" class="w-8 h-8 rounded-lg object-cover border border-slate-700 bg-slate-950 flex-shrink-0" onerror="this.src='https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?auto=format&fit=crop&w=100&q=80'" />
            <div>
              <div class="font-semibold text-slate-200 capitalize">${r.damage_type}</div>
              <div class="text-[10px] text-slate-400">Severity: <span class="text-slate-300 font-medium">${r.severity}</span> &bull; Conf: ${Math.round((r.confidence || 0) * 100)}%</div>
            </div>
          </div>
        </td>
        <td class="py-2.5 px-3 text-slate-300 text-[11px]">
          ${r.road_class}
        </td>
        <td class="py-2.5 px-3 whitespace-nowrap">
          ${statusPill}
        </td>
        <td class="py-2.5 px-3 whitespace-nowrap">
          <select onchange="updateReportStatus('${r.id}', this.value)" class="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:outline-none focus:border-cyan-500 cursor-pointer">
            <option value="Reported" ${r.status === 'Reported' ? 'selected' : ''}>Reported</option>
            <option value="Assigned" ${r.status === 'Assigned' ? 'selected' : ''}>Assigned</option>
            <option value="In Progress" ${r.status === 'In Progress' ? 'selected' : ''}>In Progress</option>
            <option value="Resolved" ${r.status === 'Resolved' ? 'selected' : ''}>Resolved</option>
          </select>
        </td>
        <td class="py-2.5 px-3 text-right whitespace-nowrap">
          <button onclick="inspectReport('${r.id}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[11px] font-medium transition">
            Inspect
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

// Quick Status Transition (PATCH /api/v1/reports/{id}/status)
async function updateReportStatus(reportId, newStatus) {
  try {
    const res = await fetch(`/api/v1/reports/${reportId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: newStatus,
        notes: `Status changed to ${newStatus} by Dispatcher`
      })
    });

    if (res.ok) {
      showToast(`Report updated to ${newStatus}`, "success");
      fetchReportsAndRefresh(false);
    } else {
      const err = await res.json();
      showToast(err.detail || "Update failed", "error");
    }
  } catch (e) {
    showToast("Network error updating status", "error");
  }
}

function handlePopupStatusChange(reportId, newStatus) {
  updateReportStatus(reportId, newStatus);
}

// Inspect Modal
function inspectReport(reportId) {
  const report = allReports.find(r => r.id === reportId);
  if (!report) return;

  activeReportForModal = report;
  document.getElementById("modalReportId").textContent = "ID: " + report.id;
  document.getElementById("modalImg").src = report.image_url;
  document.getElementById("modalPriority").textContent = report.priority_score;
  document.getElementById("modalSeverity").textContent = report.severity;
  document.getElementById("modalDamageType").textContent = report.damage_type;
  document.getElementById("modalConfidence").textContent = Math.round((report.confidence || 0) * 100) + "%";
  document.getElementById("modalCoords").textContent = `${report.latitude.toFixed(5)}, ${report.longitude.toFixed(5)}`;
  document.getElementById("modalRoadClass").textContent = report.road_class;

  if (report.assigned_crew) {
    document.getElementById("modalCrewSelect").value = report.assigned_crew;
  }

  document.getElementById("inspectModal").classList.remove("hidden");
  if (window.lucide) window.lucide.createIcons();

  // Make sure the location map is visible, then size it AFTER the modal is displayed
  document.getElementById("inspectMapWrap").classList.remove("hidden");
  document.getElementById("inspectMapToggle").textContent = "Minimize";
  showInspectMap(report);
}

function showInspectMap(report) {
  const lat = parseFloat(report.latitude);
  const lng = parseFloat(report.longitude);
  if (isNaN(lat) || isNaN(lng)) return;

  if (!inspectMap) {
    inspectMap = L.map("inspectMap", { zoomControl: true }).setView([lat, lng], 16);
    L.tileLayer(OSM_TILE_URL, { maxZoom: 19, attribution: OSM_ATTRIB }).addTo(inspectMap);
    inspectMarker = L.marker([lat, lng]).addTo(inspectMap);
    if (window.ResizeObserver) {
      new ResizeObserver(() => inspectMap && inspectMap.invalidateSize())
        .observe(document.getElementById("inspectMapWrap"));
    }
  } else {
    inspectMarker.setLatLng([lat, lng]);
    inspectMap.setView([lat, lng], 16);
  }
  // Modal was hidden a moment ago -> Leaflet must recalculate its size
  requestAnimationFrame(() => {
    inspectMap.invalidateSize();
    inspectMap.setView([lat, lng], 16);
  });
  setTimeout(() => inspectMap && inspectMap.invalidateSize(), 250);
}

function toggleInspectMap() {
  const wrap = document.getElementById("inspectMapWrap");
  const btn = document.getElementById("inspectMapToggle");
  const collapsed = wrap.classList.toggle("hidden");
  btn.textContent = collapsed ? "Expand" : "Minimize";
  if (!collapsed && inspectMap) {
    setTimeout(() => {
      inspectMap.invalidateSize();
      if (activeReportForModal) {
        inspectMap.setView([parseFloat(activeReportForModal.latitude), parseFloat(activeReportForModal.longitude)], 16);
      }
    }, 50);
  }
}

function closeInspectModal() {
  document.getElementById("inspectModal").classList.add("hidden");
  // Return focus to the main map in a correct state
  setTimeout(() => adminMap && adminMap.invalidateSize(), 50);
}

async function saveCrewAssignment() {
  if (!activeReportForModal) return;
  const crew = document.getElementById("modalCrewSelect").value;

  try {
    const res = await fetch(`/api/v1/reports/${activeReportForModal.id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: "Assigned",
        assigned_crew: crew,
        notes: `Dispatched ${crew} to location.`
      })
    });

    if (res.ok) {
      showToast(`Dispatched ${crew}!`, "success");
      closeInspectModal();
      fetchReportsAndRefresh(false);
    }
  } catch (e) {
    showToast("Failed to assign crew", "error");
  }
}

// Toast notification helper
function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");

  const bgColor = type === "success" ? "bg-emerald-600" : type === "error" ? "bg-red-600" : "bg-cyan-600";
  toast.className = `${bgColor} text-white px-4 py-2.5 rounded-xl shadow-xl text-xs font-semibold flex items-center gap-2 transform transition-all duration-300 translate-y-2 opacity-0`;
  toast.innerHTML = `<span>${message}</span>`;

  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.remove("translate-y-2", "opacity-0");
  }, 10);

  setTimeout(() => {
    toast.classList.add("translate-y-2", "opacity-0");
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
