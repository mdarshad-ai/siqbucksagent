import { useEffect, useRef, useState } from "react";
import Character from "../components/Character.jsx";
import PreviewCards from "../components/PreviewCard.jsx";
import RichText from "../components/RichText.jsx";
import StoneCard from "../components/StoneCard.jsx";
import { LogoMark } from "../site/Logo.jsx";
import { partnerCopy } from "../site/partners.js";

function Turn({ turn, history, partner, onHandoff, disabled }) {
  return (
    <div className={`chat-turn chat-turn-${turn.role}`}>
      {(turn.content || turn.role === "user") && (
        <div className={`chat-bubble chat-bubble-${turn.role}`}>
          {turn.role === "assistant" ? <RichText text={turn.content} /> : turn.content}
          {turn.streaming && <span className="stream-caret" aria-hidden="true" />}
        </div>
      )}
      {turn.cards?.length > 0 && (
        <div className="stone-cards">
          {turn.cards.map((card) => (
            <StoneCard key={card.id} card={card} getTranscript={() => history} />
          ))}
        </div>
      )}
      <PreviewCards images={turn.images} partner={partner} getTranscript={() => history} />
      {turn.handoff && (
        <div className="handoff">
          <span>
            {turn.handoff.display_name} at {turn.handoff.stall_name} can help with this.
          </span>
          <button onClick={() => onHandoff(turn.handoff)} disabled={disabled}>
            Continue with {turn.handoff.display_name} <span aria-hidden="true">→</span>
          </button>
        </div>
      )}
    </div>
  );
}

export default function CounterView({
  agents,
  agent,
  history,
  live,
  busy,
  error,
  restored,
  onSend,
  onSwitch,
  onClose,
  onHandoff,
  onStartFresh,
}) {
  const [input, setInput] = useState("");
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const copy = partnerCopy(agent.id);

  useEffect(() => {
    inputRef.current?.focus();
  }, [agent.id]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && !document.querySelector(".modal, .lightbox") && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [history.length, live?.content, live?.cards?.length, live?.images?.length, agent.id, error]);

  function send(text) {
    const message = (text ?? input).trim();
    if (!message || busy) return;
    if (text === undefined) setInput("");
    // If sending fails, give the typed text back so it can be retried.
    Promise.resolve(onSend(message)).then((ok) => {
      if (!ok && text === undefined) setInput(message);
    });
  }

  const turns = live ? [...history, live] : history;
  const last = history[history.length - 1];
  const suggestions = !busy && last?.role === "assistant" ? last.suggestions || [] : [];
  const sketching = live?.images?.some((i) => i.pending);
  const status = busy
    ? sketching
      ? `${agent.display_name} is sketching a preview...`
      : live?.content
      ? `${agent.display_name} is talking...`
      : `${agent.display_name} is checking the stock...`
    : copy.role;

  return (
    <div
      className="counter"
      role="dialog"
      aria-modal="true"
      aria-label={`Chat with ${agent.display_name}`}
      style={{ "--stall-accent": agent.theme.accent, "--stall-glow": agent.theme.glow }}
    >
      <header className="counter-bar">
        <span className="counter-brand">
          <LogoMark size={26} />
          <span>Luxuria Gems</span>
        </span>
        <div className="counter-switch" role="tablist" aria-label="Choose an AI partner">
          {agents.map((a) => (
            <button
              key={a.id}
              role="tab"
              aria-selected={a.id === agent.id}
              className={a.id === agent.id ? "is-current" : ""}
              style={{ "--stall-accent": a.theme.accent }}
              onClick={() => onSwitch(a.id)}
              disabled={busy && a.id !== agent.id}
            >
              <span className="counter-switch-dot" />
              {a.display_name}
            </button>
          ))}
        </div>
        <button className="counter-close" onClick={onClose}>
          <span className="counter-close-label">Back to the shop</span>
          <span aria-hidden="true">✕</span>
        </button>
      </header>

      <div className="counter-body">
        <aside className="counter-stage">
          <div className="counter-plinth">
            <Character theme={agent.theme} variant={agent.id} talking={busy} active />
            <div className="counter-stage-text">
              <h2>{agent.display_name}</h2>
              <div className="counter-stall">{agent.stall_name}</div>
              <p className="counter-tagline">“{agent.tagline}”</p>
              <div className={`counter-status ${busy ? "is-busy" : ""}`} aria-live="polite">
                {status}
              </div>
            </div>
          </div>
        </aside>

          <section className="counter-chat">
            <div className="counter-thread" ref={scrollRef}>
              {restored && history.length > 0 && (
                <div className="welcome-back">
                  Welcome back. Here's where you left off with {agent.display_name}.
                  <button onClick={onStartFresh} disabled={busy}>
                    Start fresh
                  </button>
                </div>
              )}
              {turns.length === 0 && (
                <div className="counter-empty">
                  <p className="counter-greeting">“{copy.greeting}”</p>
                  <div className="counter-empty-prompts">
                    {copy.questions.map((q) => (
                      <button key={q} className="chip" onClick={() => send(q)}>
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {turns.map((turn, i) => (
                <Turn
                  key={i}
                  turn={turn}
                  history={history}
                  partner={agent.display_name}
                  onHandoff={onHandoff}
                  disabled={busy}
                />
              ))}
              {busy && !live?.content && !live?.cards?.length && !live?.images?.length && (
                <div className="chat-bubble chat-bubble-assistant chat-bubble-thinking" aria-label="Thinking">
                  <span className="dots">
                    <span className="dot" />
                    <span className="dot" />
                    <span className="dot" />
                  </span>
                </div>
              )}
              {error && <div className="chat-error">{error}</div>}
            </div>

            {suggestions.length > 0 && (
              <div className="counter-suggestions" aria-label="Suggested questions">
                {suggestions.map((s) => (
                  <button key={s} className="chip" onClick={() => send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            )}

            <form
              className="counter-input"
              onSubmit={(e) => {
                e.preventDefault();
                send();
              }}
            >
              <label className="visually-hidden" htmlFor="counter-message">
                Message {agent.display_name}
              </label>
              <input
                id="counter-message"
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={`Ask ${agent.display_name} anything...`}
                maxLength={2000}
                autoComplete="off"
              />
              <button type="submit" disabled={busy || !input.trim()}>
                Send
              </button>
            </form>
          </section>
        </div>
      </div>
    );
  }
