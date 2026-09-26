import { useEffect, useState } from "react";
import { api } from "./adminApi.js";

const FIELDS = [
  ["burst_limit", "Messages per visitor in a short burst", "e.g. 15"],
  ["burst_window_minutes", "Burst window (minutes)", "e.g. 10"],
  ["visitor_daily_limit", "Messages per visitor per day", "e.g. 100"],
  ["global_daily_limit", "Messages for the whole shop per day", "Your budget ceiling"],
  ["history_messages", "Past messages sent to the AI with each question", "Fewer = cheaper, less memory"],
];

function shortDay(day) {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, { weekday: "short", timeZone: "UTC" });
}

export default function SettingsTab() {
  const [usage, setUsage] = useState(null);
  const [form, setForm] = useState(null);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  function load() {
    api("/usage")
      .then((u) => {
        setUsage(u);
        setForm((f) => f ?? Object.fromEntries(FIELDS.map(([k]) => [k, String(u.settings[k])])));
      })
      .catch((err) => setError(err.message));
  }

  useEffect(load, []);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const body = Object.fromEntries(FIELDS.map(([k]) => [k, Number(form[k])]));
      const saved = await api("/settings/limits", { method: "PUT", body });
      setForm(Object.fromEntries(FIELDS.map(([k]) => [k, String(saved[k])])));
      setStatus("Saved. New limits apply within 30 seconds.");
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!usage || !form) return error ? <div className="admin-error">{error}</div> : <div className="admin-muted">Loading...</div>;

  const cap = usage.settings.global_daily_limit;
  const used = usage.today.messages;
  const pct = Math.min(100, Math.round((used / cap) * 100));
  const maxDay = Math.max(1, ...usage.last_7_days.map((d) => d.count));

  return (
    <section className="settings-layout">
      <div className="admin-card">
        <h3>Chat usage today</h3>
        <div className="usage-stats">
          <div>
            <div className="usage-number">{used.toLocaleString()}</div>
            <div className="admin-muted">messages of {cap.toLocaleString()} daily cap</div>
          </div>
          <div>
            <div className="usage-number">{usage.today.visitors.toLocaleString()}</div>
            <div className="admin-muted">visitors chatting</div>
          </div>
        </div>
        <div className="progress usage-meter" title={`${pct}% of today's cap`}>
          <div className={`progress-bar ${pct >= 90 ? "progress-bar-warn" : ""}`} style={{ width: `${pct}%` }} />
        </div>
        <p className="admin-hint">Counts reset at midnight UTC.</p>

        <h3 className="usage-week-title">Last 7 days</h3>
        <div className="usage-week">
          {usage.last_7_days.map((d) => (
            <div key={d.day} className="usage-day" title={`${d.day}: ${d.count} messages`}>
              <div className="usage-bar-track">
                <div className="usage-bar" style={{ height: `${(d.count / maxDay) * 100}%` }} />
              </div>
              <div className="usage-day-count">{d.count}</div>
              <div className="admin-muted">{shortDay(d.day)}</div>
            </div>
          ))}
        </div>
      </div>

      <form className="admin-card" onSubmit={save}>
        <h3>Chat limits</h3>
        <p className="admin-muted">
          Protects your OpenRouter bill. Customers who hit a limit get a friendly message from the
          dealer instead of an answer.
        </p>
        <div className="form-grid">
          {FIELDS.map(([key, label, hint]) => (
            <label key={key} className="span-2">
              {label}
              <input
                type="number"
                min="1"
                step="1"
                value={form[key]}
                onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                placeholder={hint}
                required
              />
            </label>
          ))}
        </div>
        {status && <div className="admin-success">{status}</div>}
        {error && <div className="admin-error">{error}</div>}
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Saving..." : "Save limits"}
        </button>
      </form>
    </section>
  );
}
