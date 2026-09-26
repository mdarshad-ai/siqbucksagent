// In dev the API runs separately on :8000. In a production build with no
// VITE_API_URL, the backend serves this app itself, so use the same origin.
export const API_URL =
  import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

export async function fetchAgents() {
  const res = await fetch(`${API_URL}/api/agents`);
  if (!res.ok) throw new Error("Failed to load agents");
  return res.json();
}

export async function fetchInventory(agentId) {
  const res = await fetch(`${API_URL}/api/agents/${agentId}/inventory`);
  if (!res.ok) throw new Error("Failed to load inventory");
  return res.json();
}

// An anonymous id for this browser, used only for fair-use chat limits.
let sessionVisitorId = null;
export function getVisitorId() {
  try {
    let id = localStorage.getItem("gem-visitor-id");
    if (!id) {
      id = crypto.randomUUID().replace(/-/g, "");
      localStorage.setItem("gem-visitor-id", id);
    }
    return id;
  } catch {
    // Storage blocked: keep one id for this page load.
    sessionVisitorId ??= Math.random().toString(36).slice(2).padEnd(12, "0");
    return sessionVisitorId;
  }
}

export class ChatError extends Error {
  constructor(message, { code = null, retryAfter = null } = {}) {
    super(message);
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

export async function sendChatMessage(agentId, message, history) {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Visitor-Id": getVisitorId() },
    body: JSON.stringify({ agent_id: agentId, message, history }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    if (detail && typeof detail === "object" && detail.code) {
      throw new ChatError(detail.message, { code: detail.code, retryAfter: detail.retry_after });
    }
    throw new ChatError(typeof detail === "string" ? detail : "Chat request failed");
  }
  return res.json();
}

// Media URLs from local-dev storage are relative to the API; Supabase URLs
// are absolute already.
export function assetUrl(url) {
  return url && url.startsWith("/") ? `${API_URL}${url}` : url;
}

export async function requestReservation(body) {
  const res = await fetch(`${API_URL}/api/reservations`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Visitor-Id": getVisitorId() },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const message = Array.isArray(detail)
      ? "Please check the form: " + detail.map((d) => d.loc?.[d.loc.length - 1]).join(", ")
      : detail || "Couldn't send your request. Please try again.";
    throw new Error(message);
  }
  return data;
}

// Remember which stones this browser has already asked to reserve.
const REQUESTED_KEY = "gem-requested";
export function getRequested() {
  try {
    return JSON.parse(localStorage.getItem(REQUESTED_KEY) || "{}");
  } catch {
    return {};
  }
}
export function rememberRequested(stoneKey, reference) {
  try {
    localStorage.setItem(REQUESTED_KEY, JSON.stringify({ ...getRequested(), [stoneKey]: reference }));
  } catch {
    // Not critical - the button just won't remember after a reload.
  }
}
