/*
 * NexSport homepage script.
 * Currently only checks API health. Auth, matchmaking etc. come later.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const statusEl = document.getElementById("api-status");
    if (!statusEl) return;

    fetch(CONFIG.API_BASE_URL + "/api/health")
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        statusEl.textContent = "" + data.message + " (v" + data.version + ")";
        statusEl.classList.add("ok");
        const dot = document.getElementById("api-status-dot");
        if (dot) {
          dot.className = "status-dot ok";
        }
      })
      .catch(function () {
        statusEl.textContent =
          "Backend not reachable. Start it with: python run.py";
        statusEl.classList.add("down");
        const dot = document.getElementById("api-status-dot");
        if (dot) {
          dot.className = "status-dot down";
        }
      });

    renderAuthNav(); // highlight Login/Dashboard in navbar based on session
  });
})();
