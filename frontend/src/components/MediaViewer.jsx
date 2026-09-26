import { useEffect, useRef, useState } from "react";
import { assetUrl } from "../api.js";

// One media item rendered at full size: photo, playable video, or a
// YouTube/Vimeo player that only loads once tapped.
export function MediaView({ item, onImageClick, autoPlayEmbed = false }) {
  const [embedActive, setEmbedActive] = useState(autoPlayEmbed);

  useEffect(() => setEmbedActive(autoPlayEmbed), [item?.id, autoPlayEmbed]);

  if (!item) {
    return (
      <div className="media-empty">
        <span className="media-empty-gem">◆</span>
        <span>No photos yet</span>
      </div>
    );
  }
  if (item.kind === "image") {
    return (
      <img
        className={`media-fill ${onImageClick ? "media-zoomable" : ""}`}
        src={assetUrl(item.url)}
        alt={item.caption || ""}
        loading="lazy"
        onClick={onImageClick}
      />
    );
  }
  if (item.kind === "video") {
    return (
      <video
        key={item.id}
        className="media-fill"
        src={assetUrl(item.url)}
        poster={assetUrl(item.poster_url) || undefined}
        controls
        playsInline
        preload="none"
      />
    );
  }
  // embed
  if (!embedActive) {
    return (
      <button className="media-embed-cover" onClick={() => setEmbedActive(true)} aria-label="Play video">
        {item.poster_url ? (
          <img
            className="media-fill"
            src={item.poster_url}
            alt=""
            loading="lazy"
            onError={(e) => (e.currentTarget.style.visibility = "hidden")}
          />
        ) : (
          <span className="media-embed-blank" />
        )}
        <span className="media-play">▶</span>
      </button>
    );
  }
  const sep = item.url.includes("?") ? "&" : "?";
  return (
    <iframe
      className="media-fill"
      src={`${item.url}${sep}autoplay=1&playsinline=1`}
      title={item.caption || "Video"}
      allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
      allowFullScreen
    />
  );
}

export function MediaThumb({ item }) {
  const src = item.kind === "image" ? item.url : item.poster_url;
  const [failed, setFailed] = useState(false);
  return (
    <span className="media-thumb-inner">
      {src && !failed ? (
        <img src={assetUrl(src)} alt="" loading="lazy" onError={() => setFailed(true)} />
      ) : (
        <span className="media-thumb-blank" />
      )}
      {item.kind !== "image" && <span className="media-thumb-play">▶</span>}
    </span>
  );
}

// Full-screen gallery: arrows, swipe and keyboard.
export function Lightbox({ items, index, onIndex, onClose }) {
  const touchStart = useRef(null);
  const count = items.length;
  const go = (delta) => onIndex((index + delta + count) % count);

  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") go(1);
      if (e.key === "ArrowLeft") go(-1);
    }
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  });

  const item = items[index];
  return (
    <div
      className="lightbox"
      role="dialog"
      aria-modal="true"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      onTouchStart={(e) => (touchStart.current = e.touches[0].clientX)}
      onTouchEnd={(e) => {
        if (touchStart.current == null) return;
        const dx = e.changedTouches[0].clientX - touchStart.current;
        if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1);
        touchStart.current = null;
      }}
    >
      <button className="lightbox-close" onClick={onClose} aria-label="Close">
        ✕
      </button>
      {count > 1 && (
        <button className="lightbox-nav lightbox-prev" onClick={() => go(-1)} aria-label="Previous">
          ‹
        </button>
      )}
      <figure className="lightbox-figure">
        <div className="lightbox-media">
          <MediaView item={item} autoPlayEmbed />
        </div>
        <figcaption>
          {item.caption}
          {count > 1 && <span className="lightbox-count">{index + 1} / {count}</span>}
        </figcaption>
      </figure>
      {count > 1 && (
        <button className="lightbox-nav lightbox-next" onClick={() => go(1)} aria-label="Next">
          ›
        </button>
      )}
    </div>
  );
}
