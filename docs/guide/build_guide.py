"""Builds docs/guide/TRIKAL_KASAUTI_Field_Guide.pdf  (python docs/guide/build_guide.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

from content import SECTIONS

OUT = Path(__file__).with_name("TRIKAL_KASAUTI_Field_Guide.pdf")
F = Path(r"C:\Windows\Fonts")
for name, file in (("Body", "calibri.ttf"), ("Body-B", "calibrib.ttf"), ("Body-I", "calibrii.ttf"), ("Body-L", "calibril.ttf"),
                   ("Head", "cambriab.ttf"), ("Code", "consola.ttf"), ("Code-B", "consolab.ttf"), ("Nirmala", "Nirmala.ttc")):
    pdfmetrics.registerFont(TTFont(name, str(F / file), subfontIndex=0) if file.endswith('.ttc') else TTFont(name, str(F / file)))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-B", italic="Body-I", boldItalic="Body-B")

INK, GOLD, GOLD_D = colors.HexColor("#14161A"), colors.HexColor("#B8962E"), colors.HexColor("#8C6F1E")
PAPER, SOFT, LINE = colors.HexColor("#FFFFFF"), colors.HexColor("#F5F2E8"), colors.HexColor("#D9D3C0")
TEAL, RED, GREY = colors.HexColor("#1F8F86"), colors.HexColor("#B83A4B"), colors.HexColor("#5F6670")
W, H = A4
M = 20 * mm

S = {
    "body": ParagraphStyle("body", fontName="Body", fontSize=10.2, leading=14.6, textColor=INK, spaceAfter=5.5, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName="Body", fontSize=8.8, leading=12, textColor=GREY, spaceAfter=3),
    "h1toc": ParagraphStyle("h1toc", fontName="Head", fontSize=24, leading=28, textColor=INK, spaceAfter=4),
    "h1": ParagraphStyle("h1", fontName="Head", fontSize=24, leading=28, textColor=INK, spaceBefore=0, spaceAfter=4),
    "h1sub": ParagraphStyle("h1sub", fontName="Body-L", fontSize=11.5, leading=15, textColor=GOLD_D, spaceAfter=12),
    "h2": ParagraphStyle("h2", fontName="Head", fontSize=14, leading=18, textColor=INK, spaceBefore=12, spaceAfter=5),
    "h3": ParagraphStyle("h3", fontName="Body-B", fontSize=10.8, leading=14, textColor=GOLD_D, spaceBefore=7, spaceAfter=2),
    "bullet": ParagraphStyle("bullet", fontName="Body", fontSize=10.2, leading=14.2, textColor=INK, leftIndent=13, bulletIndent=2, spaceAfter=2.5),
    "code": ParagraphStyle("code", fontName="Code", fontSize=8.6, leading=11.6, textColor=colors.HexColor("#E8E6E1"), leftIndent=8, rightIndent=8),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=8.9, leading=11.6, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Body-B", fontSize=8.9, leading=11.6, textColor=INK),
    "cellh": ParagraphStyle("cellh", fontName="Body-B", fontSize=8.8, leading=11, textColor=colors.white),
    "cellc": ParagraphStyle("cellc", fontName="Code", fontSize=8.2, leading=11, textColor=colors.HexColor("#3A2F0B")),
    "call": ParagraphStyle("call", fontName="Body", fontSize=9.8, leading=13.6, textColor=INK),
    "toc1": ParagraphStyle("toc1", fontName="Body-B", fontSize=11, leading=17, textColor=INK, leftIndent=0),
    "toc2": ParagraphStyle("toc2", fontName="Body", fontSize=9.5, leading=13, textColor=GREY, leftIndent=14),
}
WIDTH = W - 2 * M


def P(t, s="body"):
    return Paragraph(t, S[s])


def bullets(items):
    return [Paragraph(i, S["bullet"], bulletText="•") for i in items]


def callout(title, text, kind="note"):
    bar = {"note": GOLD, "warn": RED, "ok": TEAL}[kind]
    inner = [Paragraph(f"<b>{title}</b>", ParagraphStyle("ct", parent=S["call"], textColor=bar if kind != "note" else GOLD_D)), Paragraph(text, S["call"])]
    t = Table([[inner]], colWidths=[WIDTH])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("LINEBEFORE", (0, 0), (0, -1), 3, bar), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return [t, Spacer(1, 7)]


def code(lines):
    t = Table([[Paragraph("<br/>".join(l.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(" ", "&nbsp;") for l in lines), S["code"])]], colWidths=[WIDTH])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), INK), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return [t, Spacer(1, 7)]


def table(header, rows, widths, mono_first=False):
    data = [[Paragraph(h, S["cellh"]) for h in header]]
    for r in rows:
        data.append([Paragraph(str(c), S["cellc"] if (mono_first and i == 0) else S["cell"]) for i, c in enumerate(r)])
    t = Table(data, colWidths=[WIDTH * w for w in widths], repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), INK), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
    for i in range(2, len(data), 2):
        st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FAF8F0")))
    t.setStyle(TableStyle(st))
    return [t, Spacer(1, 8)]


class Doc(BaseDocTemplate):
    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and f.style.name in ("h1", "h2"):
            lvl = 0 if f.style.name == "h1" else 1
            text = f.getPlainText()
            key = f"toc-{self.seq.nextf('toc')}"
            self.canv.bookmarkPage(key)
            self.notify("TOCEntry", (lvl, text, self.page, key))


def cover(c, d):
    c.saveState()
    c.setFillColor(colors.HexColor("#0B0D10"))
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.6)
    for i, y in enumerate(range(40, int(H), 14)):                       # a faint price-chart stair of gold hairlines
        c.setStrokeColor(colors.Color(0.72, 0.58, 0.18, alpha=0.05 + 0.1 * (i % 5) / 5))
        c.line(0, y, W, y)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.4)
    c.line(M, H - 78 * mm, M + 46 * mm, H - 78 * mm)
    c.setFillColor(GOLD)
    c.setFont("Body-B", 10)
    c.drawString(M, H - 70 * mm, "T R I K A L   ·   P O I N T - I N - T I M E   R E S E A R C H")
    c.setFillColor(colors.white)
    c.setFont("Head", 40)
    c.drawString(M, H - 100 * mm, "TRIKAL × KASAUTI")
    c.setFont("Head", 22)
    c.setFillColor(colors.HexColor("#F2D27A"))
    c.drawString(M, H - 113 * mm, "The Field Guide")
    c.setFillColor(colors.HexColor("#C9C6BD"))
    c.setFont("Body-L", 13)
    for i, line in enumerate(["A point-in-time research terminal for Indian equities,", "and the sector-relative ranking that audits itself.", "",
                              "How to run it, read it, trust it, and what comes next."]):
        c.drawString(M, H - (132 + 7 * i) * mm, line)
    c.setFillColor(GOLD)
    c.setFont("Body", 9.5)
    c.drawString(M, 36 * mm, f"Edition of {dt.date(2026, 10, 16):%d %B %Y}   ·   TRIKAL v0.7 (M1–M7)   ·   KASAUTI v1 (frozen)")
    c.setFillColor(colors.HexColor("#8A877E"))
    c.setFont("Body", 8.5)
    c.drawString(M, 29 * mm, "Personal research tool. Not investment advice: no ratings, no target prices, no recommendations.")
    c.restoreState()


def page(c, d):
    c.saveState()
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.line(M, H - 14 * mm, W - M, H - 14 * mm)
    c.setFont("Body", 8.2)
    c.setFillColor(GREY)
    c.drawString(M, H - 11.2 * mm, "TRIKAL × KASAUTI · Field Guide")
    c.drawRightString(W - M, H - 11.2 * mm, "Point-in-time · lineage on every value · personal research tool")
    c.line(M, 14 * mm, W - M, 14 * mm)
    c.drawString(M, 9.6 * mm, "Not investment advice")
    c.setFillColor(GOLD_D)
    c.setFont("Body-B", 8.6)
    c.drawRightString(W - M, 9.6 * mm, str(d.page))
    c.restoreState()


def build():
    doc = Doc(str(OUT), pagesize=A4, leftMargin=M, rightMargin=M, topMargin=20 * mm, bottomMargin=20 * mm,
              title="TRIKAL × KASAUTI — The Field Guide", author="TRIKAL", subject="How to use, read and trust TRIKAL and KASAUTI")
    fr = Frame(M, 20 * mm, WIDTH, H - 40 * mm, id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="cover", frames=[Frame(0, 0, W, H)], onPage=cover), PageTemplate(id="page", frames=[fr], onPage=page)])
    story: list = [Spacer(1, 1), PageBreak()]
    from reportlab.platypus import NextPageTemplate
    story.insert(1, NextPageTemplate("page"))
    toc = TableOfContents()
    toc.levelStyles = [S["toc1"], S["toc2"]]
    toc.dotsMinLevel = 0
    story += [P("Contents", "h1toc"), P("Everything in this guide, in the order you will need it.", "h1sub"), toc, PageBreak()]
    for n, sec in enumerate(SECTIONS):
        story.append(P(sec["title"], "h1"))
        story.append(P(sec["sub"], "h1sub"))
        for kind, *args in sec["blocks"]:
            if kind == "p":
                story.append(P(args[0]))
            elif kind == "h2":
                story.append(P(args[0], "h2"))
            elif kind == "h3":
                story.append(P(args[0], "h3"))
            elif kind == "ul":
                story += bullets(args[0])
            elif kind == "note":
                story += callout(args[0], args[1], "note")
            elif kind == "warn":
                story += callout(args[0], args[1], "warn")
            elif kind == "ok":
                story += callout(args[0], args[1], "ok")
            elif kind == "code":
                story += code(args[0])
            elif kind == "table":
                story += table(*args[:3], mono_first=args[3] if len(args) > 3 else False)
            elif kind == "space":
                story.append(Spacer(1, args[0]))
            elif kind == "break":
                story.append(PageBreak())
        if n < len(SECTIONS) - 1:
            story.append(PageBreak())
    doc.multiBuild(story)
    print("written", OUT, OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    build()
