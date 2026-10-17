"use client";

/* Buttons for the tools in the top bar, so nothing depends on remembering a command. The watchlist button carries the alert count. */

import { FUNCTIONS } from "@/lib/commands";
import { useAlertFeed } from "@/lib/lists";
import { useT, workspace, type FnCode } from "@/lib/store";

const MAIN: { fn?: FnCode; label: string; title: string; act?: "compare" | "report" }[] = [
  { fn: "SCRN", label: "Screener", title: "Find companies by a condition" },
  { fn: "CALC", label: "Calculator", title: "If I had put an amount in on a date" },
  { fn: "WL", label: "Watchlist", title: "Your watchlist, alerts and price levels" },
  { fn: "PORT", label: "Portfolio", title: "Value your holdings" },
  { fn: "CAL", label: "Calendar", title: "Upcoming results, dividends and board meetings" },
  { label: "Compare", title: "Compare this company with others (full page)", act: "compare" },
  { label: "Report", title: "PDF report of this company as of the current date", act: "report" },
];

export default function HeaderTools() {
  const { code, asOf } = useT();
  const feed = useAlertFeed();
  const run = (b: (typeof MAIN)[number]) => {
    if (b.fn) { workspace.open(b.fn); return; }
    if (b.act === "compare") window.location.href = `/compare?codes=${encodeURIComponent(code ?? "")},${asOf !== "NOW" ? `&asof=${asOf}` : ""}`;
    if (b.act === "report" && code) window.open(`/api/company/${encodeURIComponent(code)}/report.pdf?as_of=${encodeURIComponent(asOf)}`, "_blank");
  };
  return (
    <nav className="t-tools" aria-label="Tools">
      {MAIN.map((b) => (
        <button key={b.label} title={b.title} onClick={() => run(b)}>
          {b.label}
          {b.fn === "WL" && feed.count > 0 && <em className="t-badge">{feed.count}</em>}
        </button>
      ))}
      <details className="t-more">
        <summary title="Every function">More ▾</summary>
        <div className="t-more-menu" onClick={(e) => ((e.currentTarget.parentElement as HTMLDetailsElement).open = false)}>
          {(Object.keys(FUNCTIONS) as FnCode[]).map((f) => (
            <button key={f} onClick={() => workspace.open(f)} title={FUNCTIONS[f].desc}><b className="mono">{f}</b><span>{FUNCTIONS[f].label}</span></button>
          ))}
        </div>
      </details>
    </nav>
  );
}
