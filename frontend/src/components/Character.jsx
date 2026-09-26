export default function Character({ theme, talking, active }) {
  const { accent, accent_dim, glow } = theme;

  return (
    <div className={`character ${talking ? "is-talking" : ""} ${active ? "is-active" : ""}`}>
      <div
        className="character-glow"
        style={{ background: `radial-gradient(circle, ${glow}55 0%, transparent 70%)` }}
      />
      <svg
        className="character-figure"
        viewBox="0 0 200 260"
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* lantern above */}
        <line x1="100" y1="0" x2="100" y2="26" stroke={accent_dim} strokeWidth="2" />
        <circle
          className="lantern"
          cx="100"
          cy="34"
          r="11"
          fill={glow}
          stroke={accent}
          strokeWidth="2"
        />

        {/* robe / body */}
        <path
          d="M60 250
             C55 180, 62 130, 100 118
             C138 130, 145 180, 140 250
             Z"
          fill={accent_dim}
          stroke={accent}
          strokeWidth="2"
        />
        {/* robe front seam */}
        <path
          d="M100 118 L100 250"
          stroke={accent}
          strokeWidth="1"
          opacity="0.5"
        />

        {/* arms */}
        <path
          d="M62 165 C45 175, 40 200, 46 225"
          fill="none"
          stroke={accent_dim}
          strokeWidth="14"
          strokeLinecap="round"
        />
        <path
          d="M138 165 C155 175, 160 200, 154 225"
          fill="none"
          stroke={accent_dim}
          strokeWidth="14"
          strokeLinecap="round"
        />

        {/* head */}
        <circle cx="100" cy="88" r="34" fill="#EFE0C8" />
        {/* hood */}
        <path
          d="M64 92 C60 55, 78 30, 100 30 C122 30, 140 55, 136 92
             C130 75, 116 66, 100 66 C84 66, 70 75, 64 92 Z"
          fill={accent_dim}
          stroke={accent}
          strokeWidth="2"
        />

        {/* face */}
        <circle cx="88" cy="90" r="3.2" fill="#2A2A2A" />
        <circle cx="112" cy="90" r="3.2" fill="#2A2A2A" />
        <ellipse
          className="character-mouth"
          cx="100"
          cy="102"
          rx="7"
          ry="2.4"
          fill="#2A2A2A"
        />
      </svg>
    </div>
  );
}
