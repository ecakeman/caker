const STORAGE_KEY = "caker.web.sessions";
const SETTINGS_KEY = "caker.web.settings";

/** @typedef {{ role: 'user' | 'assistant', content: string, ts: number }} Message */
/** @typedef {{ id: string, title: string, userId: string, updatedAt: number, messages: Message[] }} ChatSession */
/** @typedef {{ userId: string, streaming: boolean, theme: 'system' | 'light' | 'dark', activeId: string | null }} Settings */

/** @returns {Settings} */
export function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) {
      return {
        userId: "local",
        streaming: true,
        theme: "system",
        activeId: null,
      };
    }
    const s = JSON.parse(raw);
    return {
      userId: s.userId ?? "local",
      streaming: s.streaming !== false,
      theme: s.theme ?? "system",
      activeId: s.activeId ?? null,
    };
  } catch {
    return {
      userId: "local",
      streaming: true,
      theme: "system",
      activeId: null,
    };
  }
}

/** @param {Partial<Settings>} patch */
export function saveSettings(patch) {
  const cur = loadSettings();
  const next = { ...cur, ...patch };
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
  return next;
}

/** @returns {ChatSession[]} */
export function loadSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw);
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

/** @param {ChatSession[]} sessions */
export function saveSessions(sessions) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

export function newSessionId() {
  return `chat-${crypto.randomUUID()}`;
}

/** @param {string} text */
export function titleFromMessage(text) {
  const t = text.trim().replace(/\s+/g, " ");
  if (!t) return "新对话";
  return t.length > 30 ? `${t.slice(0, 30)}…` : t;
}

/** @returns {ChatSession} */
export function createSession(userId) {
  const now = Date.now();
  return {
    id: newSessionId(),
    title: "新对话",
    userId: userId || "local",
    updatedAt: now,
    messages: [],
  };
}

/** @param {string} id */
export function getSession(id) {
  return loadSessions().find((s) => s.id === id) ?? null;
}

/** @param {ChatSession} session */
export function upsertSession(session) {
  const list = loadSessions().filter((s) => s.id !== session.id);
  list.unshift({ ...session, updatedAt: Date.now() });
  saveSessions(list);
  return list;
}

/** @param {string} id */
export function deleteSession(id) {
  const list = loadSessions().filter((s) => s.id !== id);
  saveSessions(list);
  return list;
}
