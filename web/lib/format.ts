/* Number and date formatting. Money is INR; displayed in crore (1 Cr = 1e7) and lakh crore (1 L Cr = 1e12). */

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

export function indianGroup(n: number, digits = 0): string {
  return n.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function inr(v: number, compact = true): string {
  const a = Math.abs(v);
  const s = v < 0 ? "−" : "";
  if (!compact) return `${s}₹${indianGroup(a, 2)}`;
  if (a >= 1e12) return `${s}₹${(a / 1e12).toFixed(2)} L Cr`;
  if (a >= 1e7) return `${s}₹${indianGroup(a / 1e7, a >= 1e10 ? 0 : 1)} Cr`;
  if (a >= 1e5) return `${s}₹${(a / 1e5).toFixed(1)} L`;
  return `${s}₹${indianGroup(a, a < 100 ? 2 : 0)}`;
}

export function crore(v: number): string {
  return indianGroup(v / 1e7, Math.abs(v) >= 1e9 ? 0 : 1);
}

export function byUnit(v: number, unit: string): string {
  switch (unit) {
    case "INR": return inr(v);
    case "ratio": return `${(v * 100).toFixed(1)}%`;
    case "x": return `${v.toFixed(1)}×`;
    case "days": return `${v.toFixed(0)} d`;
    case "score": return v.toFixed(2);
    default: return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  }
}

export function compactNumber(n: number): string {
  if (n >= 1e7) return `${(n / 1e7).toFixed(1)} Cr`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(1)} L`;
  return indianGroup(n);
}

export function dmy(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = iso.slice(0, 10).split("-");
  return `${d[2]}-${MONTHS[+d[1] - 1]}-${d[0]}`;
}

export function dmyTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const ist = new Date(d.getTime() + (330 + d.getTimezoneOffset()) * 60_000);
  const hh = String(ist.getHours()).padStart(2, "0");
  const mm = String(ist.getMinutes()).padStart(2, "0");
  return `${dmy(iso.slice(0, 10))} ${hh}:${mm} IST`;
}

export function monYear(iso: string): string {
  const d = iso.slice(0, 10).split("-");
  return `${MONTHS[+d[1] - 1].charAt(0)}${MONTHS[+d[1] - 1].slice(1).toLowerCase()} ${d[0].slice(2)}`;
}

export const METRIC_LABEL: Record<string, string> = {
  market_cap: "Market cap", revenue_ttm: "Revenue (TTM)", pat_ttm: "Net profit (TTM)", ebitda: "EBITDA",
  ebitda_margin: "EBITDA margin", ebit_margin: "EBIT margin", net_margin: "Net margin", roe: "ROE", roa: "ROA", roce: "ROCE",
  pe: "P/E", pb: "P/B", ev_ebitda: "EV/EBITDA", ev_sales: "EV/Sales", ev: "Enterprise value", debt_to_equity: "Debt/Equity",
  net_debt: "Net debt", net_debt_ebitda: "Net debt/EBITDA", revenue_growth: "Revenue growth", profit_growth: "Profit growth",
  current_ratio: "Current ratio", interest_coverage: "Interest cover", fcf: "Free cash flow", fcf_yield: "FCF yield",
  altman_z: "Altman Z''", receivable_days: "Receivable days", inventory_days: "Inventory days", payable_days: "Payable days",
  cash_conversion_cycle: "Cash cycle", asset_turnover: "Asset turnover", equity_multiplier: "Equity multiplier",
};

export const LINE_LABEL = (li: string) =>
  li.replace(/_/g, " ").replace(/\bttm\b/, "TTM").replace(/\bnpa\b/, "NPA").replace(/\bppe\b/, "PPE").replace(/^./, (c) => c.toUpperCase());

export function todayIST(): string {
  const d = new Date();
  const ist = new Date(d.getTime() + (330 + d.getTimezoneOffset()) * 60_000);
  return `${ist.getFullYear()}-${String(ist.getMonth() + 1).padStart(2, "0")}-${String(ist.getDate()).padStart(2, "0")}`;
}
