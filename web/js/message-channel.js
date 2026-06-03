/** @typedef {'main' | 'followup'} MessageChannel */

export const CHANNEL_MAIN = "main";
export const CHANNEL_FOLLOWUP = "followup";

/** @param {MessageChannel} [channel] */
export function normalizeChannel(channel) {
  return channel === CHANNEL_FOLLOWUP ? CHANNEL_FOLLOWUP : CHANNEL_MAIN;
}

/**
 * @param {object} msg
 * @param {MessageChannel} [channel]
 */
export function tagMessage(msg, channel = CHANNEL_MAIN) {
  return { ...msg, channel: normalizeChannel(channel) };
}

/**
 * @param {Array<{ role?: string, channel?: string }> | undefined} messages
 * @param {MessageChannel} channel
 */
export function filterMessagesByChannel(messages, channel) {
  const want = normalizeChannel(channel);
  return (messages || []).filter((m) => {
    if (m.role !== "user" && m.role !== "assistant") return false;
    return normalizeChannel(m.channel) === want;
  });
}

/**
 * Map display index (in filtered list) to index in full messages array.
 * @param {Array<{ role?: string, channel?: string }>} all
 * @param {MessageChannel} channel
 * @param {number} displayIndex
 */
export function globalIndexForDisplay(all, channel, displayIndex) {
  const want = normalizeChannel(channel);
  let seen = -1;
  for (let i = 0; i < all.length; i++) {
    const m = all[i];
    if (m.role !== "user" && m.role !== "assistant") continue;
    if (normalizeChannel(m.channel) !== want) continue;
    seen += 1;
    if (seen === displayIndex) return i;
  }
  return -1;
}
