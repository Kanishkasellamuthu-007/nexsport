/*
 * Find Matches page (PROTECTED).
 * GPS via Geolocation API with graceful fallback to manual coordinates.
 */
(function () {
  "use strict";

  let ORIGIN = null; // {lat, lon, source}

  document.addEventListener("DOMContentLoaded", async function () {
    const session = await requireAuth();
    if (!session) return;

    renderAuthNav();
    document.getElementById("logout-btn").addEventListener("click", async function (e) {
      e.preventDefault();
      await supabaseClient.auth.signOut();
      window.location.replace("index.html");
    });

    loadSportsFilter();

    document.getElementById("gps-btn").addEventListener("click", useGps);
    document.getElementById("manual-btn").addEventListener("click", useManual);
    document.getElementById("manual-city").addEventListener("change", function () {
      const v = this.value;
      if (!v) return;
      const [lat, lon] = v.split(",");
      document.getElementById("manual-lat").value = lat;
      document.getElementById("manual-lon").value = lon;
    });
    document.getElementById("search-btn").addEventListener("click", search);
  });

  // ---------- GPS ----------
  function useGps() {
    const status = document.getElementById("location-status");
    const alertBox = document.getElementById("alert-box");

    if (!("geolocation" in navigator)) {
      showAlert(alertBox, "Your browser does not support GPS. Please enter your location manually.", "warning");
      return;
    }

    setButtonLoading(document.getElementById("gps-btn"), true, "Locating…");
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        setButtonLoading(document.getElementById("gps-btn"), false);
        setOrigin(pos.coords.latitude, pos.coords.longitude, "GPS");
      },
      function (err) {
        setButtonLoading(document.getElementById("gps-btn"), false);
        const reasons = {
          1: "Location permission denied. Enter your location manually instead.",
          2: "Location unavailable right now. Try manual entry.",
          3: "Location request timed out. Try again or use manual entry.",
        };
        showAlert(alertBox, reasons[err.code] || "Could not get your location. Use manual entry.", "warning");
        document.getElementById("manualBox").classList.add("show"); // open fallback
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  }

  // ---------- Manual ----------
  function useManual() {
    const alertBox = document.getElementById("alert-box");
    const lat = parseFloat(document.getElementById("manual-lat").value);
    const lon = parseFloat(document.getElementById("manual-lon").value);

    if (isNaN(lat) || isNaN(lon)) {
      showAlert(alertBox, "Enter both latitude and longitude as numbers.", "warning");
      return;
    }
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      showAlert(alertBox, "Latitude must be -90..90 and longitude -180..180.", "warning");
      return;
    }
    showAlert(alertBox, "");
    setOrigin(lat, lon, "manual");
  }

  function setOrigin(lat, lon, source) {
    ORIGIN = { lat: lat, lon: lon };
    document.getElementById("location-status").innerHTML =
      "✅ Using <strong>" + source + "</strong> location: " +
      lat.toFixed(4) + ", " + lon.toFixed(4);
    document.getElementById("filters-card").classList.remove("d-none");
  }

  // ---------- Filters ----------
  async function loadSportsFilter() {
    try {
      const res = await fetch(CONFIG.API_BASE_URL + "/api/sports");
      const data = await res.json();
      document.getElementById("filter-sport").innerHTML +=
        (data.sports || [])
          .map((s) => '<option value="' + s.id + '">' + s.icon + " " + s.name + "</option>")
          .join("");
    } catch { /* dropdown stays "All sports" */ }
  }

  // ---------- Search ----------
  async function search() {
    const alertBox = document.getElementById("alert-box");
    const results = document.getElementById("results");
    if (!ORIGIN) {
      showAlert(alertBox, "Set your location first.", "warning");
      return;
    }
    showAlert(alertBox, "");
    results.innerHTML =
      '<div class="text-center py-4"><div class="spinner-border text-success"></div>' +
      '<p class="text-muted mt-2">Searching nearby lobbies…</p></div>';

    const params = new URLSearchParams({
      lat: ORIGIN.lat,
      lon: ORIGIN.lon,
      radius_km: document.getElementById("filter-radius").value,
    });
    const sport = document.getElementById("filter-sport").value;
    if (sport) params.set("sport_id", sport);

    const { ok, data } = await apiFetch("/api/lobbies/nearby?" + params.toString());
    if (!ok) {
      results.innerHTML = "";
      showAlert(alertBox, data.error || "Search failed.", "danger");
      return;
    }

    if (!data.lobbies.length) {
      results.innerHTML =
        '<div class="card stat-card"><div class="card-body text-center py-5">' +
        '<p class="fs-1 mb-2">🔍</p>' +
        '<h2 class="h5 fw-bold">No matches found nearby</h2>' +
        '<p class="text-muted mb-3">No open lobbies found within ' + data.radius_km +
        " km of your location. Try a larger radius, a different sport, or host a game yourself!</p>" +
        '<a href="create-lobby.html" class="btn btn-sm btn-success"><i class="bi bi-plus-circle me-1"></i>Create a Match Lobby</a>' +
        "</div></div>";
      return;
    }

    results.innerHTML =
      '<p class="text-muted small mb-2">' + data.count + " lobby(ies) found, nearest first. " +
      'Distances via the Haversine formula.</p>' +
      '<div class="row g-3">' +
      data.lobbies.map(lobbyCard).join("") +
      "</div>";
  }

  function lobbyCard(lb) {
    const statusBadge = {
      open: '<span class="badge badge-status-open"><i class="bi bi-door-open-fill me-1"></i>Open</span>',
      full: '<span class="badge badge-status-full"><i class="bi bi-people-fill me-1"></i>Full</span>',
      in_progress: '<span class="badge badge-status-in-progress"><i class="bi bi-play-circle-fill me-1"></i>In Progress</span>',
    }[lb.status] || '<span class="badge bg-secondary">' + lb.status + "</span>";

    const totalPlaces = lb.players_joined + lb.places_available;
    const fillPercent = totalPlaces > 0 ? Math.round((lb.players_joined / totalPlaces) * 100) : 0;
    const progressClass = lb.places_available <= 1 ? "almost-full" : (lb.status === "full" ? "full" : "");

    const actionBtn = '<a href="lobby.html?id=' + encodeURIComponent(lb.id) + '" class="btn btn-sm btn-success w-100">' +
      '<i class="bi bi-box-arrow-in-right"></i> View &amp; Join Lobby</a>';

    const when = new Date(lb.scheduled_at).toLocaleString(undefined, {
      weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
    });

    return (
      '<div class="col-12 col-md-6 col-lg-4">' +
      '<div class="lobby-item-card">' +
      '<div class="d-flex justify-content-between align-items-center mb-2">' +
      '<span class="badge bg-success-subtle text-success-emphasis border border-success-subtle fw-semibold px-2 py-1">' +
      (lb.sport ? lb.sport.icon + " " + lb.sport.name : "⚽ Match") +
      '</span>' +
      statusBadge +
      '</div>' +
      '<h4 class="h6 fw-bold mb-1 text-dark">' + escapeHtml(lb.title) + '</h4>' +
      '<p class="text-muted small mb-2"><i class="bi bi-geo-alt-fill text-danger me-1"></i>' +
      escapeHtml(lb.ground_name) + ' <span class="badge bg-light text-muted border ms-1">~' + lb.distance_km + ' km</span></p>' +
      '<div class="small text-secondary mb-2"><i class="bi bi-clock me-1"></i>' + when + '</div>' +
      '<div class="my-2">' +
      '<div class="d-flex justify-content-between small text-muted mb-1">' +
      '<span><i class="bi bi-people me-1"></i>Players (' + lb.players_joined + '/' + totalPlaces + ')</span>' +
      '<strong class="' + (lb.places_available > 0 ? 'text-success' : 'text-danger') + '">' +
      (lb.places_available > 0 ? lb.places_available + ' spot(s) open' : 'Full') + '</strong>' +
      '</div>' +
      '<div class="progress-capacity"><div class="progress-capacity-bar ' + progressClass + '" style="width:' + fillPercent + '%;"></div></div>' +
      '</div>' +
      '<div class="mt-auto pt-2">' + actionBtn + '</div>' +
      '</div></div>'
    );
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }
})();
