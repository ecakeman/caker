import { createUser as createUserRemote, fetchUsers } from "./store-api.js";

/** @typedef {{ id: string, createdAt: number }} WebUser */

/** @type {WebUser[]} */
let usersCache = [];

/** @returns {WebUser[]} */
export function loadUsers() {
  return usersCache;
}

export async function refreshUsers() {
  usersCache = await fetchUsers();
  if (!usersCache.length) {
    usersCache = [await createUserRemote("local")];
  }
  return usersCache;
}

/** @param {string} id */
export function getUser(id) {
  return usersCache.find((u) => u.id === id) ?? null;
}

/**
 * @param {string} id
 * @returns {Promise<{ ok: true, user: WebUser } | { ok: false, error: string }>}
 */
export async function addUser(id) {
  const trimmed = id.trim();
  if (!trimmed) return { ok: false, error: "用户 ID 不能为空" };
  if (!/^[A-Za-z0-9_-]+$/.test(trimmed)) {
    return { ok: false, error: "仅允许字母、数字、下划线与连字符" };
  }
  if (usersCache.some((u) => u.id === trimmed)) {
    return { ok: false, error: "该用户已存在" };
  }
  try {
    const user = await createUserRemote(trimmed);
    usersCache.push(user);
    return { ok: true, user };
  } catch (e) {
    return { ok: false, error: e.message || "添加用户失败" };
  }
}

/** @param {string} id */
export function removeUserLocal(id) {
  usersCache = usersCache.filter((u) => u.id !== id);
}
