import { checkHealth, chatGraph, streamChat } from "./api.js";
import {
  createSession,
  deleteSession,
  getSession,
  loadSessions,
  loadSettings,
  saveSettings,
  titleFromMessage,
  upsertSession,
} from "./sessions.js";

/** @type {AbortController | null} */
let abortController = null;

/** @type {import('./sessions.js').ChatSession | null} */
let currentSession = null;

const $ = (id) => document.getElementById(id);

const els = {
  healthBanner: $("health-banner"),
  sidebar: $("sidebar"),
  sidebarOverlay: $("sidebar-overlay"),
  chatList: $("chat-list"),
  messages: $("messages"),
  emptyState: $("empty-state"),
  chatTitle: $("chat-title"),
  composer: $("composer"),
  btnSend: $("btn-send"),
  btnStop: $("btn-stop"),
  btnNewChat: $("btn-new-chat"),
  btnOpenSidebar: $("btn-open-sidebar"),
  btnCloseSidebar: $("btn-close-sidebar"),
  inputUserId: $("input-user-id"),
  toggleStreaming: $("toggle-streaming"),
  statusDot: $("status-dot"),
  settingsModal: $("settings-modal"),
  btnSettings: $("btn-settings"),
  btnSettingsClose: $("btn-settings-close"),
  settingsStreaming: $("settings-streaming"),
  settingsTheme: $("settings-theme"),
};

function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "dark") root.classList.add("dark");
  else if (theme === "light") root.classList.remove("dark");
  else {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    root.classList.toggle("dark", prefersDark);
  }
}

function openSidebar() {
  els.sidebar?.classList.remove("-translate-x-full");
  els.sidebarOverlay?.classList.remove("hidden");
}

function closeSidebar() {
  els.sidebar?.classList.add("-translate-x-full");
  els.sidebarOverlay?.classList.add("hidden");
}

function setGenerating(on) {
  if (els.btnSend) els.btnSend.disabled = on;
  if (els.composer) els.composer.disabled = on;
  els.btnStop?.classList.toggle("hidden", !on);
  els.btnSend?.classList.toggle("hidden", on);
}

function escapeHtml(text) {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

/** @param {import('./sessions.js').Message[]} messages */
function renderMessages(messages) {
  if (!els.messages) return;
  els.messages.innerHTML = "";
  if (!messages.length) {
    els.emptyState?.classList.remove("hidden");
    return;
  }
  els.emptyState?.classList.add("hidden");

  const wrap = document.createElement("div");
  wrap.className = "mx-auto max-w-3xl space-y-4";

  for (const msg of messages) {
    const isUser = msg.role === "user";
    const row = document.createElement("div");
    row.className = `flex ${isUser ? "justify-end" : "justify-start"}`;

    const bubble = document.createElement("div");
    bubble.className = isUser
      ? "max-w-[85%] rounded-2xl rounded-br-md bg-gray-900 px-4 py-2.5 text-sm text-white dark:bg-gray-100 dark:text-gray-900"
      : "max-w-[85%] rounded-2xl rounded-bl-md bg-gray-100 px-4 py-2.5 text-sm text-gray-900 dark:bg-gray-850 dark:text-gray-100";

    const content = document.createElement("div");
    content.className = "message-content";
    content.innerHTML = escapeHtml(msg.content);
    bubble.appendChild(content);
    row.appendChild(bubble);
    wrap.appendChild(row);
  }

  els.messages.appendChild(wrap);
  els.messages.scrollTop = els.messages.scrollHeight;
}

function renderChatList() {
  if (!els.chatList) return;
  const sessions = loadSessions();
  const activeId = currentSession?.id;
  els.chatList.innerHTML = "";

  if (!sessions.length) {
    const empty = document.createElement("p");
    empty.className = "px-3 py-2 text-xs text-gray-400";
    empty.textContent = "暂无历史对话";
    els.chatList.appendChild(empty);
    return;
  }

  for (const s of sessions) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "group flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-900 " +
      (s.id === activeId ? "bg-gray-100 dark:bg-gray-900" : "");

    const title = document.createElement("span");
    title.className = "flex-1 truncate";
    title.textContent = s.title;

    const del = document.createElement("span");
    del.className =
      "hidden group-hover:inline text-gray-400 hover:text-red-500 text-xs px-1";
    del.textContent = "×";
    del.setAttribute("role", "button");
    del.setAttribute("aria-label", "删除");
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!confirm("删除此对话？（仅本地记录）")) return;
      deleteSession(s.id);
      if (currentSession?.id === s.id) {
        startNewChat();
      } else {
        renderChatList();
      }
    });

    btn.appendChild(title);
    btn.appendChild(del);
    btn.addEventListener("click", () => selectSession(s.id));
    els.chatList.appendChild(btn);
  }
}

function selectSession(id) {
  const s = getSession(id);
  if (!s) return;
  currentSession = s;
  saveSettings({ activeId: id });
  if (els.chatTitle) els.chatTitle.textContent = s.title;
  renderMessages(s.messages);
  renderChatList();
  closeSidebar();
}

function startNewChat() {
  const settings = loadSettings();
  const userId = els.inputUserId?.value.trim() || settings.userId || "local";
  currentSession = createSession(userId);
  upsertSession(currentSession);
  saveSettings({ activeId: currentSession.id });
  if (els.chatTitle) els.chatTitle.textContent = "新对话";
  renderMessages([]);
  renderChatList();
  closeSidebar();
  els.composer?.focus();
}

function persistCurrent() {
  if (!currentSession) return;
  upsertSession(currentSession);
  renderChatList();
}

async function sendMessage() {
  const text = els.composer?.value.trim();
  if (!text || !currentSession) return;

  const settings = loadSettings();
  const userId = els.inputUserId?.value.trim() || settings.userId || "local";
  currentSession.userId = userId;
  saveSettings({ userId });

  const userMsg = { role: "user", content: text, ts: Date.now() };
  currentSession.messages.push(userMsg);
  if (currentSession.messages.filter((m) => m.role === "user").length === 1) {
    currentSession.title = titleFromMessage(text);
    if (els.chatTitle) els.chatTitle.textContent = currentSession.title;
  }

  const assistantMsg = { role: "assistant", content: "", ts: Date.now() };
  currentSession.messages.push(assistantMsg);
  els.composer.value = "";
  autoResizeComposer();
  renderMessages(currentSession.messages);
  persistCurrent();

  const body = { message: text, session_id: currentSession.id };
  const streaming = els.toggleStreaming?.checked ?? settings.streaming;

  abortController = new AbortController();
  setGenerating(true);

  try {
    if (streaming) {
      await streamChat(body, {
        userId,
        signal: abortController.signal,
        onDelta: (chunk) => {
          assistantMsg.content += chunk;
          renderMessages(currentSession.messages);
        },
      });
    } else {
      assistantMsg.content = await chatGraph(body, {
        userId,
        signal: abortController.signal,
      });
      renderMessages(currentSession.messages);
    }
  } catch (err) {
    if (err.name === "AbortError") {
      if (!assistantMsg.content) assistantMsg.content = "（已停止）";
    } else {
      assistantMsg.content =
        assistantMsg.content || `请求失败：${err.message || "未知错误"}`;
    }
    renderMessages(currentSession.messages);
  } finally {
    abortController = null;
    setGenerating(false);
    persistCurrent();
    els.composer?.focus();
  }
}

function stopGeneration() {
  abortController?.abort();
}

function autoResizeComposer() {
  if (!els.composer) return;
  els.composer.style.height = "auto";
  els.composer.style.height = `${Math.min(els.composer.scrollHeight, 160)}px`;
}

function openSettings() {
  const s = loadSettings();
  if (els.settingsStreaming) els.settingsStreaming.checked = s.streaming;
  if (els.settingsTheme) els.settingsTheme.value = s.theme;
  els.settingsModal?.classList.remove("hidden");
  els.settingsModal?.classList.add("flex");
}

function closeSettings() {
  els.settingsModal?.classList.add("hidden");
  els.settingsModal?.classList.remove("flex");
}

function syncSettingsFromModal() {
  const streaming = els.settingsStreaming?.checked ?? true;
  const theme = /** @type {'system'|'light'|'dark'} */ (
    els.settingsTheme?.value || "system"
  );
  saveSettings({ streaming, theme });
  if (els.toggleStreaming) els.toggleStreaming.checked = streaming;
  applyTheme(theme);
}

async function initHealth() {
  try {
    const ok = await checkHealth();
    els.statusDot?.classList.toggle("bg-green-500", ok);
    els.statusDot?.classList.toggle("bg-gray-300", !ok);
    els.statusDot?.classList.toggle("dark:bg-green-600", ok);
    els.healthBanner?.classList.toggle("hidden", ok);
  } catch {
    els.statusDot?.classList.remove("bg-green-500");
    els.healthBanner?.classList.remove("hidden");
  }
}

function boot() {
  const settings = loadSettings();
  applyTheme(settings.theme);
  if (els.inputUserId) els.inputUserId.value = settings.userId;
  if (els.toggleStreaming) els.toggleStreaming.checked = settings.streaming;

  els.btnNewChat?.addEventListener("click", startNewChat);
  els.btnSend?.addEventListener("click", sendMessage);
  els.btnStop?.addEventListener("click", stopGeneration);
  els.btnOpenSidebar?.addEventListener("click", openSidebar);
  els.btnCloseSidebar?.addEventListener("click", closeSidebar);
  els.sidebarOverlay?.addEventListener("click", closeSidebar);

  els.composer?.addEventListener("input", autoResizeComposer);
  els.composer?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  els.inputUserId?.addEventListener("change", () => {
    saveSettings({ userId: els.inputUserId.value.trim() || "local" });
  });

  els.toggleStreaming?.addEventListener("change", () => {
    saveSettings({ streaming: els.toggleStreaming.checked });
    if (els.settingsStreaming) {
      els.settingsStreaming.checked = els.toggleStreaming.checked;
    }
  });

  els.btnSettings?.addEventListener("click", openSettings);
  els.btnSettingsClose?.addEventListener("click", () => {
    syncSettingsFromModal();
    closeSettings();
  });
  els.settingsStreaming?.addEventListener("change", syncSettingsFromModal);
  els.settingsTheme?.addEventListener("change", syncSettingsFromModal);
  els.settingsModal?.addEventListener("click", (e) => {
    if (e.target === els.settingsModal) {
      syncSettingsFromModal();
      closeSettings();
    }
  });

  const sessions = loadSessions();
  if (settings.activeId && getSession(settings.activeId)) {
    selectSession(settings.activeId);
  } else if (sessions.length) {
    selectSession(sessions[0].id);
  } else {
    startNewChat();
  }

  initHealth();
  setInterval(initHealth, 30000);
}

boot();
