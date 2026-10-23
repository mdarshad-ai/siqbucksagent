import { useEffect, useState } from "react";
import { assetUrl } from "../api.js";
import Character from "../components/Character.jsx";
import { Link, navigate } from "../router.jsx";
import AskBox from "./AskBox.jsx";
import Logo from "./Logo.jsx";
import { BRAND, HEADLINE, LEDE } from "./brand.js";
import { EXPERT_COPY, HERO_PROMPTS } from "./expert.js";


function formatPrice(n) {
  return `$${Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

// Home-page sections: scroll there, going back to the home page first if needed.
function goToSection(e, id) {
  e.preventDefault();
  if (window.location.pathname !== "/") navigate("/");
  requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }));
}

export function SiteHeader({ expert, onTalk, current }) {
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
        <Link to="/" className="site-brand" aria-label="Luxuria Gems, home">
          <Logo />
        </Link>
        <nav className="site-nav" aria-label="Main">
          <Link to="/catalogue" className={current === "catalogue" ? "is-current" : ""}>
            Catalogue
          </Link>
          <a href="/#expert" onClick={(e) => goToSection(e, "expert")}>
            {expert?.display_name || "Gem Expert"}
          </a>
          <a href="/#how" onClick={(e) => goToSection(e, "how")}>
            How it works
          </a>
        </nav>
        <button className="btn-gold btn-small" onClick={() => onTalk()} disabled={!expert}>
          <span className="btn-label-extra">Talk to our </span>
          {expert?.display_name || "Gem Expert"}
        </button>
      </div>
    </header>
  );
}

export function Hero({ expert, onAsk, onTalk }) {
  return (
    <section className="hero" id="top">
      <div className="hero-backdrop" aria-hidden="true" />
      <div className="site-container hero-inner">
        <div className="hero-copy">
          <p className="eyebrow">{BRAND}</p>
          <h1>
            Gems crafted
            <br />
            to be <em>remembered.</em>
          </h1>
          <p className="hero-lede">{LEDE}</p>
          <AskBox
            onAsk={onAsk}
            prompts={HERO_PROMPTS}
            placeholder='Ask our AI gem expert, e.g. "a blue stone for a ring"'
          />
          {expert && (
            <div className="hero-partners" aria-label="Your AI gem expert">
              <span className="hero-partners-label">Your AI gem expert</span>
              <button
                className="hero-partner"
                style={{ "--stall-accent": expert.theme.accent, "--stall-glow": expert.theme.glow }}
                onClick={() => onTalk()}
              >
                <Character theme={expert.theme} variant={expert.id} talking={false} active />
                <span>
                  <span className="hero-partner-name">{expert.display_name}</span>
                  <span className="hero-partner-stall">{expert.stall_name}</span>
                </span>
              </button>
            </div>
          )}
          <Link to="/catalogue" className="hero-browse">
            Or explore the collection yourself <span aria-hidden="true">→</span>
          </Link>
        </div>
      </div>
    </section>
  );
}

export function MeetExpert({ expert, onTalk, onAsk }) {
  if (!expert) return null;
  const copy = EXPERT_COPY;
  return (
    <section className="section" id="expert">
      <div className="site-container">
        <p className="eyebrow">Meet your AI gem expert</p>
        <h2 className="section-title">Fine stones and great finds, one expert</h2>
        <article
          className="partner-card partner-card-solo"
          style={{ "--stall-accent": expert.theme.accent, "--stall-glow": expert.theme.glow }}
        >
          <div className="partner-card-figure">
            <Character theme={expert.theme} variant={expert.id} talking={false} active />
          </div>
          <div className="partner-card-body">
            <div className="partner-card-role">{copy.role}</div>
            <h3>
              {expert.display_name} <span>· {expert.stall_name}</span>
            </h3>
            <p className="partner-card-tagline">“{expert.tagline}”</p>
            <ul className="partner-known">
              {copy.knownFor.map((k) => (
                <li key={k}>{k}</li>
              ))}
            </ul>
            <div className="partner-ask">
              <span>Ask:</span>
              {copy.questions.map((q) => (
                <button key={q} className="chip" onClick={() => onAsk(q)}>
                  {q}
                </button>
              ))}
            </div>
            <button className="btn-partner" onClick={() => onTalk()}>
              Talk to our {expert.display_name} <span aria-hidden="true">→</span>
            </button>
          </div>
        </article>
      </div>
    </section>
  );
}

export function OnTheCounter({ stones }) {
  if (!stones.length) return null;
  return (
    <section className="section section-counter" id="counter">
      <div className="site-container">
        <p className="eyebrow">On the counter tonight</p>
        <h2 className="section-title">A few stones our expert is excited about</h2>
        <div className="featured-grid">
          {stones.map((s) => {
            const lead = s.media.find((m) => m.kind === "image") || s.media.find((m) => m.poster_url);
            const src = lead ? lead.kind === "image" ? lead.url : lead.poster_url : null;
            return (
              <button
                key={s.id}
                className="featured-card"
                style={{ "--stall-accent": s.agent.theme.accent, "--stall-glow": s.agent.theme.glow }}
                onClick={() => navigate(`/stones/${s.id}`)}
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
                    See it with our {s.agent.display_name} <span aria-hidden="true">→</span>
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
  ["Ask in your own words", "Budget, colour, occasion, a stone you saw once. Our expert understands plain questions, not filters."],
  ["See the real stone", "It checks live stock and shows you that exact stone, with photos, video and its story."],
  ["Reserve it", "Found the one? Tap Reserve and the shop contacts you to hold it. No payment online."],
];

const PROMISES = [
  ["Only real stock", "Our expert looks up every price and stone before it answers. If it isn't in stock, it says so."],
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
      <div className="closing-texture" aria-hidden="true" />
      <div className="site-container closing-inner">
        <p className="eyebrow">Your AI gem expert</p>
        <h2 className="section-title">What are you looking for?</h2>
        <p className="hero-lede">Describe it in your own words, and our expert will take it from there.</p>
        <AskBox onAsk={onAsk} compact placeholder="Type your question..." />
      </div>
    </section>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-container site-footer-inner">
        <div className="site-footer-brand">
          <Logo stacked size={30} />
          <p>{HEADLINE}</p>
        </div>
        <nav className="site-footer-links" aria-label="Footer">
          <Link to="/catalogue">Catalogue</Link>
          <a href="/#expert" onClick={(e) => goToSection(e, "expert")}>
            AI gem expert
          </a>
          <a href="/#how" onClick={(e) => goToSection(e, "how")}>
            How it works
          </a>
        </nav>
        <div className="site-footer-meta">
          <span>© {new Date().getFullYear()} {BRAND}</span>
          <a href="/admin">Staff login</a>
        </div>
      </div>
    </footer>
  );
}
