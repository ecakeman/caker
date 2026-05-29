/**
 * Resizable split panes for sandbox layout.
 * Uses overlay handles (no extra flex siblings). Persists to sessionStorage.
 */

const STORAGE_KEY = "caker.sandbox.layout";

const DEFAULTS = {
  left: 224,
  right: 384,
  terminal: 208,
};

const LIMITS = {
  left: { min: 160, max: 480 },
  right: { min: 280, max: 640 },
  terminal: { min: 120, max: 480 },
};

/**
 * @param {number} value
 * @param {{ min: number, max: number }} lim
 * @param {number} fallback
 */
function clamp(value, lim, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return fallback;
  return Math.min(lim.max, Math.max(lim.min, n));
}

/**
 * @param {{
 *   root: HTMLElement,
 *   leftPane: HTMLElement,
 *   centerPane: HTMLElement,
 *   rightPane: HTMLElement,
 *   terminalPane: HTMLElement,
 *   editorPane: HTMLElement,
 *   onResize?: () => void,
 * }} opts
 */
export function initSplitPanes(opts) {
  const { root, leftPane, centerPane, rightPane, terminalPane, editorPane, onResize } = opts;

  /** @type {{ left?: number, right?: number, terminal?: number }} */
  let stored = {};
  try {
    stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    stored = {};
  }

  let layout = {
    left: clamp(stored.left, LIMITS.left, DEFAULTS.left),
    right: clamp(stored.right, LIMITS.right, DEFAULTS.right),
    terminal: clamp(stored.terminal, LIMITS.terminal, DEFAULTS.terminal),
  };

  leftPane.classList.add("relative", "flex", "shrink-0", "flex-col");
  rightPane.classList.add("relative", "flex", "shrink-0", "flex-col");
  centerPane.classList.add("relative", "min-h-0", "min-w-0", "flex-1", "flex", "flex-col");
  editorPane.classList.add("min-h-0", "flex-1");
  terminalPane.classList.add("relative", "shrink-0", "flex", "flex-col");
  terminalPane.style.minHeight = "120px";
  root.classList.add("relative");

  const applyLayout = () => {
    leftPane.style.width = `${layout.left}px`;
    rightPane.style.width = `${layout.right}px`;
    terminalPane.style.height = `${layout.terminal}px`;
    onResize?.();
  };

  const save = () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
  };

  /**
   * @param {"left"|"right"|"terminal"} which
   * @param {MouseEvent} startEv
   */
  const startDrag = (which, startEv) => {
    startEv.preventDefault();
    const startX = startEv.clientX;
    const startY = startEv.clientY;
    const startLeft = layout.left;
    const startRight = layout.right;
    const startTerminal = layout.terminal;

    const onMove = (e) => {
      if (which === "left") {
        layout.left = clamp(
          startLeft + (e.clientX - startX),
          LIMITS.left,
          DEFAULTS.left,
        );
      } else if (which === "right") {
        layout.right = clamp(
          startRight - (e.clientX - startX),
          LIMITS.right,
          DEFAULTS.right,
        );
      } else if (which === "terminal") {
        layout.terminal = clamp(
          startTerminal - (e.clientY - startY),
          LIMITS.terminal,
          DEFAULTS.terminal,
        );
      }
      applyLayout();
    };

    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      save();
    };

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  const mkHandle = (which, className, cursor) => {
    const handle = document.createElement("div");
    handle.className = className;
    handle.style.cursor = cursor;
    handle.setAttribute("role", "separator");
    handle.addEventListener("mousedown", (e) => startDrag(which, e));
    return handle;
  };

  const leftHandle = mkHandle(
    "left",
    "absolute top-0 bottom-0 z-20 w-1.5 hover:bg-gray-300/80 dark:hover:bg-gray-600/80",
    "col-resize",
  );
  leftHandle.style.right = "-3px";
  leftPane.appendChild(leftHandle);

  const rightHandle = mkHandle(
    "right",
    "absolute top-0 bottom-0 z-20 w-1.5 hover:bg-gray-300/80 dark:hover:bg-gray-600/80",
    "col-resize",
  );
  rightHandle.style.left = "-3px";
  rightPane.appendChild(rightHandle);

  const termHandle = mkHandle(
    "terminal",
    "absolute left-0 right-0 z-20 h-1.5 hover:bg-gray-400/80 dark:hover:bg-gray-500/80",
    "row-resize",
  );
  termHandle.style.top = "-3px";
  terminalPane.appendChild(termHandle);

  applyLayout();
  save();
}

/**
 * Reset persisted layout (e.g. after corruption).
 */
export function resetSplitLayout() {
  sessionStorage.removeItem(STORAGE_KEY);
}
