"use client";

/* FA · DUP · CR */

import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { SankeyChart, BarChart } from "echarts/charts";
import { TooltipComponent, GridComponent, LegendComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useCashRiver, useDupont, useFinancials, type Cell, type MetricResult } from "@/lib/api";
import { crore, dmy, dmyTime, inr, LINE_LABEL, METRIC_LABEL, monYear } from "@/lib/format";
import { useT } from "@/lib/store";
import { Value } from "@/components/ui/Value";
import { Tip } from "@/components/ui/Tooltip";
import { PanelState, Seg, usePanelAsOf } from "./common";
import type { PanelProps } from "./PanelsA";

echarts.use([SankeyChart, BarChart, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer]);

/* ------------------------------------------------------------------ FA */
const STATEMENTS: [string, string][] = [["income", "Income statement"], ["bank", "Bank items"], ["ratio", "Ratios as reported"], ["balance", "Balance sheet"], ["cashflow", "Cash flow"]];
const PER_SHARE = new Set(["eps_basic", "eps_diluted", "face_value"]);

function CellView({ c, li, lineage }: { c?: Cell; li: string; lineage: boolean }) {
  if (!c) return <span className="v v-muted">—</span>;
  const shown = PER_SHARE.has(li) ? c.value.toFixed(2) : crore(c.value);
  return (
    <Tip content={
      <div>
        <b>{LINE_LABEL(li)}</b> <span className="k">{c.basis}</span>
        <div className="mono" style={{ margin: "4px 0" }}>{inr(c.value, false)}</div>
        <div>source concept <span className="mono">{c.concept}</span>{c.source_rank > 0 && <span className="k"> (fallback #{c.source_rank})</span>}</div>
        <div className="k mono" style={{ wordBreak: "break-all" }}>{c.filing_id.split("/").pop()}</div>
        <div className="k">public at {dmyTime(c.known_at)}</div>
        {c.restated && <div style={{ color: "var(--gold-0)" }}>Restated: an earlier filing showed a different value</div>}
        {c.low_confidence && <div style={{ color: "var(--warn)" }}>From a pre-2018 results page (HTML), not XBRL</div>}
      </div>
    }>
      <span className={`v ${c.value < 0 ? "neg" : ""}`}>
        {shown}
        {c.restated && <span className="v-r">R</span>}
        {c.low_confidence && <span className="v-dot" />}
        {lineage && <span className="lin mono">{c.concept.replace("html:", "h:").slice(0, 18)}</span>}
      </span>
    </Tip>
  );
}

export function FA({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const lineage = useT((s) => s.lineage);
  const asOf = usePanelAsOf(params.pin);
  const [period, setPeriod] = useState<"Q" | "FY">("FY");
  const q = useFinancials(code, asOf, { period });
  const d = q.data;
  return (
    <div className="t-panel fa">
      <div className="t-toolbar">
        <Seg value={period} onChange={setPeriod} options={[{ v: "FY", l: "Annual" }, { v: "Q", l: "Quarterly" }]} />
        <span className="t-dim">₹ crore · EPS in ₹ · consolidated where reported</span>
        <span className="t-legend"><span className="v-r">R</span> restated <span className="v-dot" /> pre-2018 page</span>
      </div>
      <PanelState q={q} empty={d && !d.rows.length ? "No results filings parsed for this company yet. The exchange-archive download is still running; this grid fills as documents arrive." : undefined}>
        {() => (
          <div className="fa-scroll">
            <table className="t-table fa-table">
              <thead>
                <tr><th className="sticky">Line item</th>{d!.periods.map((p) => <th key={p} className="mono">{period === "Q" ? monYear(p) : `FY${p.slice(2, 4)}`}<i>{dmy(p)}</i></th>)}</tr>
              </thead>
              {STATEMENTS.map(([st, title]) => {
                const rows = d!.rows.filter((r) => r.statement === st);
                if (!rows.length) return null;
                return (
                  <tbody key={st}>
                    <tr className="fa-sec"><td colSpan={d!.periods.length + 1}>{title}</td></tr>
                    {rows.map((r) => (
                      <tr key={r.line_item}>
                        <td className="sticky">{LINE_LABEL(r.line_item)}</td>
                        {d!.periods.map((p) => <td key={p}><CellView c={r.cells[p]} li={r.line_item} lineage={lineage} /></td>)}
                      </tr>
                    ))}
                  </tbody>
                );
              })}
            </table>
          </div>
        )}
      </PanelState>
    </div>
  );
}

/* ------------------------------------------------------------------ DUP */
type Node = MetricResult | { state: "value"; value: number; unit: string; formula: string };

function DNode({ title, sub, r, x, y, root }: { title: string; sub: string; r?: Node; x: number; y: number; root?: boolean }) {
  return (
    <div className={`dup-node ${root ? "root" : ""} ${r?.state === "value" ? "ok" : ""}`} style={{ left: `${x}%`, top: y }}>
      <div className="dup-t">{title}</div>
      <div className="dup-v">
        {!r ? <span className="v v-muted">…</span>
          : "metric" in r ? <Value r={r as MetricResult} />
            : r.state === "value" ? <span className="v">{(r as { value: number }).value.toFixed(2)}×</span>
              : <Value r={{ ...(r as object), metric: title } as MetricResult} />}
      </div>
      <div className="dup-s">{sub}</div>
    </div>
  );
}

export function DUP({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const asOf = usePanelAsOf(params.pin);
  const q = useDupont(code, asOf);
  const t = q.data?.tree;
  return (
    <div className="t-panel dup">
      <PanelState q={q}>
        {() => (
          <div className="dup-stage">
            <svg className="dup-wires" viewBox="0 0 100 100" preserveAspectRatio="none">
              {[16.6, 50, 83.4].map((x) => <path key={x} d={`M50 22 C50 40, ${x} 34, ${x} 52`} className={t?.roe?.state === "value" ? "live" : ""} />)}
              {[16.6, 50].map((x) => <path key={"b" + x} d={`M${x} 70 L${x} 80`} />)}
            </svg>
            <DNode root title="Return on equity" sub="PAT / average equity" r={t?.roe} x={50} y={16} />
            <DNode title="Net margin" sub="PAT / revenue" r={t?.net_margin} x={16.6} y={150} />
            <DNode title="Asset turnover" sub="revenue / assets" r={t?.asset_turnover} x={50} y={150} />
            <DNode title="Equity multiplier" sub="assets / equity" r={t?.equity_multiplier} x={83.4} y={150} />
            <DNode title="Net profit (TTM)" sub="sum of last 4 quarters" r={t?.pat_ttm} x={16.6} y={290} />
            <DNode title="Revenue (TTM)" sub="sum of last 4 quarters" r={t?.revenue_ttm} x={50} y={290} />
            <p className="dup-note">ROE = net margin × asset turnover × equity multiplier. Branches that cannot be computed say which input is missing; for lenders the playbook replaces this tree with the ROA tree in M7.</p>
          </div>
        )}
      </PanelState>
    </div>
  );
}

/* ------------------------------------------------------------------ CR: Cash River */
const LABEL: Record<string, string> = {
  revenue_from_operations: "Revenue", other_income: "Other income", interest_earned: "Interest earned",
  cost_of_materials: "Materials", purchases_of_traded_goods: "Traded goods", change_in_inventories: "Inventory change",
  employee_expense: "Employees", other_expenses: "Other expenses", depreciation_amortisation: "Depreciation", finance_costs: "Interest",
  interest_expended: "Interest paid", bank_provisions: "Provisions", exceptional_items: "Exceptional", tax_expense: "Tax", profit_after_tax: "Net profit",
  profit_before_tax: "Profit before tax",
};

export function CR({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const asOf = usePanelAsOf(params.pin);
  const q = useCashRiver(code, asOf);
  const [yi, setYi] = useState(0);
  const el = useRef<HTMLDivElement>(null);
  const year = q.data?.years[yi];

  const model = useMemo(() => {
    if (!year) return null;
    const it = year.items;
    const v = (k: string) => it[k]?.value ?? null;
    const income: [string, number][] = [];
    const rev = v("revenue_from_operations") ?? v("interest_earned");
    if (rev !== null) income.push([v("revenue_from_operations") !== null ? "revenue_from_operations" : "interest_earned", rev]);
    if (v("other_income") !== null) income.push(["other_income", v("other_income")!]);
    const total = income.reduce((a, [, x]) => a + x, 0);
    const mats = ["cost_of_materials", "purchases_of_traded_goods", "change_in_inventories"].map(v).filter((x): x is number => x !== null);
    const costs: [string, number][] = [];
    if (mats.length) costs.push(["Materials (net of inventory)", mats.reduce((a, b) => a + b, 0)]);
    for (const k of ["employee_expense", "other_expenses", "depreciation_amortisation", "finance_costs", "interest_expended", "bank_provisions"])
      if (v(k) !== null && v(k)! > 0) costs.push([LABEL[k], v(k)!]);
    const pbt = v("profit_before_tax"), tax = v("tax_expense"), pat = v("profit_after_tax");
    const missing = ["employee_expense", "other_expenses", "depreciation_amortisation", "finance_costs", "profit_before_tax", "tax_expense", "profit_after_tax"]
      .filter((k) => v(k) === null && !(k === "finance_costs" && v("interest_expended") !== null)).map((k) => LABEL[k]);
    if (!income.length || total <= 0) return { empty: true, missing } as const;
    const nodes = new Map<string, { name: string; itemStyle: { color: string } }>();
    const add = (name: string, color: string) => nodes.set(name, { name, itemStyle: { color } });
    const links: { source: string; target: string; value: number }[] = [];
    add("Total income", "#D4AF37");
    for (const [k, x] of income) { add(LABEL[k], "#F2D27A"); links.push({ source: LABEL[k], target: "Total income", value: x }); }
    const costSum = costs.reduce((a, [, x]) => a + x, 0);
    for (const [n, x] of costs) { add(n, "#3A414C"); links.push({ source: "Total income", target: n, value: x }); }
    let note = "";
    if (pbt !== null && pbt > 0) {
      add("Profit before tax", "#2EC4B6");
      links.push({ source: "Total income", target: "Profit before tax", value: pbt });
      if (tax !== null && tax > 0) { add("Tax", "#F0577A"); links.push({ source: "Profit before tax", target: "Tax", value: tax }); }
      if (pat !== null && pat > 0) { add("Net profit", "#2EC4B6"); links.push({ source: "Profit before tax", target: "Net profit", value: pat }); }
      const resid = total - costSum - pbt;
      if (Math.abs(resid) / total > 0.005 && resid > 0) { add("Other / reconciling", "#6B7079"); links.push({ source: "Total income", target: "Other / reconciling", value: resid }); note = "“Other / reconciling” = income − listed costs − PBT (items the filing does not break out, exceptional items)."; }
    } else if (pbt !== null && pbt <= 0) {
      add("Loss before tax", "#F0577A");
      links.push({ source: "Loss before tax", target: "Total income", value: -pbt });
      note = "A loss year: costs exceeded income; the loss is shown flowing in.";
    }
    return { empty: false, nodes: [...nodes.values()], links, missing, total, note } as const;
  }, [year]);

  useEffect(() => {
    if (!el.current || !model || model.empty) return;
    const ch = echarts.init(el.current, undefined, { renderer: "canvas" });
    ch.setOption({
      animationDuration: 900, animationEasing: "cubicOut",
      tooltip: {
        trigger: "item", backgroundColor: "rgba(13,15,18,0.96)", borderColor: "#3A414C", textStyle: { color: "#E8E6E1", fontSize: 12 },
        formatter: (p: { dataType: string; data: { source?: string; target?: string; value?: number }; name: string; value: number }) =>
          p.dataType === "edge" ? `${p.data.source} → ${p.data.target}<br/><b>${inr(p.data.value!)}</b> · ${((p.data.value! / model.total!) * 100).toFixed(1)}% of income` : `${p.name}<br/><b>${inr(p.value)}</b>`,
      },
      series: [{
        type: "sankey", left: 8, right: 120, top: 14, bottom: 14, nodeWidth: 12, nodeGap: 12, draggable: false, layoutIterations: 64,
        data: model.nodes, links: model.links,
        lineStyle: { color: "gradient", opacity: 0.38, curveness: 0.55 },
        emphasis: { focus: "adjacency", lineStyle: { opacity: 0.75 } },
        label: { color: "#A7A9AE", fontFamily: "Inter Tight", fontSize: 11.5, formatter: (p: { name: string; value: number }) => `${p.name}  {v|${inr(p.value)}}`, rich: { v: { color: "#E8E6E1", fontFamily: "JetBrains Mono", fontSize: 10.5 } } },
        itemStyle: { borderWidth: 0 },
      }],
    });
    const ro = new ResizeObserver(() => ch.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); ch.dispose(); };
  }, [model]);

  return (
    <div className="t-panel cr">
      {q.data && q.data.years.length > 0 && (
        <div className="t-toolbar">
          <div className="t-seg">{q.data.years.map((y, i) => <button key={y.period_end} className={i === yi ? "on" : ""} onClick={() => setYi(i)}>FY{y.period_end.slice(2, 4)}</button>)}</div>
          <span className="t-dim">where a year’s income went · annual filing · ₹</span>
        </div>
      )}
      <PanelState q={q} empty={q.data && !q.data.years.length ? "No annual results parsed for this company yet (download in progress)." : undefined}>
        {() => (
          <>
            {model?.empty ? <div className="t-empty"><b>Not enough lines to draw the river</b><span>missing: {model.missing.join(", ")}</span></div> : <div ref={el} className="cr-chart" />}
            {model && !model.empty && (
              <div className="t-foot">
                {model.missing.length > 0 && <span className="cr-miss">not in this filing: {model.missing.join(", ")} — shown as absent, never as zero. </span>}
                {model.note}
              </div>
            )}
          </>
        )}
      </PanelState>
    </div>
  );
}

export { METRIC_LABEL };
