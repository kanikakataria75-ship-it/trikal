"use client";

/* The star and bell next to a company's name: add it to the watchlist, or set a price alert. Both lists live in this browser. */

import { useEffect, useRef, useState } from "react";
import { newId, usePriceAlerts, useWatch } from "@/lib/lists";
import { workspace } from "@/lib/store";

export function WatchButton({ code }: { code: string }) {
  const [w, setW] = useWatch();
  const on = w.codes.includes(code);
  return (
    <button className={`des-pdf des-star ${on ? "on" : ""}`} title={on ? "On your watchlist (click to remove)" : "Add to your watchlist: alerts for results, score moves, big price moves"}
      onClick={() => setW({ codes: on ? w.codes.filter((c) => c !== code) : [...w.codes, code] })}>{on ? "★ Watching" : "☆ Watch"}</button>
  );
}

export function AlertButton({ code, price }: { code: string; price: number | null }) {
  const [list, setList] = usePriceAlerts();
  const [open, setOpen] = useState(false);
  const [op, setOp] = useState<"above" | "below">("above");
  const [val, setVal] = useState("");
  const box = useRef<HTMLSpanElement>(null);
  const mine = list.filter((a) => a.code === code);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  const add = (e: React.FormEvent) => {
    e.preventDefault();
    const p = Number(val.replace(/,/g, ""));
    if (!(p > 0)) return;
    setList([...list, { id: newId(), code, op, price: p }]);
    setVal("");
  };
  return (
    <span ref={box} className="al-wrap">
      <button className={`des-pdf ${mine.length ? "on" : ""}`} onClick={() => { setOpen(!open); if (!val && price) setVal(String(Math.round(price))); }}
        title="Set a price alert: tell me when the price goes above or below a level">🔔 Alert{mine.length ? ` (${mine.length})` : ""}</button>
      {open && (
        <div className="al-pop">
          <div className="al-h">Price alert for <b className="mono">{code}</b>{price ? <span className="t-dim"> · last close ₹{price.toLocaleString("en-IN")}</span> : null}</div>
          <form onSubmit={add}>
            <select value={op} onChange={(e) => setOp(e.target.value as "above" | "below")}><option value="above">goes above</option><option value="below">falls below</option></select>
            <input value={val} onChange={(e) => setVal(e.target.value)} inputMode="decimal" placeholder="price ₹" autoFocus />
            <button type="submit">Add</button>
          </form>
          {mine.map((a) => (
            <div key={a.id} className="al-row"><span>{a.op === "above" ? "above" : "below"} <b className="mono">₹{a.price.toLocaleString("en-IN")}</b></span><i onClick={() => setList(list.filter((x) => x.id !== a.id))} title="remove">×</i></div>
          ))}
          <div className="al-f">Checked every few minutes while TRIKAL is open, against the latest close. <a onClick={() => { setOpen(false); workspace.open("WL"); }}>Open watchlist</a></div>
        </div>
      )}
    </span>
  );
}
