/*
 * Skill questionnaire page (PROTECTED).
 * Loads questions from the Flask API, validates every answer client-side,
 * and submits to POST /api/questionnaire/submit with the Bearer token.
 */
(function () {
  "use strict";

  let QUESTIONS = [];

  document.addEventListener("DOMContentLoaded", async function () {
    const session = await requireAuth();
    if (!session) return;

    renderAuthNav();
    document.getElementById("logout-btn").addEventListener("click", async function (e) {
      e.preventDefault();
      await supabaseClient.auth.signOut();
      window.location.replace("index.html");
    });

    await Promise.all([loadSports(), loadQuestions()]);
  });

  async function loadSports() {
    const select = document.getElementById("sport");
    try {
      const res = await fetch(CONFIG.API_BASE_URL + "/api/sports");
      const data = await res.json();
      select.innerHTML =
        '<option value="">Choose a sport…</option>' +
        (data.sports || [])
          .map((s) => '<option value="' + s.id + '">' + s.icon + " " + s.name + "</option>")
          .join("");
    } catch {
      select.innerHTML = '<option value="">Could not load sports</option>';
    }
  }

  async function loadQuestions() {
    const container = document.getElementById("questions-container");
    try {
      const res = await fetch(CONFIG.API_BASE_URL + "/api/questionnaire/questions");
      const data = await res.json();
      QUESTIONS = data.questions || [];

      container.innerHTML = QUESTIONS.map(function (q, i) {
        return (
          '<fieldset class="mb-4 question-block" data-qid="' + q.id + '">' +
          '<legend class="fs-6 fw-semibold mb-2">' + (i + 1) + ". " + q.text + "</legend>" +
          q.options
            .map(function (o) {
              return (
                '<div class="form-check">' +
                '<input class="form-check-input" type="radio" name="' + q.id +
                '" id="' + q.id + "_" + o.value + '" value="' + o.value + '" required />' +
                '<label class="form-check-label" for="' + q.id + "_" + o.value + '">' +
                o.label + "</label></div>"
              );
            })
            .join("") +
          '<div class="form-text-error" data-error-for="' + q.id + '"></div>' +
          "</fieldset>"
        );
      }).join("");

      document.getElementById("submit-btn").disabled = false;
    } catch {
      container.innerHTML = '<p class="text-danger">Could not load questions. Is the API running?</p>';
    }
  }

  function validate() {
    let ok = true;
    const sportId = document.getElementById("sport").value;
    document.querySelector('[data-error-for="sport"]');

    QUESTIONS.forEach(function (q) {
      const errEl = document.querySelector('[data-error-for="' + q.id + '"]');
      errEl.textContent = "";
      const chosen = document.querySelector('input[name="' + q.id + '"]:checked');
      if (!chosen) {
        errEl.textContent = "Please choose an answer.";
        ok = false;
      }
    });

    if (!sportId) {
      showAlert(document.getElementById("alert-box"), "Please select a sport.", "warning");
      ok = false;
    }
    return ok;
  }

  document.addEventListener("submit", async function (e) {
    if (e.target.id !== "questionnaire-form") return;
    e.preventDefault();

    const alertBox = document.getElementById("alert-box");
    showAlert(alertBox, "");
    if (!validate()) return;

    const answers = {};
    QUESTIONS.forEach(function (q) {
      answers[q.id] = parseInt(document.querySelector('input[name="' + q.id + '"]:checked').value, 10);
    });

    const submitBtn = document.getElementById("submit-btn");
    setButtonLoading(submitBtn, true, "Computing your rating…");

    const { ok, status, data } = await apiFetch("/api/questionnaire/submit", {
      method: "POST",
      body: JSON.stringify({ sport_id: document.getElementById("sport").value, answers: answers }),
    });

    setButtonLoading(submitBtn, false);

    if (!ok) {
      showAlert(alertBox, data.error || "Submission failed.", "danger");
      return;
    }

    // Show the transparent breakdown.
    const b = data.breakdown;
    document.getElementById("result-box").innerHTML =
      '<div class="card stat-card border-success">' +
      '<div class="card-body text-center">' +
      '<h2 class="h4 text-success mb-1">🏆 Provisional rating: ' + data.provisional_rating + "</h2>" +
      '<p class="text-muted small mb-3">' + data.notice + "</p>" +
      '<dl class="row text-start small mb-0">' +
      '<dt class="col-6">Weighted score</dt><dd class="col-6">' + b.weighted_score + " / 1.0</dd>" +
      '<dt class="col-6">Adjustment from base 1000</dt><dd class="col-6">' +
      (b.adjustment >= 0 ? "+" : "") + b.adjustment + "</dd>" +
      '<dt class="col-6">Range guard</dt><dd class="col-6">' + (b.clamped ? "clamped to limits" : "within limits") + "</dd>" +
      "</dl></div></div>" +
      '<a href="dashboard.html" class="btn btn-success w-100 mt-3">Go to Dashboard</a>';

    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  });
})();
