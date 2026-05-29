/** @typedef {{ op: 'copy' | 'cut', path: string } | null} WorkspaceClipboard */

/** @type {WorkspaceClipboard} */
let workspaceClipboard = null;

/**
 * @param {object} hooks
 * @param {(path: string) => boolean} hooks.isReadonly
 * @param {(path: string) => void} [hooks.onOpen]
 * @param {(path: string) => Promise<void>} hooks.onCopyPath
 * @param {(path: string) => void} hooks.onCut
 * @param {(path: string) => void} hooks.onCopy
 * @param {(destDir: string) => Promise<void>} hooks.onPaste
 * @param {(path: string) => Promise<void>} hooks.onRename
 * @param {(path: string) => Promise<void>} hooks.onDelete
 * @param {(parentDir: string) => Promise<void>} hooks.onMkdir
 */
export function createWorkspaceContextMenu(hooks) {
  const menu = document.createElement("div");
  menu.id = "workspace-context-menu";
  menu.className =
    "fixed z-50 hidden min-w-[10rem] rounded-lg border border-gray-200 bg-white py-1 text-xs shadow-lg dark:border-gray-700 dark:bg-gray-900";
  document.body.appendChild(menu);

  /** @type {{ path: string, isDir: boolean } | null} */
  let target = null;

  function hide() {
    menu.classList.add("hidden");
    target = null;
  }

  function show(x, y, item) {
    target = item;
    const ro = hooks.isReadonly(item.path);
    const items = [];

    items.push({ label: "复制路径", action: () => hooks.onCopyPath(item.path) });
    if (!item.isDir) {
      items.push({ label: "打开", action: () => hooks.onOpen?.(item.path) });
    }
    if (!ro) {
      items.push({ label: "复制", action: () => hooks.onCopy(item.path) });
      items.push({ label: "剪切", action: () => hooks.onCut(item.path) });
      if (workspaceClipboard) {
        const dest = item.isDir ? item.path : item.path.split("/").slice(0, -1).join("/");
        items.push({
          label: "粘贴",
          action: () => hooks.onPaste(dest || "data"),
        });
      }
      items.push({ label: "重命名", action: () => hooks.onRename(item.path) });
      if (item.isDir) {
        items.push({ label: "新建文件夹", action: () => hooks.onMkdir(item.path) });
      }
      items.push({ label: "删除", action: () => hooks.onDelete(item.path), danger: true });
    }

    menu.innerHTML = "";
    for (const it of items) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `block w-full px-3 py-1.5 text-left hover:bg-gray-100 dark:hover:bg-gray-800 ${
        it.danger ? "text-red-600 dark:text-red-400" : ""
      }`;
      btn.textContent = it.label;
      btn.addEventListener("click", () => {
        hide();
        void it.action();
      });
      menu.appendChild(btn);
    }

    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    menu.classList.remove("hidden");
  }

  document.addEventListener("click", hide);
  document.addEventListener("contextmenu", (e) => {
    if (!menu.contains(/** @type {Node} */ (e.target))) hide();
  });

  return {
    show,
    hide,
    setClipboard(op, path) {
      workspaceClipboard = { op, path };
    },
    getClipboard() {
      return workspaceClipboard;
    },
    clearClipboard() {
      workspaceClipboard = null;
    },
  };
}
