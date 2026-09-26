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

export async function sendChatMessage(agentId, message, history) {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: agentId, message, history }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Chat request failed");
  }
  return res.json();
}

// Media URLs from local-dev storage are relative to the API; Supabase URLs
// are absolute already.
export function assetUrl(url) {
  return url && url.startsWith("/") ? `${API_URL}${url}` : url;
}
