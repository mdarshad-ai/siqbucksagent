// Conversations are kept in this browser only, one per partner, so returning
// visitors can pick up where they left off.
const KEY = (agentId) => `loupe-chat-${agentId}`;
const MAX_MESSAGES = 60;

export function loadHistory(agentId) {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY(agentId)) || "null");
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

export function saveHistory(agentId, history) {
  try {
    if (history.length) localStorage.setItem(KEY(agentId), JSON.stringify(history.slice(-MAX_MESSAGES)));
    else localStorage.removeItem(KEY(agentId));
  } catch {
    // Storage full or blocked: the chat still works, it just won't be remembered.
  }
}
