import {
  approveExec,
  chatGraph,
  fetchExecPending,
  regenerateSession,
  rejectExec,
  streamChat,
} from "./api.js";
import {
  autoResizeComposer,
  createStreamingMarkdownPainter,
  mountComposer,
  renderMessages,
  setStreamStatus,
} from "./chat-ui.js";
import {
  bindWorkspaceDrag,
  createComposerFileRefs,
} from "./composer-file-ref.js";
import { createWorkspaceContextMenu } from "./workspace-context-menu.js";
import { openSessionLogsViewer } from "./logs-viewer.js";
import { fetchSession, loadSettings, refreshSessionTitle, refreshSettings, upsertSession } from "./sessions.js";
import {
  composeDown,
  composeUp,
  fetchComposeStatus,
  fetchWorkspaceFile,
  fetchWorkspaceTree,
  saveWorkspaceFile,
  workspaceCopy,
  workspaceDeleteEntry,
  workspaceMkdir,
  workspaceMove,
} from "./store-api.js";
import { initSplitPanes, resetSplitLayout } from "./split-panes.js";

const params = new URLSearchParams(window.location.search);
const userId = params.get("user_id") || "local";
const sessionId = params.get("session_id") || "";

const titleEl = document.getElementById("sandbox-title");
const statusEl = document.getElementById("terminal-status");
const treeEl = document.getElementById("file-tree");
const editorPathEl = document.getElementById("editor-path");
const editorDirtyEl = document.getElementById("editor-dirty");
const btnSaveFile = document.getElementById("btn-save-file");
const editorHostEl = document.getElementById("code-editor-host");
const messagesEl = document.getElementById("chat-messages");
const btnExit = document.getElementById("btn-exit");
const btnLogs = document.getElementById("btn-logs");
const btnComposeUp = document.getElementById("btn-compose-up");
const btnComposeDown = document.getElementById("btn-compose-down");
const composeStatusEl = document.getElementById("compose-status");
const terminalHost = document.getElementById("terminal-host");
const composerMount = document.getElementById("composer-mount");

/** @type {import('./sessions.js').ChatSession | null} */
let currentSession = null;
/** @type {string | null} */
let selectedFilePath = null;
/** @type {AbortController | null} */
let abortController = null;
/** @type {Array<{ path: string, type: string }> | null} */
let treeEntriesCache = null;
/** @type {Set<string>} */
const expandedDirs = new Set(["data", "outputs", "compose"]);
/** @type {Map<string, { dirs: string[], files: { path: string, name: string }[] }> | null} */
let treeIndex = null;

/** @type {CodeMirror.Editor | null} */
let codeEditor = null;
let editorDirty = false;
let savingFile = false;

/** @type {import('@xterm/xterm').Terminal | null} */
let term = null;
/** @type {WebSocket | null} */
let ws = null;
/** @type {import('@xterm/addon-fit').FitAddon | null} */
let fitAddon = null;
let fitTimer = null;
let resizeObserver = null;

/** @type {HTMLElement | null} */
let assistantBubbleEl = null;

/** @type {ReturnType<typeof createComposerFileRefs> | null} */
let composerFileRefs = null;

/** @type {ReturnType<typeof createWorkspaceContextMenu> | null} */
let workspaceMenu = null;

let composeBusy = false;

/** @type {ReturnType<typeof mountComposer> | null} */
let composerUi = null;

/** @type {boolean} */
let agentTurnBusy = false;

/** @type {Set<string>} */
const promptedPendingIds = new Set();

function editorTheme() {
  return document.documentElement.classList.contains("dark") ? "material-darker" : "default";
}

function guessEditorMode(path) {
  const ext = (path.split(".").pop() || "").toLowerCase();
  if (typeof CodeMirror !== "undefined" && CodeMirror.findModeByExtension) {
    const info = CodeMirror.findModeByExtension(ext);
    if (info?.mode) return info.mode;
  }
  const map = {
    py: "python",
    js: "javascript",
    mjs: "javascript",
    ts: "text/typescript",
    json: "application/json",
    yaml: "yaml",
    yml: "yaml",
    md: "markdown",
    html: "htmlmixed",
    css: "css",
    sh: "shell",
    bash: "shell",
    sql: "sql",
    xml: "xml",
  };
  return map[ext] || "text/plain";
}

function setEditorDirty(dirty) {
  editorDirty = dirty;
  editorDirtyEl?.classList.toggle("hidden", !dirty);
  if (btnSaveFile) btnSaveFile.disabled = !dirty || !selectedFilePath || savingFile;
}

function initCodeEditor() {
  if (!editorHostEl || typeof CodeMirror === "undefined") return;
  codeEditor = CodeMirror(editorHostEl, {
    value: "",
    lineNumbers: true,
    lineWrapping: false,
    indentUnit: 2,
    tabSize: 2,
    indentWithTabs: false,
    theme: editorTheme(),
    mode: "text/plain",
    extraKeys: {
      "Ctrl-S": () => void saveCurrentFile(),
      "Cmd-S": () => void saveCurrentFile(),
      Tab: (cm) => {
        if (cm.somethingSelected()) {
          cm.indentSelection("add");
        } else {
          cm.replaceSelection("  ", "end");
        }
      },
    },
  });
  codeEditor.setSize("100%", "100%");
  codeEditor.on("change", () => {
    if (!savingFile) setEditorDirty(true);
  });
  setEditorDirty(false);
}

function setEditorReadOnly(readOnly) {
  codeEditor?.setOption("readOnly", readOnly);
}

function setEditorContent(content, path) {
  if (!codeEditor) return;
  savingFile = true;
  codeEditor.setValue(content ?? "");
  codeEditor.setOption("mode", guessEditorMode(path));
  codeEditor.setOption("theme", editorTheme());
  codeEditor.clearHistory();
  codeEditor.refresh();
  savingFile = false;
  setEditorDirty(false);
  window.setTimeout(() => codeEditor?.refresh(), 0);
}

async function confirmDiscardEdits() {
  if (!editorDirty) return true;
  return window.confirm("当前文件有未保存修改，确定放弃吗？");
}

async function saveCurrentFile() {
  if (!selectedFilePath || !codeEditor || savingFile) return;
  savingFile = true;
  if (btnSaveFile) btnSaveFile.disabled = true;
  try {
    await saveWorkspaceFile(userId, sessionId, selectedFilePath, codeEditor.getValue());
    setEditorDirty(false);
    if (editorPathEl) editorPathEl.textContent = selectedFilePath;
  } catch (e) {
    alert(`保存失败：${e.message || e}`);
  } finally {
    savingFile = false;
    if (btnSaveFile) btnSaveFile.disabled = !editorDirty;
  }
}

function applyThemeFromSystem() {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle("dark", prefersDark);
  if (codeEditor) {
    codeEditor.setOption("theme", editorTheme());
  }
}

function paintMessages() {
  assistantBubbleEl = renderMessages(messagesEl, currentSession?.messages || [], {
    maxWidthClass: "max-w-[92%]",
    bubbleUserClass:
      "rounded-2xl rounded-br-md bg-gray-900 px-3 py-2 text-sm text-white dark:bg-gray-100 dark:text-gray-900",
    bubbleAssistantClass:
      "rounded-2xl rounded-bl-md bg-gray-100 px-3 py-2 text-sm text-gray-900 dark:bg-gray-850 dark:text-gray-100",
    wrapClass: "space-y-3",
    onAssistantBubble: (el) => {
      assistantBubbleEl = el;
    },
    onCopyAssistant: (_index, msg) => {
      const text = msg.content || "";
      if (navigator.clipboard?.writeText) {
        void navigator.clipboard.writeText(text);
      }
    },
    onRegenerateAssistant: (index) => {
      void regenerateAssistant(index);
    },
  });
}

async function regenerateAssistant(assistantIndex) {
  if (!currentSession || !sessionId || !userId?.trim() || agentTurnBusy) return;
  if (!window.confirm("重新生成将删除此条助手回复及之后的消息，是否继续？")) return;

  agentTurnBusy = true;
  setGenerating(true);
  try {
    const data = await regenerateSession(sessionId, userId, assistantIndex);
    currentSession.messages = data.messages || [];
    currentSession.messages.push({ role: "assistant", content: "", ts: Date.now() });
    const assistantIdx = currentSession.messages.length - 1;
    paintMessages();
    await persistSession();

    const streaming = true;
    const body = {
      message: data.regenerate_input || "",
      session_id: sessionId,
      attachments: [],
      regenerate: true,
    };

    abortController = new AbortController();
    const assistant = () => currentSession.messages[assistantIdx];
    let streamPainter = null;
    if (streaming && assistantBubbleEl) {
      streamPainter = createStreamingMarkdownPainter(assistantBubbleEl, messagesEl);
    }

    const chatOpts = {
      userId,
      sandbox: true,
      signal: abortController.signal,
    };

    if (streaming) {
      await streamChat(body, {
        ...chatOpts,
        onStatus: (payload) => {
          setStreamStatus(composerUi?.streamStatus ?? null, payload?.detail || payload?.tool || "");
        },
        onDelta: (chunk) => {
          setStreamStatus(composerUi?.streamStatus ?? null, "");
          assistant().content += chunk;
          streamPainter?.update(assistant().content || "");
        },
      });
    } else {
      assistant().content = await chatGraph(body, chatOpts);
      paintMessages();
    }

    if (streamPainter) {
      streamPainter.flush(assistant().content || "");
      streamPainter.destroy();
    }
    paintMessages();
    await persistSession();
  } catch (err) {
    alert(`重新生成失败：${err.message || "未知错误"}`);
    paintMessages();
  } finally {
    abortController = null;
    agentTurnBusy = false;
    setGenerating(false);
  }
}

async function loadSession() {
  if (!sessionId) return;
  try {
    currentSession = await fetchSession(userId, sessionId);
    currentSession.userId = userId;
    paintMessages();
  } catch (e) {
    console.warn("load session", e);
    currentSession = {
      id: sessionId,
      userId,
      title: "执行环境",
      updatedAt: Date.now(),
      messages: [],
    };
  }
}

function setGenerating(on) {
  if (composerUi?.composer) composerUi.composer.disabled = on;
  if (composerUi?.btnSend) composerUi.btnSend.disabled = on;
  composerUi?.btnStop?.classList.toggle("hidden", !on);
  composerUi?.btnSend?.classList.toggle("hidden", on);
}

async function persistSession() {
  if (!currentSession) return;
  currentSession.updatedAt = Date.now();
  currentSession = await upsertSession(currentSession);
}

function isReadonlyPath(relPath) {
  const p = (relPath || "").replace(/\\/g, "/");
  return p.startsWith("skills/") || p.startsWith("books/");
}

function setComposeButtonsDisabled(disabled) {
  if (btnComposeUp) btnComposeUp.disabled = disabled;
  if (btnComposeDown) btnComposeDown.disabled = disabled;
}

async function refreshComposeStatus() {
  if (!sessionId || !composeStatusEl) return;
  try {
    const data = await fetchComposeStatus(userId, sessionId);
    composeStatusEl.textContent = data.running ? "环境运行中" : "环境未启动";
  } catch (e) {
    composeStatusEl.textContent = String(e.message || "无法获取状态");
  }
}

async function handleComposeUp() {
  if (composeBusy || !sessionId) return;
  if (!window.confirm("在宿主机启动 compose 环境？\n\n将拉取镜像并启动 compose/docker-compose.yml 中的服务。")) {
    return;
  }
  composeBusy = true;
  setComposeButtonsDisabled(true);
  if (composeStatusEl) composeStatusEl.textContent = "启动中（拉取镜像可能需要数分钟）…";
  try {
    await composeUp(userId, sessionId);
    teardownTerminal();
    connectTerminal();
    await refreshComposeStatus();
  } catch (e) {
    alert(`启动失败：${e.message || e}`);
    await refreshComposeStatus();
  } finally {
    composeBusy = false;
    setComposeButtonsDisabled(false);
  }
}

async function handleComposeDown() {
  if (composeBusy || !sessionId) return;
  if (!window.confirm("停止 compose 环境？\n\n终端将回到 venue 壳。")) return;
  composeBusy = true;
  setComposeButtonsDisabled(true);
  if (composeStatusEl) composeStatusEl.textContent = "停止中…";
  try {
    await composeDown(userId, sessionId);
    teardownTerminal();
    connectTerminal();
    await refreshComposeStatus();
  } catch (e) {
    alert(`停止失败：${e.message || e}`);
    await refreshComposeStatus();
  } finally {
    composeBusy = false;
    setComposeButtonsDisabled(false);
  }
}

function initWorkspaceContextMenu() {
  workspaceMenu = createWorkspaceContextMenu({
    isReadonly: isReadonlyPath,
    onOpen: (path) => void openFile(path),
    onCopyPath: async (path) => {
      try {
        await navigator.clipboard.writeText(path);
      } catch {
        window.prompt("复制路径：", path);
      }
    },
    onCut: (path) => workspaceMenu?.setClipboard("cut", path),
    onCopy: (path) => workspaceMenu?.setClipboard("copy", path),
    onPaste: async (destDir) => {
      const clip = workspaceMenu?.getClipboard();
      if (!clip) return;
      const base = clip.path.split("/").pop() || clip.path;
      const dest = destDir ? `${destDir}/${base}` : base;
      try {
        if (clip.op === "cut") {
          await workspaceMove(userId, sessionId, clip.path, dest);
          workspaceMenu?.clearClipboard();
          if (selectedFilePath === clip.path) selectedFilePath = null;
        } else {
          await workspaceCopy(userId, sessionId, clip.path, destDir || "data");
        }
        await loadTree();
      } catch (e) {
        alert(`粘贴失败：${e.message || e}`);
      }
    },
    onRename: async (path) => {
      const base = path.split("/").pop() || path;
      const next = window.prompt("重命名为：", base);
      if (!next || next === base) return;
      const parent = path.split("/").slice(0, -1).join("/");
      const dest = parent ? `${parent}/${next}` : next;
      try {
        await workspaceMove(userId, sessionId, path, dest);
        if (selectedFilePath === path) selectedFilePath = dest;
        await loadTree();
        if (selectedFilePath === dest) await openFile(dest);
      } catch (e) {
        alert(`重命名失败：${e.message || e}`);
      }
    },
    onDelete: async (path) => {
      if (!window.confirm(`确定删除「${path}」？`)) return;
      try {
        await workspaceDeleteEntry(userId, sessionId, path);
        if (selectedFilePath === path) {
          selectedFilePath = null;
          if (editorPathEl) editorPathEl.textContent = "展开文件夹，点击文件编辑";
          setEditorContent("", "");
        }
        await loadTree();
      } catch (e) {
        alert(`删除失败：${e.message || e}`);
      }
    },
    onMkdir: async (parentDir) => {
      const name = window.prompt("新建文件夹名称：");
      if (!name?.trim()) return;
      const rel = parentDir ? `${parentDir}/${name.trim()}` : name.trim();
      try {
        await workspaceMkdir(userId, sessionId, rel);
        expandedDirs.add(parentDir || rel.split("/")[0]);
        await loadTree();
      } catch (e) {
        alert(`创建失败：${e.message || e}`);
      }
    },
  });
}

function bindTreeContextMenu(el, path, isDir) {
  el.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    workspaceMenu?.show(e.clientX, e.clientY, { path, isDir });
  });
  bindWorkspaceDrag(el, path);
}

async function refreshAfterAgent() {
  await loadTree();
  if (!selectedFilePath) return;
  try {
    const data = await fetchWorkspaceFile(userId, sessionId, selectedFilePath);
    if (editorDirty) {
      const ok = window.confirm(
        `Agent 可能已更新「${selectedFilePath}」。是否用磁盘内容覆盖编辑器？`,
      );
      if (!ok) return;
    }
    setEditorContent(data.content ?? "", selectedFilePath);
    setEditorReadOnly(false);
  } catch {
    /* ignore */
  }
}

function formatExecFollowUp(pending, result, approved) {
  if (!approved) {
    return [
      "[沙箱命令已拒绝]",
      "用户拒绝了你在 sandbox_exec 中提议的以下命令。请告知用户并建议改用手动终端或其他非交互方式。",
      "",
      `command: ${pending.command}`,
      `cwd: ${pending.cwd || "/workspace"}`,
    ].join("\n");
  }

  const r = result || {};
  return [
    "[沙箱命令执行结果]",
    "用户已确认并执行你在 sandbox_exec 中提议的命令。请根据以下输出继续完成任务。",
    "",
    `command: ${pending.command}`,
    `cwd: ${pending.cwd || "/workspace"}`,
    `exit_code: ${r.exit_code ?? "?"}`,
    r.stdout ? `\nstdout:\n${r.stdout}` : "",
    r.stderr ? `\nstderr:\n${r.stderr}` : "",
  ].join("\n");
}

function formatExecUserDisplay(pending, result, approved) {
  if (!approved) {
    return `已拒绝执行容器命令：\`${pending.command}\``;
  }
  const code = result?.exit_code ?? "?";
  return `已确认执行容器命令（exit ${code}）：\`${pending.command}\``;
}

async function resumeAgentAfterExec(pending, result, { approved }) {
  const message = formatExecFollowUp(pending, result, approved);
  const userDisplay = formatExecUserDisplay(pending, result, approved);
  await runAgentTurn(message, { userDisplay });
}

async function pollExecPending() {
  if (agentTurnBusy) return;
  try {
    const data = await fetchExecPending(userId, sessionId);
    const pending = data.pending;
    if (!pending?.pending_id) return;
    if (promptedPendingIds.has(pending.pending_id)) return;
    promptedPendingIds.add(pending.pending_id);

    const ok = window.confirm(
      `Agent 请求在容器内执行命令：\n\n${pending.command}\n\n工作目录：${pending.cwd}\n\n是否允许执行？`,
    );
    if (ok) {
      const res = await approveExec(userId, sessionId, pending.pending_id);
      promptedPendingIds.delete(pending.pending_id);
      await resumeAgentAfterExec(pending, res.result || {}, { approved: true });
    } else {
      await rejectExec(userId, sessionId, pending.pending_id);
      promptedPendingIds.delete(pending.pending_id);
      await resumeAgentAfterExec(pending, null, { approved: false });
    }
  } catch (e) {
    console.warn("exec pending", e);
  }
}

/**
 * @param {string} message Graph input (also persisted to checkpointer)
 * @param {{ userDisplay?: string, onStatus?: (payload: object) => void }} [opts]
 */
async function runAgentTurn(message, opts = {}) {
  const fileRefs = opts.fileRefs ?? composerFileRefs?.getRelPaths() ?? [];
  const hasMessage = Boolean(message?.trim());
  if ((!hasMessage && !fileRefs.length) || !sessionId || !currentSession || agentTurnBusy) return;

  let userDisplay = opts.userDisplay || message;
  if (fileRefs.length) {
    const lines = fileRefs.map((p) => `[定位] ${p}`);
    userDisplay = hasMessage ? `${userDisplay}\n${lines.join("\n")}` : lines.join("\n");
  }

  agentTurnBusy = true;
  currentSession.messages = currentSession.messages || [];
  currentSession.messages.push({
    role: "user",
    content: userDisplay,
    ts: Date.now(),
  });
  currentSession.messages.push({ role: "assistant", content: "", ts: Date.now() });
  const assistantIdx = currentSession.messages.length - 1;

  paintMessages();
  await persistSession();
  composerFileRefs?.clear();

  abortController = new AbortController();
  setGenerating(true);
  setStreamStatus(composerUi?.streamStatus ?? null, "");

  const streaming = true;
  const body = { message: message || "", session_id: sessionId, attachments: fileRefs };
  const chatOpts = {
    userId,
    sandbox: true,
    signal: abortController.signal,
  };
  /** @type {ReturnType<typeof createStreamingMarkdownPainter> | null} */
  let streamPainter = null;
  if (streaming && assistantBubbleEl) {
    streamPainter = createStreamingMarkdownPainter(assistantBubbleEl, messagesEl);
  }

  try {
    if (streaming) {
      await streamChat(body, {
        ...chatOpts,
        onDelta: (chunk) => {
          const msg = currentSession.messages[assistantIdx];
          msg.content = (msg.content || "") + chunk;
          streamPainter?.update(msg.content || "");
        },
        onStatus: (payload) => {
          opts.onStatus?.(payload);
          if (payload.phase === "tool" && payload.tool) {
            setStreamStatus(
              composerUi?.streamStatus ?? null,
              payload.detail || `执行 ${payload.tool}…`,
            );
          } else if (payload.phase === "tool_done" && payload.tool === "sandbox_exec") {
            void pollExecPending();
          } else if (payload.detail) {
            setStreamStatus(composerUi?.streamStatus ?? null, payload.detail);
          }
        },
      });
    } else {
      const reply = await chatGraph(body, chatOpts);
      currentSession.messages[assistantIdx].content = reply;
      paintMessages();
      await pollExecPending();
    }
  } catch (e) {
    if (e.name !== "AbortError") {
      currentSession.messages[assistantIdx].content = `请求失败：${e.message || e}`;
      paintMessages();
    }
  } finally {
    if (streamPainter) {
      const finalText = currentSession?.messages?.[assistantIdx]?.content || "";
      streamPainter.flush(finalText);
      streamPainter.destroy();
      streamPainter = null;
    }
    paintMessages();
    abortController = null;
    agentTurnBusy = false;
    setGenerating(false);
    setStreamStatus(composerUi?.streamStatus ?? null, "");
    await persistSession();
    await refreshSessionTitle(userId, sessionId);
    await refreshAfterAgent();
    await pollExecPending();
  }
}

function buildTreeIndex(entries) {
  /** @type {Map<string, { dirs: string[], files: { path: string, name: string }[] }>} */
  const index = new Map();
  const ensure = (key) => {
    if (!index.has(key)) index.set(key, { dirs: [], files: [] });
    return index.get(key);
  };
  ensure("");

  for (const e of entries || []) {
    if (e.type === "file") {
      const parts = e.path.split("/");
      const name = parts.pop() || e.path;
      const parent = parts.join("/");
      ensure(parent).files.push({ path: e.path, name });
    } else if (e.type === "dir") {
      const parts = e.path.split("/");
      const parent = parts.slice(0, -1).join("/");
      const node = ensure(parent);
      if (!node.dirs.includes(e.path)) node.dirs.push(e.path);
      ensure(e.path);
    }
  }

  for (const node of index.values()) {
    node.dirs.sort((a, b) => a.localeCompare(b));
    node.files.sort((a, b) => a.name.localeCompare(b.name));
  }
  return index;
}

function renderDirList(parentPath, depth) {
  const node = treeIndex?.get(parentPath);
  if (!node) return null;

  const ul = document.createElement("ul");
  ul.className = "list-none";

  for (const dirPath of node.dirs) {
    const li = document.createElement("li");
    const open = expandedDirs.has(dirPath);
    const label = dirPath.split("/").pop() || dirPath;

    const folderBtn = document.createElement("button");
    folderBtn.type = "button";
    folderBtn.className =
      "flex w-full min-w-0 items-center gap-1 truncate rounded py-0.5 text-left text-gray-600 hover:bg-gray-200 dark:text-gray-300 dark:hover:bg-gray-800";
    folderBtn.style.paddingLeft = `${depth * 10 + 4}px`;
    folderBtn.title = dirPath;
    folderBtn.innerHTML = `<span class="shrink-0 w-3 text-[10px]">${open ? "▼" : "▶"}</span><span class="truncate">${label}/</span>`;
    folderBtn.addEventListener("click", () => {
      if (expandedDirs.has(dirPath)) expandedDirs.delete(dirPath);
      else expandedDirs.add(dirPath);
      renderTree(treeEntriesCache);
    });
    bindTreeContextMenu(folderBtn, dirPath, true);
    li.appendChild(folderBtn);

    if (open) {
      const nested = renderDirList(dirPath, depth + 1);
      if (nested) li.appendChild(nested);
    }
    ul.appendChild(li);
  }

  for (const f of node.files) {
    const li = document.createElement("li");
    const fileBtn = document.createElement("button");
    fileBtn.type = "button";
    fileBtn.className =
      "w-full min-w-0 truncate rounded py-0.5 text-left text-gray-900 hover:bg-gray-200 dark:text-gray-100 dark:hover:bg-gray-800";
    fileBtn.style.paddingLeft = `${depth * 10 + 18}px`;
    fileBtn.textContent = f.name;
    fileBtn.title = f.path;
    if (f.path === selectedFilePath) {
      fileBtn.classList.add("bg-gray-200", "font-medium", "dark:bg-gray-800");
    }
    fileBtn.addEventListener("click", () => void openFile(f.path));
    bindTreeContextMenu(fileBtn, f.path, false);
    li.appendChild(fileBtn);
    ul.appendChild(li);
  }

  return ul.childElementCount ? ul : null;
}

function renderTree(entries) {
  if (!treeEl) return;
  treeEntriesCache = entries;
  treeIndex = buildTreeIndex(entries);
  treeEl.innerHTML = "";
  const root = renderDirList("", 0);
  if (root) {
    treeEl.appendChild(root);
  } else {
    treeEl.textContent = "工作区暂无文件";
  }
}

async function openFile(path) {
  if (path === selectedFilePath) return;
  if (!(await confirmDiscardEdits())) return;

  selectedFilePath = path;
  if (editorPathEl) editorPathEl.textContent = path;
  setEditorReadOnly(false);
  setEditorContent("加载中…", path);

  try {
    const data = await fetchWorkspaceFile(userId, sessionId, path);
    setEditorContent(data.content ?? "", path);
  } catch (e) {
    setEditorContent(String(e.message || e), path);
    setEditorReadOnly(true);
  }

  highlightSelectedFile();
  codeEditor?.focus();
}

function highlightSelectedFile() {
  if (!treeEl || !selectedFilePath) return;
  treeEl.querySelectorAll("button").forEach((btn) => {
    const isFile = btn.title && btn.title === selectedFilePath;
    btn.classList.toggle("bg-gray-200", isFile);
    btn.classList.toggle("font-medium", isFile);
    btn.classList.toggle("dark:bg-gray-800", isFile);
  });
}

async function loadTree() {
  if (!sessionId || !treeEl) return;
  try {
    const data = await fetchWorkspaceTree(userId, sessionId);
    renderTree(data.entries || []);
  } catch (e) {
    treeEl.textContent = String(e.message || e);
  }
}

function scheduleFitTerminal() {
  if (fitTimer) clearTimeout(fitTimer);
  fitTimer = setTimeout(() => {
    fitTimer = null;
    try {
      fitAddon?.fit();
      term?.focus();
    } catch {
      /* ignore */
    }
  }, 80);
}

function connectTerminal() {
  if (!sessionId || !terminalHost) {
    if (statusEl) statusEl.textContent = "缺少 session_id";
    return;
  }

  if (typeof Terminal === "undefined") {
    if (statusEl) statusEl.textContent = "xterm 未加载";
    return;
  }

  if (statusEl) statusEl.textContent = "连接中…";

  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const q = new URLSearchParams({ user_id: userId });
  const url = `${proto}//${window.location.host}/api/v2/web/sessions/${encodeURIComponent(sessionId)}/terminal?${q}`;

  term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: "Menlo, Monaco, 'Courier New', monospace",
    theme: { background: "#171717", foreground: "#e5e5e5" },
    scrollback: 2000,
  });

  const FitCtor =
    globalThis.FitAddon?.FitAddon ||
    globalThis.FitAddon ||
    (typeof FitAddon !== "undefined" ? FitAddon?.FitAddon || FitAddon : null);
  fitAddon = FitCtor ? new FitCtor() : null;
  if (fitAddon) term.loadAddon(fitAddon);
  term.open(terminalHost);
  scheduleFitTerminal();

  terminalHost.addEventListener("mousedown", () => term?.focus());

  ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    if (statusEl) statusEl.textContent = "已连接";
    scheduleFitTerminal();
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data === "string") {
      term?.write(ev.data);
    } else {
      term?.write(new Uint8Array(ev.data));
    }
  };
  ws.onclose = (ev) => {
    if (statusEl) {
      statusEl.textContent = ev.reason ? `已断开：${ev.reason}` : "已断开";
    }
  };
  ws.onerror = () => {
    if (statusEl) statusEl.textContent = "连接错误";
  };

  term.onData((data) => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(data);
    }
  });

  window.addEventListener("resize", scheduleFitTerminal);
  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(scheduleFitTerminal);
    resizeObserver.observe(terminalHost);
    resizeObserver.observe(terminalHost.parentElement || terminalHost);
  }
}

function teardownTerminal() {
  if (fitTimer) clearTimeout(fitTimer);
  resizeObserver?.disconnect();
  resizeObserver = null;
  ws?.close();
  ws = null;
  term?.dispose();
  term = null;
  fitAddon = null;
}

function exitWorkbench() {
  if (editorDirty) {
    const save = window.confirm("有未保存修改。确定退出？（取消后可点「保存」）");
    if (!save) return;
  }
  abortController?.abort();
  teardownTerminal();
  window.location.href = "/";
}

async function sendChat() {
  const text = composerUi?.composer?.value?.trim() || "";
  const fileRefs = composerFileRefs?.getRelPaths() ?? [];
  if (!text && !fileRefs.length) return;
  if (!sessionId || !currentSession) return;

  if (composerUi?.composer) composerUi.composer.value = "";
  autoResizeComposer(composerUi?.composer ?? null);
  await runAgentTurn(text);
}

function initComposer() {
  if (!composerMount) return;
  composerUi = mountComposer(composerMount, {
    showAttach: false,
    compact: true,
    onSend: () => void sendChat(),
    onStop: () => {
      abortController?.abort();
      setGenerating(false);
    },
  });
  const shell = composerMount.querySelector(".composer-shell");
  if (shell) {
    composerFileRefs = createComposerFileRefs(shell, { silent: true });
  }
  btnLogs?.addEventListener("click", () => {
    if (!sessionId) {
      alert("缺少会话 ID");
      return;
    }
    openSessionLogsViewer(userId, sessionId);
  });
  initWorkspaceContextMenu();
}

function showBootError(message) {
  console.error("[sandbox boot]", message);
  if (statusEl) statusEl.textContent = "初始化失败";
  if (messagesEl) {
    messagesEl.innerHTML = `<p class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">${message}</p>`;
  }
}

function initLayout() {
  const root = document.getElementById("sandbox-main");
  const left = document.getElementById("pane-left");
  const center = document.getElementById("pane-center");
  const right = document.getElementById("pane-right");
  const terminal = document.getElementById("terminal-panel");
  const editor = document.getElementById("editor-panel");
  if (!root || !left || !center || !right || !terminal || !editor) return;

  try {
    initSplitPanes({
      root,
      leftPane: left,
      centerPane: center,
      rightPane: right,
      terminalPane: terminal,
      editorPane: editor,
      onResize: () => {
        scheduleFitTerminal();
        codeEditor?.refresh();
      },
    });
  } catch (e) {
    console.warn("split panes init failed, resetting layout", e);
    resetSplitLayout();
    initSplitPanes({
      root,
      leftPane: left,
      centerPane: center,
      rightPane: right,
      terminalPane: terminal,
      editorPane: editor,
      onResize: () => {
        scheduleFitTerminal();
        codeEditor?.refresh();
      },
    });
  }
}

btnExit?.addEventListener("click", exitWorkbench);
btnSaveFile?.addEventListener("click", () => void saveCurrentFile());
btnComposeUp?.addEventListener("click", () => void handleComposeUp());
btnComposeDown?.addEventListener("click", () => void handleComposeDown());

async function boot() {
  try {
    applyThemeFromSystem();
    initCodeEditor();
    initComposer();
    if (!composerUi?.composer) {
      showBootError("对话区初始化失败：请硬刷新页面（Ctrl+Shift+R）");
    }
    initLayout();

    if (!sessionId) {
      if (titleEl) titleEl.textContent = "缺少 session_id";
      showBootError("URL 缺少 session_id。请从主站点击「进入执行环境」打开。");
      return;
    }
    if (titleEl) titleEl.textContent = `执行环境 · ${sessionId}`;

    connectTerminal();
    await Promise.all([
      refreshSettings().catch(() => {}),
      loadSession(),
      loadTree(),
      refreshComposeStatus(),
    ]);
    scheduleFitTerminal();
    window.setTimeout(() => codeEditor?.refresh(), 120);
  } catch (e) {
    showBootError(`沙箱初始化失败：${e?.message || e}`);
  }
}

boot();
