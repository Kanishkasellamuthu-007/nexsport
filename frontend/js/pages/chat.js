/**
 * NexSport AI Chat Client — powered by GitHub Models open-source LLMs.
 */
(function () {
  "use strict";

  const STORAGE_KEY_TOKEN = "nexsport_github_token";
  const STORAGE_KEY_HISTORY = "nexsport_chat_history";

  let availableModels = [];
  let currentModel = "meta/llama-3.1-70b-instruct";
  let conversationHistory = [];
  let isGenerating = false;
  let serverHasToken = false;

  // DOM Elements
  const chatMessagesEl = document.getElementById("chat-messages");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");
  const modelSelect = document.getElementById("model-select");
  const activeModelNameEl = document.getElementById("active-model-name");
  const tokenStatusPill = document.getElementById("token-status-pill");
  const modalServerStatus = document.getElementById("modal-server-status");
  const customTokenInput = document.getElementById("custom-github-token");
  const modalSaveTokenBtn = document.getElementById("modal-save-token-btn");
  const modalClearTokenBtn = document.getElementById("modal-clear-token-btn");
  const clearChatBtn = document.getElementById("clear-chat-btn");
  const typingIndicator = document.getElementById("typing-indicator");
  const quickPromptsContainer = document.getElementById("quick-prompts");

  // Format markdown with fallback
  function renderMarkdown(text) {
    if (window.marked && window.DOMPurify) {
      try {
        const rawHtml = window.marked.parse(text, { breaks: true, gfm: true });
        return window.DOMPurify.sanitize(rawHtml);
      } catch (err) {
        console.warn("Markdown parsing error:", err);
      }
    }
    // Simple fallback formatter if CDN fails
    let escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    // Code blocks
    escaped = escaped.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>");
    // Bold
    escaped = escaped.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    // Newlines
    escaped = escaped.replace(/\n/g, "<br/>");
    return escaped;
  }

  // Load available models from the Flask backend
  async function loadModels() {
    try {
      const res = await fetch(`${CONFIG.API_BASE_URL}/api/chat/models`);
      if (!res.ok) throw new Error("Could not load models list.");
      const data = await res.json();

      availableModels = data.models || [];
      serverHasToken = Boolean(data.has_server_token);

      if (data.default_model) {
        currentModel = data.default_model;
      }

      // Populate select dropdown
      if (modelSelect && availableModels.length > 0) {
        modelSelect.innerHTML = "";
        availableModels.forEach((m) => {
          const opt = document.createElement("option");
          opt.value = m.id;
          opt.textContent = `${m.icon || "🤖"} ${m.name} (${m.badge || m.provider})`;
          if (m.id === currentModel) opt.selected = true;
          modelSelect.appendChild(opt);
        });
      }

      updateStatusBadges();
    } catch (err) {
      console.warn("Failed to load models list:", err);
      updateStatusBadges();
    }
  }

  // Update token pills and server status text
  function updateStatusBadges() {
    const customToken = localStorage.getItem(STORAGE_KEY_TOKEN) || "";

    if (customToken.trim()) {
      tokenStatusPill.className = "badge bg-primary-subtle text-primary border border-primary-subtle";
      tokenStatusPill.innerHTML = '<i class="bi bi-key-fill me-1"></i> Custom Token Active';
      modalServerStatus.innerHTML = '<span class="text-primary fw-semibold">Using your custom GitHub token from browser storage.</span>';
    } else if (serverHasToken) {
      tokenStatusPill.className = "badge bg-success-subtle text-success border border-success-subtle";
      tokenStatusPill.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i> Server Connected';
      modalServerStatus.innerHTML = '<span class="text-success fw-semibold">Connected via server environment variable (GITHUB_TOKEN).</span>';
    } else {
      tokenStatusPill.className = "badge bg-warning-subtle text-warning-emphasis border border-warning-subtle";
      tokenStatusPill.innerHTML = '<i class="bi bi-lightning-charge me-1"></i> Preview Mode (No Token)';
      modalServerStatus.innerHTML = '<span class="text-muted">No server token found. Add token below or in <code>.env</code>.</span>';
    }

    const selectedModelObj = availableModels.find((m) => m.id === currentModel);
    if (selectedModelObj && activeModelNameEl) {
      activeModelNameEl.textContent = selectedModelObj.name;
    }
  }

  // Append a message bubble to the chat window
  function appendMessage(role, content, modelName = "", isFallback = false) {
    const isUser = role === "user";
    const msgDiv = document.createElement("div");
    msgDiv.className = `chat-message ${isUser ? "user-message" : "assistant-message"} mb-3`;

    const avatar = isUser ? "👤" : "🏅";
    const headerTitle = isUser ? "You" : "NexSport Coach";
    const badgeHtml = !isUser && modelName
      ? `<span class="badge bg-light text-muted border ms-2">${modelName}</span>`
      : "";
    const fallbackBadge = !isUser && isFallback
      ? `<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle ms-1" title="Offline preview mode">Preview</span>`
      : "";

    msgDiv.innerHTML = `
      <div class="message-avatar">${avatar}</div>
      <div class="message-content">
        <div class="message-header d-flex align-items-center">
          <strong class="${isUser ? 'text-primary' : 'text-success'}">${headerTitle}</strong>
          ${badgeHtml}
          ${fallbackBadge}
          <button class="btn btn-link btn-sm text-muted p-0 ms-auto copy-msg-btn" title="Copy message" style="font-size: 0.8rem;">
            <i class="bi bi-clipboard"></i>
          </button>
        </div>
        <div class="message-body mt-1">
          ${renderMarkdown(content)}
        </div>
      </div>
    `;

    // Wire copy button
    const copyBtn = msgDiv.querySelector(".copy-msg-btn");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(content).then(() => {
          copyBtn.innerHTML = '<i class="bi bi-check text-success"></i>';
          setTimeout(() => {
            copyBtn.innerHTML = '<i class="bi bi-clipboard"></i>';
          }, 2000);
        });
      });
    }

    chatMessagesEl.appendChild(msgDiv);
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
  }

  // Handle sending a message
  async function sendMessage(text) {
    const prompt = (text || chatInput.value || "").trim();
    if (!prompt || isGenerating) return;

    // Reset input
    chatInput.value = "";
    autoResizeTextarea();

    // Hide quick prompts container after first interaction
    if (quickPromptsContainer) {
      quickPromptsContainer.classList.add("d-none");
    }

    // Add user message to UI and history
    appendMessage("user", prompt);
    conversationHistory.push({ role: "user", content: prompt });

    // Enable typing indicator
    isGenerating = true;
    sendBtn.disabled = true;
    typingIndicator.classList.remove("d-none");
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;

    // Prepare API headers and payload
    const customToken = localStorage.getItem(STORAGE_KEY_TOKEN) || "";
    const headers = { "Content-Type": "application/json" };
    if (customToken.trim()) {
      headers["X-GitHub-Token"] = customToken.trim();
    }

    // Send the last 8 messages for context
    const recentMessages = conversationHistory.slice(-8);

    try {
      const res = await fetch(`${CONFIG.API_BASE_URL}/api/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          messages: recentMessages,
          model: currentModel,
          temperature: 0.7,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        const errorMsg = data.error || `Error ${res.status}: Failed to get answer.`;
        appendMessage(
          "assistant",
          `⚠️ **Assistant Error:** ${errorMsg}\n\n*Tip: If your GitHub token expired or exceeded rate limits, update it in [Settings](#) above.*`
        );
      } else {
        const reply = data.reply || "I didn't receive an answer. Please try again.";
        appendMessage("assistant", reply, data.model_name || currentModel, Boolean(data.is_fallback));
        conversationHistory.push({ role: "assistant", content: reply });

        // Save session history
        try {
          sessionStorage.setItem(STORAGE_KEY_HISTORY, JSON.stringify(conversationHistory.slice(-16)));
        } catch (e) {
          // Ignore quota errors
        }
      }
    } catch (err) {
      console.error("Chat request failed:", err);
      appendMessage(
        "assistant",
        "❌ **Connection Error:** Could not reach the NexSport chat server. Ensure the backend Flask server is running."
      );
    } finally {
      isGenerating = false;
      sendBtn.disabled = false;
      typingIndicator.classList.add("d-none");
      chatInput.focus();
    }
  }

  // Auto-resize input textarea as user types
  function autoResizeTextarea() {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
  }

  // Restore saved messages or load defaults
  function restoreSession() {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY_HISTORY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          conversationHistory = parsed;
          parsed.forEach((m) => {
            appendMessage(m.role, m.content, m.role === "assistant" ? currentModel : "");
          });
          if (quickPromptsContainer) {
            quickPromptsContainer.classList.add("d-none");
          }
        }
      }
    } catch (e) {
      sessionStorage.removeItem(STORAGE_KEY_HISTORY);
    }
  }

  // Check login state to toggle navbar buttons
  async function checkAuthNav() {
    const navLogin = document.getElementById("nav-login");
    const navLogout = document.getElementById("nav-logout");
    const logoutBtn = document.getElementById("logout-btn");

    if (window.supabaseClient) {
      try {
        const { data: { session } } = await window.supabaseClient.auth.getSession();
        if (session && session.user) {
          if (navLogin) navLogin.classList.add("d-none");
          if (navLogout) navLogout.classList.remove("d-none");
        }
      } catch (err) {
        console.warn("Auth check failed:", err);
      }
    }

    if (logoutBtn) {
      logoutBtn.addEventListener("click", async (e) => {
        e.preventDefault();
        if (window.supabaseClient) {
          await window.supabaseClient.auth.signOut();
        }
        window.location.href = "login.html";
      });
    }
  }

  // Initialization
  function init() {
    loadModels();
    restoreSession();
    checkAuthNav();

    // Populate token input in modal if previously stored
    const savedToken = localStorage.getItem(STORAGE_KEY_TOKEN) || "";
    if (customTokenInput && savedToken) {
      customTokenInput.value = savedToken;
    }

    // Model selection changes
    if (modelSelect) {
      modelSelect.addEventListener("change", (e) => {
        currentModel = e.target.value;
        const modelObj = availableModels.find((m) => m.id === currentModel);
        if (activeModelNameEl && modelObj) {
          activeModelNameEl.textContent = modelObj.name;
        }
      });
    }

    // Input typing & auto-resize
    if (chatInput) {
      chatInput.addEventListener("input", autoResizeTextarea);
      chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          sendMessage();
        }
      });
    }

    // Form submit
    if (chatForm) {
      chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        sendMessage();
      });
    }

    // Quick prompt buttons
    document.querySelectorAll(".quick-prompt-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const promptText = btn.getAttribute("data-prompt");
        if (promptText) {
          sendMessage(promptText);
        }
      });
    });

    // Clear chat
    if (clearChatBtn) {
      clearChatBtn.addEventListener("click", () => {
        if (confirm("Clear this conversation?")) {
          conversationHistory = [];
          sessionStorage.removeItem(STORAGE_KEY_HISTORY);
          chatMessagesEl.innerHTML = "";
          // Re-append welcome
          location.reload();
        }
      });
    }

    // Save token modal button
    if (modalSaveTokenBtn) {
      modalSaveTokenBtn.addEventListener("click", () => {
        const token = (customTokenInput.value || "").trim();
        if (token) {
          localStorage.setItem(STORAGE_KEY_TOKEN, token);
        } else {
          localStorage.removeItem(STORAGE_KEY_TOKEN);
        }
        updateStatusBadges();
        const modalEl = document.getElementById("settingsModal");
        const modalInstance = bootstrap.Modal.getInstance(modalEl);
        if (modalInstance) modalInstance.hide();
      });
    }

    // Clear token modal button
    if (modalClearTokenBtn) {
      modalClearTokenBtn.addEventListener("click", () => {
        localStorage.removeItem(STORAGE_KEY_TOKEN);
        if (customTokenInput) customTokenInput.value = "";
        updateStatusBadges();
        const modalEl = document.getElementById("settingsModal");
        const modalInstance = bootstrap.Modal.getInstance(modalEl);
        if (modalInstance) modalInstance.hide();
      });
    }
  }

  // Run on DOM load
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

