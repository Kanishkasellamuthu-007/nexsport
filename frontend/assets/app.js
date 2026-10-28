/* NexSport - prototype UI behaviour and presentation helpers. */
(function () {
  var KEY = "nexsport.auth.session";

  function session() {
    try { return sessionStorage.getItem(KEY) === "active"; } catch (e) { return false; }
  }

function syncAuthHeader() {
    var signedIn = session();
    document.body.classList.toggle("is-signed-in", signedIn);
    document.body.classList.toggle("is-signed-out", !signedIn);
    document.querySelectorAll(".signup-link").forEach(function (link) {
      link.hidden = signedIn;
      link.setAttribute("aria-hidden", signedIn ? "true" : "false");
      link.style.display = signedIn ? "none" : "";
    });

  }

  function toast(title, body) {
    var wrap = document.querySelector(".toast-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "toast-wrap";
      document.body.appendChild(wrap);
    }
    var el = document.createElement("div");
    el.className = "toast";
    el.setAttribute("role", "status");
    el.innerHTML = "<strong></strong><span></span>";
    el.querySelector("strong").textContent = title;
    el.querySelector("span").textContent = body || "";
    wrap.appendChild(el);
    setTimeout(function () { el.remove(); }, 4200);
  }
  window.nexToast = toast;

  function debounce(fn, wait) {
    var t;
    return function () {
      clearTimeout(t);
      t = setTimeout(fn, wait);
    };
  }

  function initMarquee() {
    var marquee = document.querySelector(".marquee");
    var track = document.querySelector(".marquee-track");
    if (!marquee || !track) return;

    function setDuration() {
      // The track duplicates its content, so half-width is one full cycle.
      var halfWidth = track.scrollWidth / 2;
      // Keep a steady, smooth speed (~70px/sec) with a sensible floor.
      var seconds = Math.max(halfWidth / 70, 12);
      marquee.style.setProperty("--marquee-duration", seconds.toFixed(2) + "s");
    }

    setDuration();
    window.addEventListener("resize", debounce(setDuration, 150));
  }

  function renderCourtResults() {
    var page = document.body.getAttribute("data-page");
    if (page !== "courts") return;
    var backend = window.NexBackend;
    if (!backend || typeof backend.loadCourts !== "function") return;
    backend.loadCourts().then(function (courts) {
      if (!Array.isArray(courts) || !courts.length) return;
      var section = document.querySelector('body[data-page="courts"] .grid.g-main section.card');
      if (!section) return;
      var rows = courts.slice(0, 6).map(function (court) {
        return '<article class="list-row"><div><strong>' + (court.name || 'Court') + '</strong><small>' + (court.sport || 'Sport') + ' · ' + (court.address || 'Location') + '</small></div><div class="meta"><span>★ ' + (court.rating != null ? Number(court.rating).toFixed(1) : '0.0') + '</span></div></article>';
      }).join("");
      section.innerHTML = '<div class="card-head"><div class="ico">◎</div><div><h3>Search results</h3><div class="hint">Live venue data</div></div></div><div class="stack list-compact">' + rows + '</div>';
    }).catch(function () {});
  }

  function renderLeaderboard() {
    var page = document.body.getAttribute("data-page");
    if (page !== "leaderboard") return;
    var backend = window.NexBackend;
    if (!backend || typeof backend.loadLeaderboard !== "function") return;
    backend.loadLeaderboard().then(function (rows) {
      if (!Array.isArray(rows) || !rows.length) return;
      var table = document.querySelector('body[data-page="leaderboard"] .table');
      var empty = document.querySelector('body[data-page="leaderboard"] .empty');
      if (!table) return;
      var body = rows.map(function (row, index) {
        var user = row.userId ? String(row.userId).slice(0, 8) : 'Athlete';
        var sport = row.sport || 'General';
        var played = row.played != null ? row.played : 0;
        var points = row.elo != null ? row.elo : 1000;
        return '<tr><td>' + (index + 1) + '</td><td>' + user + '</td><td>' + sport + '</td><td>' + played + '</td><td>' + points + '</td></tr>';
      }).join("");
      table.innerHTML = '<thead><tr><th>#</th><th>Athlete</th><th>Sport</th><th>Matches</th><th>Points</th></tr></thead><tbody>' + body + '</tbody>';
      if (empty) empty.style.display = 'none';
      var standing = document.querySelector('body[data-page="leaderboard"] .pfield .v');
      if (standing && rows[0]) {
        standing.textContent = '#1 overall';
        standing.classList.remove('is-empty');
      }
    }).catch(function () {});
  }

  function seedDashboardDemo() {
    var page = document.body.getAttribute("data-page");
    if (page !== "dashboard") return;

    var stats = {
      elo: document.querySelector('[data-flow="elo"]'),
      rankBand: document.querySelector('[data-flow="rank-band"]'),
      played: document.querySelector('[data-flow="played"]'),
      winrate: document.querySelector('[data-flow="winrate"]'),
      roomState: document.querySelector('[data-flow="room-state"]')
    };

    if (stats.elo) stats.elo.textContent = '\u2014';
    if (stats.rankBand) stats.rankBand.textContent = 'Unrated';
    if (stats.played) stats.played.textContent = '0';
    if (stats.winrate) stats.winrate.textContent = '\u2014';
    if (stats.roomState) stats.roomState.textContent = 'No open room';

    var flowHost = document.getElementByById('flow-pipeline');
    if (flowHost) flowHost.innerHTML = "";
  }

  function seedNotificationsDemo() {
    var page = document.body.getAttribute("data-page");
    if (page !== "notifications") return;

  }

  document.addEventListener("DOMContentLoaded", function () {
    var page = document.body.getAttribute("data-page");
    syncAuthHeader();
    renderCourtResults();
    renderLeaderboard();
    window.addEventListener("storage", function (event) {
      if (!event.key || event.key !== KEY) return;
      syncAuthHeader();
    });

    /* --- login page (real auth is attached by nexsport-integration.js) --- */
    var form = document.getElementById("login-form");
    if (form) {
      if (session()) { window.location.replace("dashboard.html"); return; }
      form.addEventListener("submit", function (e) {
        e.preventDefault();
      });
      ["email", "password"].forEach(function (name) {
        var f = form[name];
        if (!f) return;
        f.addEventListener("input", function () {
          f.removeAttribute("aria-invalid");
          var e3 = document.getElementById("login-error");
          if (e3) { e3.classList.remove("is-visible"); }
        });
      });
      initMarquee();
      return;
    }

    var forgotForm = document.getElementById("forgot-form");
    if (forgotForm) {
      forgotForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var field = forgotForm["email"];
        var email = (field && field.value ? field.value : "").trim().toLowerCase();
        var err = document.getElementById("forgot-error");
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
          if (err) { err.textContent = "Enter the email address you sign in with."; err.classList.add("is-visible"); }
          if (field) { field.setAttribute("aria-invalid", "true"); field.setAttribute("aria-describedby", "forgot-error"); field.focus(); }
          return;
        }
        if (err) { err.classList.remove("is-visible"); }
        if (field) { field.removeAttribute("aria-invalid"); }
        var out = document.getElementById("forgot-email");
        if (out) { out.textContent = email; }
        forgotForm.setAttribute("hidden", "");
        var ok = document.getElementById("forgot-success");
        if (ok) { ok.removeAttribute("hidden"); }
      });
      var retry = document.getElementById("forgot-retry");
      if (retry) {
        retry.addEventListener("click", function () {
          var ok = document.getElementById("forgot-success");
          if (ok) { ok.setAttribute("hidden", ""); }
          forgotForm.removeAttribute("hidden");
          forgotForm.reset();
          if (forgotForm["email"]) { forgotForm["email"].focus(); }
        });
      }
      forgotForm.addEventListener("input", function (e) {
        if (e.target) { e.target.removeAttribute("aria-invalid"); }
        var e2 = document.getElementById("forgot-error");
        if (e2) { e2.classList.remove("is-visible"); }
      });
      initMarquee();
      return;
    }

    /* --- shared nav a11y helpers --- */
    var SIDEBAR_ID = "app-sidebar";
    var sidebarEl = document.querySelector(".sidebar");
    if (sidebarEl && !sidebarEl.id) sidebarEl.id = SIDEBAR_ID;
    var isMobileNav = function () {
      return typeof window.matchMedia === "function" && window.matchMedia("(max-width: 900px)").matches;
    };
    var navStatus = function () {
      var live = document.getElementById("nav-status");
      if (!live) {
        live = document.createElement("div");
        live.id = "nav-status";
        live.className = "sr-only";
        live.setAttribute("role", "status");
        live.setAttribute("aria-live", "polite");
        document.body.appendChild(live);
      }
      return live;
    };
    /* Keep the off-screen sidebar out of the a11y tree and tab order. */
    var syncSidebarHidden = function () {
      if (!sidebarEl) return;
      var hidden = isMobileNav() && !document.body.classList.contains("nav-open");
      sidebarEl.setAttribute("aria-hidden", hidden ? "true" : "false");
      sidebarEl.inert = hidden;
      if (hidden) sidebarEl.setAttribute("tabindex", "-1");
      else sidebarEl.removeAttribute("tabindex");
    };

    /* --- mobile nav --- */
    var menu = document.getElementById("menu-btn");
    var syncMenuButton = function () {
      var open = document.body.classList.contains("nav-open");
      if (menu) {
        menu.setAttribute("aria-expanded", open ? "true" : "false");
        menu.setAttribute("aria-controls", SIDEBAR_ID);
        menu.setAttribute("aria-label", open ? "Close navigation menu" : "Open navigation menu");
      }
      syncSidebarHidden();
    };
    var closeDrawer = function (returnFocus) {
      if (!document.body.classList.contains("nav-open")) return;
      document.body.classList.remove("nav-open");
      syncMenuButton();
      if (returnFocus && menu) menu.focus();
    };
    if (menu) {
      menu.addEventListener("click", function () {
        var open = document.body.classList.toggle("nav-open");
        syncMenuButton();
        if (open) {
          var first = document.querySelector(".sidebar a, .sidebar button");
          if (first) first.focus();
        }
      });
      syncMenuButton();
    }
    var backdrop = document.querySelector(".backdrop");
    if (backdrop) {
      backdrop.addEventListener("click", function () { closeDrawer(true); });
    }
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDrawer(true);
    });

    /* --- sign out --- */
    var out = document.getElementById("sign-out");
    if (out) {
      out.addEventListener("click", function (e) {
        e.preventDefault();
        try { sessionStorage.removeItem(KEY); } catch (e2) {}
        window.location.href = "index.html";
      });
    }

  });
})();

/* Grouped nav dropdowns + account menu (standalone static build). */
(function () {
  function closeAll(except) {
    document.querySelectorAll('.nav-group').forEach(function (g) {
      if (g === except) return;
      g.classList.remove('is-open');
      var t = g.querySelector('.nav-trigger, .account-trigger');
      if (t) t.setAttribute('aria-expanded', 'false');
    });
  }
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('.nav-trigger, .account-trigger');
    if (t) {
      e.preventDefault();
      var g = t.closest('.nav-group');
      var open = g.classList.toggle('is-open');
      t.setAttribute('aria-expanded', open ? 'true' : 'false');
      closeAll(g);
      return;
    }
    if (!(e.target.closest && e.target.closest('.nav-menu'))) closeAll();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAll();
  });
})();

/* Sign-up password strength meter (standalone static build). */
(function () {
  var RULES = [
    ['len', function (v) { return v.length >= 8; }],
    ['upper', function (v) { return /[A-Z]/.test(v); }],
    ['lower', function (v) { return /[a-z]/.test(v); }],
    ['digit', function (v) { return /\d/.test(v); }],
    ['symbol', function (v) { return /[^A-Za-z0-9]/.test(v); }]
  ];
  var VERDICTS = ['start typing', 'weak', 'fair', 'good', 'strong'];
  function paint(value) {
    var wrap = document.getElementById('pw-strength');
    if (!wrap) return;
    var met = 0;
    RULES.forEach(function (r) {
      var ok = r[1](value);
      if (ok) met++;
      var li = wrap.querySelector('li[data-rule="' + r[0] + '"]');
      if (!li) return;
      li.classList.toggle('is-met', ok);
      var tick = li.querySelector('.pw-tick');
      if (tick) tick.textContent = ok ? '\u25cf' : '\u25cb';
    });
    var score = 0;
    if (value) {
      score = Math.min(4, Math.max(1, met - 1));
      if (met === 5 && value.length >= 12) score = 4;
    }
    wrap.setAttribute('data-score', String(score));
    var v = document.getElementById('pw-verdict');
    if (v) v.textContent = 'Password strength: ' + VERDICTS[value ? score : 0];
  }
  document.addEventListener('input', function (e) {
    var t = e.target;
    if (!t || t.name !== 'password' || !t.closest('#register-form')) return;
    paint(t.value);
  });
  if (document.getElementById('pw-strength')) paint('');
})();
