/**
 * Floating AI Coach Shortcut Widget for NexSport pages.
 */
(function () {
  "use strict";

  // Don't render floating launcher if already on chat page
  if (window.location.pathname.endsWith("chat.html")) return;

  function createWidget() {
    if (document.getElementById("nexsport-ai-floating-widget")) return;

    const widget = document.createElement("div");
    widget.id = "nexsport-ai-floating-widget";
    widget.className = "nexsport-chat-widget";
    widget.innerHTML = `
      <a href="chat.html" class="chat-fab shadow-lg" title="Ask AI Coach (Llama 3.1, Mistral, DeepSeek)" aria-label="Open NexSport AI Coach">
        <span class="fab-icon">🤖</span>
        <span class="fab-badge">AI</span>
      </a>
    `;

    document.body.appendChild(widget);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createWidget);
  } else {
    createWidget();
  }
})();

