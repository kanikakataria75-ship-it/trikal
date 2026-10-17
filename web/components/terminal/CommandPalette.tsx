"use client";

import { Command } from "cmdk";
import { useEffect, useState } from "react";
import { useSearch } from "@/lib/api";
import { FUNCTIONS, parse } from "@/lib/commands";
import { dmy, todayIST } from "@/lib/format";
import { useT, workspace, type FnCode } from "@/lib/store";
import { Mark } from "@/components/ui/Logo";

const TIME_PRESETS: [string, string][] = [
  ["NOW", "Return to the present"], ["-1Y", "One year ago"], ["-5Y", "Five years ago"],
  ["2020-03-23", "COVID crash low"], ["2016-11-09", "Day after demonetisation"], ["2008-10-24", "October 2008 crash"],
];

export default function CommandPalette() {
  const open = useT((s) => s.paletteOpen);
  const setOpen = useT((s) => s.setPalette);
  const { code, asOf, setCode, setAsOf, say, history, pushHistory, setMode, setShock } = useT();
  const [v, setV] = useState("");
  const [deb, setDeb] = useState("");
  useEffect(() => { const t = setTimeout(() => setDeb(v), 140); return () => clearTimeout(t); }, [v]);
  useEffect(() => { if (open) setV(""); }, [open]);
  const today = todayIST();
  const p = parse(v, today);
  const term = p.kind === "entity" ? p.code : "";
  const { data } = useSearch(term && deb.toUpperCase().startsWith(term) ? term : "", "NOW");

  const close = () => setOpen(false);
  const execute = (raw: string, pickedCode?: string) => {
    const q = parse(raw, today);
    pushHistory(raw.toUpperCase().trim());
    if (q.kind === "asof") { setAsOf(q.value); say(q.value === "NOW" ? "Back to the present" : `Rewound to ${dmy(q.value)} — nothing published later is visible`, "info"); }
    else if (q.kind === "fn") workspace.open(q.fn);
    else if (q.kind === "entity") { setCode(pickedCode ?? q.code); workspace.open(q.fn); }
    else if (q.kind === "mode") { setMode(q.mode); say(q.mode === "pro" ? "PRO mode: flat, dense, keyboard-first" : "CINEMA mode: the 3D experience", "info"); }
    else if (q.kind === "shock") { setShock(q.text); workspace.open("TX"); }
    else if (q.kind === "help") workspace.open("HELP");
    else if (q.kind === "report") { window.open(`/api/company/${encodeURIComponent(code ?? "")}/report.pdf?as_of=${encodeURIComponent(asOf)}`, "_blank"); }
    else if (q.kind === "compare") { window.location.href = `/compare?codes=${q.codes.join(",")}${asOf !== "NOW" ? `&asof=${asOf}` : ""}`; return; }
    else if (q.kind === "later") say(`${q.word} arrives with ${q.milestone}`, "warn");
    else if (q.kind === "bad") { say(q.why, "warn"); return; }
    close();
  };

  if (!open) return null;
  const hits = data?.results ?? [];
  const fnArg = p.kind === "entity" ? p.fn : "DES";
  return (
    <div className="pal-back" onMouseDown={close}>
      <div className="pal" onMouseDown={(e) => e.stopPropagation()}>
        <Command label="TRIKAL command" shouldFilter={false} loop>
          <div className="pal-in">
            <Mark size={16} />
            <Command.Input autoFocus value={v} onValueChange={setV} placeholder="TCS FA · HDFCBANK · ASOF 2008-10-24 · HELP"
              onKeyDown={(e) => { if (e.key === "Escape") close(); }} />
            <span className="pal-ctx mono">{code}</span>
          </div>
          <div className="pal-parse">
            {p.kind === "asof" && <>Rewind every panel to <b>{p.value === "NOW" ? "NOW" : dmy(p.value)}</b></>}
            {p.kind === "entity" && <>Open <b>{p.code}</b> · {FUNCTIONS[p.fn].label}</>}
            {p.kind === "fn" && <>Open <b>{FUNCTIONS[p.fn].label}</b> for {code}</>}
            {p.kind === "later" && <span className="warn">{p.word} arrives with {p.milestone}</span>}
            {p.kind === "bad" && <span className="warn">{p.why}</span>}
            {p.kind === "help" && <>Function codes, grammar and keys</>}
            {p.kind === "shock" && <>Run the shock <b>{p.text.toUpperCase()}</b> through the Transmission Engine</>}
            {p.kind === "mode" && <>Switch to <b>{p.mode === "pro" ? "PRO" : "CINEMA"}</b> mode</>}
            {p.kind === "empty" && <span className="t-dim">Type a company, a function code, or ASOF &lt;date&gt;</span>}
          </div>
          <Command.List className="pal-list">
            {p.kind !== "empty" && p.kind !== "bad" && !(p.kind === "entity" && hits.length) && (
              <Command.Item value={"run:" + v} onSelect={() => execute(v)}>
                <span className="pal-k">↵</span><span>Run <b className="mono">{v.toUpperCase()}</b></span>
              </Command.Item>
            )}
            {p.kind === "entity" && hits.length > 0 && (
              <Command.Group heading="Securities — including delisted">
                {hits.slice(0, 8).map((h) => (
                  <Command.Item key={h.security_id} value={h.security_id} onSelect={() => execute(`${h.code} ${fnArg}`, h.code)}>
                    <b className="mono pal-code">{h.code}</b>
                    <span className="pal-name">{h.name}</span>
                    <i className={`mono ${h.active ? "" : "neg"}`}>{h.active ? `${h.exchange} · since ${h.listed_from.slice(0, 4)}` : `delisted · last ${dmy(h.last_trade)}`}</i>
                  </Command.Item>
                ))}
              </Command.Group>
            )}
            {p.kind === "empty" && (
              <>
                {history.length > 0 && (
                  <Command.Group heading="Recent">
                    {history.slice(0, 5).map((h) => (
                      <Command.Item key={h} value={"h:" + h} onSelect={() => execute(h)}><span className="pal-k">↺</span><span className="mono">{h}</span></Command.Item>
                    ))}
                  </Command.Group>
                )}
                <Command.Group heading={`Functions for ${code}`}>
                  {(Object.keys(FUNCTIONS) as FnCode[]).map((f) => (
                    <Command.Item key={f} value={"f:" + f} onSelect={() => execute(f)}>
                      <b className="mono pal-code">{f}</b><span className="pal-name">{FUNCTIONS[f].label}</span><i>{FUNCTIONS[f].desc}</i>
                    </Command.Item>
                  ))}
                </Command.Group>
                <Command.Group heading="Time">
                  {TIME_PRESETS.map(([d, l]) => (
                    <Command.Item key={d} value={"t:" + d} onSelect={() => execute(`ASOF ${d}`)}>
                      <b className="mono pal-code">ASOF {d}</b><span className="pal-name">{l}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              </>
            )}
          </Command.List>
          <div className="pal-foot"><span>↑↓ select</span><span>↵ run</span><span>esc close</span><span className="pal-right">Research tool · no ratings or target prices</span></div>
        </Command>
      </div>
    </div>
  );
}
