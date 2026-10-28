/*
 * Registration page logic.
 *
 * Sign-up happens directly between the browser and Supabase Auth — Flask
 * never touches the password. After signup we create/complete the profile.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("register-form");
    const alertBox = document.getElementById("alert-box");
    const registerBtn = document.getElementById("register-btn");
    const googleBtn = document.getElementById("google-btn");

    function setFieldError(id, message) {
      const el = document.querySelector('[data-error-for="' + id + '"]');
      if (el) el.textContent = message || "";
    }

    function validate() {
      let ok = true;
      const name = document.getElementById("full_name");
      const email = document.getElementById("email");
      const password = document.getElementById("password");
      const confirm = document.getElementById("confirm_password");

      ["full_name", "email", "password", "confirm_password"].forEach((f) => setFieldError(f, ""));

      if (name.value.trim().length < 2) {
        setFieldError("full_name", "Display name must be at least 2 characters.");
        ok = false;
      }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
        setFieldError("email", "Enter a valid email address.");
        ok = false;
      }
      if (password.value.length < 6) {
        setFieldError("password", "Password must be at least 6 characters.");
        ok = false;
      }
      if (password.value !== confirm.value) {
        setFieldError("confirm_password", "Passwords do not match.");
        ok = false;
      }
      return ok;
    }

    async function afterSignup(userId, fullName) {
      // Create the profile row through the Flask backend (service role).
      // The backend derives the user id from the verified token — the browser
      // never declares "who am I".
      const { ok, data } = await apiFetch("/api/auth/profile", {
        method: "POST",
        body: JSON.stringify({ full_name: fullName }),
      });
      if (!ok) console.warn("Profile creation deferred:", data && data.error);
      window.location.replace("dashboard.html");
    }

    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      showAlert(alertBox, "");
      if (!validate()) return;

      const fullName = document.getElementById("full_name").value.trim();
      const email = document.getElementById("email").value.trim();
      const password = document.getElementById("password").value;

      setButtonLoading(registerBtn, true, "Creating account…");
      const { data, error } = await supabaseClient.auth.signUp({
        email: email,
        password: password,
        options: { data: { full_name: fullName } },
      });
      setButtonLoading(registerBtn, false);

      if (error) {
        showAlert(alertBox, friendlyAuthError(error), "danger");
        return;
      }

      // Email confirmation case: no session yet.
      if (data.session) {
        await afterSignup(data.user.id, fullName);
      } else {
        showAlert(
          alertBox,
          "Account created! Check your inbox for a confirmation email, then sign in.",
          "success"
        );
      }
    });

    googleBtn.addEventListener("click", async function () {
      setButtonLoading(googleBtn, true, "Redirecting…");
      const { error } = await supabaseClient.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: location.origin + location.pathname.replace("register.html", "") + "oauth-callback.html",
        },
      });
      if (error) {
        setButtonLoading(googleBtn, false);
        showAlert(alertBox, friendlyAuthError(error), "danger");
      }
    });
  });
})();
