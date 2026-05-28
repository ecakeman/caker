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
import {
  fetchWorkspace,
  importLegacy,
  revealWorkspace,
  uploadSessionFiles,
} from "./store-api.js";
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
  attachmentChips: $("attachment-chips"),
  attachmentHint: $("attachment-hint"),
  streamStatus: $("stream-status"),
  workspaceStatus: $("workspace-status"),
  workspaceMeta: $("workspace-meta"),
  workspaceSessionPath: $("workspace-session-path"),
  workspaceFileCount: $("workspace-file-count"),
  workspaceFileList: $("workspace-file-list"),
  workspaceHint: $("workspace-hint"),
  btnCopyWorkspace: $("btn-copy-workspace"),
  btnOpenWorkspace: $("btn-open-workspace"),
};

/** @type {{ session_path?: string, workspace_root?: string, files?: { rel_path: string, filename: string }[] } | null} */
let workspaceInfo = null;

const FILE_ICON_SVG = `<svg class="h-4 w-4 shrink-0 text-gray-500 dark:text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>`;

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
  if (!on) setStreamStatus("");
}

function setStreamStatus(text) {
  if (!els.streamStatus) return;
  const t = (text || "").trim();
  els.streamStatus.textContent = t;
  els.streamStatus.classList.toggle("hidden", !t);
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

function formatBytes(n) {
  if (!n || n < 1024) return `${n || 0} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function renderWorkspaceMeta(userId, sessionId) {
  if (!els.workspaceMeta) return;
  els.workspaceMeta.replaceChildren();
  const userLine = document.createElement("p");
  userLine.textContent = `用户 ${userId}`;
  const sessionLine = document.createElement("p");
  sessionLine.className = "truncate font-mono text-[10px] text-gray-500 dark:text-gray-400";
  sessionLine.title = sessionId;
  sessionLine.textContent = `会话 ${sessionId}`;
  els.workspaceMeta.append(userLine, sessionLine);
}

function workspacePathForClipboard() {
  return workspaceInfo?.session_path_windows || workspaceInfo?.session_path || "";
}

function workspacePathTitle() {
  const linux = workspaceInfo?.session_path || "";
  const win = workspaceInfo?.session_path_windows;
  if (linux && win) {
    return `WSL: ${linux}\nWindows 资源管理器: ${win}`;
  }
  return linux;
}

function setWorkspacePanelLoading() {
  if (els.workspaceStatus) {
    els.workspaceStatus.textContent = "加载中";
    els.workspaceStatus.className =
      "rounded-md px-1.5 py-0.5 text-[10px] font-medium text-amber-700 bg-amber-50 dark:text-amber-200 dark:bg-amber-950/50";
  }
  if (els.btnCopyWorkspace) els.btnCopyWorkspace.disabled = true;
  if (els.btnOpenWorkspace) els.btnOpenWorkspace.disabled = true;
}

function setWorkspacePanelIdle() {
  workspaceInfo = null;
  if (els.workspaceStatus) {
    els.workspaceStatus.textContent = "未选择";
    els.workspaceStatus.className =
      "rounded-md px-1.5 py-0.5 text-[10px] font-medium text-gray-400 bg-gray-100 dark:bg-gray-800";
  }
  if (els.workspaceMeta) {
    els.workspaceMeta.innerHTML =
      "<p>选择或新建对话后，将显示用户与会话。</p>";
  }
  if (els.workspaceSessionPath) {
    els.workspaceSessionPath.textContent = "（尚无工作目录）";
    els.workspaceSessionPath.title = "";
    els.workspaceSessionPath.disabled = true;
  }
  if (els.workspaceFileCount) els.workspaceFileCount.textContent = "";
  if (els.workspaceFileList) {
    els.workspaceFileList.innerHTML = "";
    els.workspaceFileList.classList.add("hidden");
  }
  if (els.btnCopyWorkspace) els.btnCopyWorkspace.disabled = true;
  if (els.btnOpenWorkspace) els.btnOpenWorkspace.disabled = true;
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
}

async function refreshWorkspacePanel() {
  if (!activeUserId || !currentSession?.id) {
    setWorkspacePanelIdle();
    return;
  }

  setWorkspacePanelLoading();
  try {
    workspaceInfo = await fetchWorkspace(activeUserId, currentSession.id);
    const path = workspaceInfo.session_path || "";
    const rel = workspaceInfo.session_rel || path;
    const files = workspaceInfo.files || [];
    const uploads = files.filter((f) => f.rel_path?.startsWith("data/uploads/"));

    if (els.workspaceStatus) {
      els.workspaceStatus.textContent = "已就绪";
      els.workspaceStatus.className =
        "rounded-md px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 bg-emerald-50 dark:text-emerald-200 dark:bg-emerald-950/40";
    }
    renderWorkspaceMeta(activeUserId, currentSession.id);
    if (els.workspaceSessionPath) {
      els.workspaceSessionPath.textContent = rel;
      els.workspaceSessionPath.title = workspacePathTitle();
      els.workspaceSessionPath.disabled = !path;
    }
    if (els.workspaceFileCount) {
      if (uploads.length) {
        const total = uploads.reduce((s, f) => s + (f.bytes || 0), 0);
        els.workspaceFileCount.textContent = `已上传 ${uploads.length} 个文件（约 ${formatBytes(total)}），位于 data/uploads/`;
      } else if (files.length) {
        els.workspaceFileCount.textContent = `目录内有 ${files.length} 个文件，尚无 uploads；请用输入框左侧 + 上传`;
      } else {
        els.workspaceFileCount.textContent = "目录为空；用输入框左侧 + 将文件保存到 data/uploads/";
      }
    }
    if (els.workspaceHint && workspaceInfo.hint) {
      els.workspaceHint.textContent = workspaceInfo.hint;
    }
    if (els.workspaceFileList) {
      els.workspaceFileList.innerHTML = "";
      const show = uploads.length ? uploads : files.slice(0, 8);
      if (show.length) {
        els.workspaceFileList.classList.remove("hidden");
        for (const f of show) {
          const li = document.createElement("li");
          li.className = "truncate font-mono";
          li.textContent = `${f.rel_path} (${formatBytes(f.bytes)})`;
          li.title = f.rel_path;
          els.workspaceFileList.appendChild(li);
        }
        if (files.length > show.length) {
          const more = document.createElement("li");
          more.textContent = `… 另有 ${files.length - show.length} 个文件`;
          els.workspaceFileList.appendChild(more);
        }
      } else {
        els.workspaceFileList.classList.add("hidden");
      }
    }
    if (els.btnCopyWorkspace) els.btnCopyWorkspace.disabled = !path;
    if (els.btnOpenWorkspace) els.btnOpenWorkspace.disabled = !path;
    syncPendingFromWorkspaceFiles(uploads);
  } catch (err) {
    workspaceInfo = null;
    if (els.workspaceStatus) {
      els.workspaceStatus.textContent = "失败";
      els.workspaceStatus.className =
        "rounded-md px-1.5 py-0.5 text-[10px] font-medium text-red-700 bg-red-50 dark:text-red-200 dark:bg-red-950/40";
    }
    if (els.workspaceMeta) {
      els.workspaceMeta.textContent = "无法加载工作区。若提示 Not Found，请重启 uvicorn 后再刷新页面。";
    }
    if (els.workspaceSessionPath) {
      els.workspaceSessionPath.textContent = err.message || "加载失败";
      els.workspaceSessionPath.title = "";
      els.workspaceSessionPath.disabled = true;
    }
    if (els.workspaceFileCount) els.workspaceFileCount.textContent = "";
    if (els.workspaceFileList) {
      els.workspaceFileList.innerHTML = "";
      els.workspaceFileList.classList.add("hidden");
    }
    if (els.btnCopyWorkspace) els.btnCopyWorkspace.disabled = true;
    if (els.btnOpenWorkspace) els.btnOpenWorkspace.disabled = true;
  }
}

async function copyWorkspacePath() {
  const path = workspacePathForClipboard();
  if (!path) return;
  try {
    await copyTextToClipboard(path);
    const label = workspaceInfo?.session_path_windows ? "已复制 Windows 路径" : "已复制工作区路径";
    setStreamStatus(label);
    window.setTimeout(() => setStreamStatus(""), 2200);
  } catch {
    alert(path);
  }
}

async function openWorkspaceFolder() {
  if (!activeUserId || !currentSession?.id || !workspaceInfo?.session_path) return;
  try {
    setStreamStatus("正在打开资源管理器…");
    const data = await revealWorkspace(activeUserId, currentSession.id);
    if (data.session_path_windows) {
      workspaceInfo.session_path_windows = data.session_path_windows;
      if (els.workspaceSessionPath) {
        els.workspaceSessionPath.title = workspacePathTitle();
      }
    }
    const shown = data.session_path_windows || data.session_path || "";
    setStreamStatus(`已在资源管理器中打开：${shown}`);
    window.setTimeout(() => setStreamStatus(""), 3500);
  } catch (err) {
    setStreamStatus("");
    const win = workspaceInfo?.session_path_windows;
    const linux = workspaceInfo?.session_path;
    const fallback = win
      ? `无法自动打开：${err.message || "未知错误"}\n\n请手动在资源管理器地址栏粘贴：\n${win}`
      : `无法自动打开：${err.message || "未知错误"}\n\n请确认服务运行在 WSL 内，且已安装 explorer.exe / wslpath。\n\nWSL 路径：\n${linux}`;
    try {
      await copyTextToClipboard(win || linux || "");
      alert(`${fallback}\n\n（路径已复制到剪贴板）`);
    } catch {
      alert(fallback);
    }
  }
}

/** @param {{ rel_path: string, filename: string }[]} serverFiles */
function syncPendingFromWorkspaceFiles(serverFiles) {
  const uploads = serverFiles.filter((f) => f.rel_path.startsWith("data/uploads/"));
  if (!uploads.length) return;
  for (const f of uploads) {
    if (!pendingAttachments.some((a) => a.relPath === f.rel_path)) {
      pendingAttachments.push({ relPath: f.rel_path, filename: f.filename });
    }
  }
  renderAttachmentBar();
}

async function selectSession(id) {
  const s = await fetchSession(activeUserId, id);
  if (!s || s.userId !== activeUserId) return;
  currentSession = s;
  await setActiveSessionForUser(activeUserId, id);
  if (els.chatTitle) els.chatTitle.textContent = s.title;
  renderMessages(s.messages || []);
  renderChatList();
  await refreshWorkspacePanel();
  closeSidebar();
}

function clearCurrentChat() {
  currentSession = null;
  pendingAttachments = [];
  renderAttachmentBar();
  void setActiveSessionForUser(activeUserId, null);
  if (els.chatTitle) els.chatTitle.textContent = "新对话";
  renderMessages([]);
  renderChatList();
  void refreshWorkspacePanel();
}

async function startNewChat() {
  currentSession = await createSession(activeUserId);
  await setActiveSessionForUser(activeUserId, currentSession.id);
  if (els.chatTitle) els.chatTitle.textContent = "新对话";
  renderMessages([]);
  renderChatList();
  await refreshWorkspacePanel();
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
    void refreshWorkspacePanel();
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

function setAttachBusy(busy) {
  if (els.btnAttach) {
    els.btnAttach.disabled = busy;
    els.btnAttach.setAttribute("aria-busy", busy ? "true" : "false");
  }
}

function renderAttachmentBar() {
  if (!els.attachmentBar || !els.attachmentChips) return;
  els.attachmentChips.innerHTML = "";
  if (!pendingAttachments.length) {
    els.attachmentBar.classList.add("hidden");
    return;
  }
  els.attachmentBar.classList.remove("hidden");
  if (els.attachmentHint) {
    els.attachmentHint.textContent =
      `已保存到工作区（${pendingAttachments.length} 个文件），发送后 Agent 可用 read 读取`;
  }

  for (const att of pendingAttachments) {
    const chip = document.createElement("div");
    chip.className =
      "attachment-chip inline-flex max-w-full items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 py-1.5 pl-2 pr-1 text-left dark:border-gray-700 dark:bg-gray-850/80";
    chip.innerHTML = FILE_ICON_SVG;

    const textWrap = document.createElement("div");
    textWrap.className = "min-w-0 flex-1";
    const name = document.createElement("div");
    name.className = "truncate text-sm font-medium text-gray-800 dark:text-gray-100";
    name.textContent = att.filename;
    name.title = att.filename;
    const path = document.createElement("div");
    path.className = "truncate text-xs text-gray-500 dark:text-gray-400";
    path.textContent = att.relPath;
    path.title = att.relPath;
    textWrap.appendChild(name);
    textWrap.appendChild(path);
    chip.appendChild(textWrap);

    const rm = document.createElement("button");
    rm.type = "button";
    rm.className =
      "shrink-0 rounded-lg p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-700 dark:hover:bg-gray-800 dark:hover:text-gray-200";
    rm.setAttribute("aria-label", `移除 ${att.filename}`);
    rm.innerHTML =
      '<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>';
    rm.addEventListener("click", () => {
      pendingAttachments = pendingAttachments.filter((a) => a.relPath !== att.relPath);
      renderAttachmentBar();
    });
    chip.appendChild(rm);
    els.attachmentChips.appendChild(chip);
  }
}

async function handleFilesSelected(fileList) {
  if (!fileList?.length) return;
  if (!activeUserId?.trim()) {
    alert("请先选择或添加用户");
    return;
  }

  if (!currentSession) {
    await startNewChat();
  }
  if (!currentSession) return;

  currentSession.userId = activeUserId;
  setAttachBusy(true);
  setStreamStatus("正在上传到工作区…");

  try {
    const data = await uploadSessionFiles(activeUserId, currentSession.id, fileList);
    let added = 0;
    for (const f of data.files ?? []) {
      if (!pendingAttachments.some((a) => a.relPath === f.rel_path)) {
        pendingAttachments.push({
          relPath: f.rel_path,
          filename: f.filename,
          bytes: f.bytes,
        });
        added += 1;
      }
    }
    renderAttachmentBar();
    await refreshWorkspacePanel();
    if (data.verify && !data.verify.ok && (data.files?.length ?? 0) > 0) {
      alert(`上传校验失败，以下路径不可用：\n${(data.verify.missing || []).join("\n")}`);
    }
    if (added > 0) {
      setStreamStatus(`已加入工作区 ${added} 个文件`);
      window.setTimeout(() => {
        if (els.streamStatus?.textContent?.startsWith("已加入工作区")) {
          setStreamStatus("");
        }
      }, 2800);
    } else {
      setStreamStatus("");
    }
    if (data.errors?.length) {
      alert(`部分文件未上传：\n${data.errors.join("\n")}`);
    }
    els.composer?.focus();
  } catch (err) {
    setStreamStatus("");
    alert(`上传失败：${err.message || "未知错误"}`);
  } finally {
    setAttachBusy(false);
    if (els.fileInput) els.fileInput.value = "";
  }
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

  if (attachmentPaths.length) {
    try {
      const ws = await fetchWorkspace(activeUserId, currentSession.id);
      const missing = attachmentPaths.filter(
        (p) => !(ws.files || []).some((f) => f.rel_path === p)
      );
      if (missing.length) {
        alert(
          `以下文件不在当前工作区，请重新用 + 上传：\n${missing.join("\n")}\n\n工作区：${ws.session_path}`
        );
        return;
      }
    } catch (err) {
      alert(`无法校验附件：${err.message || "未知错误"}`);
      return;
    }
  }

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
        onStatus: (payload) => {
          const detail = payload?.detail || payload?.tool || payload?.phase || "";
          setStreamStatus(detail);
        },
        onDelta: (chunk) => {
          setStreamStatus("");
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

    els.btnCopyWorkspace?.addEventListener("click", () => void copyWorkspacePath());
    els.btnOpenWorkspace?.addEventListener("click", () => openWorkspaceFolder());
    els.workspaceSessionPath?.addEventListener("click", () => {
      if (!els.workspaceSessionPath?.disabled) openWorkspaceFolder();
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
    void refreshWorkspacePanel();

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
