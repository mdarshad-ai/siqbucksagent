import { useEffect, useRef, useState } from "react";
import { requestReservation } from "../api.js";

function formatPrice(n) {
  return `$${Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export default function ReserveModal({ card, getTranscript, onClose, onRequested }) {
  const [form, setForm] = useState({ name: "", email: "", phone: "", note: "", consent: false, share_chat: true });
  const [website, setWebsite] = useState(""); // honeypot
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);
  const firstField = useRef(null);

  useEffect(() => {
    firstField.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const set = (key) => (e) =>
    setForm((f) => ({ ...f, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const transcript = form.share_chat
        ? getTranscript().map(({ role, content }) => ({ role, content: content.slice(0, 4000) }))
        : [];
      const res = await requestReservation({
        agent_id: card.agent_id,
        item_id: card.id,
        ...form,
        transcript,
        website,
      });
      setDone(res.reference);
      onRequested(res.reference);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="reserve-title">
        <button className="modal-close" onClick={onClose} aria-label="Close">
          ✕
        </button>
        {done ? (
          <div className="reserve-done">
            <div className="reserve-done-gem">◆</div>
            <h2 id="reserve-title">Request sent</h2>
            <p>
              Your reference is <strong>{done}</strong>. The shop will contact you to confirm the hold on
              the <strong>{card.name}</strong>.
            </p>
            <p className="modal-muted">Nothing is held until the shop confirms.</p>
            <button className="modal-primary" onClick={onClose}>
              Back to the chat
            </button>
          </div>
        ) : (
          <form onSubmit={submit}>
            <h2 id="reserve-title">Reserve this stone</h2>
            <div className="reserve-stone">
              <span>{card.name}</span>
              <span className="reserve-price">{formatPrice(card.price)}</span>
            </div>
            <p className="modal-muted">
              Send a request and the shop will contact you to confirm. Once confirmed, the stone is held
              for you for a few days. No payment is taken here.
            </p>
            <label>
              Your name
              <input ref={firstField} value={form.name} onChange={set("name")} required maxLength={120} autoComplete="name" />
            </label>
            <label>
              Email
              <input type="email" value={form.email} onChange={set("email")} required maxLength={255} autoComplete="email" />
            </label>
            <label>
              <span>
                Phone <span className="modal-muted">(optional)</span>
              </span>
              <input type="tel" value={form.phone} onChange={set("phone")} maxLength={40} autoComplete="tel" />
            </label>
            <label>
              <span>
                Anything we should know? <span className="modal-muted">(optional)</span>
              </span>
              <textarea
                rows={3}
                value={form.note}
                onChange={set("note")}
                maxLength={1000}
                placeholder="e.g. I'd like to see it in person on Saturday."
              />
            </label>
            {/* Hidden from people; bots tend to fill it in. */}
            <input
              className="honeypot"
              tabIndex={-1}
              autoComplete="off"
              aria-hidden="true"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              name="website"
            />
            <label className="check">
              <input type="checkbox" checked={form.share_chat} onChange={set("share_chat")} />
              <span>Include my chat with the dealer, so the shop knows what I'm after.</span>
            </label>
            <label className="check">
              <input type="checkbox" checked={form.consent} onChange={set("consent")} required />
              <span>
                I agree to be contacted about this request. My details are only used for it and deleted
                90 days after it's closed.
              </span>
            </label>
            {error && <div className="modal-error">{error}</div>}
            <button className="modal-primary" disabled={busy}>
              {busy ? "Sending..." : "Send request"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
