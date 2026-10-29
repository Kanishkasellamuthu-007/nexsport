/*
 * Nearby Courts page — Leaflet map + court search with filters.
 *
 * Loads demo court data from /data/courts.json, renders markers on the map,
 * populates the search-results list, and wires up the venue filters.
 */
(function () {
  "use strict";

  /* ── Sport → marker colour mapping ─────────────────────────── */
  const SPORT_COLORS = {
    Football:      "#2563EB",
    Basketball:    "#F97316",
    Tennis:        "#16A34A",
    Cricket:       "#EAB308",
    Badminton:     "#8B5CF6",
    Volleyball:    "#EC4899",
    Swimming:      "#06B6D4",
    Running:       "#10B981",
    "Table tennis": "#6366F1",
  };

  function markerIcon(color) {
    return L.divIcon({
      className: "",
      html:
        '<div style="width:28px;height:28px;border-radius:50%;background:' +
        color +
        ";border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35);" +
        'display:flex;align-items:center;justify-content:center;">' +
        '<span style="color:#fff;font-size:13px;font-weight:700;">⚑</span></div>',
      iconSize: [28, 28],
      iconAnchor: [14, 28],
      popupAnchor: [0, -30],
    });
  }

  /* ── Haversine distance (km) ───────────────────────────────── */
  function haversine(lat1, lng1, lat2, lng2) {
    var R = 6371;
    var dLat = ((lat2 - lat1) * Math.PI) / 180;
    var dLng = ((lng2 - lng1) * Math.PI) / 180;
    var a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.sin(dLng / 2) *
        Math.sin(dLng / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  /* ── Render a single court card (HTML string) ──────────────── */
  function courtCard(court, distKm) {
    var dist =
      distKm !== null ? distKm.toFixed(1) + " km away" : "Distance unknown";
    var stars = "★".repeat(Math.round(court.rating || 0)) +
                "☆".repeat(5 - Math.round(court.rating || 0));
    return (
      '<div class="court-item" data-id="' + court.id + '" style="' +
        "padding:14px 16px;border-bottom:1px solid var(--border);" +
        'cursor:pointer;transition:background .15s;"' +
        ' onmouseenter="this.style.background=\'var(--surface-muted)\'"' +
        ' onmouseleave="this.style.background=\'transparent\'">' +
        '<div style="display:flex;justify-content:space-between;align-items:start;gap:10px">' +
          '<div>' +
            '<strong style="font-size:14px;color:var(--text)">' + court.name + "</strong>" +
            '<div style="font-size:12px;color:var(--text-2);margin-top:2px">' +
              court.address +
            "</div>" +
          "</div>" +
          '<span style="' +
            "font-size:11px;font-weight:600;white-space:nowrap;padding:3px 8px;" +
            "border-radius:20px;background:" +
            (SPORT_COLORS[court.sport] || "#6B7280") +
            ';color:#fff">' +
            court.sport +
          "</span>" +
        "</div>" +
        '<div style="display:flex;gap:12px;margin-top:8px;font-size:12px;color:var(--text-2)">' +
          "<span>📍 " + dist + "</span>" +
          "<span>🏟 " + court.venue_type + "</span>" +
          "<span>" + (court.access === "Free" ? "🟢" : "🔵") + " " + court.access + "</span>" +
          '<span style="color:#F59E0B;letter-spacing:1px">' + stars + "</span>" +
        "</div>" +
      "</div>"
    );
  }

  /* ── Main init ─────────────────────────────────────────────── */
  document.addEventListener("DOMContentLoaded", function () {
    var mapEl = document.getElementById("map");
    if (!mapEl || typeof L === "undefined") {
      console.error("Leaflet or #map container missing");
      return;
    }

    /* Default centre: Chennai */
    var DEFAULT_LAT = 13.0827;
    var DEFAULT_LNG = 80.2707;
    var userLat = null;
    var userLng = null;
    var allCourts = [];
    var markers = [];

    /* Initialise map */
    var map = L.map("map", { scrollWheelZoom: true }).setView(
      [DEFAULT_LAT, DEFAULT_LNG],
      12
    );
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map);

    /* Fix Leaflet tiles not rendering inside hidden/flex containers */
    setTimeout(function () {
      map.invalidateSize();
    }, 300);

    /* ── Try to get user location ─────────────────────────────── */
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          userLat = pos.coords.latitude;
          userLng = pos.coords.longitude;
          map.setView([userLat, userLng], 13);
          L.marker([userLat, userLng], {
            icon: L.divIcon({
              className: "",
              html:
                '<div style="width:14px;height:14px;border-radius:50%;background:#2563EB;' +
                'border:3px solid #fff;box-shadow:0 0 0 3px rgba(37,99,235,.35)"></div>',
              iconSize: [14, 14],
              iconAnchor: [7, 7],
            }),
          })
            .addTo(map)
            .bindPopup("<strong>You are here</strong>");
          applyFilters(); // re-sort by distance
        },
        function () {
          /* permission denied or unavailable — use default centre */
        }
      );
    }

    /* ── Fetch court data ─────────────────────────────────────── */
    fetch("/data/courts.json")
      .then(function (res) { return res.json(); })
      .then(function (data) {
        allCourts = data;
        applyFilters();
      })
      .catch(function (err) {
        console.error("Failed to load courts:", err);
      });

    /* ── Filter controls ──────────────────────────────────────── */
    var sportFilter = document.querySelector('select[name="sport"]');
    var venueFilter = document.querySelector('select[name="venue"]');
    var distFilter = document.querySelector('select[name="distance"]');
    var accessFilter = document.querySelector('select[name="booking"]');

    [sportFilter, venueFilter, distFilter, accessFilter].forEach(function (el) {
      if (el) el.addEventListener("change", applyFilters);
    });

    /* ── Apply filters + render ────────────────────────────────── */
    function applyFilters() {
      var sport = sportFilter ? sportFilter.value : "";
      var venue = venueFilter ? venueFilter.value : "";
      var dist = distFilter ? distFilter.value : "";
      var access = accessFilter ? accessFilter.value : "";

      /* Parse max km from distance filter */
      var maxKm = Infinity;
      var m = dist.match(/(\d+)/);
      if (m) maxKm = parseInt(m[1], 10);

      var filtered = allCourts.filter(function (c) {
        if (sport && sport !== "Any sport" && c.sport !== sport) return false;
        if (venue && venue !== "All venues" && c.venue_type !== venue) return false;
        if (access && access !== "Any access" && c.access !== access) return false;
        return true;
      });

      /* Compute distances and filter by max km */
      var refLat = userLat !== null ? userLat : DEFAULT_LAT;
      var refLng = userLng !== null ? userLng : DEFAULT_LNG;
      filtered = filtered
        .map(function (c) {
          c._dist = haversine(refLat, refLng, c.lat, c.lng);
          return c;
        })
        .filter(function (c) {
          return c._dist <= maxKm;
        })
        .sort(function (a, b) {
          return a._dist - b._dist;
        });

      renderResults(filtered);
      renderMarkers(filtered);
    }

    /* ── Render search results list ────────────────────────────── */
    function renderResults(courts) {
      /* Find the "Search results" card body */
      var resultsCard = document.querySelectorAll(".card")[1]; // second card
      if (!resultsCard) return;

      var body = resultsCard.querySelector(".empty") || resultsCard.querySelector(".court-list");
      if (!body) return;

      if (courts.length === 0) {
        body.className = "empty";
        body.innerHTML =
          '<div class="glyph">◎</div>' +
          "<h4>No courts to show</h4>" +
          "<p>Adjust your filters or increase the distance range to see results.</p>";
        return;
      }

      body.className = "court-list";
      body.style.cssText = "max-height:500px;overflow-y:auto;";
      var html = "";
      courts.forEach(function (c) {
        html += courtCard(c, c._dist !== undefined ? c._dist : null);
      });
      body.innerHTML = html;

      /* Click a card → pan map to that court */
      body.querySelectorAll(".court-item").forEach(function (el) {
        el.addEventListener("click", function () {
          var id = parseInt(el.dataset.id, 10);
          var court = allCourts.find(function (c) { return c.id === id; });
          if (court) {
            map.setView([court.lat, court.lng], 15);
            markers.forEach(function (m) {
              if (m._courtId === id) m.openPopup();
            });
          }
        });
      });
    }

    /* ── Render map markers ────────────────────────────────────── */
    function renderMarkers(courts) {
      /* Clear old markers */
      markers.forEach(function (m) { map.removeLayer(m); });
      markers = [];

      courts.forEach(function (c) {
        var color = SPORT_COLORS[c.sport] || "#6B7280";
        var marker = L.marker([c.lat, c.lng], { icon: markerIcon(color) })
          .addTo(map)
          .bindPopup(
            "<div style='min-width:180px'>" +
              "<strong>" + c.name + "</strong><br>" +
              "<span style='font-size:12px;color:#555'>" + c.address + "</span><br>" +
              "<span style='display:inline-block;margin-top:4px;padding:2px 8px;border-radius:12px;" +
              "background:" + color + ";color:#fff;font-size:11px;font-weight:600'>" +
              c.sport + "</span> " +
              "<span style='font-size:12px'>" + c.venue_type + " · " + c.access + "</span>" +
            "</div>"
          );
        marker._courtId = c.id;
        markers.push(marker);
      });

      /* Fit map to all markers if any */
      if (markers.length > 0) {
        var group = L.featureGroup(markers);
        map.fitBounds(group.getBounds().pad(0.15));
      }
    }
  });
})();

