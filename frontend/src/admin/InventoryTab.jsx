import { useEffect, useMemo, useState } from "react";
import { api } from "./adminApi.js";
import CertificatesManager from "./CertificatesManager.jsx";
import MediaManager from "./MediaManager.jsx";

const EMPTY_STONE = {
  name: "",
  category: "",
  carat: "",
  cut: "",
  color: "",
  clarity: "",
  origin: "",
  treatment: "",
  certification: "",
  price: "",
  quantity: 1,
  status: "available",
  description: "",
  story: "",
  sales_guidance: "",
  sku: "",
  featured: false,
};

const DETAIL_FIELDS = [
  ["carat", "Carat", "number"],
  ["cut", "Cut / shape"],
  ["color", "Colour"],
  ["clarity", "Clarity"],
  ["origin", "Origin"],
  ["treatment", "Treatment", "text", "e.g. Unheated"],
  ["certification", "Certification", "text", "Lab and number, e.g. GIA 2141438"],
];

function formatPrice(n) {
  return `$${Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function toForm(item) {
  const form = { ...EMPTY_STONE };
  for (const key of Object.keys(EMPTY_STONE)) {
    form[key] = item[key] ?? "";
  }
  return form;
}

function toPayload(form) {
  return {
    ...form,
    carat: form.carat === "" ? null : Number(form.carat),
    price: Number(form.price),
    quantity: Number(form.quantity),
  };
}

function StoneForm({ agentId, item, onSaved, onCancel, onDeleted, onMediaCount }) {
  const [form, setForm] = useState(item ? toForm(item) : EMPTY_STONE);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (key) => (e) =>
    setForm((f) => ({ ...f, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const saved = item
        ? await api(`/agents/${agentId}/items/${item.id}`, { method: "PUT", body: toPayload(form) })
        : await api(`/agents/${agentId}/items`, { method: "POST", body: toPayload(form) });
      onSaved(saved);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete "${item.name}"? This can't be undone.`)) return;
    setBusy(true);
    try {
      await api(`/agents/${agentId}/items/${item.id}`, { method: "DELETE" });
      onDeleted(item.id);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="admin-card stone-form">
      <form onSubmit={save}>
        <div className="admin-row admin-row-between">
          <h3>{item ? `Edit: ${item.name}` : "Add a stone"}</h3>
          <button type="button" className="btn" onClick={onCancel}>
            Close
          </button>
        </div>

        <fieldset>
          <legend>Basics</legend>
          <div className="form-grid">
            <label className="span-2">
              Name *
              <input value={form.name} onChange={set("name")} required maxLength={200} />
            </label>
            <label>
              Category
              <input value={form.category} onChange={set("category")} placeholder="e.g. Sapphire" />
            </label>
            <label>
              Stock code
              <input value={form.sku} onChange={set("sku")} maxLength={40} placeholder="Automatic if blank" />
            </label>
            <label>
              Price (USD) *
              <input type="number" min="0" step="0.01" value={form.price} onChange={set("price")} required />
            </label>
            <label>
              Quantity *
              <input type="number" min="0" step="1" value={form.quantity} onChange={set("quantity")} required />
            </label>
            <label>
              Status
              <select value={form.status} onChange={set("status")}>
                <option value="available">Available</option>
                <option value="reserved">Reserved (on hold)</option>
                <option value="sold">Sold</option>
              </select>
            </label>
            <label className="span-2 check-row">
              <input type="checkbox" checked={Boolean(form.featured)} onChange={set("featured")} />
              <span>
                Feature on the homepage under <em>On the counter tonight</em>{" "}
                <span className="admin-muted">(up to 4 are shown, available stones only)</span>
              </span>
            </label>
          </div>
        </fieldset>

        <fieldset>
          <legend>Stone details</legend>
          <div className="form-grid">
            {DETAIL_FIELDS.map(([key, label, type = "text", placeholder]) => (
              <label key={key}>
                {label}
                <input
                  type={type}
                  min={type === "number" ? "0" : undefined}
                  step={type === "number" ? "0.01" : undefined}
                  value={form[key]}
                  onChange={set(key)}
                  placeholder={placeholder}
                />
              </label>
            ))}
            <label className="span-2">
              Short description
              <textarea rows={2} value={form.description} onChange={set("description")} maxLength={2000} />
            </label>
          </div>
        </fieldset>

        <fieldset>
          <legend>Stone memory (what the dealer knows)</legend>
          <label>
            Story <span className="admin-muted">— the dealer may tell customers this</span>
            <textarea
              rows={4}
              value={form.story}
              onChange={set("story")}
              maxLength={5000}
              placeholder="Provenance, how it was found, what makes it special, who it suits, how it looks in different light..."
            />
          </label>
          <label>
            Sales guidance <span className="admin-muted">— private coaching, never quoted to customers</span>
            <textarea
              rows={3}
              value={form.sales_guidance}
              onChange={set("sales_guidance")}
              maxLength={5000}
              placeholder="e.g. Mention the certificate early. Pairs well with the tanzanite."
            />
          </label>
          <p className="admin-hint">
            Don't put anything truly secret here (like your lowest price). An AI can
            sometimes be talked into revealing its instructions.
          </p>
        </fieldset>

        {error && <div className="admin-error">{error}</div>}
        <div className="admin-row admin-row-between">
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Saving..." : item ? "Save changes" : "Add stone"}
          </button>
          {item && (
            <button type="button" className="btn btn-danger" onClick={remove} disabled={busy}>
              Delete stone
            </button>
          )}
        </div>
      </form>

      <fieldset className="media-fieldset">
        <legend>Photos &amp; videos</legend>
        {item ? (
          <>
            <p className="admin-hint media-intro">
              Customers see these on the stone's page and on its card in the chat. Changes here save
              straight away.
            </p>
            <MediaManager agentId={agentId} itemId={item.id} onCountChange={onMediaCount} />
          </>
        ) : (
          <p className="admin-muted">Add the stone first, then you can upload photos and videos.</p>
        )}
      </fieldset>

      {item && (
        <fieldset className="media-fieldset">
          <legend>Certificates</legend>
          <CertificatesManager agentId={agentId} itemId={item.id} />
        </fieldset>
      )}
    </div>
  );
}

export default function InventoryTab() {
  const [agents, setAgents] = useState([]);
  const [agentId, setAgentId] = useState(null);
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState(null); // null | "new" | item
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

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
    setLoading(true);
    setEditing(null);
    api(`/agents/${agentId}/items`)
      .then(setItems)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [agentId]);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) =>
      [i.name, i.category, i.origin, i.color].some((v) => (v || "").toLowerCase().includes(q))
    );
  }, [items, filter]);

  function handleSaved(saved) {
    const isNew = !items.some((i) => i.id === saved.id);
    setItems((prev) => {
      const old = prev.find((i) => i.id === saved.id);
      const merged = { ...saved, media_count: old?.media_count ?? 0 };
      const next = old ? prev.map((i) => (i.id === saved.id ? merged : i)) : [...prev, merged];
      return next.sort((a, b) => a.name.localeCompare(b.name));
    });
    // A new stone stays open so photos and videos can be added right away.
    setEditing(isNew ? { ...saved, media_count: 0 } : null);
  }

  function handleMediaCount(itemId, count) {
    setItems((prev) => prev.map((i) => (i.id === itemId ? { ...i, media_count: count } : i)));
  }

  return (
    <section>
      <div className="admin-row admin-row-between admin-toolbar">
        <div className="admin-row">
          <div className="segmented">
            {agents.map((a) => (
              <button
                key={a.id}
                className={agentId === a.id ? "segmented-active" : ""}
                onClick={() => setAgentId(a.id)}
              >
                {a.display_name} <span className="admin-muted">· {a.stall_name}</span>
              </button>
            ))}
          </div>
          <input
            className="admin-search"
            placeholder="Filter stones..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
        <button className="btn btn-primary" onClick={() => setEditing("new")}>
          + Add stone
        </button>
      </div>

      {error && <div className="admin-error">{error}</div>}

      {editing && (
        <StoneForm
          key={editing === "new" ? "new" : editing.id}
          agentId={agentId}
          item={editing === "new" ? null : editing}
          onSaved={handleSaved}
          onCancel={() => setEditing(null)}
          onMediaCount={(count) => editing !== "new" && handleMediaCount(editing.id, count)}
          onDeleted={(id) => {
            setItems((prev) => prev.filter((i) => i.id !== id));
            setEditing(null);
          }}
        />
      )}

      <div className="admin-card admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Stone</th>
              <th>Details</th>
              <th className="num">Price</th>
              <th className="num">Qty</th>
              <th>Status</th>
              <th>Media</th>
              <th>Memory</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((i) => (
              <tr key={i.id} onClick={() => setEditing(i)} className="clickable">
                <td>
                  <div className="cell-strong">
                    {i.featured && <span className="featured-star" title="On the counter tonight">★ </span>}
                    {i.name}
                  </div>
                  <div className="admin-muted">{i.category}</div>
                </td>
                <td className="admin-muted">
                  {[i.carat != null ? `${i.carat}ct` : null, i.cut, i.origin].filter(Boolean).join(" · ")}
                </td>
                <td className="num">{formatPrice(i.price)}</td>
                <td className="num">{i.quantity}</td>
                <td>
                  <span className={`pill pill-${i.status}`}>{i.status}</span>
                </td>
                <td className={i.media_count ? "" : "admin-muted"}>
                  {i.media_count ? `${i.media_count}` : "none"}
                </td>
                <td className="admin-muted">
                  {[i.story && "story", i.sales_guidance && "guidance"].filter(Boolean).join(", ") || "—"}
                </td>
              </tr>
            ))}
            {!loading && visible.length === 0 && (
              <tr>
                <td colSpan={7} className="admin-muted">
                  {items.length ? "No stones match that filter." : "No stones yet."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
