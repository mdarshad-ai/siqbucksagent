import { useState } from "react";
import { assetUrl, getRequested, rememberRequested } from "../api.js";
import { Link } from "../router.jsx";
import { Lightbox } from "./MediaViewer.jsx";
import ReserveModal from "./ReserveModal.jsx";

// Stream handlers that keep a live turn's AI previews up to date:
// a sketching placeholder first, then the finished picture (or nothing).
export function previewHandlers(turn, update) {
  const list = () => turn.images || [];
  return {
    onImagePending: (p) => update({ images: [...list(), { ...p, pending: true }] }),
    onImage: ({ id, image }) => update({ images: list().map((i) => (i.id === id && i.pending ? image : i)) }),
    onImageFailed: ({ id }) => update({ images: list().filter((i) => !(i.id === id && i.pending)) }),
  };
}

function Sketching({ preview, partner }) {
  return (
    <div className="preview-card preview-card-pending" aria-live="polite">
      <div className="preview-shimmer">
        <span className="preview-shimmer-gem" aria-hidden="true">◆</span>
      </div>
      <div className="preview-body">
        <div className="preview-title">
          {partner ? `${partner} is sketching` : "Sketching"} your {preview.label.toLowerCase()}...
        </div>
        <div className="preview-note">AI previews take 10-30 seconds.</div>
      </div>
    </div>
  );
}

// An AI preview of a stone set in jewellery (GemGenerate).
function Preview({ preview, currentStoneId, getTranscript }) {
  const [zoom, setZoom] = useState(false);
  const [reserving, setReserving] = useState(false);
  const stoneKey = `${preview.agent_id}:${preview.item_id}`;
  const [requested, setRequested] = useState(() => getRequested()[stoneKey] || null);
  const onStonePage = currentStoneId === preview.item_id;
  const available = preview.status === "available" && preview.quantity > 0;
  const caption = `${preview.label} · AI preview of the ${preview.item_name}, not the finished piece`;

  return (
    <div className="preview-card">
      <button className="preview-media" onClick={() => setZoom(true)} aria-label={`Enlarge: ${caption}`}>
        <img src={assetUrl(preview.url)} alt={caption} loading="lazy" />
        <span className="preview-badge">AI preview</span>
      </button>
      <div className="preview-body">
        <div className="preview-title">{preview.label}</div>
        <div className="preview-note">
          With the {preview.item_name}. An AI sketch to help you picture it, not the finished piece.
        </div>
        {!onStonePage && (
          <div className="preview-actions">
            <Link to={`/stones/${preview.item_id}`} className="stone-card-link">
              View stone <span aria-hidden="true">→</span>
            </Link>
            {requested ? (
              <span className="stone-card-requested">✓ Requested · {requested}</span>
            ) : (
              available && (
                <button className="preview-reserve" onClick={() => setReserving(true)}>
                  Reserve
                </button>
              )
            )}
          </div>
        )}
      </div>

      {zoom && (
        <Lightbox
          items={[{ id: preview.id, kind: "image", url: preview.url, caption }]}
          index={0}
          onIndex={() => {}}
          onClose={() => setZoom(false)}
        />
      )}
      {reserving && (
        <ReserveModal
          card={{ id: preview.item_id, agent_id: preview.agent_id, name: preview.item_name, price: preview.price }}
          getTranscript={getTranscript}
          onClose={() => setReserving(false)}
          onRequested={(ref) => {
            rememberRequested(stoneKey, ref);
            setRequested(ref);
          }}
        />
      )}
    </div>
  );
}

export default function PreviewCards({ images, partner, currentStoneId = null, getTranscript = () => [] }) {
  if (!images?.length) return null;
  return (
    <div className="stone-cards">
      {images.map((p) =>
        p.pending ? (
          <Sketching key={`pending-${p.id}`} preview={p} partner={partner} />
        ) : (
          <Preview key={p.id} preview={p} currentStoneId={currentStoneId} getTranscript={getTranscript} />
        )
      )}
    </div>
  );
}
