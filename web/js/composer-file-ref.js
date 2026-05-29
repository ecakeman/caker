/** Workspace path MIME for drag-and-drop into composer. */
export const WORKSPACE_PATH_MIME = "application/x-caker-workspace-path";

const FILE_ICON_SVG =
  '<svg class="h-4 w-4 shrink-0 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>';

/**
 * @param {HTMLElement} shellEl composer-shell element
 * @param {{ chipsEl?: HTMLElement | null, hintEl?: HTMLElement | null, onChange?: () => void }} [opts]
 */
export function createComposerFileRefs(shellEl, opts = {}) {
  /** @type {Array<{ relPath: string }>} */
  let refs = [];

  const bar = document.createElement("div");
  bar.id = "file-ref-bar";
  bar.className =
    "hidden border-b border-gray-100 px-3 pt-3 pb-2 dark:border-gray-800";
  bar.innerHTML = `
    <p class="mb-2 text-xs text-gray-500 dark:text-gray-400">已定位工作区路径，发送后 Agent 可用 read 读取</p>
    <div class="file-ref-chips flex flex-wrap gap-2"></div>`;

  const chipsEl = opts.chipsEl || bar.querySelector(".file-ref-chips");
  const hintEl = opts.hintEl || bar.querySelector("p");

  const existingBar = shellEl.querySelector("#file-ref-bar");
  if (existingBar) existingBar.remove();
  shellEl.insertBefore(bar, shellEl.firstChild);

  function render() {
    if (!chipsEl) return;
    chipsEl.innerHTML = "";
    bar.classList.toggle("hidden", !refs.length);
    for (const ref of refs) {
      const chip = document.createElement("div");
      chip.className =
        "inline-flex max-w-full items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 py-1.5 pl-2 pr-1 text-left dark:border-blue-900 dark:bg-blue-950/40";
      chip.innerHTML = FILE_ICON_SVG;
      const textWrap = document.createElement("div");
      textWrap.className = "min-w-0 flex-1";
      const name = document.createElement("div");
      name.className = "truncate text-sm font-medium text-gray-800 dark:text-gray-100";
      name.textContent = ref.relPath.split("/").pop() || ref.relPath;
      name.title = ref.relPath;
      const path = document.createElement("div");
      path.className = "truncate text-xs text-gray-500 dark:text-gray-400";
      path.textContent = ref.relPath;
      textWrap.appendChild(name);
      textWrap.appendChild(path);
      chip.appendChild(textWrap);
      const rm = document.createElement("button");
      rm.type = "button";
      rm.className =
        "shrink-0 rounded-lg p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-700 dark:hover:bg-gray-800";
      rm.innerHTML =
        '<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>';
      rm.addEventListener("click", () => {
        refs = refs.filter((r) => r.relPath !== ref.relPath);
        render();
        opts.onChange?.();
      });
      chip.appendChild(rm);
      chipsEl.appendChild(chip);
    }
    opts.onChange?.();
  }

  function addRef(relPath) {
    const p = (relPath || "").trim().replace(/\\/g, "/");
    if (!p || refs.some((r) => r.relPath === p)) return;
    refs.push({ relPath: p });
    render();
  }

  function clear() {
    refs = [];
    render();
  }

  function getRelPaths() {
    return refs.map((r) => r.relPath);
  }

  shellEl.addEventListener("dragover", (e) => {
    if (e.dataTransfer?.types.includes(WORKSPACE_PATH_MIME)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  });

  shellEl.addEventListener("drop", (e) => {
    const path = e.dataTransfer?.getData(WORKSPACE_PATH_MIME);
    if (!path) return;
    e.preventDefault();
    addRef(path);
  });

  return { addRef, clear, getRelPaths, render, bar, hintEl };
}

/**
 * @param {HTMLElement} el draggable tree/file node
 * @param {string} relPath
 */
export function bindWorkspaceDrag(el, relPath) {
  el.draggable = true;
  el.addEventListener("dragstart", (e) => {
    e.dataTransfer?.setData(WORKSPACE_PATH_MIME, relPath);
    if (e.dataTransfer) e.dataTransfer.effectAllowed = "copy";
  });
}
