/** @typedef {{ message: string, session_id?: string }} ChatBody */

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
 * @param {ChatBody} body
 * @param {{ userId?: string, signal?: AbortSignal }} opts
 * @returns {Promise<string>}
 */
export async function chatGraph(body, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  if (opts.userId) headers["x-user-id"] = opts.userId;

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
 * @param {ChatBody} body
 * @param {{
 *   userId?: string,
 *   signal?: AbortSignal,
 *   onDelta?: (text: string) => void,
 * }} opts
 */
export async function streamChat(body, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  if (opts.userId) headers["x-user-id"] = opts.userId;

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

      if (parsed.event === "delta" && parsed.data?.text) {
        opts.onDelta?.(String(parsed.data.text));
      } else if (parsed.event === "error") {
        throw new Error(parsed.data?.detail || "stream upstream request failed");
      } else if (parsed.event === "done") {
        return;
      }
    }
  }
}
