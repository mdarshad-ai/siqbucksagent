import { useId } from "react";

// An AI partner avatar: a faceted, gem-cut helmet with a glowing visor, a
// gem core in the chest, circuit traces, and an orbiting ring. While the
// partner talks, a voice waveform animates and the visor brightens.
//
// variant picks the face so partners don't look identical:
//   "visor" - one wraparound visor band (default)
//   "twin"  - two angular eye slits
const VARIANTS = { siq: "visor", bucks: "twin" };

export default function Character({ theme, talking, active, variant }) {
  const { accent, accent_dim: dim, glow } = theme;
  const face = VARIANTS[variant] || variant || "visor";
  // Gradient ids must be unique per avatar on the page.
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const id = (name) => `${name}-${uid}`;

  return (
    <div className={`character ${talking ? "is-talking" : ""} ${active ? "is-active" : ""}`}>
      <div
        className="character-glow"
        style={{ background: `radial-gradient(circle, ${glow}66 0%, transparent 68%)` }}
      />
      <svg className="character-figure" viewBox="0 0 200 244" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <defs>
          <linearGradient id={id("shell")} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={dim} />
            <stop offset="0.55" stopColor="#12141f" />
            <stop offset="1" stopColor="#07080d" />
          </linearGradient>
          <linearGradient id={id("visor")} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor={accent} stopOpacity="0.2" />
            <stop offset="0.5" stopColor={glow} />
            <stop offset="1" stopColor={accent} stopOpacity="0.2" />
          </linearGradient>
          <radialGradient id={id("core")}>
            <stop offset="0" stopColor="#ffffff" />
            <stop offset="0.45" stopColor={glow} />
            <stop offset="1" stopColor={accent} stopOpacity="0" />
          </radialGradient>
          <filter id={id("blur")} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.4" />
          </filter>
        </defs>

        {/* orbit ring behind the head */}
        <g className="ai-orbit">
          <ellipse cx="100" cy="92" rx="84" ry="20" fill="none" stroke={glow} strokeOpacity="0.35" strokeWidth="1.2" strokeDasharray="3 7" />
          <circle cx="184" cy="92" r="3" fill={glow} />
        </g>

        {/* shoulders / bust */}
        <path
          d="M28 244 L38 196 L70 178 L100 186 L130 178 L162 196 L172 244 Z"
          fill={`url(#${id("shell")})`}
          stroke={accent}
          strokeWidth="1.5"
        />
        {/* facet lines on the bust */}
        <path d="M70 178 L84 244 M130 178 L116 244 M38 196 L60 244 M162 196 L140 244" stroke={accent} strokeOpacity="0.35" strokeWidth="1" />
        {/* circuit traces */}
        <g className="ai-circuit" stroke={glow} strokeWidth="1.2" fill="none" strokeOpacity="0.8">
          <path d="M100 214 V230 H122 L130 238" />
          <path d="M100 214 V224 H80 L70 234" />
          <circle cx="130" cy="238" r="2" fill={glow} />
          <circle cx="70" cy="234" r="2" fill={glow} />
        </g>
        {/* gem core */}
        <circle className="ai-core-glow" cx="100" cy="206" r="16" fill={`url(#${id("core")})`} />
        <path className="ai-core" d="M92 204 L96 198 H104 L108 204 L100 216 Z" fill={glow} stroke="#fff" strokeWidth="0.8" />

        {/* neck */}
        <path d="M88 160 H112 L116 184 L100 190 L84 184 Z" fill="#0d0f18" stroke={accent} strokeOpacity="0.6" strokeWidth="1.2" />
        <path d="M90 168 H110 M89 175 H111" stroke={accent} strokeOpacity="0.5" strokeWidth="1" />

        {/* faceted head: a gem-cut helmet */}
        <path
          d="M100 30 L134 44 L148 78 L144 118 L126 150 L100 162 L74 150 L56 118 L52 78 L66 44 Z"
          fill={`url(#${id("shell")})`}
          stroke={accent}
          strokeWidth="1.8"
        />
        <path
          d="M100 30 L100 62 M66 44 L84 66 M134 44 L116 66 M52 78 L84 66 L116 66 L148 78 M56 118 L74 132 M144 118 L126 132 M74 150 L86 138 H114 L126 150"
          stroke={accent}
          strokeOpacity="0.4"
          strokeWidth="1"
          fill="none"
        />
        {/* crown light */}
        <path d="M92 36 L100 30 L108 36" stroke={glow} strokeWidth="2" fill="none" strokeLinecap="round" />

        {/* face */}
        {face === "twin" ? (
          <g className="ai-eyes">
            <path d="M66 96 L92 90 L92 102 L70 106 Z" fill={`url(#${id("visor")})`} />
            <path d="M134 96 L108 90 L108 102 L130 106 Z" fill={`url(#${id("visor")})`} />
            <path d="M66 96 L92 90 L92 102 L70 106 Z M134 96 L108 90 L108 102 L130 106 Z" fill={glow} filter={`url(#${id("blur")})`} opacity="0.7" />
            <circle className="ai-pupil" cx="82" cy="97" r="3" fill="#fff" />
            <circle className="ai-pupil" cx="118" cy="97" r="3" fill="#fff" />
          </g>
        ) : (
          <g className="ai-eyes">
            <rect x="60" y="86" width="80" height="20" rx="10" fill="#05060a" stroke={accent} strokeWidth="1.2" />
            <rect x="64" y="90" width="72" height="12" rx="6" fill={`url(#${id("visor")})`} />
            <rect x="64" y="90" width="72" height="12" rx="6" fill={glow} filter={`url(#${id("blur")})`} opacity="0.55" />
            <rect className="ai-scan" x="64" y="90" width="14" height="12" rx="6" fill="#fff" opacity="0.85" />
          </g>
        )}

        {/* voice waveform: animates while talking */}
        <g className="ai-wave" fill={glow}>
          {[0, 1, 2, 3, 4].map((i) => (
            <rect key={i} className="ai-wave-bar" x={86 + i * 6} y="124" width="3" height="10" rx="1.5" />
          ))}
        </g>
      </svg>
    </div>
  );
}
