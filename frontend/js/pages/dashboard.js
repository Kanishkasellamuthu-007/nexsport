/*
 * Dashboard page (PROTECTED — redirects to login if no session).
 *
 * Loads profile, ratings, and stats. Falls back to demo/mock data
 * when the backend or Supabase is unavailable.
 */
(function () {
  "use strict";

  /* ── Demo fallback data ────────────────────────────────────── */
  var DEMO_PROFILE = {
    full_name: "Kanishka Sellamuthu",
    username: "kanishka",
    city: "Chennai",
    bio: "Weekend football striker & cricket all-rounder. Ready for pickup matches!",
  };

  var DEMO_RATINGS = [
    { current_rating: 1347, peak_rating: 1410, matches_count: 24, sports: { name: "Football", icon: "⚽" } },
    { current_rating: 1280, peak_rating: 1305, matches_count: 11, sports: { name: "Cricket", icon: "🏏" } },
    { current_rating: 1190, peak_rating: 1220, matches_count: 6,  sports: { name: "Basketball", icon: "🏀" } },
  ];

  var DEMO_STATS = { played: 41, wins: 26, winRate: "63%", rankBand: "Silver II" };

  document.addEventListener("DOMContentLoaded", async function () {
    /* ── Auth check ──────────────────────────────────────────── */
    var session = await getSession();
    var demoMode = false;

    // Check for demo token in localStorage
    var demoToken = localStorage.getItem("nexsport_demo_token");

    if (!session && !demoToken) {
      window.location.replace(
        AUTH_REDIRECT_PATHS.login +
          "?redirect=" +
          encodeURIComponent(
            location.pathname.split("/").pop() + location.search + location.hash
          )
      );
      return;
    }

    if (demoToken) {
      demoMode = true;
    }

    var userEmail = session
      ? session.user.email
      : localStorage.getItem("nexsport_demo_email") || "demo@nexsport.app";

    renderAuthNav();

    // Sign-out handler
    var signOut = document.getElementById("sign-out");
    if (signOut) {
      signOut.addEventListener("click", async function (e) {
        e.preventDefault();
        localStorage.removeItem("nexsport_demo_token");
        localStorage.removeItem("nexsport_demo_email");
        await supabaseClient.auth.signOut();
        window.location.replace("index.html");
      });
    }

    /* ── Load profile ────────────────────────────────────────── */
    var profile = DEMO_PROFILE;
    try {
      var headers = {};
      if (demoMode) {
        headers["Authorization"] = "Bearer " + demoToken;
      }
      var opts = demoMode ? { headers: headers } : {};
      var res = demoMode
        ? await fetch(
            (typeof CONFIG !== "undefined" ? CONFIG.API_BASE_URL : "") + "/api/auth/me",
            { headers: { "Content-Type": "application/json", Authorization: "Bearer " + demoToken } }
          ).then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, data: d }; });
          })
        : await apiFetch("/api/auth/me");

      if (res.ok && res.data.profile) {
        profile = res.data.profile;
      }
    } catch (e) {
      console.warn("Profile load failed, using demo data:", e);
    }

    // Populate profile elements
    var displayName = profile.full_name || profile.username || userEmail.split("@")[0];

    var playerNameEl = document.getElementById("dashboard-player-name");
    if (playerNameEl) playerNameEl.textContent = displayName;

    var locationSubEl = document.getElementById("dashboard-location-sub");
    if (locationSubEl) {
      locationSubEl.innerHTML = "📍 " + escapeHtml(profile.city || "Public grounds") + " · Athlete";
    }

    var avatarEl = document.getElementById("dashboard-avatar");
    if (avatarEl) {
      var initials = displayName.split(" ").map(function (w) { return w[0]; }).join("").toUpperCase().slice(0, 2);
      avatarEl.textContent = initials || "⚽";
    }

    // Sidebar account name
    var accountBtn = document.getElementById("account-btn");
    if (accountBtn) {
      var whoEl = accountBtn.querySelector(".who strong");
      if (whoEl) whoEl.textContent = displayName;
      var avSmall = accountBtn.querySelector(".avatar");
      if (avSmall) {
        var init2 = displayName.split(" ").map(function (w) { return w[0]; }).join("").toUpperCase().slice(0, 2);
        avSmall.textContent = init2;
      }
    }

    /* ── Load ratings ────────────────────────────────────────── */
    var ratings = DEMO_RATINGS;
    var stats = DEMO_STATS;
    try {
      var rRes = demoMode
        ? await fetch(
            (typeof CONFIG !== "undefined" ? CONFIG.API_BASE_URL : "") + "/api/ratings/me",
            { headers: { "Content-Type": "application/json", Authorization: "Bearer " + demoToken } }
          ).then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, data: d }; });
          })
        : await apiFetch("/api/ratings/me");

      if (rRes.ok && rRes.data.ratings && rRes.data.ratings.length > 0) {
        ratings = rRes.data.ratings;
        var totalPlayed = 0;
        ratings.forEach(function (r) { totalPlayed += r.matches_count || 0; });
        stats = {
          played: totalPlayed,
          wins: Math.round(totalPlayed * 0.63),
          winRate: "63%",
          rankBand: ratings[0].current_rating >= 1300 ? "Silver II" : "Bronze I",
        };
      }
    } catch (e) {
      console.warn("Ratings load failed, using demo data:", e);
    }

    // Populate stat cards
    var eloEl = document.querySelector('[data-flow="elo"]');
    if (eloEl) eloEl.textContent = ratings[0].current_rating;

    var rankEl = document.querySelector('[data-flow="rank-band"]');
    if (rankEl) rankEl.textContent = stats.rankBand;

    var playedEl = document.querySelector('[data-flow="played"]');
    if (playedEl) playedEl.textContent = stats.played;

    var winrateEl = document.querySelector('[data-flow="winrate"]');
    if (winrateEl) winrateEl.textContent = stats.winRate;

    // Workflow section
    var assessEl = document.querySelector('[data-flow="assessment-state"]');
    if (assessEl) assessEl.textContent = "Completed";

    var seedEloEl = document.querySelector('[data-flow="seed-elo"]');
    if (seedEloEl) seedEloEl.textContent = ratings[0].current_rating + " (" + ratings[0].sports.icon + " " + ratings[0].sports.name + ")";

    var verifyEl = document.querySelector('[data-flow="verify-state"]');
    if (verifyEl) verifyEl.textContent = "Verified ✓";

    /* ── Populate AI match suggestions (demo) ────────────────── */
    var suggestionsCard = document.querySelector('.card .empty .glyph');
    if (suggestionsCard && suggestionsCard.textContent.trim() === "✦") {
      var emptyDiv = suggestionsCard.parentElement;
      emptyDiv.className = "";
      emptyDiv.innerHTML =
        '<div style="padding:4px 0">' +
          suggestionItem("Arun K.", "Football", "⚽", 1320, "2.1 km", "#2563EB") +
          suggestionItem("Priya R.", "Tennis", "🎾", 1185, "3.4 km", "#16A34A") +
          suggestionItem("Vikram S.", "Cricket", "🏏", 1290, "1.8 km", "#EAB308") +
        "</div>" +
        '<div style="padding:12px 16px;text-align:center">' +
          '<a class="btn btn-ghost btn-sm" href="find-match.html">View all suggestions →</a>' +
        "</div>";
    }

    /* ── Populate upcoming schedule (demo) ────────────────────── */
    var schedGlyph = document.querySelectorAll('.card .empty .glyph');
    schedGlyph.forEach(function (g) {
      if (g.textContent.trim() === "◳") {
        var emptyDiv = g.parentElement;
        emptyDiv.className = "";
        emptyDiv.innerHTML =
          '<div style="padding:4px 0">' +
            scheduleItem("Football 5v5", "Chennai Sports Arena", "Today, 6:00 PM", "4/10 joined") +
            scheduleItem("Cricket Practice", "ECR Cricket Ground", "Tomorrow, 8:00 AM", "7/12 joined") +
          "</div>";
      }
    });

    /* ── Populate recent activity (demo) ──────────────────────── */
    var actGlyph = document.querySelectorAll('.card .empty .glyph');
    actGlyph.forEach(function (g) {
      if (g.textContent.trim() === "◉") {
        var emptyDiv = g.parentElement;
        emptyDiv.className = "";
        emptyDiv.innerHTML =
          '<div style="padding:4px 0">' +
            activityItem("⚽ Won", "Football 5v5 at Marina Beach · +17 Elo", "2 hours ago") +
            activityItem("🏏 Draw", "Cricket T10 at ECR Ground · +3 Elo", "Yesterday") +
            activityItem("🏀 Lost", "Basketball 3v3 at Egmore Stadium · -12 Elo", "2 days ago") +
            activityItem("📋 Joined", "Lobby: Evening Football at Besant Nagar", "3 days ago") +
          "</div>";
      }
    });

    /* ── Second row stat cards ────────────────────────────────── */
    var statCards = document.querySelectorAll(".grid.g4 .card.stat");
    if (statCards.length >= 8) {
      // Second set of 4 stat cards (index 4-7)
      statCards[4].querySelector(".v").textContent = stats.played;
      statCards[4].querySelector(".n").textContent = "Across " + ratings.length + " sports";
      statCards[5].querySelector(".v").textContent = stats.winRate;
      statCards[5].querySelector(".n").textContent = stats.wins + " wins out of " + stats.played;
      statCards[6].querySelector(".v").textContent = "78";
      statCards[6].querySelector(".n").textContent = "Based on recent 10 matches";
      statCards[7].querySelector(".v").textContent = stats.rankBand;
      statCards[7].querySelector(".n").textContent = "Top 35% in your region";
    }

    /* ── Performance chart placeholder → mini chart ──────────── */
    var perfPlaceholder = document.querySelector(".placeholder");
    if (perfPlaceholder) {
      perfPlaceholder.innerHTML =
        '<div style="padding:16px">' +
          '<div style="font-size:13px;color:var(--text-2);margin-bottom:12px">Elo trend — last 7 sessions</div>' +
          miniBarChart([1290, 1310, 1295, 1330, 1310, 1347, 1347]) +
        "</div>";
    }

    // Diagnostics verify button
    var verifyBtn = document.getElementById("verify-btn");
    if (verifyBtn) {
      verifyBtn.addEventListener("click", async function () {
        var pre = document.getElementById("verify-result");
        pre.classList.remove("d-none");
        pre.textContent = "Calling /api/auth/me …";
        var result = demoMode
          ? await fetch(
              (typeof CONFIG !== "undefined" ? CONFIG.API_BASE_URL : "") + "/api/auth/me",
              { headers: { "Content-Type": "application/json", Authorization: "Bearer " + demoToken } }
            ).then(function (r) { return r.json(); })
          : (await apiFetch("/api/auth/me")).data;
        pre.textContent = JSON.stringify(result, null, 2);
      });
    }
  });

  /* ── Helper: suggestion item ───────────────────────────────── */
  function suggestionItem(name, sport, icon, elo, dist, color) {
    return (
      '<div style="display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--border)">' +
        '<div style="width:36px;height:36px;border-radius:50%;background:' + color + '15;display:flex;align-items:center;justify-content:center;font-size:18px">' + icon + '</div>' +
        '<div style="flex:1">' +
          '<div style="font-weight:600;font-size:14px;color:var(--text)">' + name + '</div>' +
          '<div style="font-size:12px;color:var(--text-2)">' + sport + ' · ' + elo + ' Elo · ' + dist + '</div>' +
        '</div>' +
        '<a class="btn btn-ghost btn-sm" href="find-match.html" style="font-size:12px">Challenge</a>' +
      '</div>'
    );
  }

  /* ── Helper: schedule item ─────────────────────────────────── */
  function scheduleItem(title, venue, time, status) {
    return (
      '<div style="display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--border)">' +
        '<div style="flex:1">' +
          '<div style="font-weight:600;font-size:14px;color:var(--text)">' + title + '</div>' +
          '<div style="font-size:12px;color:var(--text-2)">' + venue + ' · ' + time + '</div>' +
        '</div>' +
        '<span style="font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;background:var(--blue-soft);color:var(--blue)">' + status + '</span>' +
      '</div>'
    );
  }

  /* ── Helper: activity item ─────────────────────────────────── */
  function activityItem(label, detail, timeAgo) {
    return (
      '<div style="display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--border)">' +
        '<div style="flex:1">' +
          '<div style="font-weight:600;font-size:13px;color:var(--text)">' + label + '</div>' +
          '<div style="font-size:12px;color:var(--text-2)">' + detail + '</div>' +
        '</div>' +
        '<span style="font-size:11px;color:var(--text-2);white-space:nowrap">' + timeAgo + '</span>' +
      '</div>'
    );
  }

  /* ── Helper: mini bar chart (CSS only) ─────────────────────── */
  function miniBarChart(values) {
    var max = Math.max.apply(null, values);
    var min = Math.min.apply(null, values) - 30;
    var bars = "";
    values.forEach(function (v, i) {
      var h = Math.max(12, ((v - min) / (max - min)) * 80);
      var color = i === values.length - 1 ? "var(--blue)" : "var(--border)";
      bars +=
        '<div style="display:flex;flex-direction:column;align-items:center;gap:4px;flex:1">' +
          '<div style="width:100%;max-width:28px;height:' + h + 'px;background:' + color + ';border-radius:4px 4px 0 0"></div>' +
          '<span style="font-size:10px;color:var(--text-2)">' + v + '</span>' +
        '</div>';
    });
    return '<div style="display:flex;align-items:end;gap:4px;height:110px">' + bars + '</div>';
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
})();
