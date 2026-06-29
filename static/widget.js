(function () {
  "use strict";

  const script = document.currentScript || (function () {
    const scripts = document.getElementsByTagName("script");
    return scripts[scripts.length - 1];
  })();

  const cfg = {
    apiKey: script.getAttribute("data-api-key") || "",
    apiUrl: script.getAttribute("data-api-url") || "/v1/chat",
    title: script.getAttribute("data-title") || "Assistant",
    placeholder: script.getAttribute("data-placeholder") || "Ask me anything...",
    theme: script.getAttribute("data-theme") || "light",
    position: script.getAttribute("data-position") || "bottom-right",
  };

  if (!cfg.apiKey) {
    console.error("[RAG Widget] data-api-key is required.");
    return;
  }

  // ── Styles ────────────────────────────────────────────────────────────────

  const COLORS = {
    light: {
      bg: "#ffffff",
      surface: "#f9fafb",
      border: "#e5e7eb",
      text: "#111827",
      subtext: "#6b7280",
      userBubble: "#2563eb",
      userText: "#ffffff",
      botBubble: "#f3f4f6",
      botText: "#111827",
      input: "#ffffff",
      inputBorder: "#d1d5db",
      btnBg: "#2563eb",
      btnText: "#ffffff",
      toggleBg: "#2563eb",
      shadow: "rgba(0,0,0,0.15)",
    },
    dark: {
      bg: "#1f2937",
      surface: "#111827",
      border: "#374151",
      text: "#f9fafb",
      subtext: "#9ca3af",
      userBubble: "#3b82f6",
      userText: "#ffffff",
      botBubble: "#374151",
      botText: "#f9fafb",
      input: "#374151",
      inputBorder: "#4b5563",
      btnBg: "#3b82f6",
      btnText: "#ffffff",
      toggleBg: "#3b82f6",
      shadow: "rgba(0,0,0,0.4)",
    },
  };

  const c = COLORS[cfg.theme] || COLORS.light;
  const isRight = cfg.position !== "bottom-left";

  const css = `
    #rag-widget-toggle {
      position: fixed;
      ${isRight ? "right: 24px" : "left: 24px"};
      bottom: 24px;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: ${c.toggleBg};
      color: #fff;
      border: none;
      cursor: pointer;
      box-shadow: 0 4px 14px ${c.shadow};
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 99999;
      transition: transform 0.2s;
    }
    #rag-widget-toggle:hover { transform: scale(1.08); }
    #rag-widget-toggle svg { width: 26px; height: 26px; }

    #rag-widget-window {
      position: fixed;
      ${isRight ? "right: 24px" : "left: 24px"};
      bottom: 92px;
      width: 360px;
      max-width: calc(100vw - 32px);
      height: 520px;
      max-height: calc(100vh - 120px);
      border-radius: 16px;
      background: ${c.bg};
      border: 1px solid ${c.border};
      box-shadow: 0 8px 32px ${c.shadow};
      display: flex;
      flex-direction: column;
      z-index: 99998;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-size: 14px;
      color: ${c.text};
      overflow: hidden;
      transition: opacity 0.2s, transform 0.2s;
    }
    #rag-widget-window.rag-hidden {
      opacity: 0;
      transform: translateY(12px) scale(0.97);
      pointer-events: none;
    }

    #rag-header {
      padding: 14px 16px;
      background: ${c.btnBg};
      color: ${c.btnText};
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-radius: 16px 16px 0 0;
    }
    #rag-header-title { font-weight: 600; font-size: 15px; }
    #rag-header-actions { display: flex; gap: 8px; align-items: center; }
    .rag-icon-btn {
      background: transparent;
      border: none;
      color: rgba(255,255,255,0.8);
      cursor: pointer;
      padding: 2px;
      display: flex;
      align-items: center;
    }
    .rag-icon-btn:hover { color: #fff; }
    .rag-icon-btn svg { width: 18px; height: 18px; }

    #rag-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: ${c.surface};
    }
    #rag-messages::-webkit-scrollbar { width: 4px; }
    #rag-messages::-webkit-scrollbar-thumb { background: ${c.border}; border-radius: 2px; }

    .rag-msg { display: flex; flex-direction: column; max-width: 85%; }
    .rag-msg.user { align-self: flex-end; align-items: flex-end; }
    .rag-msg.bot { align-self: flex-start; align-items: flex-start; }

    .rag-bubble {
      padding: 10px 13px;
      border-radius: 12px;
      line-height: 1.5;
      word-break: break-word;
    }
    .rag-msg.user .rag-bubble {
      background: ${c.userBubble};
      color: ${c.userText};
      border-bottom-right-radius: 4px;
    }
    .rag-msg.bot .rag-bubble {
      background: ${c.botBubble};
      color: ${c.botText};
      border-bottom-left-radius: 4px;
    }

    .rag-sources {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 6px;
    }
    .rag-source-chip {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 999px;
      background: ${c.border};
      color: ${c.subtext};
      border: 1px solid ${c.inputBorder};
    }

    .rag-typing {
      display: flex;
      gap: 4px;
      padding: 10px 13px;
      background: ${c.botBubble};
      border-radius: 12px;
      border-bottom-left-radius: 4px;
      align-self: flex-start;
    }
    .rag-dot {
      width: 7px; height: 7px;
      border-radius: 50%;
      background: ${c.subtext};
      animation: rag-bounce 1.2s infinite ease-in-out;
    }
    .rag-dot:nth-child(2) { animation-delay: 0.2s; }
    .rag-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes rag-bounce {
      0%, 80%, 100% { transform: scale(0.7); opacity: 0.4; }
      40% { transform: scale(1); opacity: 1; }
    }

    #rag-footer {
      padding: 12px;
      border-top: 1px solid ${c.border};
      background: ${c.bg};
      display: flex;
      gap: 8px;
      align-items: flex-end;
    }
    #rag-input {
      flex: 1;
      border: 1px solid ${c.inputBorder};
      border-radius: 10px;
      padding: 9px 12px;
      font-size: 14px;
      background: ${c.input};
      color: ${c.text};
      resize: none;
      outline: none;
      max-height: 100px;
      overflow-y: auto;
      font-family: inherit;
      line-height: 1.4;
    }
    #rag-input:focus { border-color: ${c.btnBg}; }
    #rag-input::placeholder { color: ${c.subtext}; }
    #rag-send {
      background: ${c.btnBg};
      color: ${c.btnText};
      border: none;
      border-radius: 10px;
      width: 38px;
      height: 38px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      transition: opacity 0.15s;
    }
    #rag-send:disabled { opacity: 0.5; cursor: not-allowed; }
    #rag-send svg { width: 18px; height: 18px; }

    #rag-error {
      padding: 8px 12px;
      background: #fef2f2;
      color: #dc2626;
      font-size: 12px;
      border-top: 1px solid #fecaca;
      display: none;
    }
  `;

  // ── SVG icons ─────────────────────────────────────────────────────────────

  const SVG = {
    chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    clear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>',
  };

  // ── DOM ───────────────────────────────────────────────────────────────────

  function injectStyles() {
    const el = document.createElement("style");
    el.textContent = css;
    document.head.appendChild(el);
  }

  function buildDOM() {
    // Toggle button
    const toggle = document.createElement("button");
    toggle.id = "rag-widget-toggle";
    toggle.setAttribute("aria-label", "Open chat");
    toggle.innerHTML = SVG.chat;

    // Window
    const win = document.createElement("div");
    win.id = "rag-widget-window";
    win.classList.add("rag-hidden");
    win.setAttribute("role", "dialog");
    win.setAttribute("aria-label", cfg.title);

    win.innerHTML = `
      <div id="rag-header">
        <span id="rag-header-title">${escHtml(cfg.title)}</span>
        <div id="rag-header-actions">
          <button class="rag-icon-btn" id="rag-clear-btn" title="Clear conversation">${SVG.clear}</button>
          <button class="rag-icon-btn" id="rag-close-btn" title="Close">${SVG.close}</button>
        </div>
      </div>
      <div id="rag-messages" aria-live="polite"></div>
      <div id="rag-error"></div>
      <div id="rag-footer">
        <textarea id="rag-input" rows="1" placeholder="${escHtml(cfg.placeholder)}"></textarea>
        <button id="rag-send" aria-label="Send">${SVG.send}</button>
      </div>
    `;

    document.body.appendChild(toggle);
    document.body.appendChild(win);
    return { toggle, win };
  }

  // ── State & logic ─────────────────────────────────────────────────────────

  function escHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function init() {
    injectStyles();
    const { toggle, win } = buildDOM();

    const messagesEl = win.querySelector("#rag-messages");
    const inputEl = win.querySelector("#rag-input");
    const sendBtn = win.querySelector("#rag-send");
    const closeBtn = win.querySelector("#rag-close-btn");
    const clearBtn = win.querySelector("#rag-clear-btn");
    const errorEl = win.querySelector("#rag-error");

    let sessionId = null;
    let isOpen = false;
    let isLoading = false;
    let typingEl = null;

    function setOpen(open) {
      isOpen = open;
      win.classList.toggle("rag-hidden", !open);
      toggle.innerHTML = open ? SVG.close : SVG.chat;
      toggle.setAttribute("aria-label", open ? "Close chat" : "Open chat");
      if (open) setTimeout(() => inputEl.focus(), 50);
    }

    function showError(msg) {
      errorEl.textContent = msg;
      errorEl.style.display = "block";
      setTimeout(() => { errorEl.style.display = "none"; }, 5000);
    }

    function appendMessage(role, text, sources) {
      const msg = document.createElement("div");
      msg.className = `rag-msg ${role}`;

      const bubble = document.createElement("div");
      bubble.className = "rag-bubble";
      bubble.textContent = text;
      msg.appendChild(bubble);

      if (sources && sources.length) {
        const chips = document.createElement("div");
        chips.className = "rag-sources";
        sources.forEach(function (s) {
          const chip = document.createElement("span");
          chip.className = "rag-source-chip";
          chip.textContent = s.page ? `${s.file} p.${s.page}` : s.file;
          chips.appendChild(chip);
        });
        msg.appendChild(chips);
      }

      messagesEl.appendChild(msg);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function showTyping() {
      typingEl = document.createElement("div");
      typingEl.className = "rag-typing";
      typingEl.innerHTML = '<div class="rag-dot"></div><div class="rag-dot"></div><div class="rag-dot"></div>';
      messagesEl.appendChild(typingEl);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function hideTyping() {
      if (typingEl) { typingEl.remove(); typingEl = null; }
    }

    function autoResize() {
      inputEl.style.height = "auto";
      inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + "px";
    }

    async function sendMessage() {
      const text = inputEl.value.trim();
      if (!text || isLoading) return;

      isLoading = true;
      sendBtn.disabled = true;
      inputEl.value = "";
      inputEl.style.height = "auto";
      errorEl.style.display = "none";

      appendMessage("user", text, null);
      showTyping();

      const controller = new AbortController();
      const timeoutId = setTimeout(function () { controller.abort(); }, 60000);

      try {
        const body = { message: text };
        if (sessionId) body.session_id = sessionId;

        const res = await fetch(cfg.apiUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-API-Key": cfg.apiKey,
          },
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        clearTimeout(timeoutId);
        hideTyping();

        if (!res.ok) {
          const err = await res.json().catch(function () { return {}; });
          showError(err.detail || "Request failed (" + res.status + ")");
        } else {
          const data = await res.json();
          sessionId = data.session_id;
          appendMessage("bot", data.answer, data.sources);
        }
      } catch (e) {
        clearTimeout(timeoutId);
        hideTyping();
        if (e && e.name === "AbortError") {
          showError("The assistant is taking longer than usual. Please try again.");
        } else {
          showError("Network error — please try again.");
        }
      }

      isLoading = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }

    function clearConversation() {
      if (sessionId) {
        fetch(cfg.apiUrl.replace("/chat", "/session/" + sessionId), {
          method: "DELETE",
          headers: { "X-API-Key": cfg.apiKey },
        }).catch(function () {});
      }
      messagesEl.innerHTML = "";
      sessionId = null;
    }

    // ── Event listeners ──────────────────────────────────────────────────────

    toggle.addEventListener("click", function () { setOpen(!isOpen); });
    closeBtn.addEventListener("click", function () { setOpen(false); });
    clearBtn.addEventListener("click", clearConversation);

    sendBtn.addEventListener("click", sendMessage);

    inputEl.addEventListener("input", autoResize);
    inputEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    // Close on Escape
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && isOpen) setOpen(false);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
