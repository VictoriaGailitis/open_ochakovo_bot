/** Exact raster and vector assets exported from the supplied Figma file. */
export function Mascot({
  pose = 0,
  className = "",
}: {
  pose?: number;
  className?: string;
}) {
  const frame = Math.min(3, Math.max(0, Math.floor(pose)));
  return (
    <span
      className={`mascot ${className}`}
      role="img"
      aria-label="Открывашка — маскот Очаково"
    >
      <img
        src="/assets/eb811.png"
        alt=""
        width="432"
        height="144"
        style={{ left: -108 * frame }}
      />
    </span>
  );
}

export function WelcomeHistory({ className = "" }: { className?: string }) {
  return (
    <div
      className={`welcome-history ${className}`}
      aria-label="История продолжается с 1978 года"
    >
      <img
        className="history-line"
        src="/assets/c9aae.svg"
        alt=""
        width="350.904"
        height="49.0378"
      />
      <img
        className="history-ring"
        src="/assets/c7d4f.svg"
        alt=""
        width="107.877"
        height="107.877"
      />
      <img
        className="history-ring-inner"
        src="/assets/1c05f.svg"
        alt=""
        width="76"
        height="76"
      />
      <span className="history-label">ИСТОРИЯ ПРОДОЛЖАЕТСЯ</span>
      <span className="history-year">С 1978 ГОДА</span>
    </div>
  );
}

