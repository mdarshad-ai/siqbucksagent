import { useEffect, useRef, useState } from "react";
import { sendChatMessage } from "../api.js";
import RichText from "./RichText.jsx";
import StoneCard from "./StoneCard.jsx";

function waitText(seconds) {
  const minutes = Math.ceil((seconds || 60) / 60);
  return minutes <= 1 ? "a minute" : `${minutes} minutes`;
}

// Limit messages in the dealer's own voice rather than a bare error.
export function friendlyChatError(err, name) {
  if (err.code === "slow_down") {
    return `${name} sets down the loupe. "Give me ${waitText(err.retryAfter)}, then ask me again."`;
  }
  if (err.code === "daily") {
    return `${name} smiles. "That's plenty of questions for one day. Come back tomorrow and I'll be here."`;
  }
  if (err.code === "closed") {
    return "The counters are closed for tonight. Please come back tomorrow.";
  }
  return err.message;
}

export default function ChatPanel({ agent, history, setHistory, onTalkingChange }) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [history, loading]);

  async function handleSend(e) {
    e.preventDefault();
    const message = input.trim();
    if (!message || loading) return;

    setInput("");
    setError(null);
    const optimistic = [...history, { role: "user", content: message }];
    setHistory(optimistic);
    setLoading(true);
    onTalkingChange(true);

    try {
      const data = await sendChatMessage(agent.id, message, history);
      setHistory(data.history);
    } catch (err) {
      setError(friendlyChatError(err, agent.display_name));
      setHistory(history); // roll back optimistic update on failure
      setInput(message); // give the user their text back so they can retry
    } finally {
      setLoading(false);
      onTalkingChange(false);
    }
  }

  return (
    <div className="chat-panel" style={{ "--stall-accent": agent.theme.accent }}>
      <div className="chat-header">
        <div>
          <div className="chat-header-name">{agent.display_name}</div>
          <div className="chat-header-stall">{agent.stall_name}</div>
        </div>
      </div>

      <div className="chat-scroll" ref={scrollRef}>
        {history.length === 0 && (
          <div className="chat-empty">
            Say hello to {agent.display_name} — ask what's in stock, prices,
            or for a recommendation.
          </div>
        )}
        {history.map((turn, i) => (
          <div key={i} className={`chat-turn chat-turn-${turn.role}`}>
            <div className={`chat-bubble chat-bubble-${turn.role}`}>
              {turn.role === "assistant" ? <RichText text={turn.content} /> : turn.content}
            </div>
            {turn.cards?.length > 0 && (
              <div className="stone-cards">
                {turn.cards.map((card) => (
                  <StoneCard key={card.id} card={card} getTranscript={() => history} />
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="chat-bubble chat-bubble-assistant chat-bubble-loading">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </div>
        )}
      </div>

      {error && <div className="chat-error">{error}</div>}

      <form className="chat-input-row" onSubmit={handleSend}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={`Ask ${agent.display_name} something...`}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
