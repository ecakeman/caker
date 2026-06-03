const LAYOUT_KEY = "caker.ui.layout";
const GITHUB_URL = "https://github.com/ecakeman/caker";

/** @typedef {{ sidebarCollapsed: boolean, followupOpen: boolean, followupCollapsed: boolean, sidebarWidth?: number, followupWidth?: number }} UiLayoutState */

/** @returns {UiLayoutState} */
export function loadUiLayout() {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (!raw) return defaultUiLayout();
    const data = JSON.parse(raw);
    return {
      sidebarCollapsed: !!data.sidebarCollapsed,
      followupOpen: !!data.followupOpen,
      followupCollapsed: !!data.followupCollapsed,
      sidebarWidth: data.sidebarWidth,
      followupWidth: data.followupWidth,
    };
  } catch {
    return defaultUiLayout();
  }
}

/** @returns {UiLayoutState} */
export function defaultUiLayout() {
  return {
    sidebarCollapsed: false,
    followupOpen: false,
    followupCollapsed: false,
  };
}

/** @param {Partial<UiLayoutState>} patch */
export function saveUiLayout(patch) {
  const next = { ...loadUiLayout(), ...patch };
  localStorage.setItem(LAYOUT_KEY, JSON.stringify(next));
  return next;
}

/**
 * @param {{
 *   shell: HTMLElement,
 *   sidebar: HTMLElement,
 *   contentRow: HTMLElement,
 *   mainPane: HTMLElement,
 *   followupPanel: HTMLElement,
 *   followupCollapsedTab: HTMLElement,
 *   btnToggleSidebar: HTMLElement,
 *   btnFollowup: HTMLElement,
 *   btnFollowupCollapse: HTMLElement,
 *   btnFollowupClose: HTMLElement,
 *   onLayoutChange?: () => void,
 * }} els
 */
export function initLayoutChrome(els) {
  let state = loadUiLayout();

  const apply = () => {
    els.shell.classList.toggle("sidebar-collapsed", state.sidebarCollapsed);
    els.contentRow.classList.toggle("followup-open", state.followupOpen);
    els.followupPanel.classList.toggle("hidden", !state.followupOpen);
    els.followupPanel.classList.toggle("followup-panel-collapsed", state.followupCollapsed);
    els.followupCollapsedTab?.classList.toggle("hidden", !state.followupOpen || !state.followupCollapsed);
    els.btnFollowup?.setAttribute("aria-pressed", state.followupOpen ? "true" : "false");
    els.onLayoutChange?.();
  };

  els.btnToggleSidebar?.addEventListener("click", () => {
    state = saveUiLayout({ sidebarCollapsed: !state.sidebarCollapsed });
    apply();
  });

  els.btnFollowup?.addEventListener("click", () => {
    const open = !state.followupOpen;
    state = saveUiLayout({
      followupOpen: open,
      followupCollapsed: open ? false : state.followupCollapsed,
    });
    apply();
  });

  els.btnFollowupCollapse?.addEventListener("click", () => {
    if (!state.followupOpen) return;
    state = saveUiLayout({ followupCollapsed: !state.followupCollapsed });
    apply();
  });

  els.btnFollowupClose?.addEventListener("click", () => {
    state = saveUiLayout({ followupOpen: false, followupCollapsed: false });
    apply();
  });

  els.followupCollapsedTab?.addEventListener("click", () => {
    state = saveUiLayout({ followupCollapsed: false });
    apply();
  });

  const brandLink = document.getElementById("brand-github-link");
  if (brandLink) {
    brandLink.href = GITHUB_URL;
    brandLink.target = "_blank";
    brandLink.rel = "noopener noreferrer";
    brandLink.title = "Caker on GitHub";
  }

  apply();

  return {
    getState: () => ({ ...state }),
    setState: (patch) => {
      state = saveUiLayout(patch);
      apply();
      return state;
    },
    apply,
  };
}
