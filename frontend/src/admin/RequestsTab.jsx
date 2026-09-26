import { useEffect, useState } from "react";
import RichText from "../components/RichText.jsx";
import { api } from "./adminApi.js";

const GROUPS = [
  ["pending", "Waiting"],
  ["active", "On hold"],
  ["closed", "Closed"],
];

const STATUS_LABELS = {
  pending: "Waiting for you",
  confirmed: "On hold",
  declined: "Declined",
  cancelled: "Hold released",
  completed: "Sold",
  expired: "Hold expired",
};

function formatPrice(n) {
  return `$${Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function formatDate(value) {
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function RequestCard({ r, onChange }) {
  const [holdDays, setHoldDays] = useState(3);
  const [extraDays, setExtraDays] = useState(2);
  const [note, setNote] = useState(r.admin_note);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function act(path, body, confirmText) {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    setError(null);
    try {
      onChange(await api(`/reservations/${r.id}/${path}`, { method: "POST", body }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveNote() {
    if (note === r.admin_note) return;
    try {
      onChange(await api(`/reservations/${r.id}`, { method: "PATCH", body: { admin_note: note } }));
    } catch (err) {
      setError(err.message);
    }
  }

  const stock = r.item
    ? `Now: ${r.item.status}${r.item.quantity > 1 ? ` · ${r.item.quantity} in stock` : ""}`
    : "Stone deleted from inventory";

  return (
    <article className="admin-card request-card">
      <header className="admin-row admin-row-between">
        <div>
          <div className="cell-strong">
            {r.item_name} <span className="admin-muted">· {formatPrice(r.item_price)}</span>
          </div>
          <div className="admin-muted">
            {r.reference} · {r.agent_id === "siq" ? "Siq" : r.agent_id === "bucks" ? "Bucks" : r.agent_id} · {stock}
          </div>
        </div>
        <span className={`pill pill-req-${r.status}`}>{STATUS_LABELS[r.status] || r.status}</span>
      </header>

      <div className="request-body">
        <div className="request-customer">
          <div className="cell-strong">{r.customer_name}</div>
          <a href={`mailto:${r.email}?subject=${encodeURIComponent(`Your reservation ${r.reference}: ${r.item_name}`)}`}>{r.email}</a>
          {r.phone && <a href={`tel:${r.phone}`}>{r.phone}</a>}
          <div className="admin-muted">Requested {formatDate(r.created_at)}</div>
          {r.status === "confirmed" && r.hold_until && (
            <div className="request-hold">Held until {formatDate(r.hold_until)}</div>
          )}
          {r.handled_by && r.status !== "pending" && (
            <div className="admin-muted">By {r.handled_by}</div>
          )}
        </div>
        <div className="request-note">
          {r.note ? <blockquote>{r.note}</blockquote> : <div className="admin-muted">No note from the customer.</div>}
          {r.transcript && (
            <details>
              <summary>Their chat with the dealer ({r.transcript.length} messages)</summary>
              <div className="request-transcript">
                {r.transcript.map((m, i) => (
                  <div key={i} className={`preview-bubble preview-${m.role}`}>
                    {m.role === "assistant" ? <RichText text={m.content} /> : m.content}
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      </div>

      <label className="request-admin-note">
        Private notes
        <textarea
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={saveNote}
          placeholder="e.g. Called Tue, visiting Saturday 11am"
          maxLength={2000}
        />
      </label>

      {error && <div className="admin-error">{error}</div>}

      {r.status === "pending" && (
        <div className="admin-row">
          <label className="inline-field">
            Hold for
            <input type="number" min="1" max="30" value={holdDays} onChange={(e) => setHoldDays(e.target.value)} />
            days
          </label>
          <button className="btn btn-primary" disabled={busy} onClick={() => act("confirm", { hold_days: Number(holdDays) })}>
            Confirm hold
          </button>
          <button className="btn btn-danger" disabled={busy} onClick={() => act("decline", undefined, "Decline this request?")}>
            Decline
          </button>
        </div>
      )}
      {r.status === "confirmed" && (
        <div className="admin-row">
          <button className="btn btn-primary" disabled={busy} onClick={() => act("complete", undefined, "Mark this stone as sold to this customer?")}>
            Mark sold
          </button>
          <label className="inline-field">
            <input type="number" min="1" max="30" value={extraDays} onChange={(e) => setExtraDays(e.target.value)} />
            days
          </label>
          <button className="btn" disabled={busy} onClick={() => act("extend", { extra_days: Number(extraDays) })}>
            Extend hold
          </button>
          <button className="btn btn-danger" disabled={busy} onClick={() => act("release", undefined, "Release the hold and put the stone back on sale?")}>
            Release hold
          </button>
        </div>
      )}
      {r.status === "pending" && (
        <p className="admin-hint">
          Contact the customer, then confirm. Confirming marks a one-off stone as reserved (or sets one aside
          if you have several) so the dealers tell other customers it's on hold.
        </p>
      )}
    </article>
  );
}

export default function RequestsTab({ onPendingCount }) {
  const [group, setGroup] = useState("pending");
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  function load(g = group) {
    setLoading(true);
    api(`/reservations?group=${g}`)
      .then(setRows)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
    api("/reservations/summary").then((s) => onPendingCount?.(s.pending)).catch(() => {});
  }

  useEffect(() => load(group), [group]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleChange(updated) {
    // A request that moved to another group leaves this list.
    const stillHere =
      (group === "pending" && updated.status === "pending") ||
      (group === "active" && updated.status === "confirmed") ||
      (group === "closed" && !["pending", "confirmed"].includes(updated.status));
    setRows((prev) => (stillHere ? prev.map((r) => (r.id === updated.id ? updated : r)) : prev.filter((r) => r.id !== updated.id)));
    api("/reservations/summary").then((s) => onPendingCount?.(s.pending)).catch(() => {});
  }

  return (
    <section>
      <div className="admin-row admin-row-between admin-toolbar">
        <div className="segmented">
          {GROUPS.map(([id, label]) => (
            <button key={id} className={group === id ? "segmented-active" : ""} onClick={() => setGroup(id)}>
              {label}
            </button>
          ))}
        </div>
        <button className="btn" onClick={() => load()}>
          Refresh
        </button>
      </div>
      {error && <div className="admin-error">{error}</div>}
      {!loading && rows.length === 0 && (
        <div className="admin-card admin-muted">
          {group === "pending"
            ? "No requests waiting. When a customer taps “Reserve this stone”, it appears here."
            : group === "active"
              ? "No stones on hold right now."
              : "No closed requests. Closed requests and their customer details are deleted after 90 days."}
        </div>
      )}
      {rows.map((r) => (
        <RequestCard key={`${r.id}-${r.status}`} r={r} onChange={handleChange} />
      ))}
    </section>
  );
}
