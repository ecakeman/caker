/**
 * Session observability logs — live tail via workspace file API.
 */
import { fetchWorkspaceFileOrEmpty } from "./store-api.js";

/** @type {{ id: string, label: string, path: string }[]} */
export const LOG_SOURCES = [
  { id: "engine", label: "引擎", path: "logs/engine.jsonl" },
  { id: "sandbox_log", label: "沙箱汇总", path: "logs/sandbox.log" },
  { id: "sandbox_exec", label: "容器命令", path: "logs/sandbox.exec.jsonl" },
  { id: "terminal", label: "终端", path: "logs/sandbox.terminal.txt" },
  { id: "container", label: "容器服务", path: "logs/sandbox.container.txt" },
  { id: "skills", label: "技能脚本", path: "logs/skills.jsonl" },
  { id: "agent", label: "Agent", path: "logs/agent.jsonl" },
];

const POLL_MS = 1500;
const MAX_LINES = 400;

/** @type {HTMLElement | null} */
let modalRoot = null;
/** @type {ReturnType<typeof setInterval> | null} */
let pollTimer = null;
/** @type {string} */
let activeId = LOG_SOURCES[0].id;
/** @type {string} */
let boundUserId = "";
/** @type {string} */
let boundSessionId = "";
/** @type {boolean} */
let stickToBottom = true;

function ensureModal() {
  if (modalRoot) return;

  const root = document.createElement("div");
  root.id = "logs-modal";
  root.className =
    "fixed inset-0 z-[60] hidden items-center justify-center bg-black/50 p-3 sm:p-6";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");
  root.innerHTML = `
    <div class="flex h-[min(88vh,720px)] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-xl dark:border-gray-800 dark:bg-gray-900">
      <div class="flex shrink-0 items-center gap-2 border-b border-gray-100 px-4 py-3 dark:border-gray-800">
        <h2 class="flex-1 text-sm font-semibold text-gray-900 dark:text-gray-100">会话日志</h2>
        <label class="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
          <input id="logs-live" type="checkbox" class="rounded" checked />
          实时刷新
        </label>
        <button type="button" id="logs-close" class="rounded-lg px-2 py-1 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-850">关闭</button>
      </div>
      <div id="logs-tabs" class="flex shrink-0 flex-wrap gap-1 border-b border-gray-100 px-2 py-2 dark:border-gray-800"></div>
      <pre id="logs-body" class="thin-scroll min-h-0 flex-1 overflow-auto bg-gray-950 p-4 font-mono text-xs leading-relaxed text-gray-100"></pre>
      <p id="logs-meta" class="shrink-0 border-t border-gray-100 px-4 py-2 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400"></p>
    </div>`;

  root.addEventListener("click", (e) => {
    if (e.target === root) closeSessionLogsViewer();
  });
  root.querySelector("#logs-close")?.addEventListener("click", () => closeSessionLogsViewer());
  root.querySelector("#logs-live")?.addEventListener("change", (e) => {
    const on = /** @type {HTMLInputElement} */ (e.target).checked;
    if (on) startPoll();
    else stopPoll();
  });

  const tabs = root.querySelector("#logs-tabs");
  for (const src of LOG_SOURCES) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.logId = src.id;
    btn.className =
      "rounded-lg px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-850";
    btn.textContent = src.label;
    btn.addEventListener("click", () => {
      activeId = src.id;
      renderTabs();
      void refreshLogPane();
    });
    tabs?.appendChild(btn);
  }

  const body = root.querySelector("#logs-body");
  body?.addEventListener("scroll", () => {
    if (!body) return;
    const nearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 48;
    stickToBottom = nearBottom;
  });

  document.body.appendChild(root);
  modalRoot = root;
  renderTabs();
}

function renderTabs() {
  if (!modalRoot) return;
  for (const btn of modalRoot.querySelectorAll("#logs-tabs button")) {
    const el = /** @type {HTMLButtonElement} */ (btn);
    const on = el.dataset.logId === activeId;
    el.className = on
      ? "rounded-lg bg-gray-900 px-2.5 py-1 text-xs font-medium text-white dark:bg-gray-100 dark:text-gray-900"
      : "rounded-lg px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-850";
  }
}

function activeSource() {
  return LOG_SOURCES.find((s) => s.id === activeId) || LOG_SOURCES[0];
}

function tailText(raw) {
  const text = raw || "";
  const lines = text.split("\n");
  if (lines.length <= MAX_LINES) return text;
  return lines.slice(-MAX_LINES).join("\n");
}

async function refreshLogPane() {
  if (!modalRoot || !boundUserId || !boundSessionId) return;
  const src = activeSource();
  const body = modalRoot.querySelector("#logs-body");
  const meta = modalRoot.querySelector("#logs-meta");
  if (!body) return;

  try {
    const data = await fetchWorkspaceFileOrEmpty(boundUserId, boundSessionId, src.path, {
      missingOk: true,
    });
    const content = tailText(data.content || "");
    body.textContent = content || `（暂无内容 — ${src.path}）`;
    if (meta) {
      const kb = Math.round((data.size || content.length) / 1024);
      const note = data.missing ? " · 文件尚未生成" : "";
      meta.textContent = `${src.path} · ${kb} KB · ${new Date().toLocaleTimeString()} 更新${note}`;
    }
    if (stickToBottom) {
      body.scrollTop = body.scrollHeight;
    }
  } catch (e) {
    body.textContent = `无法读取 ${src.path}：${e.message || "未知错误"}`;
    if (meta) meta.textContent = src.path;
  }
}

function startPoll() {
  stopPoll();
  void refreshLogPane();
  pollTimer = setInterval(() => void refreshLogPane(), POLL_MS);
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

/**
 * @param {string} userId
 * @param {string} sessionId
 */
export function openSessionLogsViewer(userId, sessionId) {
  const uid = (userId || "").trim();
  const sid = (sessionId || "").trim();
  if (!uid || !sid) {
    alert("请先选择会话");
    return;
  }
  boundUserId = uid;
  boundSessionId = sid;
  stickToBottom = true;
  ensureModal();
  renderTabs();
  modalRoot?.classList.remove("hidden");
  modalRoot?.classList.add("flex");
  const live = /** @type {HTMLInputElement | null} */ (modalRoot?.querySelector("#logs-live"));
  if (live?.checked) startPoll();
  else void refreshLogPane();
}

export function closeSessionLogsViewer() {
  stopPoll();
  modalRoot?.classList.add("hidden");
  modalRoot?.classList.remove("flex");
}
