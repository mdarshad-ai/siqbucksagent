import { useEffect, useRef, useState } from "react";
import RichText from "../components/RichText.jsx";
import { api } from "./adminApi.js";

const FIELDS = ["display_name", "stall_name", "tagline", "persona", "selling_rules"];

function pickFields(source) {
  return Object.fromEntries(FIELDS.map((k) => [k, source[k] ?? ""]));
}

function formatDate(value) {
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function PreviewChat({ agentId, draft, name }) {
  const [history, setHistory] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [history, busy]);

  async function send(e) {
    e.preventDefault();
    const message = input.trim();
    if (!message || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    const before = history;
    setHistory([...history, { role: "user", content: message }]);
    try {
      const data = await api(`/agents/${agentId}/preview`, {
        method: "POST",
        body: { draft, message, history: before },
      });
      setHistory(data.history);
    } catch (err) {
      setError(err.message);
      setHistory(before);
      setInput(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-card preview">
      <div className="admin-row admin-row-between">
        <h3>Preview chat</h3>
        <button className="btn" onClick={() => setHistory([])} disabled={!history.length || busy}>
          Clear
        </button>
      </div>
      <p className="admin-muted">
        Talks to your <strong>unsaved draft</strong> using the real inventory. Customers don't see this.
      </p>
      <div className="preview-scroll" ref={scrollRef}>
        {history.length === 0 && <div className="admin-muted">Ask {name || "the agent"} something to test the draft.</div>}
        {history.map((turn, i) => (
          <div key={i} className={`preview-bubble preview-${turn.role}`}>
            {turn.role === "assistant" ? <RichText text={turn.content} /> : turn.content}
          </div>
        ))}
        {busy && <div className="preview-bubble preview-assistant admin-muted">Thinking...</div>}
      </div>
      {error && <div className="admin-error">{error}</div>}
      <form className="admin-row" onSubmit={send}>
        <input
          className="grow"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Try a customer question..."
          disabled={busy}
          maxLength={2000}
        />
        <button className="btn btn-primary" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}

export default function AgentsTab() {
  const [agents, setAgents] = useState([]);
  const [agentId, setAgentId] = useState(null);
  const [published, setPublished] = useState(null);
  const [draft, setDraft] = useState(null);
  const [coreRules, setCoreRules] = useState("");
  const [versions, setVersions] = useState([]);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/agents")
      .then((list) => {
        setAgents(list);
        if (list.length) setAgentId(list[0].id);
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!agentId) return;
    setError(null);
    setStatus(null);
    Promise.all([api(`/agents/${agentId}`), api(`/agents/${agentId}/versions`)])
      .then(([agent, vers]) => {
        setPublished(pickFields(agent));
        setDraft(pickFields(agent));
        setCoreRules(agent.core_rules);
        setVersions(vers);
      })
      .catch((err) => setError(err.message));
  }, [agentId]);

  const dirty = draft && published && FIELDS.some((k) => draft[k] !== published[k]);

  function switchAgent(id) {
    if (dirty && !window.confirm("Discard your unpublished changes?")) return;
    setAgentId(id);
  }

  const set = (key) => (e) => setDraft((d) => ({ ...d, [key]: e.target.value }));

  async function publish() {
    setBusy(true);
    setError(null);
    try {
      const agent = await api(`/agents/${agentId}`, { method: "PUT", body: { ...draft, note } });
      setPublished(pickFields(agent));
      setDraft(pickFields(agent));
      setVersions(await api(`/agents/${agentId}/versions`));
      setAgents((prev) => prev.map((a) => (a.id === agentId ? { ...a, ...pickFields(agent) } : a)));
      setNote("");
      setStatus("Published. Customers now chat with this version.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function loadVersion(v) {
    setDraft(pickFields(v));
    setStatus(`Loaded the version from ${formatDate(v.created_at)} into the editor. Preview it, then publish to restore it.`);
  }

  return (
    <section>
      <div className="admin-row admin-toolbar">
        <div className="segmented">
          {agents.map((a) => (
            <button
              key={a.id}
              className={agentId === a.id ? "segmented-active" : ""}
              onClick={() => switchAgent(a.id)}
            >
              {a.display_name}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="admin-error">{error}</div>}

      {draft && (
        <div className="agent-layout">
          <div className="agent-editor">
            <div className="admin-card">
              <div className="form-grid">
                <label>
                  Name
                  <input value={draft.display_name} onChange={set("display_name")} maxLength={80} />
                </label>
                <label>
                  Stall name
                  <input value={draft.stall_name} onChange={set("stall_name")} maxLength={120} />
                </label>
                <label className="span-2">
                  Tagline
                  <input value={draft.tagline} onChange={set("tagline")} maxLength={200} />
                </label>
                <label className="span-2">
                  Persona <span className="admin-muted">— who they are and how they talk</span>
                  <textarea rows={7} value={draft.persona} onChange={set("persona")} maxLength={8000} />
                </label>
                <label className="span-2">
                  Selling style <span className="admin-muted">— how they sell and handle requests</span>
                  <textarea rows={7} value={draft.selling_rules} onChange={set("selling_rules")} maxLength={8000} />
                </label>
              </div>

              <details className="core-rules">
                <summary>Core rules (always applied, can't be edited here)</summary>
                <pre>{coreRules}</pre>
              </details>

              {status && <div className="admin-success">{status}</div>}
              <div className="admin-row publish-row">
                <input
                  className="grow"
                  placeholder="What changed? (optional note for the history)"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  maxLength={255}
                />
                <button
                  className="btn"
                  onClick={() => setDraft(published)}
                  disabled={!dirty || busy}
                >
                  Discard changes
                </button>
                <button className="btn btn-primary" onClick={publish} disabled={!dirty || busy}>
                  {busy ? "Publishing..." : "Publish"}
                </button>
              </div>
              {dirty && <p className="admin-hint">You have unpublished changes.</p>}
            </div>

            <div className="admin-card">
              <h3>History</h3>
              <ul className="version-list">
                {versions.map((v, idx) => (
                  <li key={v.id}>
                    <div>
                      <div className="cell-strong">
                        {v.note || "No note"} {idx === 0 && <span className="pill pill-available">live</span>}
                      </div>
                      <div className="admin-muted">
                        {formatDate(v.created_at)} · {v.created_by}
                      </div>
                    </div>
                    <button className="btn" onClick={() => loadVersion(v)}>
                      Load into editor
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <PreviewChat key={agentId} agentId={agentId} draft={draft} name={draft.display_name} />
        </div>
      )}
    </section>
  );
}
