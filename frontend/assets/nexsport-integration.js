/* NexSport prototype UI connected to live Supabase Auth and Flask APIs. */
(function () {
  "use strict";
  document.body.dataset.featureIntegration = "ready";

  var AUTH_SESSION_KEY = "nexsport.auth.session";
  var page = document.body.getAttribute("data-page");
  var lastSkillDataError = "";
  var skillRefreshInFlight = false;
  var protectedPages = new Set([
    "dashboard", "find-match", "create-room", "room", "matches",
    "courts", "players", "performance", "leaderboard", "assessment",
    "verify", "profile", "settings", "notifications"
  ]);

  function errorMessage(error, fallback) {
    if (typeof friendlyAuthError === "function") {
      return friendlyAuthError(error);
    }
    return (error && error.message) || fallback;
  }

  function showError(id, message) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = message || "";
    el.classList.toggle("is-visible", Boolean(message));
  }

  function setBusy(button, busy, label) {
    if (!button) return;
    if (busy) {
      button.dataset.originalText = button.textContent;
      button.disabled = true;
      button.textContent = label;
    } else {
      button.disabled = false;
      button.textContent = button.dataset.originalText || button.textContent;
    }
  }

  async function apiFetch(path, options) {
    var isFormData = options && options.body instanceof FormData;
    var session = await getSession();
    var headers = Object.assign(
      { "Content-Type": "application/json" },
      (options && options.headers) || {}
    );
    if (isFormData) delete headers["Content-Type"];
    if (session) headers.Authorization = "Bearer " + session.access_token;
    var response = await fetch(CONFIG.API_BASE_URL + path, Object.assign({}, options || {}, { headers: headers }));
    var data = await response.json().catch(function () { return {}; });
    return { ok: response.ok, status: response.status, data: data };
  }

  function markSignedIn(session) {
    sessionStorage.setItem(AUTH_SESSION_KEY, "active");
    document.body.classList.add("is-signed-in");
    document.body.classList.remove("is-signed-out");
    var user = session && session.user;
    var identity = user && (user.user_metadata || {});
    var name = identity.full_name || identity.name || (user && user.email ? user.email.split("@")[0] : "Athlete");
    var email = user && user.email || "";
    var initials = name.trim().split(/\s+/).map(function (word) { return word[0] || ""; }).join("").slice(0, 2).toUpperCase();
    document.querySelectorAll(".account-trigger .who").forEach(function (who) {
      var strong = who.querySelector("strong");
      if (strong) strong.textContent = name;
      who.childNodes.forEach(function (node) {
        if (node.nodeType === 3) node.textContent = node === who.lastChild ? email : node.textContent;
      });
    });
    document.querySelectorAll(".account-trigger .avatar, .topbar .avatar").forEach(function (avatar) {
      avatar.textContent = initials;
    });
  }

  function redirectToLogin() {
    var target = encodeURIComponent(location.pathname.split("/").pop() + location.search + location.hash);
    location.replace("index.html?redirect=" + target);
  }

  async function initAuth() {
    var session = await getSession();
    document.body.classList.toggle("is-signed-out", !session);
    if (protectedPages.has(page) && !session) {
      redirectToLogin();
      return null;
    }
    if (session) markSignedIn(session);
    if ((page === "login" || page === "register") && session) {
      var redirect = getSafeAuthRedirect(new URLSearchParams(location.search).get("redirect"));
      location.replace(redirect || "dashboard.html");
      return session;
    }
    return session;
  }

  document.addEventListener("submit", function (event) {
    if (event.target.id === "login-form") {
      event.preventDefault();
      event.stopImmediatePropagation();
      submitLogin(event.target);
    } else if (event.target.id === "register-form") {
      event.preventDefault();
      event.stopImmediatePropagation();
      submitRegister(event.target);
    } else if (event.target.id === "room-form") {
      event.preventDefault();
      event.stopImmediatePropagation();
      submitRoom(event.target);
    } else if (event.target.id === "assessment-form") {
      event.preventDefault();
      event.stopImmediatePropagation();
      submitAssessment(event.target);
    } else if (event.target.id === "verify-form") {
      event.preventDefault();
      event.stopImmediatePropagation();
      submitVerification(event.target);
    } else if (event.target.id === "profile-form" || event.target.id === "settings-form") {
      event.preventDefault();
      event.stopImmediatePropagation();
      submitProfile(event.target);
    } else if (event.target.id === "forgot-form") {
      event.preventDefault();
      event.stopImmediatePropagation();
      submitForgotPassword(event.target);
    }
  }, true);

  document.addEventListener("click", function (event) {
    var target = event.target.closest && event.target.closest("#sign-out");
    if (!target) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    supabaseClient.auth.signOut().finally(function () {
      sessionStorage.removeItem(AUTH_SESSION_KEY);
      location.replace("index.html");
    });
  }, true);

  async function submitLogin(form) {
    showError("login-error", "");
    var email = form.elements.email.value.trim();
    var password = form.elements.password.value;
    var button = form.querySelector('[type="submit"]');
    setBusy(button, true, "Signing in...");
    var result = await supabaseClient.auth.signInWithPassword({ email: email, password: password });
    setBusy(button, false);
    if (result.error) {
      showError("login-error", errorMessage(result.error, "Sign-in failed."));
      return;
    }
    markSignedIn(result.data.session);
    var redirect = getSafeAuthRedirect(new URLSearchParams(location.search).get("redirect"));
    location.replace(redirect || "dashboard.html");
  }

  async function submitRegister(form) {
    showError("register-error", "");
    var values = Object.fromEntries(new FormData(form));
    var errors = {};
    if (!values.displayName || values.displayName.trim().length < 2) errors.displayName = "Enter your full name.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email || "")) errors.email = "Enter a valid email address.";
    if (!values.password || values.password.length < 8) errors.password = "Use at least 8 characters.";
    if (values.password !== values.confirm) errors.confirm = "Passwords do not match.";
    if (!values.terms) errors.terms = "Accept the fair-play rules.";
    Object.keys(errors).forEach(function (key) {
      var out = document.getElementById("err-" + key);
      if (out) out.textContent = errors[key];
    });
    if (Object.keys(errors).length) return;
    var button = form.querySelector('[type="submit"]');
    setBusy(button, true, "Creating account...");
    var result = await supabaseClient.auth.signUp({
      email: values.email.trim(),
      password: values.password,
      options: { data: { full_name: values.displayName.trim() } }
    });
    setBusy(button, false);
    if (result.error) {
      showError("register-error", errorMessage(result.error, "Account creation failed."));
      return;
    }
    if (!result.data.session) {
      showError("register-error", "Account created. Confirm the email sent to you, then sign in.");
      form.reset();
      return;
    }
    var profile = await apiFetch("/api/auth/profile", {
      method: "POST",
      body: JSON.stringify({
        full_name: values.displayName.trim(),
        username: values.displayName.trim().split(/\s+/).join("").slice(0, 30).toLowerCase()
      })
    });
    if (!profile.ok) {
      showError("register-error", profile.data.error || "Account created, but profile setup failed.");
      return;
    }
    location.replace("assessment.html");
  }

  async function loadProfile() {
    var result = await apiFetch("/api/auth/me");
    if (!result.ok) return null;
    return result.data;
  }

  async function refreshSkillData() {
    if (skillRefreshInFlight) return;
    skillRefreshInFlight = true;
    var assessments;
    var ratings;
    var verifications;
    try {
      [assessments, ratings, verifications] = await Promise.all([
        apiFetch("/api/questionnaire/me"),
        apiFetch("/api/ratings/me"),
        apiFetch("/api/verification/me")
      ]);
    } catch (error) {
      var message = error && error.message || "Could not refresh account data.";
      if (message !== lastSkillDataError) {
        window.nexToast("Account data unavailable", message);
        lastSkillDataError = message;
      }
      skillRefreshInFlight = false;
      return;
    }

    var failures = [];
    var records = assessments.ok ? assessments.data.assessments || [] : [];
    if (!assessments.ok) failures.push(assessments.data.error || "Could not load assessment status.");
    var assessmentStatus = document.getElementById("assessment-status");
    if (assessmentStatus) {
      assessmentStatus.textContent = assessments.ok
        ? "Your progress and seed rating are saved to your account."
        : failures[0];
    }
    var sportSelect = document.getElementById("assessment-sport");
    var selected = sportSelect && sportSelect.value;
    var activeAssessment = records.find(function (item) { return item.sport_id === selected; }) || records[0];
    if (sportSelect && activeAssessment && !selected) {
      sportSelect.value = activeAssessment.sport_id;
      activeAssessment = records.find(function (item) { return item.sport_id === sportSelect.value; });
    }
    setText('[data-flow="seed-elo"]', assessments.ok && activeAssessment ? activeAssessment.seed_rating : "—");
    setText(
      '[data-flow="assessment-state"]',
      !assessments.ok
        ? "Unavailable"
        : activeAssessment && activeAssessment.completed
          ? "Completed · " + activeAssessment.sport_name
          : "Not started"
    );

    if (ratings.ok) {
      var rating = (ratings.data.ratings || []).find(function (item) {
        return !selected || item.sport_id === selected;
      }) || (ratings.data.ratings || [])[0];
      if (rating) {
        setText('[data-flow="elo"]', rating.current_rating);
        setText('[data-flow="played"]', rating.matches_count);
      } else {
        setText('[data-flow="elo"]', "—");
        setText('[data-flow="played"]', "0");
      }
    } else failures.push(ratings.data.error || "Could not load ratings.");

    if (!verifications.ok) {
      failures.push(verifications.data.error || "Could not load verification status.");
      setText('[data-flow="verify-state"]', "Unavailable");
      var verificationMessage = document.getElementById("verification-message");
      if (verificationMessage) {
        verificationMessage.textContent = failures[failures.length - 1];
        verificationMessage.dataset.loadError = "true";
      }
    } else {
      var previousError = document.getElementById("verification-message");
      if (previousError && previousError.dataset.loadError) {
        previousError.textContent = "";
        delete previousError.dataset.loadError;
      }
      var submissions = verifications.data.submissions || [];
      var latest = submissions[0];
      var statusLabels = { pending: "Pending review", approved: "Verified", rejected: "Changes requested" };
      setText('[data-flow="verify-state"]', latest ? statusLabels[latest.status] || latest.status : "Not submitted");
      renderVerificationSubmissions(submissions);
    }

    var errorMessage = failures.join(" ");
    if (errorMessage && errorMessage !== lastSkillDataError) {
      window.nexToast("Account data unavailable", errorMessage);
    }
    lastSkillDataError = errorMessage;
    skillRefreshInFlight = false;
  }

  function renderVerificationSubmissions(submissions) {
    var empty = document.getElementById("verification-empty");
    var details = document.getElementById("verification-details");
    if (!empty || !details) return;
    empty.hidden = submissions.length > 0;
    details.hidden = submissions.length === 0;
    details.innerHTML = submissions.map(function (item) {
      var status = { pending: "Pending review", approved: "Verified", rejected: "Changes requested" }[item.status] || item.status;
      var date = item.created_at ? new Date(item.created_at).toLocaleString() : "";
      return '<article class="list-row"><div><strong>' + escapeHtml(status) + '</strong><small>' +
        escapeHtml(item.method) + " · " + escapeHtml(item.evidence_count) + " file(s) · " +
        escapeHtml(date) + (item.decision_note ? "<br>" + escapeHtml(item.decision_note) : "") +
        "</small></div></article>";
    }).join("");
  }

  async function initAssessment() {
    var select = document.getElementById("assessment-sport");
    var questions = document.getElementById("assessment-questions");
    var submit = document.getElementById("assessment-submit");
    if (!select || !questions || !submit) return;

    var sports;
    var response;
    try {
      [sports, response] = await Promise.all([
        loadSports(),
        apiFetch("/api/questionnaire/questions")
      ]);
    } catch (error) {
      document.getElementById("assessment-status").textContent =
        error && error.message || "Could not load the assessment. Check your connection and try again.";
      return;
    }
    select.innerHTML = '<option value="">Select a sport</option>' +
      sports.map(function (sport) {
        return '<option value="' + escapeHtml(sport.id) + '">' + escapeHtml(sport.name) + "</option>";
      }).join("");
    if (!response.ok) {
      document.getElementById("assessment-status").textContent =
        response.data.error || "Could not load assessment questions.";
      return;
    }
    questions.innerHTML = (response.data.questions || []).map(function (question) {
      return '<label class="field"><span>' + escapeHtml(question.text) + '</span><select class="input" name="' +
        escapeHtml(question.id) + '" required><option value="">Select an answer</option>' +
        question.options.map(function (option) {
          return '<option value="' + escapeHtml(option.value) + '">' + escapeHtml(option.label) + "</option>";
        }).join("") + "</select></label>";
    }).join("");
    submit.disabled = sports.length === 0 || !questions.children.length;
    select.addEventListener("change", function () {
      refreshSkillData();
    });
    document.getElementById("assessment-status").textContent =
      "Your progress and seed rating are saved to your account.";
    await refreshSkillData();
  }

  async function submitAssessment(form) {
    var resultBox = document.getElementById("assessment-result");
    var sportId = form.elements.sport_id.value;
    if (!sportId) {
      resultBox.textContent = "Choose a sport before saving your assessment.";
      form.elements.sport_id.focus();
      return;
    }
    var answerFields = Array.from(form.querySelectorAll("#assessment-questions select"));
    var answers = {};
    for (var field of answerFields) {
      if (!field.value) {
        field.focus();
        resultBox.textContent = "Answer every question before saving.";
        return;
      }
      answers[field.name] = Number(field.value);
    }

    var button = document.getElementById("assessment-submit");
    resultBox.textContent = "";
    setBusy(button, true, "Saving assessment...");
    var result;
    try {
      result = await apiFetch("/api/questionnaire/submit", {
        method: "POST",
        body: JSON.stringify({ sport_id: sportId, answers: answers })
      });
    } catch (error) {
      resultBox.textContent = error && error.message || "Could not save your assessment. Check your connection and try again.";
      setBusy(button, false);
      return;
    }
    setBusy(button, false);
    if (!result.ok) {
      resultBox.textContent = result.data.error || "Could not save your assessment.";
      return;
    }
    resultBox.textContent = result.data.notice + " Seed rating: " + result.data.provisional_rating + ".";
    await refreshSkillData();
  }

  async function submitVerification(form) {
    var resultBox = document.getElementById("verification-message");
    var button = document.getElementById("verification-submit");
    var fileInput = form.elements.evidence;
    var files = Array.from(fileInput.files || []);
    var allowedTypes = {
      "image/jpeg": ".jpg",
      "image/png": ".png",
      "image/webp": ".webp",
      "application/pdf": ".pdf"
    };
    if (!files.length || files.length > 3) {
      resultBox.textContent = "Attach between 1 and 3 evidence files.";
      fileInput.focus();
      return;
    }
    var invalidFile = files.find(function (file) {
      return !allowedTypes[file.type] || file.size < 1 || file.size > 5 * 1024 * 1024;
    });
    if (invalidFile) {
      resultBox.textContent = "Use JPG, PNG, WEBP, or PDF files no larger than 5 MB each.";
      fileInput.focus();
      return;
    }

    var session = await getSession();
    if (!session) {
      resultBox.textContent = "Sign in again before submitting evidence.";
      return;
    }

    resultBox.textContent = "";
    setBusy(button, true, "Uploading evidence...");
    var uploadedPaths = [];
    var result;
    try {
      for (var file of files) {
        var path = session.user.id + "/" + crypto.randomUUID() + allowedTypes[file.type];
        var upload = await supabaseClient.storage.from("skill-evidence").upload(path, file, {
          contentType: file.type,
          upsert: false
        });
        if (upload.error) throw upload.error;
        uploadedPaths.push(path);
      }
      result = await apiFetch("/api/verification/submit", {
        method: "POST",
        body: JSON.stringify({
          method: form.elements.method.value,
          note: form.elements.note.value.trim(),
          evidence_paths: uploadedPaths
        })
      });
    } catch (error) {
      setBusy(button, false);
      var detail = error && error.message || "Could not upload evidence.";
      var cleanupError = await removeUploadedEvidence(uploadedPaths);
      resultBox.textContent = cleanupError
        ? detail + " Uploaded files could not be removed: " + cleanupError
        : detail;
      return;
    }
    setBusy(button, false);
    if (!result.ok) {
      resultBox.textContent = result.data.error || "Could not submit evidence.";
      var cleanupError = await removeUploadedEvidence(uploadedPaths);
      if (cleanupError) resultBox.textContent += " Uploaded files could not be removed: " + cleanupError;
      return;
    }
    resultBox.textContent = result.data.message;
    form.reset();
    await refreshSkillData();
  }

  async function removeUploadedEvidence(paths) {
    if (!paths.length) return "";
    try {
      var result = await supabaseClient.storage.from("skill-evidence").remove(paths);
      return result.error ? result.error.message || "Storage cleanup failed." : "";
    } catch (error) {
      return error && error.message || "Storage cleanup failed.";
    }
  }

  async function initDashboard(session) {
    var data = await loadProfile();
    var profile = data && data.profile;
    var name = profile && (profile.full_name || profile.username);
    var nameNode = document.querySelector(".page-head h1");
    if (name && nameNode) nameNode.textContent = "Welcome, " + name;
    markAccountProfile(profile, data && data.user);

    await refreshSkillData();
    var mine = await apiFetch("/api/lobbies/mine");
    if (mine.ok) {
      var open = (mine.data.lobbies || []).find(function (lobby) {
        return ["open", "full", "in_progress"].indexOf(lobby.status) !== -1;
      });
      setText('[data-flow="room-state"]', open ? open.title + " \u00b7 " + open.status : "No open room");
      var schedule = document.querySelector('body[data-page="dashboard"] .grid.g-main');
      if (open && schedule) {
        var card = schedule.querySelectorAll(".card")[1];
        var empty = card && card.querySelector(".empty");
        if (empty) {
          empty.innerHTML = "";
          empty.appendChild(listRow(open.title, open.status, open.scheduled_at));
        }
      }
    }
  }

  async function initProfile() {
    var data = await loadProfile();
    if (!data) return;
    var profile = data.profile || {};
    var values = {
      displayName: profile.full_name || "",
      email: data.user.email || "",
      username: profile.username || "",
      city: profile.city || ""
    };
    Object.keys(values).forEach(function (key) {
      var input = document.querySelector('[name="' + key + '"]');
      var view = document.querySelector('[data-view="' + key + '"]');
      if (input) input.value = values[key];
      if (view) {
        view.textContent = values[key] || "Not added yet";
        view.classList.toggle("is-empty", !values[key]);
      }
    });
    markAccountProfile(profile, data.user);
    await refreshSkillData();
  }

  async function submitProfile(form) {
    var values = Object.fromEntries(new FormData(form));
    var updates = { full_name: values.displayName.trim() };
    if (values.username) updates.username = values.username.trim();
    if (values.city) updates.city = values.city.trim();
    var result = await apiFetch("/api/auth/profile", {
      method: "PUT",
      body: JSON.stringify(updates)
    });
    if (!result.ok) {
      window.nexToast("Profile not saved", result.data.error || "Update failed.");
      return;
    }
    var profile = result.data.profile;
    ["displayName", "username", "city"].forEach(function (key) {
      var view = document.querySelector('[data-view="' + key + '"]');
      var value = key === "displayName" ? profile.full_name : profile[key];
      if (view) {
        view.textContent = value || "Not added yet";
        view.classList.toggle("is-empty", !value);
      }
    });
    document.querySelectorAll('[data-view="email"]').forEach(function (view) {
      view.classList.remove("is-empty");
    });
    markAccountProfile(profile);
    window.nexToast("Profile updated", "Your athlete profile is saved.");
  }

  async function submitForgotPassword(form) {
    showError("forgot-error", "");
    var email = form.elements.email.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      showError("forgot-error", "Enter a valid email address.");
      return;
    }
    var button = form.querySelector('[type="submit"]');
    setBusy(button, true, "Sending...");
    var result = await supabaseClient.auth.resetPasswordForEmail(email, {
      redirectTo: location.origin + "/oauth-callback.html"
    });
    setBusy(button, false);
    if (result.error) {
      showError("forgot-error", errorMessage(result.error, "Could not send the reset email."));
      return;
    }
    document.getElementById("forgot-email").textContent = email;
    form.hidden = true;
    document.getElementById("forgot-success").hidden = false;
  }

  var sportsCache = null;
  async function loadSports() {
    if (sportsCache) return sportsCache;
    var response = await fetch(CONFIG.API_BASE_URL + "/api/sports");
    var data = await response.json();
    sportsCache = data.sports || [];
    return sportsCache;
  }

  async function initRoomForm() {
    var sports = await loadSports();
    var sport = document.querySelector('#room-form [name="sport"]');
    if (sport) {
      sport.innerHTML = '<option value="">Select a sport</option>' +
        sports.map(function (item) { return '<option value="' + item.id + '" data-team-size="' + item.team_size + '">' + item.name + '</option>'; }).join("");
    }
    var ground = document.querySelector('#room-form [name="ground"]');
    if (ground) {
      ground.setAttribute("list", "ground-options");
      var list = document.createElement("datalist");
      list.id = "ground-options";
      ground.insertAdjacentElement("afterend", list);
      ground.addEventListener("change", function () {
        var selectedGround = Array.from(list.options).find(function (option) {
          return option.value === ground.value;
        });
        if (!selectedGround) return;
        var latitude = document.querySelector('#room-form [name="lat"]');
        var longitude = document.querySelector('#room-form [name="lng"]');
        latitude.value = selectedGround.dataset.lat || "";
        longitude.value = selectedGround.dataset.lon || "";
      });
      fetch(CONFIG.API_BASE_URL + "/api/grounds").then(function (response) { return response.json(); }).then(function (data) {
        list.innerHTML = (data.grounds || []).map(function (item) {
          return '<option value="' + item.name + '" data-ground-id="' + item.id + '" data-lat="' + item.latitude + '" data-lon="' + item.longitude + '">';
        }).join("");
      });
    }
    var locationButton = document.getElementById("use-location");
    if (locationButton) locationButton.addEventListener("click", useLocation);
  }

  function useLocation() {
    var lat = document.querySelector('#room-form [name="lat"]');
    var lng = document.querySelector('#room-form [name="lng"]');
    if (!navigator.geolocation) {
      window.nexToast("Location unavailable", "Your browser does not support location.");
      return;
    }
    navigator.geolocation.getCurrentPosition(function (position) {
      lat.value = position.coords.latitude;
      lng.value = position.coords.longitude;
    }, function () {
      window.nexToast("Location unavailable", "Allow location access and try again.");
    }, { enableHighAccuracy: true, timeout: 10000 });
  }

  async function submitRoom(form) {
    var values = Object.fromEntries(new FormData(form));
    var selected = form.elements.sport.selectedOptions[0];
    var teamSize = parseInt(selected.dataset.teamSize, 10) || 5;
    var maxPlayers = parseInt(values.players, 10);
    var lat = parseFloat(values.lat);
    var lng = parseFloat(values.lng);
    var groundName = values.ground.trim();
    var title = groundName + " " + selected.textContent.trim();
    var scheduledDate = new Date(values.date + "T" + values.time);
    if (!selected.value) {
      window.nexToast("Check room details", "Choose a sport.");
      form.elements.sport.focus();
      return;
    }
    if (groundName.length < 3) {
      window.nexToast("Check room details", "Enter a ground or venue name.");
      form.elements.ground.focus();
      return;
    }
    if (!values.date || !values.time || !Number.isFinite(scheduledDate.getTime()) || scheduledDate <= new Date()) {
      window.nexToast("Check room details", "Choose a future date and start time.");
      form.elements.date.focus();
      return;
    }
    if (!Number.isInteger(maxPlayers) || maxPlayers < teamSize * 2 || maxPlayers > 30) {
      window.nexToast("Check room details", "Players required must fit two full teams and be no more than 30.");
      form.elements.players.focus();
      return;
    }
    if (!Number.isFinite(lat) || lat < -90 || lat > 90) {
      window.nexToast("Check room details", "Enter a latitude between -90 and 90.");
      form.elements.lat.focus();
      return;
    }
    if (!Number.isFinite(lng) || lng < -180 || lng > 180) {
      window.nexToast("Check room details", "Enter a longitude between -180 and 180.");
      form.elements.lng.focus();
      return;
    }
    if (title.length > 100) {
      window.nexToast("Check room details", "Shorten the ground name so the room title is no more than 100 characters.");
      form.elements.ground.focus();
      return;
    }
    var groundOptions = document.querySelectorAll("#ground-options option");
    var ground = Array.from(groundOptions).find(function (option) { return option.value === groundName; });
    var scheduledAt = scheduledDate.toISOString();
    var button = form.querySelector('[type="submit"]');
    setBusy(button, true, "Creating room...");
    var result = await apiFetch("/api/lobbies", {
      method: "POST",
      body: JSON.stringify({
        title: title,
        sport_id: selected.value,
        ground_id: ground ? ground.dataset.groundId : null,
        latitude: lat,
        longitude: lng,
        scheduled_at: scheduledAt,
        team_size: teamSize,
        min_players: teamSize * 2,
        max_players: maxPlayers,
        description: values.description || null
      })
    });
    setBusy(button, false);
    if (!result.ok) {
      window.nexToast("Room not created", result.data.error || "Could not create the room.");
      return;
    }
    location.href = "room.html?id=" + encodeURIComponent(result.data.lobby.id);
  }

  async function initFindMatch(session) {
    var sports = await loadSports();
    var select = document.querySelector('body[data-page="find-match"] select[name="sport"]');
    if (select) {
      select.innerHTML = '<option value="">Any sport</option>' +
        sports.map(function (item) { return '<option value="' + item.id + '">' + item.name + '</option>'; }).join("");
    }
    var button = document.querySelector('body[data-page="find-match"] .filter-foot .btn-primary');
    if (button) button.addEventListener("click", searchNearby);
    var locationButton = document.getElementById("match-location");
    if (locationButton) {
      locationButton.addEventListener("click", function () {
        if (!navigator.geolocation) {
          window.nexToast("Location unavailable", "Your browser does not support location.");
          return;
        }
        navigator.geolocation.getCurrentPosition(function (position) {
          document.querySelector('[name="match-lat"]').value = position.coords.latitude;
          document.querySelector('[name="match-lng"]').value = position.coords.longitude;
          window.nexToast("Location ready", "Nearby rooms will use your current position.");
        }, function () {
          window.nexToast("Location unavailable", "Allow location access and try again.");
        }, { enableHighAccuracy: true, timeout: 10000 });
      });
    }
  }

  async function searchNearby() {
    var lat = document.querySelector('[name="match-lat"]');
    var lng = document.querySelector('[name="match-lng"]');
    var distance = document.querySelectorAll('body[data-page="find-match"] select[name="distance"]')[0];
    var radius = distance ? parseInt(distance.value.replace(/\D/g, ""), 10) || 10 : 10;
    if (!lat || !lng) {
      navigator.geolocation.getCurrentPosition(function (position) {
        renderNearby(position.coords.latitude, position.coords.longitude, radius);
      }, function () {
        window.nexToast("Location unavailable", "Allow location access and try again.");
      });
      return;
    }
    await renderNearby(parseFloat(lat.value), parseFloat(lng.value), radius);
  }

  async function renderNearby(lat, lng, radius) {
    var sport = document.querySelector('body[data-page="find-match"] select[name="sport"]');
    var query = "?lat=" + encodeURIComponent(lat) + "&lon=" + encodeURIComponent(lng) +
      "&radius_km=" + encodeURIComponent(radius);
    if (sport && sport.value) query += "&sport_id=" + encodeURIComponent(sport.value);
    var result = await apiFetch("/api/lobbies/nearby" + query);
    var card = document.querySelector('body[data-page="find-match"] .grid.g-main .card');
    if (!card) return;
    var empty = card.querySelector(".empty");
    if (!result.ok) {
      window.nexToast("Search failed", result.data.error || "Could not search nearby rooms.");
      return;
    }
    var rows = result.data.lobbies || [];
    if (!rows.length) {
      if (empty) empty.querySelector("h4").textContent = "No nearby rooms";
      return;
    }
    var container = empty || card;
    container.innerHTML = '<div class="stack list-compact">' + rows.map(function (room) {
      return '<article class="list-row"><div><strong>' + escapeHtml(room.title) + '</strong><small>' +
        escapeHtml(room.sport && room.sport.name || "Sport") + " · " + room.distance_km + " km · " +
        room.players_joined + "/" + room.max_players + " players</small></div>" +
        (room.joinable ? '<button type="button" class="btn btn-primary btn-sm" data-join-lobby="' + room.id + '">Join</button>' : '');
      '</article>';
    }).join("") + "</div>";
  }

  document.addEventListener("click", async function (event) {
    var button = event.target.closest && event.target.closest("[data-join-lobby]");
    if (!button) return;
    var result = await apiFetch("/api/lobbies/" + encodeURIComponent(button.dataset.joinLobby) + "/join", { method: "POST", body: "{}" });
    if (!result.ok) {
      window.nexToast("Could not join", result.data.error || "Join failed.");
      return;
    }
    location.href = "room.html?id=" + encodeURIComponent(button.dataset.joinLobby);
  });

  function setText(selector, value) {
    document.querySelectorAll(selector).forEach(function (el) { el.textContent = value; });
  }

  function markAccountProfile(profile, user) {
    var name = profile && (profile.full_name || profile.username);
    var email = user && user.email;
    setText(".account-trigger .who strong", name || "Athlete");
    document.querySelectorAll(".account-trigger .who").forEach(function (who) {
      who.childNodes.forEach(function (node) {
        if (node.nodeType === 3 && node.textContent.indexOf("@") !== -1) node.textContent = email || "";
      });
    });
  }

  function listRow(title, status, scheduledAt) {
    var row = document.createElement("article");
    row.className = "list-row";
    var copy = document.createElement("div");
    var strong = document.createElement("strong");
    var small = document.createElement("small");
    strong.textContent = title;
    small.textContent = status + (scheduledAt ? " · " + new Date(scheduledAt).toLocaleString() : "");
    copy.append(strong, small);
    row.appendChild(copy);
    return row;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
    });
  }

  document.addEventListener("DOMContentLoaded", async function () {
    var session = await initAuth();
    if (protectedPages.has(page) && !session) return;
    if (page === "dashboard") await initDashboard(session);
    if (page === "profile" || page === "settings") await initProfile();
    if (page === "assessment") await initAssessment();
    if (page === "verify") await refreshSkillData();
    if (page === "create-room") await initRoomForm();
    if (page === "find-match") await initFindMatch(session);
    if (["dashboard", "profile", "assessment", "verify"].includes(page)) {
      window.setInterval(function () {
        if (!document.hidden) refreshSkillData();
      }, 20000);
      document.addEventListener("visibilitychange", function () {
        if (!document.hidden) refreshSkillData();
      });
    }
  });
})();
