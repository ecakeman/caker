import { loadUiLayout, saveUiLayout } from "./layout-chrome.js";

const SIDEBAR_MIN = 200;
const SIDEBAR_MAX = 520;
const SIDEBAR_DEFAULT = 288;

const FOLLOWUP_MIN = 220;
const FOLLOWUP_MAX = 640;
const FOLLOWUP_DEFAULT = 320;

const MAIN_MIN = 280;

/** @returns {{ sidebarWidth: number, followupWidth: number }} */
function loadWidths() {
  const data = loadUiLayout();
  const sidebarWidth = clamp(
    Number(data.sidebarWidth) || SIDEBAR_DEFAULT,
    SIDEBAR_MIN,
    SIDEBAR_MAX
  );
  const followupWidth = clamp(
    Number(data.followupWidth) || FOLLOWUP_DEFAULT,
    FOLLOWUP_MIN,
    FOLLOWUP_MAX
  );
  return { sidebarWidth, followupWidth };
}

/** @param {number} n @param {number} min @param {number} max */
function clamp(n, min, max) {
  return Math.min(max, Math.max(min, n));
}

/**
 * @param {{
 *   shell: HTMLElement,
 *   sidebar: HTMLElement,
 *   contentRow: HTMLElement,
 *   mainPane: HTMLElement,
 *   followupPanel: HTMLElement,
 *   handleSidebar: HTMLElement,
 *   handleFollowup: HTMLElement,
 *   getLayoutState: () => import('./layout-chrome.js').UiLayoutState,
 *   onResize?: () => void,
 * }} opts
 */
export function initPanelResize(opts) {
  let widths = loadWidths();

  const apply = () => {
    const state = opts.getLayoutState();
    const shellRect = opts.shell.getBoundingClientRect();

    if (state.sidebarCollapsed) {
      opts.sidebar.style.width = "";
      opts.handleSidebar?.classList.add("hidden");
    } else {
      opts.sidebar.style.width = `${widths.sidebarWidth}px`;
      opts.handleSidebar?.classList.remove("hidden");
    }

    const followupActive =
      state.followupOpen && !state.followupCollapsed && !opts.followupPanel.classList.contains("hidden");

    if (!followupActive) {
      opts.followupPanel.style.width = "";
      opts.handleFollowup?.classList.add("hidden");
    } else {
      const maxFollow = Math.min(
        FOLLOWUP_MAX,
        Math.max(FOLLOWUP_MIN, shellRect.width - widths.sidebarWidth - MAIN_MIN - 16)
      );
      widths.followupWidth = clamp(widths.followupWidth, FOLLOWUP_MIN, maxFollow);
      opts.followupPanel.style.width = `${widths.followupWidth}px`;
      opts.handleFollowup?.classList.remove("hidden");
    }

    opts.onResize?.();
  };

  const persist = () => {
    saveUiLayout({
      sidebarWidth: widths.sidebarWidth,
      followupWidth: widths.followupWidth,
    });
  };

  /** @param {'sidebar' | 'followup'} which @param {PointerEvent} e */
  const startDrag = (which, e) => {
    if (e.button !== 0) return;
    const state = opts.getLayoutState();
    if (which === "sidebar" && state.sidebarCollapsed) return;
    if (
      which === "followup" &&
      (!state.followupOpen || state.followupCollapsed)
    ) {
      return;
    }

    e.preventDefault();
    const startX = e.clientX;
    const startSidebar = widths.sidebarWidth;
    const startFollowup = widths.followupWidth;
    const shellRect = opts.shell.getBoundingClientRect();

    document.body.classList.add("ui-col-resizing");
    opts.handleSidebar?.classList.toggle("is-active", which === "sidebar");
    opts.handleFollowup?.classList.toggle("is-active", which === "followup");

    const onMove = (ev) => {
      const dx = ev.clientX - startX;
      if (which === "sidebar") {
        const maxSide = Math.min(
          SIDEBAR_MAX,
          shellRect.width - MAIN_MIN - (state.followupOpen && !state.followupCollapsed ? widths.followupWidth : 0) - 24
        );
        widths.sidebarWidth = clamp(startSidebar + dx, SIDEBAR_MIN, maxSide);
      } else {
        const maxFollow = Math.min(
          FOLLOWUP_MAX,
          shellRect.width - widths.sidebarWidth - MAIN_MIN - 16
        );
        widths.followupWidth = clamp(startFollowup - dx, FOLLOWUP_MIN, maxFollow);
      }
      apply();
    };

    const onUp = () => {
      document.body.classList.remove("ui-col-resizing");
      opts.handleSidebar?.classList.remove("is-active");
      opts.handleFollowup?.classList.remove("is-active");
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      document.removeEventListener("pointercancel", onUp);
      persist();
    };

    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
    document.addEventListener("pointercancel", onUp);
  };

  opts.handleSidebar?.addEventListener("pointerdown", (e) => startDrag("sidebar", e));
  opts.handleFollowup?.addEventListener("pointerdown", (e) => startDrag("followup", e));

  window.addEventListener("resize", () => apply());

  apply();

  return { apply, getWidths: () => ({ ...widths }) };
}
