/* Create lobby page (PROTECTED). */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", async function () {
    const session = await requireAuth();
    if (!session) return;

    renderAuthNav();
    document.getElementById("logout-btn").addEventListener("click", async function (e) {
      e.preventDefault();
      await supabaseClient.auth.signOut();
      window.location.replace("index.html");
    });

    loadSports();
    loadGrounds();

    document.getElementById("ground").addEventListener("change", function () {
      const g = this.selectedOptions[0];
      if (!g || !g.dataset.lat) return;
      document.getElementById("latitude").value = g.dataset.lat;
      document.getElementById("longitude").value = g.dataset.lon;
      groundHint();
    });

    document.getElementById("create-form").addEventListener("submit", submit);
  });

  function groundHint() {
    document.getElementById("ground-note").textContent = "Coordinates filled from the selected ground.";
  }

  async function loadSports() {
    try {
      const res = await fetch(CONFIG.API_BASE_URL + "/api/sports");
      const data = await res.json();
      document.getElementById("sport").innerHTML =
        '<option value="">Choose…</option>' +
        (data.sports || []).map(
          (s) => '<option value="' + s.id + '">' + s.icon + " " + s.name + " (" + s.team_size + "-a-side)</option>"
        ).join("");
    } catch { /* handled on submit */ }
  }

  async function loadGrounds() {
    try {
      const token = await getToken();
      const res = await fetch(CONFIG.API_BASE_URL + "/api/grounds", {
        headers: { Authorization: "Bearer " + token },
      });
      const data = await res.json();
      document.getElementById("ground").innerHTML +=
        (data.grounds || []).map(
          (g) =>
            '<option value="' + g.id + '" data-lat="' + g.latitude +
            '" data-lon="' + g.longitude + '">' + g.name +
            (g.city ? " — " + g.city : "") + "</option>"
        ).join("");
    } catch { /* grounds optional */ }
  }

  function setError(id, msg) {
    const el = document.querySelector('[data-error-for="' + id + '"]');
    if (el) el.textContent = msg || "";
  }

  function validate() {
    let ok = true;
    ["title", "sport", "scheduled_at", "players"].forEach((k) => setError(k, ""));

    const title = document.getElementById("title").value.trim();
    if (title.length < 3 || title.length > 100) {
      setError("title", "Title must be 3-100 characters.");
      ok = false;
    }
    if (!document.getElementById("sport").value) {
      setError("sport", "Choose a sport.");
      ok = false;
    }
    if (!document.getElementById("scheduled_at").value) {
      setError("scheduled_at", "Pick a date and time.");
      ok = false;
    } else if (new Date(document.getElementById("scheduled_at").value) < new Date()) {
      setError("scheduled_at", "Date & time must be in the future.");
      ok = false;
    }

    const team = parseInt(document.getElementById("team_size").value, 10);
    const minP = parseInt(document.getElementById("min_players").value, 10);
    const maxP = parseInt(document.getElementById("max_players").value, 10);
    if (!(team >= 1 && team <= 15)) { setError("players", "Players per team must be 1-15."); ok = false; }
    else if (!(maxP >= team * 2 && maxP <= 30)) {
      setError("players", "Max players must be at least 2×" + team + " (= " + team * 2 + ") and at most 30.");
      ok = false;
    } else if (!(minP >= team * 2 && minP <= maxP)) {
      setError("players", "Min players must be " + team * 2 + "-" + maxP + ".");
      ok = false;
    }

    const lat = parseFloat(document.getElementById("latitude").value);
    const lon = parseFloat(document.getElementById("longitude").value);
    if (isNaN(lat) || isNaN(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      showAlert(document.getElementById("alert-box"), "Enter valid coordinates.", "warning");
      ok = false;
    }
    return ok;
  }

  async function submit(e) {
    e.preventDefault();
    const alertBox = document.getElementById("alert-box");
    showAlert(alertBox, "");
    if (!validate()) return;

    const body = {
      title: document.getElementById("title").value.trim(),
      sport_id: document.getElementById("sport").value,
      ground_id: document.getElementById("ground").value || null,
      latitude: parseFloat(document.getElementById("latitude").value),
      longitude: parseFloat(document.getElementById("longitude").value),
      scheduled_at: new Date(document.getElementById("scheduled_at").value).toISOString(),
      team_size: parseInt(document.getElementById("team_size").value, 10),
      min_players: parseInt(document.getElementById("min_players").value, 10),
      max_players: parseInt(document.getElementById("max_players").value, 10),
      description: document.getElementById("description").value.trim() || null,
    };

    setButtonLoading(document.getElementById("create-btn"), true, "Creating…");
    const { ok, data } = await apiFetch("/api/lobbies", {
      method: "POST",
      body: JSON.stringify(body),
    });
    setButtonLoading(document.getElementById("create-btn"), false);

    if (!ok) {
      showAlert(alertBox, data.error || "Could not create the lobby.", "danger");
      return;
    }
    showAlert(alertBox, "Lobby created! Opening it…", "success");
    setTimeout(() => (window.location.href = "lobby.html?id=" + data.lobby.id), 800);
  }
})();
