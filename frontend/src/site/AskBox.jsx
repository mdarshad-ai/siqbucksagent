import { useState } from "react";

// The "just ask" box: a question field plus tappable example prompts.
export default function AskBox({ onAsk, prompts = [], placeholder, buttonLabel = "Ask", compact = false }) {
  const [text, setText] = useState("");

  function submit(e) {
    e.preventDefault();
    const message = text.trim();
    if (!message) return;
    onAsk(message);
    setText("");
  }

  return (
    <div className={`askbox ${compact ? "askbox-compact" : ""}`}>
      <form className="askbox-field" onSubmit={submit}>
        <label className="visually-hidden" htmlFor={compact ? "ask-compact" : "ask-hero"}>
          What are you looking for?
        </label>
        <input
          id={compact ? "ask-compact" : "ask-hero"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={placeholder}
          maxLength={2000}
          autoComplete="off"
        />
        <button type="submit" disabled={!text.trim()}>
          {buttonLabel} <span aria-hidden="true">→</span>
        </button>
      </form>
      {prompts.length > 0 && (
        <div className="askbox-prompts">
          {prompts.map((p) => (
            <button key={p} type="button" className="chip" onClick={() => onAsk(p)}>
              {p}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
