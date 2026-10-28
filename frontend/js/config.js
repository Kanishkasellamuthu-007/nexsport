/*
 * Frontend configuration.
 *
 * API_BASE_URL points at the Flask backend. In local development the Live
 * Server origin differs from the API port, so we use the absolute URL.
 * When deployed on Vercel (same origin) it falls back to a relative path.
 */
const CONFIG = {
  API_BASE_URL:
    window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
      ? "http://127.0.0.1:5000"
      : "",
};

// Load public browser settings from Flask. This script must execute before
// auth.js, since it creates the shared supabaseClient used by every page.
document.write(
  '<script src="' + CONFIG.API_BASE_URL + '/api/config.js"><\/script>'
);
