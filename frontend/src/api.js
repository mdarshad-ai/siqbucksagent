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

async function chatErrorFrom(res) {
  const err = await res.json().catch(() => ({}));
  const detail = err.detail;
  if (detail && typeof detail === "object" && detail.code) {
    return new ChatError(detail.message, { code: detail.code, retryAfter: detail.retry_after });
  }
  return new ChatError(typeof detail === "string" ? detail : "Chat request failed");
}

// Read a server-sent event stream. handlers: onDelta(text), onCard(card),
// onImagePending({id, label, item_name}), onImage({id, image}),
// onImageFailed({id}), onSuggestions(options), onHandoff(handoff). Resolves
// with the "done" payload ({reply, cards, images, suggestions, handoff, history}).
async function readEvents(res, handlers) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done = null;
  for (;;) {
    const { value, done: finished } = await reader.read();
    if (finished) break;
    buffer += decoder.decode(value, { stream: true });
    let split;
    while ((split = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      const payload = data ? JSON.parse(data) : {};
      if (event === "delta") handlers.onDelta?.(payload.text);
      else if (event === "card") handlers.onCard?.(payload.card);
      else if (event === "image_pending") handlers.onImagePending?.(payload);
      else if (event === "image") handlers.onImage?.(payload);
      else if (event === "image_failed") handlers.onImageFailed?.(payload);
      else if (event === "suggestions") handlers.onSuggestions?.(payload.options);
      else if (event === "handoff") handlers.onHandoff?.(payload);
      else if (event === "error") throw new ChatError(payload.message);
      else if (event === "done") done = payload;
    }
  }
  if (!done) throw new ChatError("The connection dropped. Please try again.");
  return done;
}

// Stream a partner's reply to a customer message.
export async function streamChat(agentId, message, history, handlers = {}) {
  const res = await fetch(`${API_URL}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Visitor-Id": getVisitorId() },
    body: JSON.stringify({ agent_id: agentId, message, history }),
  });
  if (!res.ok) throw await chatErrorFrom(res);
  return readEvents(res, handlers);
}

// Stream the partner's opening pitch for a stone page.
export async function streamPitch(stoneId, handlers = {}) {
  const res = await fetch(`${API_URL}/api/stones/${stoneId}/pitch`, {
    method: "POST",
    headers: { "X-Visitor-Id": getVisitorId() },
  });
  if (!res.ok) throw await chatErrorFrom(res);
  return readEvents(res, handlers);
}

export async function fetchCatalog(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== undefined)
  );
  const res = await fetch(`${API_URL}/api/catalog?${query}`);
  if (!res.ok) throw new Error("Couldn't load the catalogue");
  return res.json();
}

export async function fetchStone(id) {
  const res = await fetch(`${API_URL}/api/stones/${id}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Couldn't load this stone");
  return res.json();
}

export async function routeQuestion(message) {
  try {
    const res = await fetch(`${API_URL}/api/route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    if (res.ok) return (await res.json()).agent_id;
  } catch {
    // Fall through to the default partner.
  }
  return null;
}

export async function fetchFeatured() {
  try {
    const res = await fetch(`${API_URL}/api/featured`);
    return res.ok ? res.json() : [];
  } catch {
    return [];
  }
}
