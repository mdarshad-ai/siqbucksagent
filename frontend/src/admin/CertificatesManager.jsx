import { useEffect, useRef, useState } from "react";
import { assetUrl } from "../api.js";
import { api } from "./adminApi.js";

const MAX_BYTES = 50 * 1024 * 1024;
const ACCEPT = "application/pdf,image/jpeg,image/png,image/webp";

function putFile(target, file) {
  return fetch(assetUrl(target.url), { method: target.method || "PUT", headers: target.headers, body: file }).then(
    async (res) => {
      if (!res.ok) throw new Error(`Upload failed (${res.status}). ${(await res.text()).slice(0, 120)}`);
    }
  );
}

// Grading reports and certificates: PDFs or photos, as many as needed.
export default function CertificatesManager({ agentId, itemId }) {
  const base = `/agents/${agentId}/items/${itemId}/certificates`;
  const [certs, setCerts] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const fileInput = useRef(null);

  useEffect(() => {
    api(base).then(setCerts).catch((err) => setError(err.message));
  }, [base]);

  async function onFiles(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    setBusy(true);
    setError(null);
    try {
      for (const file of files) {
        if (!ACCEPT.split(",").includes(file.type)) throw new Error(`${file.name}: use a PDF, JPG, PNG or WebP.`);
        if (file.size > MAX_BYTES) throw new Error(`${file.name} is larger than 50 MB.`);
        const target = await api(`/agents/${agentId}/items/${itemId}/media/upload-url`, {
          method: "POST",
          body: { content_type: file.type, size_bytes: file.size, purpose: "certificate" },
        });
        await putFile(target, file);
        const title = file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").slice(0, 200);
        const created = await api(base, {
          method: "POST",
          body: { path: target.path, content_type: file.type, size_bytes: file.size, title },
        });
        setCerts((prev) => [...prev, created]);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function save(cert, field, value) {
    if (value === cert[field]) return;
    try {
      const updated = await api(`${base}/${cert.id}`, { method: "PATCH", body: { [field]: value } });
      setCerts((prev) => prev.map((c) => (c.id === cert.id ? updated : c)));
    } catch (err) {
      setError(err.message);
    }
  }

  async function remove(cert) {
    if (!window.confirm("Delete this certificate?")) return;
    try {
      await api(`${base}/${cert.id}`, { method: "DELETE" });
      setCerts((prev) => prev.filter((c) => c.id !== cert.id));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="certs-manager">
      <div className="admin-row">
        <button type="button" className="btn" onClick={() => fileInput.current.click()} disabled={busy}>
          {busy ? "Uploading..." : "Upload certificate"}
        </button>
        <input ref={fileInput} type="file" accept={ACCEPT} multiple hidden onChange={onFiles} />
        <span className="admin-muted">PDF or photo · customers can open these on the stone's page</span>
      </div>
      {certs.length > 0 && (
        <ul className="certs-list">
          {certs.map((c) => (
            <li key={c.id}>
              <a className="certs-file" href={assetUrl(c.url)} target="_blank" rel="noreferrer">
                {c.kind === "pdf" ? "PDF" : "IMG"}
              </a>
              <input defaultValue={c.lab} placeholder="Lab (e.g. GIA)" maxLength={120} onBlur={(e) => save(c, "lab", e.target.value.trim())} aria-label="Lab" />
              <input defaultValue={c.title} placeholder="Title (e.g. Colored Stone Report)" maxLength={200} onBlur={(e) => save(c, "title", e.target.value.trim())} aria-label="Title" />
              <input defaultValue={c.number} placeholder="Report number" maxLength={120} onBlur={(e) => save(c, "number", e.target.value.trim())} aria-label="Report number" />
              <button type="button" className="btn btn-small btn-danger" onClick={() => remove(c)}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <div className="admin-error">{error}</div>}
    </div>
  );
}
