/*
 * Dashboard page (PROTECTED — redirects to login if no session).
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", async function () {
    const session = await requireAuth();
    if (!session) return; // redirected

    const user = session.user;
    const emailBadge = document.getElementById("user-email-badge");
    if (emailBadge) emailBadge.textContent = user.email;

    renderAuthNav();

    // Logout
    const logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", async function (e) {
        e.preventDefault();
        await supabaseClient.auth.signOut();
        window.location.replace("index.html");
      });
    }

    // Load profile via protected Flask endpoint
    try {
      const { ok, data } = await apiFetch("/api/auth/me");
      if (ok && data.profile) {
        const p = data.profile;
        const displayName = p.full_name || p.username || user.email.split("@")[0];
        
        const playerNameEl = document.getElementById("dashboard-player-name");
        if (playerNameEl) playerNameEl.textContent = displayName;

        const locationSubEl = document.getElementById("dashboard-location-sub");
        if (locationSubEl) {
          locationSubEl.innerHTML = '<i class="bi bi-geo-alt"></i> ' + escapeHtml(p.city || "Public grounds") + " · Athlete";
        }

        const avatarEl = document.getElementById("dashboard-avatar");
        if (avatarEl) {
          const initials = displayName.split(" ").map(w => w[0]).join("").toUpperCase().slice(0, 2);
          avatarEl.textContent = initials || "⚽";
        }

        const summaryEl = document.getElementById("profile-summary");
        if (summaryEl) {
          summaryEl.innerHTML =
            '<div class="fw-bold text-dark mb-1">' + escapeHtml(displayName) + '</div>' +
            '<div class="text-muted small"><i class="bi bi-geo-alt me-1"></i>' + escapeHtml(p.city || "City not set") + '</div>' +
            (p.bio ? '<p class="text-secondary small mt-1 mb-0 text-truncate" style="max-width: 220px;">' + escapeHtml(p.bio) + '</p>' : '');
        }
      } else if (ok) {
        const summaryEl = document.getElementById("profile-summary");
        if (summaryEl) {
          summaryEl.textContent = "Profile setup pending — click below.";
        }
      }
    } catch (e) {
      console.warn("Could not load user profile:", e);
    }

    // Load user ratings from /api/ratings/me
    try {
      const { ok: rOk, data: rData } = await apiFetch("/api/ratings/me");
      const ratingNumber = document.getElementById("rating-number");
      const ratingSportName = document.getElementById("rating-sport-name");
      const ratingSubtext = document.getElementById("rating-subtext");
      const ratingActionBtn = document.getElementById("rating-action-btn");

      if (rOk && rData.ratings && rData.ratings.length > 0) {
        const primary = rData.ratings[0];
        const sportName = primary.sports ? (primary.sports.icon + " " + primary.sports.name) : "Sport";
        if (ratingNumber) ratingNumber.textContent = primary.current_rating;
        if (ratingSportName) ratingSportName.textContent = sportName;
        if (ratingSubtext) {
          ratingSubtext.innerHTML = `<strong>${primary.matches_count}</strong> match(es) played · Peak: ${primary.peak_rating || primary.current_rating}`;
        }
        if (ratingActionBtn) {
          ratingActionBtn.innerHTML = '<i class="bi bi-arrow-repeat"></i> Update Questionnaire';
        }
      } else {
        if (ratingNumber) ratingNumber.textContent = "1200";
        if (ratingSportName) ratingSportName.textContent = "Baseline";
        if (ratingSubtext) {
          ratingSubtext.textContent = "Take the 2-minute skill test to get your official rating.";
        }
      }
    } catch (e) {
      console.warn("Could not load user ratings:", e);
    }

    // Diagnostics verification button
    const verifyBtn = document.getElementById("verify-btn");
    if (verifyBtn) {
      verifyBtn.addEventListener("click", async function () {
        const pre = document.getElementById("verify-result");
        pre.classList.remove("d-none");
        pre.textContent = "Calling /api/auth/me …";
        const result = await apiFetch("/api/auth/me");
        pre.textContent = JSON.stringify(result.data, null, 2);
      });
    }
  });

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }
})();
