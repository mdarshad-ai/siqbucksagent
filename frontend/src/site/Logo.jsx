// The Luxuria Gems mark (gold ribbons and star, on a transparent background)
// and the LUXURIA / GEMS wordmark set in Cormorant Garamond.
export function LogoMark({ size = 32 }) {
  return (
    <img
      className="logo-mark"
      src="/brand/mark-128.webp"
      alt=""
      width={Math.round(size * 0.88)}
      height={size}
      decoding="async"
    />
  );
}

export default function Logo({ size = 34, stacked = false }) {
  return (
    <span className={`logo ${stacked ? "logo-stacked" : ""}`}>
      <LogoMark size={stacked ? size * 2 : size} />
      <span className="logo-word">
        <span className="logo-luxuria">Luxuria</span>
        <span className="logo-gems">Gems</span>
      </span>
    </span>
  );
}
