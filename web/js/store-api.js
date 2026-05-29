/** @param {Response} res */
async function throwIfNotOk(res) {
  if (res.ok) return;
  let detail = res.statusText;
  try {
    const j = await res.json();
    if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
  } catch {
    /* ignore */
  }
  if (res.status === 404 && detail === "Not Found") {
    detail = "文件不存在";
  }
  throw new Error(detail || `HTTP ${res.status}`);
}

export async function fetchUsers() {
  const res = await fetch("/api/v2/web/users");
  await throwIfNotOk(res);
  const data = await res.json();
  return data.users ?? [];
}

export async function createUser(id) {
  const res = await fetch("/api/v2/web/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  await throwIfNotOk(res);
  const data = await res.json();
  return data.user;
}

export async function fetchSettings() {
  const res = await fetch("/api/v2/web/settings");
  await throwIfNotOk(res);
  return res.json();
}

/** @param {Record<string, unknown>} patch */
export async function saveSettingsRemote(patch) {
  const res = await fetch("/api/v2/web/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  await throwIfNotOk(res);
  return res.json();
}

export async function listSessions(userId) {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(`/api/v2/web/sessions?${params}`);
  await throwIfNotOk(res);
  const data = await res.json();
  return data.sessions ?? [];
}

export async function getSession(userId, sessionId) {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}?${params}`
  );
  await throwIfNotOk(res);
  const data = await res.json();
  return data.session;
}

export async function createSession(userId) {
  const res = await fetch("/api/v2/web/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
  await throwIfNotOk(res);
  const data = await res.json();
  return data.session;
}

/** @param {object} session */
export async function saveSession(session) {
  const res = await fetch(`/api/v2/web/sessions/${encodeURIComponent(session.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(session),
  });
  await throwIfNotOk(res);
  const data = await res.json();
  return data.session;
}

/**
 * @param {string} userId
 * @param {string} sessionId
 * @param {FileList | File[]} files
 */
export async function fetchWorkspace(userId, sessionId) {
  const params = new URLSearchParams({
    user_id: userId,
    session_id: sessionId,
  });
  const res = await fetch(`/api/v2/web/workspace?${params}`);
  await throwIfNotOk(res);
  return res.json();
}

/**
 * @param {string} userId
 * @param {string} sessionId
 */
export async function revealWorkspace(userId, sessionId) {
  const params = new URLSearchParams({
    user_id: userId,
    session_id: sessionId,
  });
  const res = await fetch(`/api/v2/web/workspace/reveal?${params}`, {
    method: "POST",
  });
  await throwIfNotOk(res);
  return res.json();
}

export async function uploadSessionFiles(userId, sessionId, files) {
  const params = new URLSearchParams({ user_id: userId });
  const form = new FormData();
  for (const f of files) {
    form.append("files", f);
  }
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/upload?${params}`,
    { method: "POST", body: form }
  );
  await throwIfNotOk(res);
  return res.json();
}

/** @param {{ users?: unknown[], sessions?: unknown[], settings?: object }} payload */
export async function fetchWorkspaceTree(userId, sessionId) {
  const params = new URLSearchParams({
    user_id: userId,
    session_id: sessionId,
  });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/workspace/tree?${params}`
  );
  await throwIfNotOk(res);
  return res.json();
}

export async function fetchLlmProfile(userId) {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(`/api/v2/web/llm/profile?${params}`);
  await throwIfNotOk(res);
  return res.json();
}

/** @param {string} userId @param {object} profile */
export async function saveLlmProfile(userId, profile) {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(`/api/v2/web/llm/profile?${params}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  await throwIfNotOk(res);
  return res.json();
}

/** @param {{ baseUrl: string, apiKey?: string }} body */
export async function fetchLlmModels(body) {
  const res = await fetch("/api/v2/web/llm/models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await throwIfNotOk(res);
  return res.json();
}

export async function fetchWorkspaceFile(userId, sessionId, path) {
  const params = new URLSearchParams({
    user_id: userId,
    session_id: sessionId,
    path,
  });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/workspace/file?${params}`
  );
  await throwIfNotOk(res);
  return res.json();
}

export async function saveWorkspaceFile(userId, sessionId, path, content) {
  const params = new URLSearchParams({
    user_id: userId,
    session_id: sessionId,
    path,
  });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/workspace/file?${params}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    }
  );
  await throwIfNotOk(res);
  return res.json();
}

export async function importLegacy(payload) {
  const res = await fetch("/api/v2/web/import-legacy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await throwIfNotOk(res);
  return res.json();
}

export async function fetchComposeStatus(userId, sessionId) {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/compose/status?${params}`,
  );
  await throwIfNotOk(res);
  return res.json();
}

export async function composeUp(userId, sessionId) {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/compose/up?${params}`,
    { method: "POST" },
  );
  await throwIfNotOk(res);
  return res.json();
}

export async function composeDown(userId, sessionId) {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/compose/down?${params}`,
    { method: "POST" },
  );
  await throwIfNotOk(res);
  return res.json();
}

export async function workspaceMkdir(userId, sessionId, path) {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/workspace/mkdir?${params}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    },
  );
  await throwIfNotOk(res);
  return res.json();
}

export async function workspaceCopy(userId, sessionId, src, destDir) {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/workspace/copy?${params}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ src, dest_dir: destDir }),
    },
  );
  await throwIfNotOk(res);
  return res.json();
}

export async function workspaceMove(userId, sessionId, src, dest) {
  const params = new URLSearchParams({ user_id: userId });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/workspace/move?${params}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ src, dest }),
    },
  );
  await throwIfNotOk(res);
  return res.json();
}

export async function workspaceDeleteEntry(userId, sessionId, path) {
  const params = new URLSearchParams({ user_id: userId, path });
  const res = await fetch(
    `/api/v2/web/sessions/${encodeURIComponent(sessionId)}/workspace/entry?${params}`,
    { method: "DELETE" },
  );
  await throwIfNotOk(res);
  return res.json();
}
