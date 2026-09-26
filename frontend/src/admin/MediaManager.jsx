import { useEffect, useRef, useState } from "react";
import { assetUrl } from "../api.js";
import { MediaThumb } from "../components/MediaViewer.jsx";
import { api } from "./adminApi.js";

const MAX_BYTES = 50 * 1024 * 1024;
const ACCEPT = "image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm";
const ALLOWED = ACCEPT.split(",");

function formatSize(bytes) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
}

// PUT a file to a signed upload URL, reporting progress (0-1).
function putFile(target, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(target.method || "PUT", assetUrl(target.url));
    for (const [k, v] of Object.entries(target.headers || {})) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(`Upload failed (${xhr.status}). ${xhr.responseText.slice(0, 120)}`));
    xhr.onerror = () => reject(new Error("Upload failed - check your connection."));
    xhr.send(file);
  });
}

// Grab a JPEG still from a <video> at its current time.
function frameFromVideo(video) {
  const scale = Math.min(1, 1280 / (video.videoWidth || 1280));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Couldn't capture frame"))), "image/jpeg", 0.85)
  );
}

// Load a local video file and capture a frame about a second in. Resolves to
// null if this browser can't decode the video (e.g. some iPhone HEVC .mov).
function posterFromFile(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.preload = "auto";
    const done = (result) => {
      clearTimeout(timer);
      URL.revokeObjectURL(url);
      resolve(result);
    };
    const timer = setTimeout(() => done(null), 15000);
    video.onerror = () => done(null);
    video.onloadedmetadata = () => {
      video.currentTime = Math.min(1, (video.duration || 2) / 3);
    };
    video.onseeked = () => frameFromVideo(video).then(done, () => done(null));
    video.src = url;
  });
}

function StillFrameEditor({ item, onSave, onClose }) {
  const videoRef = useRef(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function useFrame() {
    setBusy(true);
    setError(null);
    try {
      const blob = await frameFromVideo(videoRef.current);
      await onSave(blob);
      onClose();
    } catch (err) {
      setError(
        err.name === "SecurityError"
          ? "The browser blocked reading this video's frames."
          : err.message
      );
      setBusy(false);
    }
  }

  return (
    <div className="admin-modal" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="admin-card admin-modal-body">
        <h3>Choose the still frame</h3>
        <p className="admin-muted">Play or scrub to the moment you want, then click "Use this frame".</p>
        <video
          ref={videoRef}
          className="still-frame-video"
          src={assetUrl(item.url)}
          crossOrigin="anonymous"
          controls
          playsInline
          preload="auto"
        />
        {error && <div className="admin-error">{error}</div>}
        <div className="admin-row">
          <button className="btn btn-primary" onClick={useFrame} disabled={busy}>
            {busy ? "Saving..." : "Use this frame"}
          </button>
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

export default function MediaManager({ agentId, itemId, onCountChange }) {
  const base = `/agents/${agentId}/items/${itemId}/media`;
  const [items, setItems] = useState([]);
  const [uploads, setUploads] = useState([]); // {key, name, progress, error, warning}
  const [link, setLink] = useState("");
  const [error, setError] = useState(null);
  const [editingFrame, setEditingFrame] = useState(null);
  const [dragId, setDragId] = useState(null);
  const fileInput = useRef(null);

  useEffect(() => {
    api(base).then(setItems).catch((err) => setError(err.message));
  }, [base]);

  useEffect(() => onCountChange?.(items.length), [items.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const patchUpload = (key, fields) =>
    setUploads((prev) => prev.map((u) => (u.key === key ? { ...u, ...fields } : u)));

  async function uploadBlob(blob, contentType, purpose, onProgress) {
    const target = await api(`${base}/upload-url`, {
      method: "POST",
      body: { content_type: contentType, size_bytes: blob.size, purpose },
    });
    await putFile(target, blob, onProgress);
    return target.path;
  }

  async function uploadOne(file, key) {
    try {
      if (!ALLOWED.includes(file.type)) {
        throw new Error("Unsupported type. Use JPG, PNG or WebP photos, or MP4/MOV/WebM videos.");
      }
      if (file.size > MAX_BYTES) {
        throw new Error(`Too big (${formatSize(file.size)}). The limit is 50 MB - try a shorter or smaller video.`);
      }
      let posterPath = null;
      if (file.type.startsWith("video/")) {
        patchUpload(key, { status: "Reading video..." });
        const poster = await posterFromFile(file);
        if (poster) {
          posterPath = await uploadBlob(poster, "image/jpeg", "poster");
        } else {
          patchUpload(key, {
            warning:
              "This browser couldn't read the video, so it has no still frame and may not play for some customers. For best results upload MP4 (H.264).",
          });
        }
      }
      patchUpload(key, { status: "Uploading..." });
      const path = await uploadBlob(file, file.type, "media", (p) => patchUpload(key, { progress: p }));
      const created = await api(base, {
        method: "POST",
        body: { path, poster_path: posterPath, content_type: file.type, size_bytes: file.size },
      });
      setItems((prev) => [...prev, created]);
      patchUpload(key, { progress: 1, status: "Done", done: true });
    } catch (err) {
      patchUpload(key, { error: err.message, status: "Failed" });
    }
  }

  function onFilesChosen(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    const batch = files.map((f, i) => ({
      key: `${Date.now()}-${i}`,
      name: f.name,
      size: f.size,
      progress: 0,
      status: "Waiting...",
    }));
    setUploads((prev) => [...prev.filter((u) => !u.done || u.warning), ...batch]);
    // One at a time keeps memory and bandwidth sane on phones.
    (async () => {
      for (let i = 0; i < files.length; i++) await uploadOne(files[i], batch[i].key);
    })();
  }

  async function addLink(e) {
    e.preventDefault();
    setError(null);
    try {
      const created = await api(`${base}/link`, { method: "POST", body: { url: link } });
      setItems((prev) => [...prev, created]);
      setLink("");
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveOrder(next) {
    const previous = items;
    setItems(next);
    try {
      setItems(await api(`${base}/order`, { method: "PUT", body: { ids: next.map((m) => m.id) } }));
    } catch (err) {
      setItems(previous);
      setError(err.message);
    }
  }

  function move(index, delta) {
    const target = index + delta;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target], next[index]];
    saveOrder(next);
  }

  function makeMain(index) {
    const next = [...items];
    const [picked] = next.splice(index, 1);
    saveOrder([picked, ...next]);
  }

  function dropOn(targetId) {
    if (dragId == null || dragId === targetId) return;
    const next = items.filter((m) => m.id !== dragId);
    const targetIndex = next.findIndex((m) => m.id === targetId);
    next.splice(targetIndex, 0, items.find((m) => m.id === dragId));
    setDragId(null);
    saveOrder(next);
  }

  async function saveCaption(item, caption) {
    if (caption === item.caption) return;
    try {
      const updated = await api(`${base}/${item.id}`, { method: "PATCH", body: { caption } });
      setItems((prev) => prev.map((m) => (m.id === item.id ? updated : m)));
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveStillFrame(item, blob) {
    const path = await uploadBlob(blob, "image/jpeg", "poster");
    const updated = await api(`${base}/${item.id}`, { method: "PATCH", body: { poster_path: path } });
    setItems((prev) => prev.map((m) => (m.id === item.id ? updated : m)));
  }

  async function remove(item) {
    if (!window.confirm("Delete this media? This can't be undone.")) return;
    try {
      await api(`${base}/${item.id}`, { method: "DELETE" });
      setItems((prev) => prev.filter((m) => m.id !== item.id));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="media-manager">
      <div className="admin-row">
        <button type="button" className="btn btn-primary" onClick={() => fileInput.current.click()}>
          Upload photos or videos
        </button>
        <input ref={fileInput} type="file" accept={ACCEPT} multiple hidden onChange={onFilesChosen} />
        <span className="admin-muted">JPG, PNG, WebP, MP4, MOV · up to 50 MB each</span>
      </div>

      {uploads.length > 0 && (
        <ul className="upload-list">
          {uploads.map((u) => (
            <li key={u.key}>
              <div className="admin-row admin-row-between">
                <span className="cell-strong">{u.name}</span>
                <span className="admin-muted">
                  {formatSize(u.size)} · {u.status}
                </span>
              </div>
              {!u.error && (
                <div className="progress">
                  <div className="progress-bar" style={{ width: `${Math.round(u.progress * 100)}%` }} />
                </div>
              )}
              {u.error && <div className="admin-error">{u.error}</div>}
              {u.warning && <div className="admin-warning">{u.warning}</div>}
            </li>
          ))}
        </ul>
      )}

      {items.length === 0 ? (
        <p className="admin-muted">No photos or videos yet. The first one becomes the main image on the stone's card.</p>
      ) : (
        <div className="media-grid">
          {items.map((m, i) => (
            <div
              key={m.id}
              className={`media-tile ${dragId === m.id ? "media-tile-dragging" : ""}`}
              draggable
              onDragStart={() => setDragId(m.id)}
              onDragEnd={() => setDragId(null)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                dropOn(m.id);
              }}
            >
              <a className="media-tile-preview" href={assetUrl(m.url)} target="_blank" rel="noreferrer">
                <MediaThumb item={m} />
                {i === 0 && <span className="media-tile-main">Main</span>}
                <span className="media-tile-kind">{{ image: "Photo", video: "Video", embed: "Link" }[m.kind]}</span>
              </a>
              <input
                className="media-caption"
                placeholder="Caption (optional)"
                defaultValue={m.caption}
                maxLength={300}
                onBlur={(e) => saveCaption(m, e.target.value.trim())}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), e.target.blur())}
              />
              <div className="media-tile-actions">
                <button type="button" className="btn btn-small" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Move earlier">
                  ←
                </button>
                <button type="button" className="btn btn-small" onClick={() => move(i, 1)} disabled={i === items.length - 1} aria-label="Move later">
                  →
                </button>
                {i !== 0 && (
                  <button type="button" className="btn btn-small" onClick={() => makeMain(i)}>
                    Make main
                  </button>
                )}
                {m.kind === "video" && (
                  <button type="button" className="btn btn-small" onClick={() => setEditingFrame(m)}>
                    Still frame
                  </button>
                )}
                <button type="button" className="btn btn-small btn-danger" onClick={() => remove(m)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {items.length > 1 && <p className="admin-hint">Drag tiles (or use the arrows) to change the order customers see.</p>}

      <form className="admin-row media-link-row" onSubmit={addLink}>
        <input
          className="grow"
          type="url"
          placeholder="Or paste a YouTube / Vimeo link for a longer video"
          value={link}
          onChange={(e) => setLink(e.target.value)}
        />
        <button className="btn" disabled={!link.trim()}>
          Add link
        </button>
      </form>

      {error && <div className="admin-error">{error}</div>}

      {editingFrame && (
        <StillFrameEditor
          item={editingFrame}
          onSave={(blob) => saveStillFrame(editingFrame, blob)}
          onClose={() => setEditingFrame(null)}
        />
      )}
    </div>
  );
}
