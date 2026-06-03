/** @typedef {{ message?: string, session_id?: string, attachments?: string[] }} ChatBody */

/**
 * @param {Response} res
 */
async function throwIfNotOk(res) {
  if (res.ok) return;
  let detail = res.statusText;
  try {
    const j = await res.json();
    if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
  } catch {
    /* ignore */
  }
  throw new Error(detail || `HTTP ${res.status}`);
}

export async function checkHealth() {
  const res = await fetch("/health", { method: "GET" });
  await throwIfNotOk(res);
  const data = await res.json();
  return data?.ok === true;
}

/**
 * @param {string} userId
 */
function requireUserId(userId) {
  const uid = (userId || "").trim();
  if (!uid) throw new Error("请先选择或添加用户");
  return uid;
}

/**
 * @param {ChatBody} body
 * @param {{
 *   userId: string,
 *   signal?: AbortSignal,
 *   sandbox?: boolean,
 * }} opts
 * @returns {Promise<string>}
 */
export async function chatGraph(body, opts) {
  const userId = requireUserId(opts.userId);
  const headers = {
    "Content-Type": "application/json",
    "x-user-id": userId,
  };
  if (opts.sandbox) headers["x-sandbox"] = "1";

  const res = await fetch("/api/v2/chat-graph", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: opts.signal,
  });
  await throwIfNotOk(res);
  const data = await res.json();
  return String(data.reply ?? "");
}

/**
 * @param {string} block
 */
function parseSseBlock(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return { event, data: { raw: dataLines.join("\n") } };
  }
}

/**
 * @param {ChatBody & { regenerate?: boolean }} body
 * @param {{
 *   userId: string,
 *   signal?: AbortSignal,
 *   sandbox?: boolean,
 *   onDelta?: (text: string) => void,
 *   onStatus?: (payload: { phase?: string; detail?: string; tool?: string }) => void,
 * }} opts
 */
export async function streamChat(body, opts) {
  const userId = requireUserId(opts.userId);
  const headers = {
    "Content-Type": "application/json",
    "x-user-id": userId,
  };
  if (opts.sandbox) headers["x-sandbox"] = "1";

  const res = await fetch("/api/v2/stream", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: opts.signal,
  });
  await throwIfNotOk(res);

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const parsed = parseSseBlock(block);
      if (!parsed) continue;

      if (parsed.event === "status") {
        opts.onStatus?.(parsed.data ?? {});
      } else if (parsed.event === "delta" && parsed.data?.text) {
        opts.onDelta?.(String(parsed.data.text));
      } else if (parsed.event === "error") {
        throw new Error(parsed.data?.detail || "stream upstream request failed");
      } else if (parsed.event === "done") {
        return;
      }
    }
  }
}

/**
 * @param {string} sessionId
 * @param {string} userId
 */
export async function deleteSessionRemote(sessionId, userId) {
  const uid = requireUserId(userId);
  const params = new URLSearchParams({ user_id: uid });
  const res = await fetch(`/api/v2/sessions/${encodeURIComponent(sessionId)}?${params}`, {
    method: "DELETE",
  });
  await throwIfNotOk(res);
  return res.json();
}

/**
 * @param {string} userId
 */
export async function deleteUserRemote(userId) {
  const uid = requireUserId(userId);
  const res = await fetch(`/api/v2/users/${encodeURIComponent(uid)}`, {
    method: "DELETE",
  });
  await throwIfNotOk(res);
  return res.json();
}

/** @deprecated 使用 deleteUserRemote */
export const deleteUserMemory = deleteUserRemote;

/**
 * @param {string} userId
 * @param {string} sessionId
 */
export async function fetchExecPending(userId, sessionId) {
  const uid = requireUserId(userId);
  const params = new URLSearchParams({ user_id: uid });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/exec/pending?${params}`,
  );
  await throwIfNotOk(res);
  return res.json();
}

/**
 * @param {string} userId
 * @param {string} sessionId
 * @param {string} pendingId
 */
export async function approveExec(userId, sessionId, pendingId) {
  const uid = requireUserId(userId);
  const params = new URLSearchParams({ user_id: uid });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/exec/approve?${params}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pending_id: pendingId }),
    },
  );
  await throwIfNotOk(res);
  return res.json();
}

/**
 * @param {string} userId
 * @param {string} sessionId
 * @param {string} pendingId
 */
export async function rejectExec(userId, sessionId, pendingId) {
  const uid = requireUserId(userId);
  const params = new URLSearchParams({ user_id: uid });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/exec/reject?${params}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pending_id: pendingId }),
    },
  );
  await throwIfNotOk(res);
  return res.json();
}

/**
 * @param {string} sessionId
 * @param {string} userId
 * @param {number} fromAssistantIndex
 */
export async function regenerateSession(sessionId, userId, fromAssistantIndex) {
  const uid = requireUserId(userId);
  const params = new URLSearchParams({ user_id: uid });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/regenerate?${params}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from_assistant_index: fromAssistantIndex }),
    },
  );
  await throwIfNotOk(res);
  return res.json();
}
