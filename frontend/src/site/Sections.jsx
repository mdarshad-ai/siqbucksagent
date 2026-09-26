import { useEffect, useState } from "react";
import { assetUrl } from "../api.js";
import Character from "../components/Character.jsx";
import AskBox from "./AskBox.jsx";
import Logo from "./Logo.jsx";
import { HERO_PROMPTS, partnerCopy } from "./partners.js";

export const TAGLINE = "Your two gem partners. Real stones. Just ask.";

function formatPrice(n) {
  return `$${Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function SiteHeader({ onTalk }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className={`site-header ${scrolled ? "site-header-scrolled" : ""}`}>
      <div className="site-container site-header-inner">
        <a href="#top" className="site-brand" aria-label="Loupe Gem, home">
          <Logo />
        </a>
        <nav className="site-nav" aria-label="Sections">
          <a href="#partners">Partners</a>
          <a href="#counter">On the counter</a>
          <a href="#how">How it works</a>
        </nav>
        <button className="btn-gold btn-small" onClick={() => onTalk()}>
          Talk to an AI partner
        </button>
      </div>
    </header>
  );
}

export function Hero({ agents, onAsk, onTalk }) {
  const [first] = agents;
  return (
    <section className="hero" id="top">
      <div className="hero-sky" aria-hidden="true">
        <span className="hero-orb hero-orb-1" />
        <span className="hero-orb hero-orb-2" />
        <span className="hero-orb hero-orb-3" />
      </div>
      <div className="site-container hero-inner">
        <div className="hero-copy">
          <p className="eyebrow">An agent-led gem house</p>
          <h1>
            Your two gem partners.
            <br />
            <span className="hero-accent">Real stones.</span> Just ask.
          </h1>
          <p className="hero-lede">
            Tell our partners what you're dreaming of. They check the real stock, show you the actual
            stone in photos and video, and put it aside for you.
          </p>
          <AskBox
            onAsk={onAsk}
            prompts={HERO_PROMPTS}
            placeholder='e.g. "a blue stone under $2,000 for a ring"'
          />
        </div>

        <div className="hero-stage" aria-label="Our partners">
          {first && (
            <div className="hero-bubble" style={{ "--stall-accent": first.theme.accent }}>
              “{partnerCopy(first.id).greeting}”
              <span className="hero-bubble-name">— {first.display_name}</span>
            </div>
          )}
          <div className="hero-partners">
            {agents.map((a) => (
              <button
                key={a.id}
                className="hero-partner"
                style={{ "--stall-accent": a.theme.accent, "--stall-glow": a.theme.glow }}
                onClick={() => onTalk(a.id)}
              >
                <span className="hero-arch" aria-hidden="true" />
                <Character theme={a.theme} variant={a.id} talking={false} active />
                <span className="hero-partner-name">{a.display_name}</span>
                <span className="hero-partner-stall">{a.stall_name}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export function Partners({ agents, onTalk, onAskPartner }) {
  return (
    <section className="section" id="partners">
      <div className="site-container">
        <p className="eyebrow">Meet your AI partners</p>
        <h2 className="section-title">Two counters, two kinds of expertise</h2>
        <div className="partner-grid">
          {agents.map((a) => {
            const copy = partnerCopy(a.id);
            return (
              <article
                key={a.id}
                className="partner-card"
                style={{ "--stall-accent": a.theme.accent, "--stall-glow": a.theme.glow }}
              >
                <div className="partner-card-figure">
                  <Character theme={a.theme} variant={a.id} talking={false} active />
                </div>
                <div className="partner-card-body">
                  <div className="partner-card-role">{copy.role}</div>
                  <h3>
                    {a.display_name} <span>· {a.stall_name}</span>
                  </h3>
                  <p className="partner-card-tagline">“{a.tagline}”</p>
                  {copy.knownFor.length > 0 && (
                    <ul className="partner-known">
                      {copy.knownFor.map((k) => (
                        <li key={k}>{k}</li>
                      ))}
                    </ul>
                  )}
                  <div className="partner-ask">
                    <span>Ask {a.display_name}:</span>
                    {copy.questions.map((q) => (
                      <button key={q} className="chip" onClick={() => onAskPartner(a.id, q)}>
                        {q}
                      </button>
                    ))}
                  </div>
                  <button className="btn-partner" onClick={() => onTalk(a.id)}>
                    Talk to {a.display_name} <span aria-hidden="true">→</span>
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export function OnTheCounter({ stones, onAskPartner }) {
  if (!stones.length) return null;
  return (
    <section className="section section-counter" id="counter">
      <div className="site-container">
        <p className="eyebrow">On the counter tonight</p>
        <h2 className="section-title">A few stones our partners are excited about</h2>
        <div className="featured-grid">
          {stones.map((s) => {
            const lead = s.media.find((m) => m.kind === "image") || s.media.find((m) => m.poster_url);
            const src = lead ? lead.kind === "image" ? lead.url : lead.poster_url : null;
            return (
              <button
                key={`${s.agent.id}-${s.id}`}
                className="featured-card"
                style={{ "--stall-accent": s.agent.theme.accent, "--stall-glow": s.agent.theme.glow }}
                onClick={() => onAskPartner(s.agent.id, `Tell me about the ${s.name}.`)}
              >
                <span className="featured-media">
                  {src ? (
                    <img src={assetUrl(src)} alt="" loading="lazy" />
                  ) : (
                    <span className="featured-placeholder" aria-hidden="true">◆</span>
                  )}
                </span>
                <span className="featured-body">
                  <span className="featured-name">{s.name}</span>
                  <span className="featured-meta">
                    {formatPrice(s.price)}
                    {s.origin ? ` · ${s.origin}` : ""}
                  </span>
                  <span className="featured-ask">
                    Ask {s.agent.display_name} about it <span aria-hidden="true">→</span>
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}

const STEPS = [
  ["Ask in your own words", "Budget, colour, occasion, a stone you saw once. Our partners understand plain questions, not filters."],
  ["See the real stone", "They check live stock and show you that exact stone, with photos, video and its story."],
  ["Reserve it", "Found the one? Tap Reserve and the shop contacts you to hold it. No payment online."],
];

const PROMISES = [
  ["Only real stock", "Partners look up every price and stone before they answer. If it isn't in stock, they say so."],
  ["The details that matter", "Carat, cut, origin, treatment and certificates, straight from the shop's records."],
  ["People behind the counter", "Every reservation is confirmed by the shop team, who follow up with you personally."],
];

export function HowItWorks() {
  return (
    <section className="section" id="how">
      <div className="site-container">
        <p className="eyebrow">How it works</p>
        <h2 className="section-title">Shopping by conversation</h2>
        <ol className="steps">
          {STEPS.map(([title, text], i) => (
            <li key={title} className="step">
              <span className="step-number">{i + 1}</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </li>
          ))}
        </ol>
        <div className="promises">
          {PROMISES.map(([title, text]) => (
            <div key={title} className="promise">
              <span className="promise-mark" aria-hidden="true">◆</span>
              <div>
                <h3>{title}</h3>
                <p>{text}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function ClosingCall({ onAsk }) {
  return (
    <section className="section closing">
      <div className="site-container closing-inner">
        <h2 className="section-title">What are you looking for?</h2>
        <p className="hero-lede">Describe it and the right partner will take it from there.</p>
        <AskBox onAsk={onAsk} compact placeholder="Type your question..." />
      </div>
    </section>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-container site-footer-inner">
        <div>
          <Logo size={26} />
          <p>{TAGLINE}</p>
        </div>
        <div className="site-footer-meta">
          <span>© {new Date().getFullYear()} Loupe Gem</span>
          <a href="/admin">Staff login</a>
        </div>
      </div>
    </footer>
  );
}
