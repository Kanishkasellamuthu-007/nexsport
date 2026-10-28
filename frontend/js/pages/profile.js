/*
 * Profile page (PROTECTED).
 * Profile edits go through the user's own Supabase session (RLS: users may
 * update only their own row). The user id is resolved server-side/DB-side —
 * the browser never sends one.
 */
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

    const alertBox = document.getElementById("alert-box");
    const saveBtn = document.getElementById("save-btn");
    const form = document.getElementById("profile-form");

    // Load current profile through the protected API (token-verified).
    const { ok, data } = await apiFetch("/api/auth/me");
    if (ok && data.profile) {
      const p = data.profile;
      document.getElementById("username").value = p.username || "";
      document.getElementById("full_name").value = p.full_name || "";
      document.getElementById("city").value = p.city || "";
      document.getElementById("bio").value = p.bio || "";
    }

    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      showAlert(alertBox, "");

      const username = document.getElementById("username").value.trim();
      if (username.length < 3 || username.length > 30) {
        showAlert(alertBox, "Username must be 3–30 characters.", "warning");
        return;
      }

      setButtonLoading(saveBtn, true, "Saving…");
      const token = await getToken();
      const res = await fetch(CONFIG.API_BASE_URL + "/api/auth/profile", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + token,
        },
        body: JSON.stringify({
          username: username,
          full_name: document.getElementById("full_name").value.trim(),
          city: document.getElementById("city").value.trim(),
          bio: document.getElementById("bio").value.trim(),
        }),
      });
      const body = await res.json().catch(() => ({}));
      setButtonLoading(saveBtn, false);

      if (res.ok) {
        showAlert(alertBox, "Profile saved!", "success");
      } else {
        showAlert(alertBox, body.error || "Could not save profile.", "danger");
      }
    });
  });
})();
