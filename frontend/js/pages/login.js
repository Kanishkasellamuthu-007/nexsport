/*
 * Login page logic.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("login-form");
    const alertBox = document.getElementById("alert-box");
    const loginBtn = document.getElementById("login-btn");
    const googleBtn = document.getElementById("google-btn");

    // Show "session expired" notice when redirected by apiFetch()
    if (new URLSearchParams(location.search).get("expired") === "1") {
      document.getElementById("expired-note").classList.remove("d-none");
    }

    // Already signed in? Go straight to the dashboard.
    supabaseClient.auth.getSession().then(({ data }) => {
      if (data.session) window.location.replace("dashboard.html");
    });

    // ---- Field-level validation ----
    function validate() {
      let ok = true;
      const email = document.getElementById("email");
      const password = document.getElementById("password");
      const emailErr = document.querySelector('[data-error-for="email"]');
      const passErr = document.querySelector('[data-error-for="password"]');
      emailErr.textContent = "";
      passErr.textContent = "";

      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
        emailErr.textContent = "Enter a valid email address.";
        ok = false;
      }
      if (password.value.length < 6) {
        passErr.textContent = "Password must be at least 6 characters.";
        ok = false;
      }
      return ok;
    }

    // ---- Email/password sign-in ----
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      showAlert(alertBox, ""); // clear
      if (!validate()) return;

      setButtonLoading(loginBtn, true, "Signing in…");
      const { error } = await supabaseClient.auth.signInWithPassword({
        email: document.getElementById("email").value.trim(),
        password: document.getElementById("password").value,
      });
      setButtonLoading(loginBtn, false);

      if (error) {
        showAlert(alertBox, friendlyAuthError(error), "danger");
        return;
      }
      window.location.replace("dashboard.html");
    });

    // ---- Google OAuth ----
    googleBtn.addEventListener("click", async function () {
      setButtonLoading(googleBtn, true, "Redirecting…");
      const { error } = await supabaseClient.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: location.origin + location.pathname.replace("login.html", "") + "oauth-callback.html",
        },
      });
      if (error) {
        setButtonLoading(googleBtn, false);
        showAlert(alertBox, friendlyAuthError(error), "danger");
      }
    });
  });
})();
