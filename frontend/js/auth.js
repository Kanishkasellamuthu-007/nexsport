/*
 * Auth helpers shared by all pages.
 *
 * - requireAuth(): redirects to index.html when no valid session (protected pages).
 * - getToken(): access token for Flask API calls.
 * - apiFetch(): fetch wrapper adding Authorization: Bearer <token>;
 *   on 401 it signs the user out locally and redirects to sign-in.
 * - friendlyAuthError(): maps Supabase error codes to human messages.
 */
const AUTH_REDIRECT_PATHS = {
  login: "index.html",
  dashboard: "dashboard.html",
};

const AUTH_PROTECTED_PAGES = new Set([
  "create-room.html",
  "dashboard.html",
  "find-match.html",
  "lobby.html",
  "room.html",
  "matches.html",
  "profile.html",
  "assessment.html",
  "performance.html",
  "leaderboard.html",
  "courts.html",
  "players.html",
  "settings.html",
  "notifications.html",
  "verify.html",
]);

function getSafeAuthRedirect(target) {
  if (!target) return null;
  const parsed = new URL(target, location.origin);
  if (parsed.origin !== location.origin) return null;
  const filename = parsed.pathname.split("/").pop();
  return AUTH_PROTECTED_PAGES.has(filename)
    ? filename + parsed.search + parsed.hash
    : null;
}

async function getSession() {
  if (typeof supabaseClient !== "undefined" && supabaseClient.auth) {
    const { data, error } = await supabaseClient.auth.getSession().catch(() => ({ data: {} }));
    if (!error && data && data.session) return data.session;
  }
  const demoToken = localStorage.getItem("nexsport_demo_token");
  if (demoToken) {
    return {
      access_token: demoToken,
      user: {
        id: "usr_demo_kanishka_77",
        email: localStorage.getItem("nexsport_demo_email") || "kanishkasellamuthu.ss3@gmail.com",
        user_metadata: {
          full_name: localStorage.getItem("nexsport_demo_name") || "Kanishka Sellamuthu"
        }
      }
    };
  }
  return null;
}

async function getUser() {
  const session = await getSession();
  return session ? session.user : null;
}

/** Guard for protected pages. Returns the session or redirects to login. */
async function requireAuth() {
  const session = await getSession();
  if (session) return session;
  // Check for demo token
  const demoToken = localStorage.getItem("nexsport_demo_token");
  if (demoToken) {
    return {
      access_token: demoToken,
      user: {
        id: "usr_demo_kanishka_77",
        email: localStorage.getItem("nexsport_demo_email") || "demo@nexsport.app",
      },
    };
  }
  window.location.replace(AUTH_REDIRECT_PATHS.login + "?redirect=" +
    encodeURIComponent(location.pathname.split("/").pop() + location.search + location.hash));
  return null;
}

/** Access token for calling Flask endpoints. */
async function getToken() {
  const session = await getSession();
  if (session) return session.access_token;
  // Fallback: demo token from localStorage
  return localStorage.getItem("nexsport_demo_token");
}

/** Fetch wrapper for protected API endpoints with expired-session handling. */
async function apiFetch(path, options = {}) {
  const token = await getToken();
  const headers = Object.assign(
    { "Content-Type": "application/json" },
    options.headers || {}
  );
  if (token) headers["Authorization"] = "Bearer " + token;

  const res = await fetch(CONFIG.API_BASE_URL + path, { ...options, headers });

  if (res.status === 401) {
    // Only redirect if not a demo session
    var demoToken = localStorage.getItem("nexsport_demo_token");
    if (!demoToken) {
      // Expired/invalid session -> clean local state and re-authenticate.
      await supabaseClient.auth.signOut();
      window.location.replace(AUTH_REDIRECT_PATHS.login + "?expired=1");
      throw new Error("Session expired");
    }
  }
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

/** Human-readable error messages for common Supabase auth failures. */
function friendlyAuthError(error) {
  const msg = (error && (error.message || error.error_description)) || "Something went wrong";
  const map = [
    [/unsupported provider/i, "Google sign-in is not enabled in Supabase. Enable the Google provider and save its OAuth client settings."],
    [/invalid login credentials/i, "Incorrect email or password."],
    [/email not confirmed/i, "Please confirm your email before signing in."],
    [/user already registered/i, "An account with this email already exists. Try signing in."],
    [/password.*at least/i, "Password is too weak — use at least 6 characters."],
    [/rate limit/i, "Too many attempts. Please wait a minute and try again."],
    [/signups not allowed/i, "Sign-ups are currently disabled for this project."],
    [/failed to fetch/i, "Cannot reach the server. Check your internet connection."],
  ];
  for (const [re, friendly] of map) {
    if (re.test(msg)) return friendly;
  }
  return msg;
}

/** Small loading-spinner helper: toggles a button into its loading state. */
function setButtonLoading(btn, isLoading, loadingText = "Please wait…") {
  if (!btn) return;
  if (isLoading) {
    btn.dataset.originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML =
      '<span class="spinner-border spinner-border-sm me-2"></span>' + loadingText;
  } else {
    btn.disabled = false;
    btn.innerHTML = btn.dataset.originalHtml || btn.innerHTML;
  }
}

/** Bootstrap alert helper inside a container element. */
function showAlert(container, message, type = "danger") {
  if (!container) return;
  container.innerHTML =
    '<div class="alert alert-' + type + ' alert-dismissible fade show" role="alert">' +
    message +
    '<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>';
}

/** Navbar rendering based on auth state (used on every page). */
async function renderAuthNav() {
  const user = await getUser();
  const loginNav = document.getElementById("nav-login");
  const userNav = document.getElementById("nav-user");
  if (!loginNav || !userNav) return;

  if (user) {
    loginNav.classList.add("d-none");
    userNav.classList.remove("d-none");
  } else {
    loginNav.classList.remove("d-none");
    userNav.classList.add("d-none");
  }
}
