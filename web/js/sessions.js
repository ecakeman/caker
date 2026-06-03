import {
  createSession as createSessionRemote,
  fetchSettings,
  getSession as getSessionRemote,
  listSessions,
  generateSessionTitle as generateSessionTitleRemote,
  saveSession as saveSessionRemote,
  saveSettingsRemote,
} from "./store-api.js";

/** @typedef {{ role: 'user' | 'assistant', content: string, ts: number }} Message */
/** @typedef {{ id: string, title: string, userId: string, updatedAt: number, messages?: Message[] }} ChatSession */
/** @typedef {{
 *   activeUserId: string,
 *   streaming: boolean,
 *   theme: 'system' | 'light' | 'dark',
 *   activeSessionByUser: Record<string, string | null>,
 * }} Settings */

/** @type {Settings} */
let settingsCache = defaultSettings();

/** @type {Map<string, ChatSession[]>} userId -> session summaries (may omit messages) */
const sessionListCache = new Map();

/** @type {Map<string, ChatSession>} `${userId}:${sessionId}` -> full session */
const sessionDetailCache = new Map();

function defaultSettings() {
  return {
    activeUserId: "local",
    streaming: true,
    theme: "system",
    activeSessionByUser: {},
  };
}

function sessionKey(userId, sessionId) {
  return `${userId}:${sessionId}`;
}

export async function refreshSettings() {
  settingsCache = { ...defaultSettings(), ...(await fetchSettings()) };
  return settingsCache;
}

/** @returns {Settings} */
export function loadSettings() {
  return settingsCache;
}

/** @param {Partial<Settings>} patch */
export async function saveSettings(patch) {
  settingsCache = { ...settingsCache, ...patch };
  settingsCache = { ...settingsCache, ...(await saveSettingsRemote(patch)) };
  return settingsCache;
}

/** @param {string} userId */
export function getActiveSessionIdForUser(userId) {
  return settingsCache.activeSessionByUser[userId] ?? null;
}

/** @param {string} userId @param {string | null} sessionId */
export async function setActiveSessionForUser(userId, sessionId) {
  const activeSessionByUser = {
    ...settingsCache.activeSessionByUser,
    [userId]: sessionId,
  };
  await saveSettings({ activeSessionByUser });
}

export async function refreshSessionsForUser(userId) {
  const list = await listSessions(userId);
  sessionListCache.set(userId, list);
  return list;
}

/** @param {string} userId */
export function loadSessionsForUser(userId) {
  return sessionListCache.get(userId) ?? [];
}

/** @param {string} text */
export function titleFromMessage(text) {
  const t = text.trim().replace(/\s+/g, " ");
  if (!t) return "新对话";
  return t.length > 30 ? `${t.slice(0, 30)}…` : t;
}

/** @param {string} userId */
export async function createSession(userId) {
  const session = await createSessionRemote(userId);
  sessionDetailCache.set(sessionKey(userId, session.id), session);
  await refreshSessionsForUser(userId);
  return session;
}

/** @param {string} userId @param {string} id */
export async function fetchSession(userId, id) {
  const key = sessionKey(userId, id);
  const cached = sessionDetailCache.get(key);
  if (cached?.messages) return cached;
  const session = await getSessionRemote(userId, id);
  sessionDetailCache.set(key, session);
  return session;
}

/** @param {string} userId @param {string} id */
export function getSessionFromCache(userId, id) {
  return sessionDetailCache.get(sessionKey(userId, id)) ?? null;
}

/** @param {ChatSession} session */
export async function upsertSession(session) {
  const saved = await saveSessionRemote(session);
  sessionDetailCache.set(sessionKey(session.userId, session.id), saved);
  await refreshSessionsForUser(session.userId);
  return saved;
}

/**
 * Ask server to LLM-summarize session title from messages (best-effort).
 * @param {string} userId
 * @param {string} sessionId
 */
export async function refreshSessionTitle(userId, sessionId) {
  try {
    const key = sessionKey(userId, sessionId);
    const cached = sessionDetailCache.get(key);
    const title = (cached?.title || "").trim();
    if (title && title !== "新对话") return null;

    const data = await generateSessionTitleRemote(userId, sessionId);
    if (data.skipped || !data.session?.title) return null;
    if (cached) {
      cached.title = data.session.title;
      sessionDetailCache.set(key, cached);
    }
    await refreshSessionsForUser(userId);
    return data.session.title;
  } catch (e) {
    console.warn("generate session title", e);
    return null;
  }
}

/** @param {string} userId @param {string} id */
export function removeSessionFromCache(userId, id) {
  sessionDetailCache.delete(sessionKey(userId, id));
  const list = sessionListCache.get(userId) ?? [];
  sessionListCache.set(
    userId,
    list.filter((s) => s.id !== id)
  );
}
