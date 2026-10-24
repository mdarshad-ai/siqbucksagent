import { useEffect, useState } from "react";
import { api } from "./adminApi.js";

function plural(n, one, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

// Owners can dress the starter stones with illustrated photos, stories and
// sales guidance, and take them away again before going live.
export default function SampleContent() {
  const [status, setStatus] = useState(null);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/samples").then(setStatus).catch((err) => setError(err.message));
  }, []);

  async function run(action) {
    if (action === "remove" && !window.confirm("Remove the sample photos, and stories and guidance that are still exactly as loaded?")) {
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await api(`/samples/${action}`, { method: "POST" });
      setStatus(res.status);
      const parts = [plural(res.photos, "photo"), plural(res.stories, "story", "stories"), `${res.guidance} sales guidance`];
      if (action === "load") {
        const skipped = res.unmatched?.length ? ` Skipped ${plural(res.unmatched.length, "stone")} the samples don't cover: ${res.unmatched.join(", ")}.` : "";
        setMessage(`Added ${parts.join(", ")}.${skipped}`);
      } else {
        setMessage(`Removed ${parts.join(", ")}.`);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-card">
      <h3>Sample content</h3>
      <p className="admin-muted">
        Fills the {status?.available ?? 20} starter stones with an illustrated photo, a story the Gem Expert
        can tell customers, and private sales guidance. It only fills gaps: photos, stories and guidance you
        added are kept. The photos are illustrations marked "Sample image", so replace them (and check the
        stories) before selling for real.
      </p>
      {status && (
        <div className="usage-stats">
          <div>
            <div className="usage-number">{status.with_sample_photo}</div>
            <div className="admin-muted">stones with a sample photo</div>
          </div>
          <div>
            <div className="usage-number">{status.with_sample_text}</div>
            <div className="admin-muted">with sample story or guidance</div>
          </div>
        </div>
      )}
      <div className="admin-row">
        <button className="btn btn-primary" disabled={busy} onClick={() => run("load")}>
          {busy ? "Working..." : "Load sample content"}
        </button>
        <button
          className="btn"
          disabled={busy || !status || (status.with_sample_photo === 0 && status.with_sample_text === 0)}
          onClick={() => run("remove")}
        >
          Remove sample content
        </button>
      </div>
      {message && <div className="admin-success">{message}</div>}
      {error && <div className="admin-error">{error}</div>}
    </div>
  );
}
