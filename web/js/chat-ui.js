/**
 * Shared chat UI helpers for main site and sandbox.
 */

/** @param {string} raw */
function parseAssistantMarkdown(raw) {
  if (typeof marked !== "undefined" && typeof DOMPurify !== "undefined") {
    return DOMPurify.sanitize(marked.parse(raw || "", { async: false }));
  }
  return null;
}

/** Throttle interval (ms) by growing assistant text length. */
function streamMarkdownInterval(len) {
  if (len > 24_000) return 320;
  if (len > 12_000) return 200;
  if (len > 6_000) return 140;
  return 90;
}

/**
 * Paint assistant markdown into a bubble with adaptive throttling (stream-friendly).
 * @param {HTMLElement} bubbleEl
 * @param {string} text
 * @param {HTMLElement | null} [scrollContainer]
 */
export function paintStreamingMarkdown(bubbleEl, text, scrollContainer = null) {
  if (!bubbleEl) return;
  const raw = text || "";
  const html = parseAssistantMarkdown(raw);
  if (html !== null) {
    bubbleEl.className = "message-content md-body";
    bubbleEl.innerHTML = html;
  } else {
    bubbleEl.className = "message-content user-plain";
    bubbleEl.textContent = raw;
  }
  if (scrollContainer) {
    scrollContainer.scrollTop = scrollContainer.scrollHeight;
  }
}

/**
 * Coalesce stream deltas → throttled markdown paints without blocking the main thread.
 * @param {HTMLElement} bubbleEl
 * @param {HTMLElement | null} [scrollContainer]
 */
export function createStreamingMarkdownPainter(bubbleEl, scrollContainer = null) {
  let pendingText = "";
  let lastPainted = "";
  let lastPaintAt = 0;
  let rafId = 0;
  let timerId = 0;

  const cancelTimers = () => {
    if (rafId) {
      window.cancelAnimationFrame(rafId);
      rafId = 0;
    }
    if (timerId) {
      window.clearTimeout(timerId);
      timerId = 0;
    }
  };

  const paint = () => {
    if (!bubbleEl || pendingText === lastPainted) return;
    lastPainted = pendingText;
    lastPaintAt = performance.now();
    paintStreamingMarkdown(bubbleEl, pendingText, scrollContainer);
  };

  const schedule = ({ immediate = false } = {}) => {
    if (!bubbleEl) return;
    cancelTimers();

    if (immediate) {
      paint();
      return;
    }

    rafId = window.requestAnimationFrame(() => {
      rafId = 0;
      const gap = streamMarkdownInterval(pendingText.length);
      const elapsed = performance.now() - lastPaintAt;
      if (elapsed < gap) {
        timerId = window.setTimeout(() => {
          timerId = 0;
          paint();
        }, gap - elapsed);
        return;
      }
      paint();
    });
  };

  return {
    /** @param {string} text */
    update(text) {
      pendingText = text || "";
      const immediate = !lastPainted && pendingText.length > 0;
      schedule({ immediate });
    },
    /** @param {string} [text] */
    flush(text) {
      if (text !== undefined) pendingText = text || "";
      cancelTimers();
      lastPainted = "";
      paint();
    },
    destroy() {
      cancelTimers();
      pendingText = "";
      lastPainted = "";
      lastPaintAt = 0;
    },
  };
}

/**
 * @param {HTMLElement} el
 * @param {{ role: string, content?: string }} msg
 */
export function renderMessageContent(el, msg) {
  const isUser = msg.role === "user";
  el.className = "message-content";
  if (isUser) {
    el.classList.add("user-plain");
    el.textContent = msg.content || "";
    return;
  }
  el.classList.add("md-body");
  const raw = msg.content || "";
  const html = parseAssistantMarkdown(raw);
  if (html !== null) {
    el.innerHTML = html;
  } else {
    el.textContent = raw;
  }
}

/**
 * @param {HTMLElement} containerEl
 * @param {Array<{ role: string, content?: string }>} messages
 * @param {{
 *   maxWidthClass?: string,
 *   bubbleUserClass?: string,
 *   bubbleAssistantClass?: string,
 *   onAssistantBubble?: (el: HTMLElement) => void,
 *   onCopyAssistant?: (index: number, msg: object) => void,
 *   onRegenerateAssistant?: (index: number, msg: object) => void,
 *   emptyStateEl?: HTMLElement
 * }} [opts]
 */
export function renderMessages(containerEl, messages, opts = {}) {
  if (!containerEl) return null;

  const maxWidthClass = opts.maxWidthClass ?? "max-w-[85%]";
  const bubbleUserClass =
    opts.bubbleUserClass ??
    "rounded-2xl rounded-br-md bg-gray-900 px-4 py-2.5 text-sm text-white dark:bg-gray-100 dark:text-gray-900";
  const bubbleAssistantClass =
    opts.bubbleAssistantClass ??
    "rounded-2xl rounded-bl-md bg-gray-100 px-4 py-2.5 text-sm text-gray-900 dark:bg-gray-850 dark:text-gray-100";

  if (opts.emptyStateEl) {
    opts.emptyStateEl.classList.toggle("hidden", (messages || []).length > 0);
  }

  containerEl.innerHTML = "";
  if (!messages?.length) return null;

  const wrapClass = opts.wrapClass ?? "space-y-4";
  const wrap = document.createElement("div");
  wrap.className = opts.outerWrapClass
    ? `${opts.outerWrapClass} ${wrapClass}`
    : wrapClass;

  /** @type {HTMLElement | null} */
  let lastAssistant = null;

  for (let index = 0; index < (messages || []).length; index++) {
    const msg = messages[index];
    if (msg.role !== "user" && msg.role !== "assistant") continue;
    const isUser = msg.role === "user";
    const row = document.createElement("div");
    row.className = `flex w-full ${isUser ? "justify-end" : "justify-start"}`;

    const col = document.createElement("div");
    col.className = isUser
      ? `${maxWidthClass} flex flex-col items-end`
      : `flex w-full flex-col gap-1 ${maxWidthClass}`;

    const bubble = document.createElement("div");
    bubble.className = isUser
      ? `${bubbleUserClass} max-w-full min-w-[6rem]`
      : `w-full ${bubbleAssistantClass}`;

    const content = document.createElement("div");
    renderMessageContent(content, msg);
    bubble.appendChild(content);
    col.appendChild(bubble);

    if (!isUser && (opts.onCopyAssistant || opts.onRegenerateAssistant)) {
      const actions = document.createElement("div");
      actions.className =
        "flex items-center gap-2 px-1 text-xs text-gray-500 dark:text-gray-400";

      if (opts.onCopyAssistant) {
        const copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "rounded px-1.5 py-0.5 hover:bg-gray-100 dark:hover:bg-gray-800";
        copyBtn.textContent = "复制";
        copyBtn.addEventListener("click", () => opts.onCopyAssistant?.(index, msg));
        actions.appendChild(copyBtn);
      }

      if (opts.onRegenerateAssistant) {
        const regenBtn = document.createElement("button");
        regenBtn.type = "button";
        regenBtn.className = "rounded px-1.5 py-0.5 hover:bg-gray-100 dark:hover:bg-gray-800";
        regenBtn.textContent = "重新生成";
        regenBtn.addEventListener("click", () => opts.onRegenerateAssistant?.(index, msg));
        actions.appendChild(regenBtn);
      }

      col.appendChild(actions);
    }

    row.appendChild(col);
    wrap.appendChild(row);

    if (msg.role === "assistant") {
      lastAssistant = content;
      opts.onAssistantBubble?.(content);
    }
  }

  containerEl.appendChild(wrap);
  containerEl.scrollTop = containerEl.scrollHeight;
  return lastAssistant;
}

/**
 * @param {HTMLElement | null} el
 * @param {string} text
 */
export function setStreamStatus(el, text) {
  if (!el) return;
  const t = (text || "").trim();
  el.textContent = t;
  el.classList.toggle("hidden", !t);
}

/**
 * @param {HTMLTextAreaElement | null} textarea
 */
export function autoResizeComposer(textarea) {
  if (!textarea) return;
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
}

/**
 * @param {HTMLElement} mountEl
 * @param {{
 *   onSend: () => void,
 *   onStop?: () => void,
 *   onAttach?: () => void,
 *   showAttach?: boolean,
 *   compact?: boolean,
 *   placeholder?: string,
 * }} hooks
 */
export function mountComposer(mountEl, hooks) {
  const compact = hooks.compact === true;
  const showAttach = hooks.showAttach !== false;

  mountEl.innerHTML = `
    <p id="stream-status" class="mb-2 hidden text-xs text-gray-500 dark:text-gray-400"></p>
    <div class="composer-shell rounded-3xl border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <div class="flex items-end gap-2 px-2 py-2">
        <input id="file-input" type="file" multiple class="hidden" />
        ${
          showAttach
            ? `<button id="btn-attach" type="button" title="添加文件到工作区 data/uploads/" aria-label="添加文件" class="composer-attach-btn mb-0.5 shrink-0 rounded-xl p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-850">
          <svg class="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M21.44 11.05l-8.49 8.49a4 4 0 0 1-5.66-5.66l8.49-8.49a2 2 0 0 1 2.83 2.83l-8.49 8.49a1 1 0 0 1-1.41-1.41l8.48-8.47"/>
          </svg>
        </button>`
            : ""
        }
        <textarea id="composer" rows="3" placeholder="${hooks.placeholder ?? "输入消息… Enter 发送，Shift+Enter 换行"}"
          class="max-h-52 min-h-[4.5rem] flex-1 resize-y bg-transparent py-2.5 text-sm leading-relaxed outline-none"></textarea>
        <button id="btn-stop" type="button" class="mb-0.5 hidden shrink-0 rounded-xl px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-850">停止</button>
        <button id="btn-send" type="button" class="mb-0.5 shrink-0 rounded-xl bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-40 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-gray-200">发送</button>
      </div>
    </div>`;

  const composer = /** @type {HTMLTextAreaElement | null} */ (mountEl.querySelector("#composer"));
  const btnSend = mountEl.querySelector("#btn-send");
  const btnStop = mountEl.querySelector("#btn-stop");
  const btnAttach = mountEl.querySelector("#btn-attach");
  const streamStatus = mountEl.querySelector("#stream-status");

  composer?.addEventListener("input", () => autoResizeComposer(composer));
  composer?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      hooks.onSend();
    }
  });
  btnSend?.addEventListener("click", () => hooks.onSend());
  btnStop?.addEventListener("click", () => hooks.onStop?.());
  btnAttach?.addEventListener("click", () => hooks.onAttach?.());

  if (compact && mountEl.querySelector(".composer-shell")) {
    mountEl.querySelector(".composer-shell")?.classList.add("rounded-2xl");
  }

  return {
    composer,
    btnSend,
    btnStop,
    btnAttach,
    streamStatus,
    fileInput: mountEl.querySelector("#file-input"),
  };
}
