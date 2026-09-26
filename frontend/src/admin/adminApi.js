import { API_URL } from "../api.js";

const TOKEN_KEY = "gem-admin-token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage unavailable (private mode etc.) - stay logged in for this tab only.
  }
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function errorMessage(body, fallback) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  // FastAPI validation errors: [{loc: [..., "field"], msg}]
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => `${d.loc?.[d.loc.length - 1] ?? "field"}: ${d.msg}`)
      .join("; ");
  }
  return fallback;
}

// Called on any 401 so the app can drop back to the login screen.
let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_URL}/api/admin${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && path !== "/login") onUnauthorized();
    throw new ApiError(errorMessage(data, `Request failed (${res.status})`), res.status);
  }
  return data;
}
