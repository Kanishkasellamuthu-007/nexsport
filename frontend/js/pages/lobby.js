/* Lobby detail page (PROTECTED): participants, join/leave, host controls. */
(function () {
  "use strict";

  let LOBBY_ID = null;
  let LOBBY = null;
  let CURRENT_USER_ID = null;

  document.addEventListener("DOMContentLoaded", async function () {
    const session = await requireAuth();
    if (!session) return;

    CURRENT_USER_ID = session.user.id;
    renderAuthNav();
    document.getElementById("logout-btn").addEventListener("click", async function (e) {
      e.preventDefault();
      await supabaseClient.auth.signOut();
      window.location.replace("index.html");
    });

    LOBBY_ID = new URLSearchParams(location.search).get("id");
    if (!LOBBY_ID) {
      document.getElementById("lobby-root").innerHTML =
        '<div class="alert alert-danger"><i class="bi bi-exclamation-triangle-fill me-2"></i>No lobby id specified in URL.</div>';
      return;
    }
    await load();
  });

  async function load() {
    const { ok, data } = await apiFetch("/api/lobbies/" + LOBBY_ID);
    if (!ok) {
      document.getElementById("lobby-root").innerHTML =
        '<div class="alert alert-danger"><i class="bi bi-exclamation-octagon-fill me-2"></i>' +
        (data.error || "Could not load match lobby.") + "</div>";
      return;
    }
    LOBBY = data.lobby;
    render();
  }

  function statusBadge(status) {
    const map = {
      open: '<span class="badge badge-status-open"><i class="bi bi-door-open-fill me-1"></i>Open</span>',
      full: '<span class="badge badge-status-full"><i class="bi bi-people-fill me-1"></i>Full</span>',
      in_progress: '<span class="badge badge-status-in-progress"><i class="bi bi-play-circle-fill me-1"></i>In Progress</span>',
      completed: '<span class="badge bg-primary"><i class="bi bi-check-all me-1"></i>Completed</span>',
      cancelled: '<span class="badge bg-danger"><i class="bi bi-x-circle-fill me-1"></i>Cancelled</span>',
    };
    return map[status] || '<span class="badge bg-secondary">' + status + '</span>';
  }

  function render() {
    const l = LOBBY;
    const isHost = l.host.id === CURRENT_USER_ID;
    const isParticipant = l.participants.some((p) => p.user_id === CURRENT_USER_ID);
    const inFuture = new Date(l.scheduled_at) > new Date();
    const canJoin = l.status === "open" && l.places_available > 0 && !isParticipant && inFuture;
    const canLeave = (l.status === "open" || l.status === "full") && isParticipant;

    const fillPercent = Math.round((l.players_joined / l.max_players) * 100);
    const progressClass = l.places_available <= 1 ? "almost-full" : (l.status === "full" ? "full" : "");

    const participantsHtml = l.participants.length
      ? l.participants.map((p, i) => {
        const name = p.username || "Player " + (i + 1);
        const initials = name.slice(0, 2).toUpperCase();
        const isCurrent = p.user_id === CURRENT_USER_ID;
        const isLobbyHost = p.user_id === l.host.id;
        return (
          '<li class="list-group-item d-flex align-items-center justify-content-between p-3">' +
          '<div class="d-flex align-items-center gap-3">' +
          '<div class="user-avatar-circle ' + (isCurrent ? 'primary' : '') + '">' + initials + '</div>' +
          '<div>' +
          '<span class="fw-semibold text-dark">' + escapeHtml(name) + '</span>' +
          (isCurrent ? ' <span class="badge bg-success-subtle text-success border border-success-subtle ms-1">You</span>' : '') +
          '</div>' +
          '</div>' +
          (isLobbyHost ? '<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle"><i class="bi bi-star-fill me-1"></i>Host</span>' : '') +
          '</li>'
        );
      }).join("")
      : '<li class="list-group-item text-muted text-center py-4">No players yet — be the first to join!</li>';

    const hostControls = isHost
      ? '<div class="card stat-card mt-3 border-0 shadow-sm"><div class="card-body p-4">' +
      '<div class="d-flex align-items-center gap-2 mb-3">' +
      '<span class="fs-5">👑</span><h5 class="h6 card-title mb-0">Host Match Controls</h5>' +
      '</div>' +
      '<div class="d-flex gap-2 flex-wrap">' +
      '<button id="teams-btn" class="btn btn-outline-success"' +
      '   ' + (l.status === "open" || l.status === "full" ? "" : "disabled") + '><i class="bi bi-shuffle me-1"></i>Generate Zig-Zag Teams</button>' +
      '<button id="start-btn" class="btn btn-success"' +
      '   ' + (l.status === "open" || l.status === "full" ? "" : "disabled") + '><i class="bi bi-play-fill me-1"></i>Start Match</button>' +
      '<button id="cancel-btn" class="btn btn-outline-danger"' +
      '   ' + (l.status !== "completed" && l.status !== "cancelled" ? "" : "disabled") + '><i class="bi bi-x-circle me-1"></i>Cancel Lobby</button>' +
      '</div></div></div>'
      : "";

    const whenFormatted = new Date(l.scheduled_at).toLocaleString(undefined, {
      weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
    });

    document.getElementById("lobby-root").innerHTML =
      '<div class="card stat-card border-0 shadow-sm overflow-hidden">' +
      '<div class="card-header bg-white border-bottom p-4">' +
      '<div class="d-flex justify-content-between align-items-start flex-wrap gap-2">' +
      '<div>' +
      '<span class="badge bg-success-subtle text-success-emphasis border border-success-subtle px-2 py-1 mb-2 d-inline-block fw-semibold">' +
      (l.sport ? l.sport.icon + " " + l.sport.name : "⚽ Sport") + '</span>' +
      '<h1 class="h4 fw-bold mb-1">' + escapeHtml(l.title) + '</h1>' +
      '<p class="text-muted small mb-0"><i class="bi bi-person-fill me-1"></i>Host: <strong>' +
      escapeHtml((l.host && l.host.username) || "Organizer") + '</strong></p>' +
      '</div>' +
      statusBadge(l.status) +
      '</div>' +
      '</div>' +

      '<div class="card-body p-4">' +
      '<div class="row g-3 mb-4">' +
      '<div class="col-sm-6">' +
      '<div class="p-3 bg-light rounded-3 h-100">' +
      '<div class="text-muted small mb-1"><i class="bi bi-geo-alt-fill text-danger me-1"></i>Ground Location</div>' +
      '<strong class="d-block text-dark">' + escapeHtml(l.ground_name) + '</strong>' +
      (l.ground && l.ground.city ? '<small class="text-muted">' + escapeHtml(l.ground.city) + '</small>' : '') +
      '</div></div>' +

      '<div class="col-sm-6">' +
      '<div class="p-3 bg-light rounded-3 h-100">' +
      '<div class="text-muted small mb-1"><i class="bi bi-calendar-event me-1"></i>Kickoff Schedule</div>' +
      '<strong class="d-block text-dark">' + whenFormatted + '</strong>' +
      '<small class="text-muted">Teams of ' + l.team_size + ' (' + l.min_players + '–' + l.max_players + ' players)</small>' +
      '</div></div>' +
      '</div>' +

      (l.description ? '<div class="alert alert-light border small text-secondary mb-4"><i class="bi bi-card-text me-2"></i>' + escapeHtml(l.description) + '</div>' : '') +

      '<div class="mb-4">' +
      '<div class="d-flex justify-content-between small text-muted mb-1">' +
      '<span><i class="bi bi-people-fill me-1"></i>Capacity: <strong>' + l.players_joined + ' / ' + l.max_players + '</strong> players</span>' +
      '<strong class="' + (l.places_available > 0 ? 'text-success' : 'text-danger') + '">' +
      (l.places_available > 0 ? l.places_available + ' spot(s) remaining' : 'Lobby is full') + '</strong>' +
      '</div>' +
      '<div class="progress-capacity"><div class="progress-capacity-bar ' + progressClass + '" style="width:' + fillPercent + '%;"></div></div>' +
      '</div>' +

      '<div class="d-flex gap-2 flex-wrap align-items-center">' +
      (canJoin ? '<button id="join-btn" class="btn btn-success px-4"><i class="bi bi-person-plus-fill me-1"></i>Join Match Lobby</button>' : "") +
      (canLeave ? '<button id="leave-btn" class="btn btn-outline-secondary"><i class="bi bi-box-arrow-left me-1"></i>Leave Lobby</button>' : "") +
      (isParticipant ? '<span class="badge bg-success-subtle text-success border border-success-subtle p-2"><i class="bi bi-check-circle-fill me-1"></i>You are registered for this match</span>' : "") +
      '<a href="chat.html" class="btn btn-outline-primary ms-auto"><i class="bi bi-robot me-1"></i>Ask Coach for Tactics</a>' +
      '</div>' +
      '</div></div>' +

      '<div class="card stat-card mt-3 border-0 shadow-sm overflow-hidden">' +
      '<div class="card-header bg-white border-bottom p-3 d-flex justify-content-between align-items-center">' +
      '<h5 class="h6 card-title mb-0"><i class="bi bi-people me-2"></i>Registered Participants (' + l.players_joined + ')</h5>' +
      '<span class="badge bg-light text-muted border">' + l.team_size + ' vs ' + l.team_size + '</span>' +
      '</div>' +
      '<ul class="list-group list-group-flush">' + participantsHtml + '</ul>' +
      '</div>' +
      hostControls;

    // wire actions
    const joinBtn = document.getElementById("join-btn");
    if (joinBtn) joinBtn.addEventListener("click", () => action("join", "Joined lobby! 🎉"));
    const leaveBtn = document.getElementById("leave-btn");
    if (leaveBtn) leaveBtn.addEventListener("click", () => action("leave", "You left the lobby."));
    const startBtn = document.getElementById("start-btn");
    if (startBtn) startBtn.addEventListener("click", () => hostAction("start", "Match started!"));
    const teamsBtn = document.getElementById("teams-btn");
    if (teamsBtn) teamsBtn.addEventListener("click", generateTeams);
    const cancelBtn = document.getElementById("cancel-btn");
    if (cancelBtn) cancelBtn.addEventListener("click", () => hostAction("cancel", "Lobby cancelled."));
  }

  async function action(kind, successMsg) {
    const alertBox = document.getElementById("alert-box");
    showAlert(alertBox, "");
    const { ok, data } = await apiFetch("/api/lobbies/" + LOBBY_ID + "/" + kind, { method: "POST" });
    if (!ok) {
      showAlert(alertBox, data.error || "Action failed.", "danger");
      return;
    }
    showAlert(alertBox, successMsg, "success");
    await load();
  }

  async function generateTeams() {
    const alertBox = document.getElementById("alert-box");
    showAlert(alertBox, "");
    const { ok, data } = await apiFetch("/api/lobbies/" + LOBBY_ID + "/teams", { method: "POST" });
    if (!ok) {
      showAlert(alertBox, data.error || "Could not generate teams.", "danger");
      return;
    }
    const t = data.teams;
    showAlert(alertBox,
      "⚡ Teams successfully generated! Rating difference: " + t.rating_difference +
      " (Team A total: " + t.team_a_total + " | Team B total: " + t.team_b_total + ")", "success");
    await load();
  }

  async function hostAction(kind, successMsg) {
    const alertBox = document.getElementById("alert-box");
    showAlert(alertBox, "");
    if (kind === "cancel" && !confirm("Are you sure you want to cancel this match lobby?")) return;

    const { ok, data } = await apiFetch("/api/lobbies/" + LOBBY_ID + "/" + kind, { method: "POST" });
    if (!ok) {
      showAlert(alertBox, data.error || "Action failed.", "danger");
      return;
    }
    showAlert(alertBox, successMsg, "success");
    await load();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }
})();
