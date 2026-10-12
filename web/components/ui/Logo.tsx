/* The TRIKAL mark: one gem, three facets — past (engraved), present (lit), future (hatched). */
export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="tk-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#F2D27A" />
          <stop offset="0.55" stopColor="#D4AF37" />
          <stop offset="1" stopColor="#8C6F1E" />
        </linearGradient>
        <pattern id="tk-h" width="2.4" height="2.4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="1" height="2.4" fill="#D4AF37" opacity="0.7" />
        </pattern>
      </defs>
      <path d="M16 2 L4 16 L16 30 Z" fill="#8C6F1E" opacity="0.85" />
      <path d="M16 2 L16 30 L28 16 Z" fill="url(#tk-h)" />
      <path d="M16 7 L10.5 16 L16 25 L21.5 16 Z" fill="url(#tk-g)" />
      <path d="M16 2 L4 16 L16 30 L28 16 Z" fill="none" stroke="#F2D27A" strokeWidth="0.8" opacity="0.9" />
    </svg>
  );
}

export function Wordmark({ deva = true }: { deva?: boolean }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
      <Mark />
      <span style={{ letterSpacing: "0.32em", fontWeight: 600, fontSize: 13 }}>TRIKAL</span>
      {deva && <span className="deva" style={{ color: "var(--gold-1)", fontSize: 15, opacity: 0.9 }}>त्रिकाल</span>}
    </span>
  );
}
