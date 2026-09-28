import { useEffect, useState } from "react";
import { api } from "./adminApi.js";

const LIMIT_FIELDS = [
  ["image_visitor_daily_limit", "New previews per visitor per day"],
  ["image_global_daily_limit", "New previews for the whole shop per day"],
];

const label = (key) => key.replace("_", " ").replace(/^./, (c) => c.toUpperCase());

// The owner's controls for GemGenerate: on/off, limits, the image model, and
// a tester to try models on a real stone before customers see them.
export default function GemGenerateSettings({ usage, onSaved }) {
  const [status, setStatus] = useState(null); // /gemgenerate
  const [form, setForm] = useState(() => ({
    image_enabled: Boolean(usage.settings.image_enabled),
    ...Object.fromEntries(LIMIT_FIELDS.map(([k]) => [k, String(usage.settings[k])])),
  }));
  const [model, setModel] = useState("");
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/gemgenerate")
      .then((s) => {
        setStatus(s);
        setModel(s.model);
      })
      .catch((err) => setError(err.message));
  }, []);

  async function run(action, done) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(done);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function saveLimits(e) {
    e.preventDefault();
    run(async () => {
      const body = {
        image_enabled: form.image_enabled ? 1 : 0,
        ...Object.fromEntries(LIMIT_FIELDS.map(([k]) => [k, Number(form[k])])),
      };
      await api("/settings/limits", { method: "PUT", body });
    }, "Saved. Changes apply within 30 seconds.");
  }

  function applyModel(next) {
    run(async () => {
      const s = await api("/gemgenerate/model", { method: "PUT", body: { model: next } });
      setStatus(s);
      setModel(s.model);
    }, `Customers' previews now use ${next}.`);
  }

  const used = usage.today.images ?? 0;
  const cap = usage.settings.image_global_daily_limit;

  return (
    <>
      <form className="admin-card" onSubmit={saveLimits}>
        <h3>GemGenerate · AI jewellery previews</h3>
        <p className="admin-muted">
          Siq and Bucks can sketch a stone set in a ring, pendant, earring or bracelet, from the
          stone's catalogue photo. Each preview is labelled as an AI preview. Repeat requests reuse
          the saved picture for free.
        </p>
        <div className="usage-stats">
          <div>
            <div className="usage-number">{used}</div>
            <div className="admin-muted">new previews today, of {cap}</div>
          </div>
          <div>
            <div className="usage-number">{status?.saved_previews ?? "–"}</div>
            <div className="admin-muted">saved previews</div>
          </div>
        </div>
        <div className="form-grid">
          <label className="span-2 check-row">
            <input
              type="checkbox"
              checked={form.image_enabled}
              onChange={(e) => setForm((f) => ({ ...f, image_enabled: e.target.checked }))}
            />
            <span>Let the partners make AI previews for customers</span>
          </label>
          {LIMIT_FIELDS.map(([key, text]) => (
            <label key={key}>
              {text}
              <input
                type="number"
                min="1"
                step="1"
                value={form[key]}
                onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                required
              />
            </label>
          ))}
        </div>
        <button className="btn btn-primary" disabled={busy}>
          Save preview settings
        </button>

        <h3 className="usage-week-title">Image model</h3>
        <p className="admin-muted">
          Any OpenRouter model that takes an image in and gives an image out. Try one below before
          switching. Changing the model makes new previews (old ones stay saved).
        </p>
        <div className="gemgen-model-row">
          <input
            list="gemgen-models"
            value={model}
            onChange={(e) => setModel(e.target.value.trim())}
            aria-label="Image model"
          />
          <button
            type="button"
            className="btn"
            disabled={busy || !model || model === status?.model}
            onClick={() => applyModel(model)}
          >
            Use this model
          </button>
        </div>
        {status && (
          <p className="admin-hint">
            In use: <strong>{status.model}</strong>
            {status.model !== status.default_model && <> · default {status.default_model}</>}
          </p>
        )}
        <datalist id="gemgen-models">
          {status?.choices.map((c) => <option key={c} value={c} />)}
        </datalist>
        {message && <div className="admin-success">{message}</div>}
        {error && <div className="admin-error">{error}</div>}
      </form>

      {status && <ModelTester status={status} onUse={applyModel} busy={busy} />}
    </>
  );
}

function ModelTester({ status, onUse, busy: saving }) {
  const [agents, setAgents] = useState([]);
  const [items, setItems] = useState([]);
  const [req, setReq] = useState({
    agent_id: "",
    item_id: "",
    setting: "ring",
    metal: "yellow_gold",
    style: "",
    model: status.model,
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/agents")
      .then((list) => {
        setAgents(list);
        if (list.length) setReq((r) => ({ ...r, agent_id: list[0].id }));
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!req.agent_id) return;
    api(`/agents/${req.agent_id}/items`)
      .then((list) => {
        const withMedia = list.filter((i) => i.media_count > 0);
        setItems(withMedia);
        setReq((r) => ({ ...r, item_id: withMedia[0]?.id ?? "" }));
      })
      .catch((err) => setError(err.message));
  }, [req.agent_id]);

  const set = (key) => (e) => setReq((r) => ({ ...r, [key]: e.target.value }));

  async function test(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    const started = performance.now();
    try {
      const res = await api("/gemgenerate/test", {
        method: "POST",
        body: { ...req, item_id: Number(req.item_id) },
      });
      setResult({ ...res, seconds: ((performance.now() - started) / 1000).toFixed(1) });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="admin-card" onSubmit={test}>
      <h3>Test an image model</h3>
      <p className="admin-muted">
        Makes one preview for you only. It isn't saved or shown to customers, but it is charged by
        OpenRouter.
      </p>
      <div className="form-grid">
        <label>
          Partner
          <select value={req.agent_id} onChange={set("agent_id")}>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.display_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Stone (with photos)
          <select value={req.item_id} onChange={set("item_id")} required>
            {items.length === 0 && <option value="">No stones with photos</option>}
            {items.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Setting
          <select value={req.setting} onChange={set("setting")}>
            {status.settings.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Metal
          <select value={req.metal} onChange={set("metal")}>
            {status.metals.map((m) => (
              <option key={m} value={m}>
                {label(m)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Style
          <select value={req.style} onChange={set("style")}>
            <option value="">Model's choice</option>
            {status.styles.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </label>
        <label className="span-2">
          Model
          <input list="gemgen-models" value={req.model} onChange={set("model")} required />
        </label>
      </div>
      <button className="btn btn-primary" disabled={busy || !req.item_id}>
        {busy ? "Sketching... (up to a minute)" : "Make a test preview"}
      </button>
      {error && <div className="admin-error">{error}</div>}
      {result && (
        <figure className="gemgen-result">
          <img src={result.image} alt={result.label} />
          <figcaption>
            <strong>{result.label}</strong> · {result.model} · {result.seconds}s
            {result.model !== status.model && (
              <button type="button" className="btn" disabled={saving} onClick={() => onUse(result.model)}>
                Use this model for customers
              </button>
            )}
          </figcaption>
        </figure>
      )}
    </form>
  );
}
