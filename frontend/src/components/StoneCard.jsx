import { useState } from "react";
import { Lightbox, MediaThumb, MediaView } from "./MediaViewer.jsx";

function formatPrice(n) {
  return `$${Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function stockLabel(card) {
  if (card.status === "reserved") return "On hold";
  if (card.status === "sold" || card.quantity <= 0) return "Sold out";
  return `${card.quantity} in stock`;
}

// Shown under a dealer's reply when they recommend a stone.
export default function StoneCard({ card }) {
  const media = card.media || [];
  const [selected, setSelected] = useState(0);
  const [lightbox, setLightbox] = useState(null);
  const current = media[selected];

  const details = [
    card.carat != null ? `${card.carat}ct` : null,
    card.cut,
    card.color,
    card.origin,
    card.treatment,
    card.certification ? `Cert: ${card.certification}` : null,
  ].filter(Boolean);

  return (
    <div className="stone-card">
      <div className="stone-card-media">
        <MediaView item={current} onImageClick={() => setLightbox(selected)} />
        {current && current.kind === "image" && (
          <button className="stone-card-expand" onClick={() => setLightbox(selected)} aria-label="View full screen">
            ⤢
          </button>
        )}
      </div>
      {current?.caption && <div className="stone-card-caption">{current.caption}</div>}

      {media.length > 1 && (
        <div className="stone-card-thumbs">
          {media.map((m, i) => (
            <button
              key={m.id}
              className={`media-thumb ${i === selected ? "media-thumb-active" : ""}`}
              onClick={() => setSelected(i)}
              aria-label={m.caption || `${m.kind} ${i + 1}`}
            >
              <MediaThumb item={m} />
            </button>
          ))}
        </div>
      )}

      <div className="stone-card-body">
        <div className="stone-card-title">{card.name}</div>
        <div className="stone-card-price">
          {formatPrice(card.price)} <span className="stone-card-stock">· {stockLabel(card)}</span>
        </div>
        {details.length > 0 && <div className="stone-card-details">{details.join(" · ")}</div>}
      </div>

      {lightbox != null && (
        <Lightbox
          items={media}
          index={lightbox}
          onIndex={(i) => {
            setLightbox(i);
            setSelected(i);
          }}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}
