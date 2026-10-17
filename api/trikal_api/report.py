"""A one-company research report as a PDF, built from the same point-in-time answers the terminal shows.

reportlab's built-in fonts are used so the report builds on any computer (so the rupee sign is written Rs). Every number carries the as-of
date of the report; nothing here is a recommendation."""

from __future__ import annotations

import datetime as dt
import io

INK, GOLD, GREY, LINE, SOFT = "#14161A", "#8C6F1E", "#5F6670", "#D9D3C0", "#F5F2E8"
POS, NEG = "#1F8F86", "#B83A4B"
METRICS = ["market_cap", "revenue_ttm", "pat_ttm", "ebitda_margin", "net_margin", "roe", "roce", "pe", "pb", "ev_ebitda", "debt_to_equity", "revenue_growth", "profit_growth", "fcf_yield"]
LABEL = {"market_cap": "Market cap", "revenue_ttm": "Revenue (TTM)", "pat_ttm": "Net profit (TTM)", "ebitda_margin": "EBITDA margin", "net_margin": "Net margin", "roe": "ROE",
         "roce": "ROCE", "pe": "P/E", "pb": "P/B", "ev_ebitda": "EV/EBITDA", "debt_to_equity": "Debt/Equity", "revenue_growth": "Revenue growth", "profit_growth": "Profit growth",
         "fcf_yield": "FCF yield"}
LINES = [("revenue_from_operations", "Revenue from operations"), ("total_income", "Total income"), ("profit_before_tax", "Profit before tax"), ("profit_after_tax", "Profit after tax"),
         ("eps_diluted", "EPS (diluted, Rs)"), ("total_assets", "Total assets"), ("total_equity", "Total equity"), ("cash_flow_operations", "Cash flow from operations")]


def _money(v: float) -> str:
    a = abs(v)
    s = "-" if v < 0 else ""
    if a >= 1e12:
        return f"{s}Rs {a / 1e12:.2f} lakh cr"
    if a >= 1e7:
        return f"{s}Rs {a / 1e7:,.0f} cr"
    if a >= 1e5:
        return f"{s}Rs {a / 1e5:.1f} lakh"
    return f"{s}Rs {a:,.0f}"


def _metric(m: dict | None) -> str:
    if not m or m.get("state") != "value":
        return "n/a"
    v, u = m["value"], m.get("unit")
    if u == "INR":
        return _money(v)
    if u == "ratio":
        return f"{v * 100:.1f}%"
    if u == "x":
        return f"{v:.1f}x"
    return f"{v:.2f}"


def build(d: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    c = lambda h: colors.HexColor(h)  # noqa: E731
    st = {
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=c(INK), spaceAfter=2),
        "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=9.5, leading=13, textColor=c(GREY), spaceAfter=8),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=c(GOLD), spaceBefore=10, spaceAfter=4),
        "b": ParagraphStyle("b", fontName="Helvetica", fontSize=9, leading=12.4, textColor=c(INK)),
        "s": ParagraphStyle("s", fontName="Helvetica", fontSize=7.6, leading=10, textColor=c(GREY)),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.4, leading=10.6, textColor=c(INK)),
        "hd": ParagraphStyle("hd", fontName="Helvetica-Bold", fontSize=8.2, leading=10, textColor=colors.white),
    }
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"{d['name']} - TRIKAL report", author="TRIKAL")
    W = A4[0] - 32 * mm

    def table(head, rows, widths, align_right_from=1):
        data = [[Paragraph(h, st["hd"]) for h in head]] + [[Paragraph(str(x), st["cell"]) for x in r] for r in rows]
        t = Table(data, colWidths=[W * w for w in widths], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), c(INK)), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 1), (-1, -1), 0.3, c(LINE)),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
                              + [("BACKGROUND", (0, i), (-1, i), c("#FAF8F0")) for i in range(2, len(data), 2)]))
        return t

    s = [Paragraph(d["name"], st["h1"]),
         Paragraph(f"{d['code']} · {d.get('sector') or 'sector not classified'} · playbook: {d.get('playbook') or 'n/a'} · as of {d['as_of_label']}"
                   + (f" · last close Rs {d['price']:,.2f} ({d['price_date']})" if d.get("price") else ""), st["sub"])]

    m = d["metrics"]
    rows = [[LABEL[k], _metric(m.get(k))] for k in METRICS if k in m]
    half = (len(rows) + 1) // 2
    two = [[Paragraph(a[0], st["cell"]), Paragraph(f"<b>{a[1]}</b>", st["cell"]),
            Paragraph(b[0], st["cell"]) if b else "", Paragraph(f"<b>{b[1]}</b>", st["cell"]) if b else ""] for a, b in zip(rows[:half], rows[half:] + [None] * (half - len(rows[half:])))]
    s += [Paragraph("Headline numbers", st["h2"])]
    if two:
        t = Table(two, colWidths=[W * 0.26, W * 0.24, W * 0.26, W * 0.24])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, c(LINE)), ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        s.append(t)
    k = d.get("kasauti")
    s.append(Paragraph("KASAUTI (a ranking among sector peers, not a rating)", st["h2"]))
    if k and k.get("score") is not None:
        pil = k["detail"]["pillars"]
        s.append(Paragraph(f"<b>Score {k['score']:.0f} / 100</b> · confidence {round((k['confidence'] or 0) * 100)}% · scored {k['scoring_date']} · peers: {k['peer_group']} ({k['n_peers']}) · "
                           f"{k['kind']}", st["b"]))
        s.append(Spacer(1, 3))
        s.append(table(["Pillar", "Percentile among peers", "Data coverage"], [[p.title(), f"{round(v['score'] * 100)}" if v["score"] is not None else "n/a", f"{round(v['coverage'] * 100)}%"] for p, v in pil.items()], [0.4, 0.35, 0.25]))
        left = ", ".join(sorted(k["detail"]["dropped"]))
        s.append(Paragraph(f"Left out of this score: {left}.", st["s"]))
    else:
        s.append(Paragraph(f"Not scored. {(k or {}).get('reason', 'KASAUTI scores Nifty 500 companies, quarterly from 2023.')}", st["b"]))

    f = d.get("financials")
    if f and f["periods"]:
        fy = [p for p in f["periods"] if p[5:7] == f["periods"][0][5:7]]          # one year-end only: the list also holds trailing 12-month filings
        ps = fy[:5][::-1]
        by = {r["line_item"]: r["cells"] for r in f["rows"]}
        body = []
        for li, lab in LINES:
            if li in by:
                body.append([lab] + [(f"{by[li][p]['value']:.2f}" if li.startswith("eps") else f"{by[li][p]['value'] / 1e7:,.0f}") if p in by[li] else "·" for p in ps])
        if body:
            s.append(Paragraph("Financial summary (Rs crore, financial years)", st["h2"]))
            s.append(table(["Line item"] + [f"FY{p[2:4]}" for p in ps], body, [0.3] + [0.7 / len(ps)] * len(ps)))
    sg = d.get("segments")
    if sg and sg["periods"]:
        p0 = sg["periods"][0]
        s.append(Paragraph(f"Segments, year to {p0['period_end']} ({p0['basis']})", st["h2"]))
        s.append(table(["Segment", "Revenue (Rs cr)", "Share", "Result (Rs cr)", "Margin"],
                       [[x["label"], f"{x['revenue'] / 1e7:,.0f}" if x.get("revenue") is not None else "n/a", f"{x['share'] * 100:.1f}%" if x.get("share") is not None else "n/a",
                         f"{x['result'] / 1e7:,.0f}" if x.get("result") is not None else "n/a", f"{x['margin'] * 100:.1f}%" if x.get("margin") is not None else "n/a"] for x in p0["segments"][:10]],
                       [0.4, 0.17, 0.12, 0.17, 0.14]))
    o = d.get("ownership")
    if o and o["quarters"]:
        q0 = o["quarters"][0]
        names = [("promoter", "Promoter"), ("mutual_funds", "Mutual funds"), ("insurance", "Insurance"), ("fpi", "Foreign portfolio"), ("retail", "Retail")]
        s.append(Paragraph(f"Ownership, quarter ended {q0['period_end']}", st["h2"]))
        s.append(Paragraph(" · ".join(f"{lab} {q0[key]:.2f}%" for key, lab in names if q0.get(key) is not None) or "No category detail in the filing.", st["b"]))
    cc = d.get("concalls")
    if cc and cc["promises"]:
        s.append(Paragraph("What management said it would do (earnings calls, rule-based reading)", st["h2"]))
        rows = [[str(p["call_period_end"])[:7], f"{p['quote'][:150]}{'...' if len(p['quote']) > 150 else ''}", {"revenue_growth": "Revenue growth", "ebit_margin": "EBIT margin", "ebitda_margin": "EBITDA margin", "profit_growth": "Profit growth"}.get(p["metric"], p["metric"]),
                 p["verdict"]] for p in cc["promises"] if p["verdict"] in ("delivered", "partially", "missed", "pending")][:8]
        if rows:
            s.append(table(["Call", "Statement", "Metric", "Verdict"], rows, [0.1, 0.57, 0.19, 0.14]))
            cr = cc["credibility"]
            s.append(Paragraph(f"{cr['judged']} statements judged: {cr['delivered']} kept, {cr['partially']} partly, {cr['missed']} missed, {cr['pending']} pending."
                               + (f" Credibility {cr['score'] * 100:.0f}%." if cr["score"] is not None else ""), st["s"]))
    s.append(Spacer(1, 10))
    s.append(Paragraph("Method and limits. All figures are point in time: only what was public on the as-of date. Ratios are computed from the company's filings under its sector playbook; "
                       "values marked n/a are not available, never estimated. KASAUTI is a percentile ranking among sector peers built from quarterly Nifty 500 data from 2023; "
                       "its report card is an in-sample backtest. Earnings-call statements are read by rules, not by a model. This is a research tool, not investment advice: "
                       "no ratings, no target prices, no recommendation. Generated by TRIKAL on " + dt.datetime.now().strftime("%d %b %Y %H:%M") + ".", st["s"]))
    doc.build(s)
    return buf.getvalue()
