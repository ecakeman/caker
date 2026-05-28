import { checkHealth, chatGraph, deleteSessionRemote, deleteUserRemote, streamChat } from "./api.js";
import {
  createSession,
  fetchSession,
  getActiveSessionIdForUser,
  loadSessionsForUser,
  loadSettings,
  refreshSessionsForUser,
  refreshSettings,
  removeSessionFromCache,
  saveSettings,
  setActiveSessionForUser,
  titleFromMessage,
  upsertSession,
} from "./sessions.js";
import { importLegacy, uploadSessionFiles } from "./store-api.js";
import { addUser, loadUsers, refreshUsers, removeUserLocal } from "./users.js";

/** @type {AbortController | null} */
let abortController = null;

/** @type {import('./sessions.js').ChatSession | null} */
let currentSession = null;

/** @type {string} */
let activeUserId = "local";

let usersExpanded = true;

/** @type {{ relPath: string, filename: string }[]} */
let pendingAttachments = [];

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
  toggleStreaming: $("toggle-streaming"),
  statusDot: $("status-dot"),
  settingsModal: $("settings-modal"),
  btnSettings: $("btn-settings"),
  btnSettingsClose: $("btn-settings-close"),
  settingsStreaming: $("settings-streaming"),
  settingsTheme: $("settings-theme"),
  btnToggleUsers: $("btn-toggle-users"),
  usersChevron: $("users-chevron"),
  userList: $("user-list"),
  inputNewUser: $("input-new-user"),
  btnAddUser: $("btn-add-user"),
  addUserRow: $("add-user-row"),
  btnAttach: $("btn-attach"),
  fileInput: $("file-input"),
  attachmentBar: $("attachment-bar"),
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

function renderMessageContent(el, msg) {
  const isUser = msg.role === "user";
  el.className = "message-content";
  if (isUser) {
    el.classList.add("user-plain");
    el.textContent = msg.content;
    return;
  }
  el.classList.add("md-body");
  const raw = msg.content || "";
  if (typeof marked !== "undefined" && typeof DOMPurify !== "undefined") {
    const html = marked.parse(raw, { async: false });
    el.innerHTML = DOMPurify.sanitize(html);
  } else {
    el.textContent = raw;
  }
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
    renderMessageContent(content, msg);
    bubble.appendChild(content);
    row.appendChild(bubble);
    wrap.appendChild(row);
  }

  els.messages.appendChild(wrap);
  els.messages.scrollTop = els.messages.scrollHeight;
}

function renderUserList() {
  if (!els.userList) return;
  const users = loadUsers();
  els.userList.innerHTML = "";
  els.userList.classList.toggle("hidden", !usersExpanded);

  for (const u of users) {
    const row = document.createElement("div");
    row.className =
      "group flex w-full items-center gap-1 rounded-xl px-2 py-1.5 text-sm " +
      (u.id === activeUserId
        ? "bg-gray-200 dark:bg-gray-800 font-medium"
        : "hover:bg-gray-100 dark:hover:bg-gray-900");

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "flex-1 truncate text-left text-sm";
    btn.textContent = u.id;
    btn.addEventListener("click", () => void selectUser(u.id));

    const del = document.createElement("button");
    del.type = "button";
    del.className =
      "shrink-0 rounded px-1 text-gray-400 opacity-60 hover:text-red-500 hover:opacity-100 group-hover:opacity-100 text-xs";
    del.textContent = "×";
    del.setAttribute("aria-label", "删除用户");
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      void deleteUser(u.id);
    });

    row.appendChild(btn);
    row.appendChild(del);
    els.userList.appendChild(row);
  }
}

function renderChatList() {
  if (!els.chatList) return;
  const sessions = loadSessionsForUser(activeUserId);
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

    const del = document.createElement("button");
    del.type = "button";
    del.className =
      "shrink-0 rounded px-1 text-gray-400 opacity-60 hover:text-red-500 hover:opacity-100 group-hover:opacity-100 text-xs";
    del.textContent = "×";
    del.setAttribute("aria-label", "删除");
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      void deleteSessionWithConfirm(s.id);
    });

    btn.appendChild(title);
    btn.appendChild(del);
    btn.addEventListener("click", () => void selectSession(s.id));
    els.chatList.appendChild(btn);
  }
}

async function selectUser(userId) {
  activeUserId = userId;
  await saveSettings({ activeUserId });
  renderUserList();
  await refreshSessionsForUser(userId);

  const savedSessionId = getActiveSessionIdForUser(userId);
  if (savedSessionId) {
    try {
      await selectSession(savedSessionId);
      return;
    } catch {
      /* session missing on server */
    }
  }

  const sessions = loadSessionsForUser(userId);
  if (sessions.length) await selectSession(sessions[0].id);
  else clearCurrentChat();
}

async function selectSession(id) {
  const s = await fetchSession(activeUserId, id);
  if (!s || s.userId !== activeUserId) return;
  currentSession = s;
  await setActiveSessionForUser(activeUserId, id);
  if (els.chatTitle) els.chatTitle.textContent = s.title;
  renderMessages(s.messages || []);
  renderChatList();
  closeSidebar();
}

function clearCurrentChat() {
  currentSession = null;
  void setActiveSessionForUser(activeUserId, null);
  if (els.chatTitle) els.chatTitle.textContent = "新对话";
  renderMessages([]);
  renderChatList();
}

async function startNewChat() {
  currentSession = await createSession(activeUserId);
  await setActiveSessionForUser(activeUserId, currentSession.id);
  if (els.chatTitle) els.chatTitle.textContent = "新对话";
  renderMessages([]);
  renderChatList();
  closeSidebar();
  els.composer?.focus();
}

async function persistCurrent() {
  if (!currentSession) return;
  const localMessages = currentSession.messages;
  const saved = await upsertSession(currentSession);
  // 保留内存中的 messages 引用，避免流式 onDelta 写到已脱离的旧对象上
  if (localMessages?.length) {
    saved.messages = localMessages;
  }
  currentSession = saved;
  renderChatList();
}

async function deleteSessionWithConfirm(sessionId) {
  if (
    !confirm(
      "删除此对话？将清除服务端聊天记录、checkpoint 与工作区目录。"
    )
  ) {
    return;
  }

  try {
    await deleteSessionRemote(sessionId, activeUserId);
  } catch (err) {
    alert(`删除失败：${err.message || "未知错误"}`);
    return;
  }

  removeSessionFromCache(activeUserId, sessionId);
  if (currentSession?.id === sessionId) {
    const remaining = loadSessionsForUser(activeUserId);
    if (remaining.length) await selectSession(remaining[0].id);
    else clearCurrentChat();
  } else {
    renderChatList();
  }
}

async function deleteUser(userId) {
  const users = loadUsers();
  if (users.length <= 1) {
    alert("至少保留一个用户。");
    return;
  }

  if (
    !confirm(
      `删除用户「${userId}」？将删除该用户全部对话、checkpoint、向量记忆与工作区，且不可恢复。`
    )
  ) {
    return;
  }

  try {
    await deleteUserRemote(userId);
  } catch (err) {
    alert(`删除失败：${err.message || "未知错误"}`);
    return;
  }

  removeUserLocal(userId);
  await refreshUsers();

  if (activeUserId === userId) {
    const next = loadUsers()[0];
    if (next) await selectUser(next.id);
  } else {
    renderUserList();
    renderChatList();
  }
}

async function submitAddUser() {
  const raw = els.inputNewUser?.value ?? "";
  const result = await addUser(raw);
  if (!result.ok) {
    alert(result.error);
    return;
  }
  if (els.inputNewUser) els.inputNewUser.value = "";
  renderUserList();
  await selectUser(result.user.id);
}

function renderAttachmentBar() {
  if (!els.attachmentBar) return;
  els.attachmentBar.innerHTML = "";
  if (!pendingAttachments.length) {
    els.attachmentBar.classList.add("hidden");
    return;
  }
  els.attachmentBar.classList.remove("hidden");
  for (const att of pendingAttachments) {
    const chip = document.createElement("span");
    chip.className =
      "inline-flex items-center gap-1 rounded-lg bg-gray-100 px-2 py-1 text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-200";
    const label = document.createElement("span");
    label.textContent = att.filename;
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "text-gray-400 hover:text-gray-700 dark:hover:text-gray-200";
    rm.textContent = "×";
    rm.addEventListener("click", () => {
      pendingAttachments = pendingAttachments.filter((a) => a.relPath !== att.relPath);
      renderAttachmentBar();
    });
    chip.appendChild(label);
    chip.appendChild(rm);
    els.attachmentBar.appendChild(chip);
  }
}

async function handleFilesSelected(fileList) {
  if (!fileList?.length) return;
  if (!currentSession) await startNewChat();
  if (!currentSession) return;
  if (!activeUserId?.trim()) {
    alert("请先选择或添加用户");
    return;
  }
  try {
    const data = await uploadSessionFiles(activeUserId, currentSession.id, fileList);
    for (const f of data.files ?? []) {
      if (!pendingAttachments.some((a) => a.relPath === f.rel_path)) {
        pendingAttachments.push({ relPath: f.rel_path, filename: f.filename });
      }
    }
    if (data.errors?.length) {
      alert(`部分文件未上传：\n${data.errors.join("\n")}`);
    }
    renderAttachmentBar();
  } catch (err) {
    alert(`上传失败：${err.message || "未知错误"}`);
  }
  if (els.fileInput) els.fileInput.value = "";
}

async function sendMessage() {
  const text = els.composer?.value.trim() ?? "";
  const attachmentPaths = pendingAttachments.map((a) => a.relPath);
  if (!text && !attachmentPaths.length) return;
  if (!currentSession) await startNewChat();
  if (!currentSession) return;

  if (!activeUserId?.trim()) {
    alert("请先选择或添加用户");
    return;
  }

  currentSession.userId = activeUserId;

  let displayContent = text;
  if (attachmentPaths.length) {
    const lines = attachmentPaths.map((p) => `[文件] ${p}`);
    displayContent = text ? `${text}\n${lines.join("\n")}` : lines.join("\n");
  }

  const userMsg = { role: "user", content: displayContent, ts: Date.now() };
  currentSession.messages = currentSession.messages || [];
  currentSession.messages.push(userMsg);
  if (currentSession.messages.filter((m) => m.role === "user").length === 1) {
    currentSession.title = titleFromMessage(text || attachmentPaths[0] || "附件");
    if (els.chatTitle) els.chatTitle.textContent = currentSession.title;
  }

  currentSession.messages.push({
    role: "assistant",
    content: "",
    ts: Date.now(),
  });
  const assistantIdx = currentSession.messages.length - 1;
  els.composer.value = "";
  pendingAttachments = [];
  renderAttachmentBar();
  autoResizeComposer();
  renderMessages(currentSession.messages);
  await persistCurrent();

  const body = {
    message: text,
    session_id: currentSession.id,
    attachments: attachmentPaths,
  };
  const settings = loadSettings();
  const streaming = els.toggleStreaming?.checked ?? settings.streaming;

  abortController = new AbortController();
  setGenerating(true);

  const assistant = () => currentSession.messages[assistantIdx];

  try {
    if (streaming) {
      await streamChat(body, {
        userId: activeUserId,
        signal: abortController.signal,
        onDelta: (chunk) => {
          assistant().content += chunk;
          renderMessages(currentSession.messages);
        },
      });
    } else {
      assistant().content = await chatGraph(body, {
        userId: activeUserId,
        signal: abortController.signal,
      });
      renderMessages(currentSession.messages);
    }
  } catch (err) {
    const msg = assistant();
    if (err.name === "AbortError") {
      if (!msg.content) msg.content = "（已停止）";
    } else {
      msg.content = msg.content || `请求失败：${err.message || "未知错误"}`;
    }
    renderMessages(currentSession.messages);
  } finally {
    abortController = null;
    setGenerating(false);
    await persistCurrent();
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

async function syncSettingsFromModal() {
  const streaming = els.settingsStreaming?.checked ?? true;
  const theme = /** @type {'system'|'light'|'dark'} */ (
    els.settingsTheme?.value || "system"
  );
  await saveSettings({ streaming, theme });
  if (els.toggleStreaming) els.toggleStreaming.checked = streaming;
  applyTheme(theme);
}

function toggleUsersPanel() {
  usersExpanded = !usersExpanded;
  if (els.usersChevron) els.usersChevron.textContent = usersExpanded ? "▼" : "▶";
  els.userList?.classList.toggle("hidden", !usersExpanded);
  els.addUserRow?.classList.toggle("hidden", !usersExpanded);
  renderUserList();
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

async function importLegacyFromBrowserIfNeeded() {
  const sessionsKey = "caker.web.sessions";
  const usersKey = "caker.web.users";
  const settingsKey = "caker.web.settings";
  if (!localStorage.getItem(sessionsKey) && !localStorage.getItem(usersKey)) {
    return;
  }
  try {
    const sessions = JSON.parse(localStorage.getItem(sessionsKey) || "[]");
    const users = JSON.parse(localStorage.getItem(usersKey) || "[]");
    const settings = JSON.parse(localStorage.getItem(settingsKey) || "null");
    await importLegacy({ sessions, users, settings: settings || undefined });
    localStorage.removeItem(sessionsKey);
    localStorage.removeItem(usersKey);
    localStorage.removeItem(settingsKey);
  } catch (e) {
    console.warn("legacy import failed", e);
  }
}

async function boot() {
  try {
    await importLegacyFromBrowserIfNeeded();
    await refreshSettings();
    await refreshUsers();

    const settings = loadSettings();
    applyTheme(settings.theme);
    if (els.toggleStreaming) els.toggleStreaming.checked = settings.streaming;

    activeUserId = settings.activeUserId;
    const users = loadUsers();
    if (!users.some((u) => u.id === activeUserId)) {
      activeUserId = users[0]?.id || "local";
      await saveSettings({ activeUserId });
    }

    await refreshSessionsForUser(activeUserId);

    els.btnNewChat?.addEventListener("click", () => void startNewChat());
    els.btnSend?.addEventListener("click", () => void sendMessage());
    els.btnStop?.addEventListener("click", stopGeneration);
    els.btnOpenSidebar?.addEventListener("click", openSidebar);
    els.btnCloseSidebar?.addEventListener("click", closeSidebar);
    els.sidebarOverlay?.addEventListener("click", closeSidebar);
    els.btnToggleUsers?.addEventListener("click", toggleUsersPanel);
    els.btnAddUser?.addEventListener("click", () => void submitAddUser());
    els.inputNewUser?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        void submitAddUser();
      }
    });

    els.btnAttach?.addEventListener("click", () => els.fileInput?.click());
    els.fileInput?.addEventListener("change", () => {
      void handleFilesSelected(els.fileInput?.files);
    });

    els.composer?.addEventListener("input", autoResizeComposer);
    els.composer?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void sendMessage();
      }
    });

    els.toggleStreaming?.addEventListener("change", () => {
      void saveSettings({ streaming: els.toggleStreaming.checked }).then(() => {
        if (els.settingsStreaming) {
          els.settingsStreaming.checked = els.toggleStreaming.checked;
        }
      });
    });

    els.btnSettings?.addEventListener("click", openSettings);
    els.btnSettingsClose?.addEventListener("click", () => {
      void syncSettingsFromModal().then(closeSettings);
    });
    els.settingsStreaming?.addEventListener("change", () => void syncSettingsFromModal());
    els.settingsTheme?.addEventListener("change", () => void syncSettingsFromModal());
    els.settingsModal?.addEventListener("click", (e) => {
      if (e.target === els.settingsModal) {
        void syncSettingsFromModal().then(closeSettings);
      }
    });

    renderUserList();

    const savedSessionId = getActiveSessionIdForUser(activeUserId);
    if (savedSessionId) {
      try {
        await selectSession(savedSessionId);
      } catch {
        const userSessions = loadSessionsForUser(activeUserId);
        if (userSessions.length) await selectSession(userSessions[0].id);
        else clearCurrentChat();
      }
    } else {
      const userSessions = loadSessionsForUser(activeUserId);
      if (userSessions.length) await selectSession(userSessions[0].id);
      else clearCurrentChat();
    }

    initHealth();
    setInterval(initHealth, 30000);
  } catch (err) {
    alert(`加载失败：${err.message || "无法连接服务端"}`);
    console.error(err);
  }
}

void boot();
