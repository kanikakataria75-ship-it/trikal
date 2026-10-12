import Link from "next/link";

// M3 in progress: panels DES/GP/EVT/HELP/FA/DUP/CR are written (components/terminal); the workspace shell is next.
export default function Page() {
  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", textAlign: "center", padding: 24 }}>
      <div>
        <p className="mono" style={{ color: "var(--gold-1)", letterSpacing: "0.2em", fontSize: 12 }}>M3 · IN PROGRESS</p>
        <h1 className="display" style={{ fontSize: 56, margin: "12px 0" }}>The terminal is being assembled.</h1>
        <Link href="/" style={{ color: "var(--fg-1)" }}>← back to the home page</Link>
      </div>
    </main>
  );
}
