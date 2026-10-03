// =============================================================================
// RoadGuard AI - Citizen Web App Client Logic
// Handles file upload, drag & drop, GPS auto-detection, Leaflet mini-map,
// and POST /api/v1/analyze dispatch.
// =============================================================================

let selectedFile = null;
let miniMap = null;
let marker = null;

// Default initial coordinates (Downtown San Francisco / Metro Hub)
let currentLat = 37.7749;
let currentLng = -122.4194;

document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    window.lucide.createIcons();
  }
  initMiniMap();
  setupDropzone();

  window.addEventListener("resize", () => miniMap && miniMap.invalidateSize());
});

// Initialize Leaflet map with interactive draggable pin
function initMiniMap() {
  const mapEl = document.getElementById("miniMap");
  if (!mapEl) return;

  miniMap = L.map("miniMap", {
    zoomControl: false,
  }).setView([currentLat, currentLng], 14);

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(miniMap);

  // Custom marker icon
  const customIcon = L.divIcon({
    className: "custom-pin",
    html: `<div style="background-color: #06b6d4; width: 16px; height: 16px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 10px rgba(6,182,212,0.8);"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8]
  });

  marker = L.marker([currentLat, currentLng], {
    draggable: true,
    icon: customIcon
  }).addTo(miniMap);

  updateInputs(currentLat, currentLng);

  // Sync when marker is dragged
  marker.on("dragend", (e) => {
    const pos = e.target.getLatLng();
    updateInputs(pos.lat, pos.lng);
  });

  // Sync when user clicks anywhere on map
  miniMap.on("click", (e) => {
    marker.setLatLng(e.latlng);
    updateInputs(e.latlng.lat, e.latlng.lng);
  });

  // Handle manual input changes
  document.getElementById("latInput").addEventListener("input", onManualCoordChange);
  document.getElementById("lngInput").addEventListener("input", onManualCoordChange);
}

function updateInputs(lat, lng) {
  currentLat = parseFloat(lat.toFixed(6));
  currentLng = parseFloat(lng.toFixed(6));
  document.getElementById("latInput").value = currentLat;
  document.getElementById("lngInput").value = currentLng;
}

function onManualCoordChange() {
  const lat = parseFloat(document.getElementById("latInput").value);
  const lng = parseFloat(document.getElementById("lngInput").value);
  if (!isNaN(lat) && !isNaN(lng)) {
    currentLat = lat;
    currentLng = lng;
    marker.setLatLng([lat, lng]);
    miniMap.panTo([lat, lng]);
  }
}

// Browser Geolocation auto-detection
function autoDetectLocation() {
  const geoBtn = document.getElementById("geoBtn");
  if (!navigator.geolocation) {
    alert("Geolocation is not supported by your browser.");
    return;
  }

  geoBtn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Locating...</span>`;
  if (window.lucide) window.lucide.createIcons();

  navigator.geolocation.getCurrentPosition(
    (position) => {
      const lat = position.coords.latitude;
      const lng = position.coords.longitude;
      updateInputs(lat, lng);
      marker.setLatLng([lat, lng]);
      miniMap.flyTo([lat, lng], 16);

      geoBtn.innerHTML = `<i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400"></i><span>Located!</span>`;
      if (window.lucide) window.lucide.createIcons();
      setTimeout(() => {
        geoBtn.innerHTML = `<i data-lucide="crosshair" class="w-3.5 h-3.5"></i><span>Auto-Locate GPS</span>`;
        if (window.lucide) window.lucide.createIcons();
      }, 3000);
    },
    (err) => {
      console.warn("Geolocation warning/fallback:", err.message);
      geoBtn.innerHTML = `<i data-lucide="crosshair" class="w-3.5 h-3.5"></i><span>Auto-Locate GPS</span>`;
      if (window.lucide) window.lucide.createIcons();
      alert("Could not fetch automatic GPS. Please pick a location on the map.");
    },
    { enableHighAccuracy: true, timeout: 8000 }
  );
}

// Drag & drop dropzone setup
function setupDropzone() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("imageInput");

  dropzone.addEventListener("click", () => {
    fileInput.click();
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add("border-cyan-400", "bg-cyan-950/20");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("border-cyan-400", "bg-cyan-950/20");
    });
  });

  dropzone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type.startsWith("image/")) {
      handleImage(files[0]);
    }
  });
}

function handleFileSelect(e) {
  if (e.target.files && e.target.files[0]) {
    handleImage(e.target.files[0]);
  }
}

function handleImage(file) {
  selectedFile = file;
  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById("imagePreview").src = e.target.result;
    document.getElementById("uploadPlaceholder").classList.add("hidden");
    document.getElementById("previewContainer").classList.remove("hidden");
  };
  reader.readAsDataURL(file);
}

function clearSelectedImage(e) {
  e.stopPropagation();
  selectedFile = null;
  document.getElementById("imageInput").value = "";
  document.getElementById("previewContainer").classList.add("hidden");
  document.getElementById("uploadPlaceholder").classList.remove("hidden");
}

// Form Submission & API Pipeline
async function handleReportSubmit(e) {
  e.preventDefault();

  if (!selectedFile) {
    alert("Please select or capture a road damage image first.");
    return;
  }

  const lat = parseFloat(document.getElementById("latInput").value);
  const lng = parseFloat(document.getElementById("lngInput").value);
  const roadClass = document.getElementById("roadClassSelect").value;
  const notes = document.getElementById("notesInput").value;

  if (isNaN(lat) || isNaN(lng)) {
    alert("Please specify valid latitude and longitude coordinates.");
    return;
  }

  const formData = new FormData();
  formData.append("image", selectedFile);
  formData.append("lat", lat);
  formData.append("lng", lng);
  formData.append("road_class", roadClass);
  formData.append("notes", notes);

  // Show loading overlay
  const overlay = document.getElementById("loadingOverlay");
  const stage = document.getElementById("loadingStage");
  overlay.classList.remove("hidden");

  try {
    stage.textContent = "Uploading image and executing YOLOv8 model inference...";
    
    const response = await fetch("/api/v1/analyze", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Analysis failed");
    }

    stage.textContent = "Calculating composite priority score and persisting to Supabase...";
    const data = await response.json();

    // Render results
    renderResults(data);

  } catch (err) {
    alert("Error processing report: " + err.message);
  } finally {
    overlay.classList.add("hidden");
  }
}

function renderResults(data) {
  const card = document.getElementById("resultsCard");
  card.classList.remove("hidden");

  // Populate data
  document.getElementById("resReportId").textContent = "ID: " + data.report_id.slice(0, 8) + "...";
  document.getElementById("resTimestamp").textContent = new Date(data.timestamp).toLocaleString();
  document.getElementById("resAnnotatedImg").src = data.image_url;
  
  const score = data.detection.priority_score;
  const scoreEl = document.getElementById("resPriorityScore");
  scoreEl.textContent = score;

  // Dynamic score color
  if (score >= 75) {
    scoreEl.className = "text-4xl font-extrabold text-red-400";
  } else if (score >= 45) {
    scoreEl.className = "text-4xl font-extrabold text-amber-400";
  } else {
    scoreEl.className = "text-4xl font-extrabold text-emerald-400";
  }

  document.getElementById("resPriorityBar").style.width = `${score}%`;
  document.getElementById("resDamageType").textContent = data.detection.type;
  document.getElementById("resSeverity").textContent = data.detection.severity;
  document.getElementById("resConfidence").textContent = Math.round(data.detection.confidence * 100) + "%";
  document.getElementById("resStatus").textContent = data.status || "Reported";

  if (window.lucide) window.lucide.createIcons();

  // Smooth scroll into view
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetCitizenForm() {
  document.getElementById("resultsCard").classList.add("hidden");
  clearSelectedImage({ stopPropagation: () => {} });
  document.getElementById("notesInput").value = "";
  window.scrollTo({ top: 0, behavior: "smooth" });
}


