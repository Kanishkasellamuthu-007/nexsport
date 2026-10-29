/*
 * OpenStreetMap integration using Leaflet (open‑source).
 * This script assumes the Leaflet CSS/JS are loaded on the page
 * (via CDN links in the HTML). It creates a map centered on a default
 * location and adds a marker. Feel free to adjust `DEFAULT_CENTER`
 * and `DEFAULT_ZOOM`.
 */

const DEFAULT_CENTER = [37.7749, -122.4194]; // San Francisco, CA
const DEFAULT_ZOOM = 12;

function initMap() {
  // Make sure the container element exists
  const mapContainer = document.getElementById('map');
  if (!mapContainer) {
    console.error('Map container #map not found');
    return;
  }

  // Initialise the Leaflet map
  const map = L.map('map').setView(DEFAULT_CENTER, DEFAULT_ZOOM);

  // Use OpenStreetMap tiles (free, open source)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);

  // Example marker – you can add more dynamically later
  L.marker(DEFAULT_CENTER).addTo(map).bindPopup('Demo location').openPopup();
}

// Initialise when the DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initMap);
} else {
  initMap();
}

