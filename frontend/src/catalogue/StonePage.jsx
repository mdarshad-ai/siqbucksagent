import { useEffect, useRef, useState } from "react";
import { fetchStone, getRequested, rememberRequested, streamChat, streamPitch } from "../api.js";
import { friendlyChatError } from "../chatErrors.js";
import Character from "../components/Character.jsx";
import { Lightbox, MediaThumb, MediaView } from "../components/MediaViewer.jsx";
import PreviewCards, { previewHandlers } from "../components/PreviewCard.jsx";
import ReserveModal from "../components/ReserveModal.jsx";
import RichText from "../components/RichText.jsx";
import StoneCard from "../components/StoneCard.jsx";
import { Link } from "../router.jsx";
import { pageTitle } from "../site/brand.js";
import { formatPrice } from "./CataloguePage.jsx";

const SPECS = [
  ["carat", "Carat", (v) => `${v} ct`],
  ["cut", "Cut / shape"],
  ["color", "Colour"],
  ["clarity", "Clarity"],
  ["origin", "Origin"],
  ["treatment", "Treatment"],
  ["certification", "Certification"],
  ["category", "Gem"],
];

function Gallery({ media, name }) {
  const [selected, setSelected] = useState(0);
  const [lightbox, setLightbox] = useState(null);
  const current = media[selected];
  return (
    <div className="stone-gallery">
      <div className="stone-gallery-main">
        <MediaView item={current} onImageClick={() => setLightbox(selected)} />
      </div>
      {current?.caption && <p className="stone-gallery-caption">{current.caption}</p>}
      {media.length > 1 && (
        <div className="stone-gallery-thumbs">
          {media.map((m, i) => (
            <button
              key={m.id}
              className={`media-thumb ${i === selected ? "media-thumb-active" : ""}`}
              onClick={() => setSelected(i)}
              aria-label={m.caption || `${name}, ${m.kind} ${i + 1}`}
            >
              <MediaThumb item={m} />
            </button>
          ))}
        </div>
      )}
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

// The stone's partner, pitching it as soon as the page opens, then chatting.
function PartnerPanel({ stone, onHandoff, onHistory }) {
  const agent = stone.agent;
  const [history, setHistory] = useState([]);
  const [live, setLive] = useState(null);
  const [error, setError] = useState(null);
  const [input, setInput] = useState("");
  const threadRef = useRef(null);
  const busy = Boolean(live);

  function stream(start, before) {
    const turn = { role: "assistant", content: "", cards: [], images: [] };
    const update = (fields) => {
      Object.assign(turn, fields);
      setLive({ ...turn });
    };
    update({});
    return start({
      onDelta: (text) => update({ content: turn.content + text }),
      onCard: (card) => update({ cards: [...turn.cards, card] }),
      ...previewHandlers(turn, update),
    })
      .then((done) => {
        setHistory(done.history);
        return true;
      })
      .catch((err) => {
        setHistory(before);
        setError(friendlyChatError(err, agent.display_name));
        return false;
      })
      .finally(() => setLive(null));
  }

  useEffect(() => {
    setHistory([]);
    setError(null);
    stream((handlers) => streamPitch(stone.id, handlers), []);
  }, [stone.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    onHistory?.(history.filter((t) => !t.hidden));
  }, [history]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [history.length, live?.content, live?.images?.length, error]);

  async function send(text) {
    const message = (text ?? input).trim();
    if (!message || busy) return;
    if (text === undefined) setInput("");
    setError(null);
    const before = history;
    setHistory([...before, { role: "user", content: message }]);
    const ok = await stream((handlers) => streamChat(agent.id, message, before, handlers), before);
    if (!ok && text === undefined) setInput(message);
  }

  const visible = (live ? [...history, { ...live, streaming: true }] : history).filter((t) => !t.hidden);
  const last = history[history.length - 1];
  const suggestions = !busy && last?.role === "assistant" ? last.suggestions || [] : [];
  const sketching = live?.images?.some((i) => i.pending);
  const askedForRing = history.some((t) => t.role === "assistant" && t.images?.some((i) => i.item_id === stone.id));
  const ringQuestion = `How would the ${stone.name} look set in a ring?`;

  return (
    <section
      className="stone-partner"
      style={{ "--stall-accent": agent.theme.accent, "--stall-glow": agent.theme.glow }}
      aria-label={`${agent.display_name} on this stone`}
    >
      <header className="stone-partner-head">
        <Character theme={agent.theme} variant={agent.id} talking={busy} active />
        <div>
          <div className="stone-partner-name">
            {agent.display_name} <span>· {agent.stall_name}</span>
          </div>
          <div className="stone-partner-status" aria-live="polite">
            {busy
              ? sketching
                ? "Sketching a preview..."
                : live?.content
                  ? "Telling you about this stone..."
                  : "Looking at this stone..."
              : "Your AI partner for this stone"}
          </div>
        </div>
      </header>

      <div className="stone-partner-thread" ref={threadRef}>
        {visible.map((turn, i) => (
          <div key={i} className={`chat-turn chat-turn-${turn.role}`}>
            {turn.content && (
              <div className={`chat-bubble chat-bubble-${turn.role}`}>
                {turn.role === "assistant" ? <RichText text={turn.content} /> : turn.content}
                {turn.streaming && <span className="stream-caret" aria-hidden="true" />}
              </div>
            )}
            {turn.cards?.length > 0 && (
              <div className="stone-cards">
                {turn.cards
                  .filter((c) => c.id !== stone.id)
                  .map((card) => (
                    <StoneCard key={card.id} card={card} getTranscript={() => history.filter((t) => !t.hidden)} />
                  ))}
              </div>
            )}
            <PreviewCards
              images={turn.images}
              partner={agent.display_name}
              currentStoneId={stone.id}
              getTranscript={() => history.filter((t) => !t.hidden)}
            />
            {turn.handoff && (
              <div className="handoff">
                <span>
                  {turn.handoff.display_name} at {turn.handoff.stall_name} can help with this.
                </span>
                <button onClick={() => onHandoff(turn.handoff)} disabled={busy}>
                  Continue with {turn.handoff.display_name} <span aria-hidden="true">→</span>
                </button>
              </div>
            )}
          </div>
        ))}
        {busy && !live?.content && !live?.images?.length && (
          <div className="chat-bubble chat-bubble-assistant chat-bubble-thinking" aria-label="Thinking">
            <span className="dots">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </span>
          </div>
        )}
        {error && <div className="chat-error">{error}</div>}
      </div>

      {stone.can_preview && !askedForRing && !busy && (
        <button className="see-in-ring" onClick={() => send(ringQuestion)}>
          <span className="see-in-ring-icon" aria-hidden="true">✦</span>
          See it in a ring
          <span className="see-in-ring-note">AI preview</span>
        </button>
      )}

      {suggestions.length > 0 && (
        <div className="stone-partner-suggestions">
          {suggestions.map((s) => (
            <button key={s} className="chip" onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className="stone-partner-input"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <label className="visually-hidden" htmlFor="stone-question">
          Ask {agent.display_name} about this stone
        </label>
        <input
          id="stone-question"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={`Ask ${agent.display_name} about this stone...`}
          maxLength={2000}
          autoComplete="off"
        />
        <button type="submit" disabled={busy || !input.trim()}>
          Ask
        </button>
      </form>
    </section>
  );
}

export default function StonePage({ id, onHandoff }) {
  const [stone, setStone] = useState(undefined); // undefined = loading, null = not found
  const [error, setError] = useState(null);
  const [reserving, setReserving] = useState(false);
  const [requested, setRequested] = useState(null);
  const transcript = useRef([]);

  useEffect(() => {
    setStone(undefined);
    setError(null);
    fetchStone(id)
      .then((s) => {
        setStone(s);
        if (s) {
          setRequested(getRequested()[`${s.agent_id}:${s.id}`] || null);
          document.title = pageTitle(s.name);
        }
      })
      .catch((err) => setError(err.message));
    return () => {
      document.title = pageTitle();
    };
  }, [id]);

  if (error) return <div className="site-container load-error">{error}</div>;
  if (stone === undefined) return <div className="site-container stone-loading">Loading...</div>;
  if (stone === null) {
    return (
      <div className="site-container stone-missing">
        <h1>This stone isn't available any more</h1>
        <p className="hero-lede">It may have just sold. Have a look at what else is on the counter.</p>
        <Link to="/catalogue" className="btn-gold">
          Back to the catalogue
        </Link>
      </div>
    );
  }

  const specs = SPECS.filter(([key]) => stone[key] !== null && stone[key] !== "");
  const available = stone.status === "available" && stone.quantity > 0;

  return (
    <article className="stone-page" style={{ "--stall-accent": stone.agent.theme.accent, "--stall-glow": stone.agent.theme.glow }}>
      <div className="site-container">
        <nav className="breadcrumb" aria-label="Breadcrumb">
          <Link to="/">Home</Link> <span aria-hidden="true">/</span> <Link to="/catalogue">Catalogue</Link>{" "}
          <span aria-hidden="true">/</span> <span>{stone.code}</span>
        </nav>

        <div className="stone-layout">
          <div className="stone-left">
            <Gallery media={stone.media} name={stone.name} />
            {stone.story && (
              <section className="stone-section">
                <h2>The story</h2>
                <p className="stone-story">{stone.story}</p>
              </section>
            )}
          </div>

          <div className="stone-right">
            <div className="stone-code">{stone.code}</div>
            <h1 className="stone-title">{stone.name}</h1>
            <div className="stone-price-row">
              <span className={`stone-price ${stone.price ? "" : "is-request"}`}>{formatPrice(stone.price)}</span>
              <span className={`stone-availability is-${stone.status}`}>
                {stone.status === "reserved" ? "On hold for another customer" : `${stone.quantity} in stock`}
              </span>
            </div>
            {stone.description && <p className="stone-description">{stone.description}</p>}

            {requested ? (
              <div className="stone-requested">✓ Reservation requested · {requested}</div>
            ) : (
              <button className="stone-reserve" disabled={!available} onClick={() => setReserving(true)}>
                {available ? "Reserve this stone" : "On hold"}
              </button>
            )}

            <PartnerPanel
              key={stone.id}
              stone={stone}
              onHandoff={onHandoff}
              onHistory={(h) => (transcript.current = h)}
            />

            {specs.length > 0 && (
              <section className="stone-section">
                <h2>Details</h2>
                <dl className="stone-specs">
                  {specs.map(([key, label, fmt]) => (
                    <div key={key}>
                      <dt>{label}</dt>
                      <dd>{fmt ? fmt(stone[key]) : stone[key]}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}

            {stone.certificates.length > 0 && (
              <section className="stone-section">
                <h2>Certificates</h2>
                <ul className="stone-certs">
                  {stone.certificates.map((c) => (
                    <li key={c.id}>
                      <a href={c.url} target="_blank" rel="noreferrer">
                        <span className="stone-cert-icon" aria-hidden="true">{c.kind === "pdf" ? "PDF" : "IMG"}</span>
                        <span>
                          <strong>{[c.lab, c.title].filter(Boolean).join(" · ") || "Certificate"}</strong>
                          {c.number && <span className="stone-cert-number">No. {c.number}</span>}
                        </span>
                        <span className="stone-cert-open" aria-hidden="true">↗</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </div>
      </div>

      {reserving && (
        <ReserveModal
          card={stone}
          getTranscript={() => transcript.current}
          onClose={() => setReserving(false)}
          onRequested={(ref) => {
            rememberRequested(`${stone.agent_id}:${stone.id}`, ref);
            setRequested(ref);
          }}
        />
      )}
    </article>
  );
}
