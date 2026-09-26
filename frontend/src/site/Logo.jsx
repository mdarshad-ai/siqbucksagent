// Loupe Gem mark: a jeweller's loupe with a faceted stone in the lens.
export function LogoMark({ size = 32 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" className="logo-mark">
      <defs>
        <linearGradient id="lg-gold" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f3dca6" />
          <stop offset="1" stopColor="#b98d3f" />
        </linearGradient>
      </defs>
      <circle cx="20" cy="20" r="15" fill="none" stroke="url(#lg-gold)" strokeWidth="3.2" />
      <path d="M31 31 L43 43" stroke="url(#lg-gold)" strokeWidth="5" strokeLinecap="round" />
      <path d="M13 17 L17 12 H23 L27 17 L20 27 Z" fill="#f3dca6" opacity="0.95" />
      <path d="M13 17 H27 M17 12 L20 17 L23 12 M20 17 V27" stroke="#8a6a2e" strokeWidth="0.9" fill="none" />
    </svg>
  );
}

export default function Logo({ size = 30 }) {
  return (
    <span className="logo">
      <LogoMark size={size} />
      <span className="logo-word">
        Loupe <em>Gem</em>
      </span>
    </span>
  );
}
