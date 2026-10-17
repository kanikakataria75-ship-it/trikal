"""Text of the field guide. Plain data so the layout code stays small. Markup: <b> <i> <font name="Code">."""

C = lambda s: f'<font name="Code" size="9">{s}</font>'  # noqa: E731

SECTIONS = []


def sec(title, sub, blocks):
    SECTIONS.append({"title": title, "sub": sub, "blocks": blocks})


# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
sec("1 · Start here", "What TRIKAL is, what it promises, and how the pieces fit", [
    ("p", "<b>TRIKAL</b> (त्रिकाल: past, present, future) is a personal research terminal for Indian equities. It answers one question better than a "
          "normal screener: <i>what could an investor have known on a given day, and what does the evidence say now?</i> Every number is stored with the "
          "moment it became public, so you can rewind the whole terminal to any past date and see exactly what was visible then."),
    ("p", "<b>KASAUTI</b> (कसौटी: the touchstone) is the ranking built on top of it. It places each company among its own sector peers, explains the "
          "result pillar by pillar, and then audits itself with a report card that shows whether the ranking has actually predicted returns."),
    ("h2", "The promises the system keeps"),
    ("table", ["Rule", "What it means in practice"], [
        ["No fabricated data", "A gap shows as <b>n/a</b> with the missing input named. There is no mock data, no imputation and no silent zero."],
        ["Point in time", "Every query carries an <i>as-of</i> date. Facts published after it do not exist. Restatements add new versions; they never overwrite."],
        ["Survivorship free", "Delisted, merged and renamed companies stay in the history, so backtests do not only see the winners."],
        ["Lineage on every value", "Click or hover to see the filing, page or deck the number came from, and when it became public."],
        ["Sector rules in the engine", "A metric the sector forbids (for example EBITDA for a bank) cannot be computed at all, not just hidden."],
        ["Research, not advice", "No ratings, no target prices, no buy or sell calls. Valuation shows ranges with their assumptions."],
        ["No LLM spend", "Everything reads documents with rules and word lists, and every extracted figure keeps its page and sentence."],
    ], [0.27, 0.73]),
    ("h2", "How the pieces fit"),
    ("table", ["Layer", "What it does", "Where it lives"], [
        ["Raw zone", "Every downloaded file, content-addressed and never edited", "data/raw (SQLite index + files)"],
        ["Pipeline", "Fetches and parses: prices, filings, shareholding, macro, decks, transcripts", "pipeline/"],
        ["Core", "The time model and the only door to the data (PitReader)", "core/"],
        ["Analytics", "Metrics, sector playbooks, valuation, sensitivities, promise judging", "analytics/"],
        ["KASAUTI", "Scoring, report card, score versions", "kasauti/, config/scores/"],
        ["API", "FastAPI; <b>as_of</b> is required on every data endpoint", "api/"],
        ["Terminal", "Next.js workspace: PRO and CINEMA modes, 3D scenes with flat twins", "web/"],
    ], [0.18, 0.5, 0.32]),
    ("note", "Bhoot · Bhavishya", "The Time Spine at the bottom of the terminal is the past (Bhoot). Drag it and every panel rewinds. To the right of NOW "
             "is Bhavishya, the future: hatched and empty, because the future holds scenarios, not data. The playhead cannot enter it."),
])

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
sec("2 · Running it", "One double-click, a daily routine, and the rules that keep the database safe", [
    ("h2", "Start and stop"),
    ("ul", [f"Double-click {C('TRIKAL.bat')} in the project folder. It starts the data server (port 8000) and the terminal (port 3000), waits until both answer, "
            "and opens the browser at the terminal. The first start takes up to a minute.",
            f"Double-click {C('STOP_TRIKAL.bat')} to stop both. Closing the browser tab alone leaves them running, which is fine.",
            "Open the terminal directly at http://localhost:3000/terminal. Add ?code=TCS to jump to a company and &amp;fn=KAS to jump to a panel."]),
    ("h2", "The daily routine"),
    ("ul", [f"A Windows scheduled task, <b>TRIKAL daily prices</b>, runs at 19:45 IST and pulls the day's prices (the exchange publishes after 19:30).",
            "Live quotes come from your own broker account (Angel One, read-only) and appear only on NOW, after you set the keys in .env.",
            f"Whenever new filings have been downloaded, run {C('trikal refresh-m2')} (parse everything, run the accounting checks, rewrite the coverage report).",
            f"Once a month after results season, run {C('trikal kasauti-score')} so the KASAUTI <b>live record</b> keeps growing."]),
    ("warn", "One writer at a time", "DuckDB lets only one process write. Anything that writes (refresh-m2, kasauti-score, build-calls, build-reported, adjust...) "
             "needs the data server stopped (STOP_TRIKAL.bat) or it waits up to 20 minutes for the lock. Read-only checks can run while the server is up."),
    ("h2", "Folders you will use"),
    ("table", ["Path", "What is in it"], [
        ["data/trikal.duckdb", "The canonical database (about 3 GB). Back it up before big pipeline runs."],
        ["data/raw/", "Immutable downloads. Safe to keep; never edit."],
        ["data/logs/", "One log per job: m2_overnight.log, m2_refresh.log, kasauti_backtest.log, fetch_calls.log ..."],
        ["data/kasauti/report_v1.json", "The report card behind the KAS panel."],
        ["config/", "Sector playbooks, line items, context tags, macro series, score files (config/scores/)."],
        ["docs/", "ADRs (decisions), formulas, risks, data sources, this guide, generated reports."],
        [".env", "Your broker keys. Git-ignored; never share or paste it. .env.example lists the names only."],
    ], [0.34, 0.66], True),
])

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
sec("3 · Driving the terminal", "The command bar, the function keys, modes and the as-of date", [
    ("h2", "Two modes"),
    ("table", ["Mode", "For", "Switch"], [
        ["PRO", "A dense workstation: DES, peers, price chart, statements, KASAUTI, map and macro on one screen. Opens straight into the terminal.", "MODE PRO or the switch at top right"],
        ["CINEMA", "The 3D experience: the Time Machine home page, market city, transmission planes, the globe. Every 3D view has a flat twin in PRO.", "MODE CINEMA"],
    ], [0.14, 0.62, 0.24]),
    ("h2", "The command bar (press / or Ctrl+K)"),
    ("table", ["Type", "What happens"], [
        ["TCS", "Loads TCS in the default view (DES). Any NSE symbol, BSE code or company name fragment works; results are searched as of the current as-of date."],
        ["TCS FA", "TCS on the Financial statements panel. The second word is any function code."],
        ["GP / FA / KAS / CALL ...", "Opens that panel for the company already loaded."],
        ["ASOF 2020-03-14", "Rewinds everything to a date. Also ASOF -5Y, ASOF -6M, ASOF -30D, ASOF NOW. The future is refused."],
        ["SHOCK CRUDE +20", "Runs the shock simulator (see section 7). Combine with &amp;: SHOCK CRUDE +20 &amp; INR 90."],
        ["MODE PRO / MODE CINEMA", "Switches mode."],
        ["CC, CONCALL, KASAUTI, SEGMENTS", "Aliases for CALL, CALL, KAS and SEG."],
        ["? or HELP", "The function list and the grammar."],
    ], [0.3, 0.7], True),
    ("h2", "Function keys (PRO)"),
    ("table", ["Key", "Panel", "Key", "Panel"], [
        ["F1", "HELP", "F7", "MAP · market heatmap"], ["F2", "DES · description", "F8", "MACRO · macro desk"],
        ["F3", "GP · price chart", "F9", "TX · transmission and SHOCK"], ["F4", "FA · statements", "F10", "OWN · ownership"],
        ["F6", "RV · relative value", "Esc", "leaves a full-window TX or GEO"],
    ], [0.1, 0.4, 0.1, 0.4]),
    ("p", "F5, F11 and F12 stay with the browser. Panels are dockview tabs: drag a tab to rearrange, double-click it to maximise, "
          "or press Ctrl+Shift+Enter. TX and GEO open full-window because their 3D scenes need room."),
    ("h2", "The as-of date and the pins"),
    ("ul", ["The Time Spine sets one global as-of for every panel. Drag it, click an event marker, or type ASOF.",
            "Markers on the spine: corporate actions (gold diamonds), results (green ticks), index entries and exits, and above the line the policy, "
            "geopolitical and market events from Wikipedia (context only, never an input to a number).",
            "A panel can be <b>pinned</b> to its own date (the pin icon in its title) to compare two moments side by side."]),
])

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
sec("4 · Panel by panel", "What each function shows and how to read it", [
    ("table", ["Code", "Shows", "How to read it"], [
        ["DES", "Identity, listings, live price, headline metrics, the sector playbook",
         "The playbook line says which valuation methods this sector allows (primary and secondary) and which are forbidden, with the reason. "
         "A metric marked n/a names what is missing."],
        ["GP", "Daily price chart: adjusted or raw prints, line or candles, log or linear, volume",
         "Adjusted prices use only splits and bonuses confirmed by both an announcement and the observed price move. Gold verticals mark them. "
         "Raw prints show what traded on the day. See the drawing tools below."],
        ["FA", "Quarterly or annual statements with lineage",
         "R marks a restated value; a dot marks a pre-2018 page (lower confidence). Click a cell for its filing and publication time. The group "
         "\"Ratios as reported\" shows ratios the company states itself (DSCR, ISCR)."],
        ["DUP", "ROE = margin × turnover × equity multiplier", "Shows which lever moved ROE. Banks use a different tree (leverage matters differently)."],
        ["CR", "Cash River: where a year's income went", "Costs, interest, tax and profit as a flow; the thickest stream is where the money goes."],
        ["RV", "Peers: same sector label <i>and</i> same resolved playbook, at the same as-of", "A company with no computable metric is hidden, not shown as zero. First load can take several seconds."],
        ["WC", "What changed since last quarter", "Metric moves and the events that became public in between."],
        ["OWN", "Promoter, funds, insurance, foreign investors, retail; pledge",
         "Category detail exists from Sep-2021; pledge history only from the first fetch. A group missing in a quarter is n/a, never 0."],
        ["DCF", "Valuation Lab", "Only the methods the sector allows. Output is always a range with assumptions and sensitivity, never a target."],
        ["EVT", "Corporate actions, results, index changes", "Each with its public time. 'Rewind here' jumps the Time Spine."],
        ["SEG", "Reportable segments as the company files them", "Revenue, share, result, margin, assets, by year or quarter. See section 6."],
        ["KAS", "KASAUTI score and report card", "See section 5."],
        ["CALL", "Earnings-call statements judged against results; tone drift", "See section 6."],
        ["MAP", "That day's index members as a heatmap", "Area = turnover, colour = move; hover a stock, click to open it. The as-of follows the Time Spine."],
        ["MACRO", "FX, rates, inflation, commodities", "Each tile shows the value as known on the as-of, with y/y; a tilde (~) means the release time is estimated."],
        ["TX", "Transmission: macro driver → sector → company, and SHOCK", "See section 7."],
        ["CALC", "Return calculator", "Pick a stock, a start date, an amount and an end date (default today): what it became. Splits and bonuses add shares; dividends can be ignored, kept as cash or reinvested. No tax or charges."],
        ["SCRN", "Screener over the KASAUTI panel", "Type a condition such as roce > 20% and pe < 25 and score > 60. Presets, your own saved screens, \"Fields & syntax\" lists every field. A company with no figure never matches."],
        ["WL", "Watchlist with alerts", "Add symbols; alerts for new results, a KASAUTI score move of 5 or more, a big one-day price move, 52-week highs and lows, ex-dates and board meetings. Mark as read; optional desktop notifications while the page is open."],
        ["PORT", "Portfolio", "Enter symbol, quantity and average price (or paste CSV). Value, P&amp;L, day change, weights, sector mix, KASAUTI score of the book. Rewind the as-of to value it on a past date."],
        ["CAL", "Calendar", "Board meetings the companies announced (results, dividends, fund raising) for 2 weeks to 90 days ahead, for the Nifty 500, your lists or everything, each with when it was announced."],
        ["RES", "Results card", "The latest quarter against the quarter before and the year before (revenue, EBITDA and margin, profit, EPS), who bought or sold since, how the KASAUTI score moved, the price after the numbers came out, and what management had said about that year. Banks show interest earned and operating profit before provisions."],
        ["HEAT", "Sector heatmap", "A sector's companies as a grid of KASAUTI pillar scores (green strong, red weak, dot = pillar left out). Click a header to sort, a row to open the company. The median row shows the group's middle."],
        ["NOTE", "Notes", "Your own words and tags per company, stamped with the price the day you first wrote. Search all notes, download them as a text file. Kept in this browser only."],
        ["GEO", "Exposure theatre: trade arteries and chokepoints", "See section 7."],
    ], [0.08, 0.3, 0.62], True),
    ("h2", "KASAUTI v2 (draft) next to the frozen v1"),
    ("p", "v1 is frozen and stays the reference. <b>v2</b> adds two pillars: <b>earnings quality</b> (how much of the profit turns into cash: cash flow from operations over profit, accruals over assets, and the share of profit that is other income; not for banks) and <b>management credibility</b> (the share of the numbers management gave on earnings calls that later came true, shrunk toward 50% so one statement cannot decide). Switch with <b>v1 · frozen / v2 · draft</b> at the top of KAS, and in HEAT. On the in-sample report card v2 is slightly better than v1 at every horizon, but by less than the noise of a short history, so it proves nothing yet. Credibility exists for only 56 companies today and for none before 2025 (the transcripts we hold start in 2024), so for most companies that pillar is shown as left out. Freezing v2 is the owner's decision."),
    ("h2", "Compare, report and the other new tools"),
    ("ul", ["<b>Score history:</b> inside KAS, a chart of the company's KASAUTI score at every quarterly scoring date next to its price. It shows what the ranking said and what the price did, nothing more.",
            "<b>Compare:</b> type <b>CMP TCS INFY WIPRO</b> (two or three symbols) or press Compare in the DES header. A clean full-page view: rebased price chart, headline numbers with the best value highlighted, KASAUTI pillars, ownership and the statements side by side. Back to Terminal returns.",
            "<b>PDF report:</b> the PDF report button in the DES header (or the command <b>RPT</b>) makes a short research report for the loaded company as of the current as-of date: headline numbers, KASAUTI, statements, segments, ownership and earnings-call statements, with the method and its limits.",
            "Your watchlist, portfolio, saved screens and drawings live in <b>this browser only</b>; the server only values them and never stores them. A different browser or cleared site data starts empty (use the CSV box in PORT to keep a copy)."]),
    ("h2", "Drawing tools on the price chart (the Draw button on GP)"),
    ("p", "Click the <b>Draw</b> button at the top-left of the chart to open the toolbar. Drawings are your own notes: they are saved in this browser, per stock, and "
          "never touch any number the system computes. They are anchored to a bar and a price, so they follow the chart when you pan, zoom or switch log and linear."),
    ("table", ["Tool", "How", "Good for"], [
        ["Select", "Drag a drawing to move it, drag a round handle to reshape it. Esc deselects.", "Editing"],
        ["Trend line", "Click two points. Double-click the line to extend it to the right as a ray. A selected line shows % change and bars.", "Trends, channels"],
        ["Horizontal line", "One click; the price is printed on the line.", "Support and resistance levels"],
        ["Vertical line", "One click.", "Events, earnings dates"],
        ["Zone", "Click two opposite corners. The block extends to the right.", "Support / resistance blocks, supply and demand"],
        ["Fibonacci", "Click swing start and swing end: 0, 23.6, 38.2, 50, 61.8, 78.6 and 100% levels with prices.", "Retracements"],
        ["Text", "One click, then type the note.", "Labels"],
        ["Measure", "Two clicks: change in price and number of bars. Not saved.", "Quick distance checks"],
    ], [0.2, 0.52, 0.28]),
    ("p", "Colours apply to the selected drawing (or the next one). The bin button or the Delete key removes the selected drawing; the undo button or Ctrl+Z undoes; "
          "the cross button clears the stock's drawings."),
])

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
sec("5 · KASAUTI", "The score, its formula, and how to read the report card honestly", [
    ("p", "KASAUTI never grades a company in the abstract. It asks: <i>among companies of the same kind, on this date, where does this one stand on each "
          "measure?</i> The answer is a percentile, and the score is a weighted blend of percentiles. A score of 62 means \"better than a bit more than half "
          "of its peers on the weighted blend\", not \"62% good\"."),
    ("h2", "The formula (version 1)"),
    ("ul", ["<b>Peers.</b> The Nifty 500 members on the scoring date that share the company's resolved sector playbook (banks with banks). "
            "If fewer than 8, the parent group is used and the output says so.",
            "<b>Metric percentile.</b> Mid-rank percentile among peers with a value (at least 5 needed). Lower-is-better metrics (P/E, debt, NPA) are flipped.",
            "<b>Pillar score.</b> Weighted average of its metric percentiles. A pillar whose data covers less than half of its metric weight is <b>dropped</b>.",
            "<b>Score.</b> 100 × weighted average of the kept pillars, needing at least 3. <b>Confidence</b> = the data coverage of the kept pillars, weighted.",
            "<b>Drivers.</b> Each metric's points = 100 × pillar share × metric share × (percentile − 0.5): what lifted or dragged the score most.",
            "Missing is never imputed. A metric the sector forbids, or flags with a caution (P/E of a cyclical at peak margins), is skipped for that company."]),
    ("h2", "Pillars and weights"),
    ("table", ["Pillar", "Weight", "Industrial companies", "Banks, NBFCs, insurers"], [
        ["Quality", "25%", "ROCE (×2), ROE, EBITDA margin, net margin", "ROE (×2), ROA, cost-to-income"],
        ["Valuation", "20%", "EV/EBITDA, P/E, P/B, FCF yield (all cheaper = better, except FCF yield)", "P/B (×2), P/E"],
        ["Growth", "15%", "Revenue growth, profit growth", "Revenue growth, profit growth"],
        ["Balance sheet", "15%", "Net debt/EBITDA, debt/equity, interest cover, Altman Z", "Gross and net NPA, CET1, credit cost, assets/equity"],
        ["Momentum", "15%", "12-1 month return (×2), 6-month return", "same"],
        ["Ownership flow", "10%", "Promoter change 1y, institutions change 1y, pledge", "same"],
    ], [0.17, 0.1, 0.4, 0.33]),
    ("warn", "What v1 does not have (listed on every score)", "<b>Management credibility</b> (the Promise Tracker is not yet a score input), <b>macro fit</b> (sector sensitivities "
             "are mostly low-confidence statistics), <b>forensics</b> (milestone 9) and a <b>sector-regime</b> term. These appear under \"Left out, and why\" on the KAS panel."),
    ("h2", "Reading the KAS panel"),
    ("ul", ["The big number is the score; the tag says <b>in-sample reconstruction</b> (computed after the fact from point-in-time inputs) or <b>live record</b> "
            "(computed on the scoring date, after the freeze). Only live scores are evidence.",
            "Pillar bars show each pillar's percentile and its data coverage. A short bar with low coverage deserves less trust.",
            "\"What moved it most\" lists the metrics with their percentile and points. \"All inputs\" shows every value, including n/a ones.",
            "Peers show the group and whether the parent group was used. Scores exist quarterly (Mar, Jun, Sep, Dec), from 2023, for Nifty 500 members."]),
    ("h2", "The report card (in-sample backtest, generated 16 Oct 2026)"),
    ("p", "Method: score the Nifty 500 at each quarter end, buy at the next session's open, measure the price return over 1, 3, 6 and 12 months, rank by score. "
          "Costs of 0.25% per side apply to the portfolio test; shares that stop trading are closed at their last price and counted; "
          "the benchmark is the equal-weight average of the scored universe; dividends are not included."),
    ("table", ["Horizon", "Dates", "Rank IC", "t-stat (Newey-West)", "Top decile − universe", "Top beat universe on"], [
        ["1 month", "13", "0.007", "0.3", "+0.2%", "54% of dates"], ["3 months", "13", "0.028", "1.3", "+1.2%", "69%"],
        ["6 months", "12", "0.037", "2.1", "+3.0%", "92%"], ["12 months", "10", "0.041", "2.1", "+5.4%", "80%"],
    ], [0.14, 0.09, 0.12, 0.2, 0.25, 0.2]),
    ("p", "Mean 12-month return by score decile (lowest to highest): 10.2, 10.2, 9.9, 13.1, 8.2, 13.0, 10.2, 11.0, 13.8, <b>17.0</b> percent. "
          "The top-decile portfolio returned 18.6% a year after costs against 14.1% for the equal-weight universe, with a maximum drawdown of −16.5% against −19.3% (13 quarters)."),
    ("h3", "How to interpret that"),
    ("ul", ["<b>Rank IC</b> is the correlation between rank by score and rank by later return, averaged over dates. 0 is noise; 0.05 is a modest real edge in practice; "
            "1.0 would be perfect foresight. The values here are small and positive.",
            "<b>t-stat</b> says how far the average IC is from zero relative to its wobble. Above about 2 is conventionally \"unlikely to be chance\", but with 10–13 overlapping "
            "dates it is suggestive, not proof.",
            "<b>Deciles</b> should rise from left to right. Here they roughly do at 12 months, but not smoothly (decile 5 is the lowest of the middle)."]),
    ("warn", "The edge is fading", "Mean 3-month IC by scoring year: 2023 +0.066, 2024 +0.048, 2025 +0.007, 2026 −0.026 (2026 has only a few dates). Most of the average comes from "
             "2023–24. A ranking can earn its keep once and then stop; only the live record, which started on 16 Oct 2026, can tell. Treat the score as one more lens, never as a signal to trade on."),
    ("note", "Why only 2023 onwards", "NSE's own 2018–2021 XBRL result files are partial (no full statements), and the older HTML pages end in 2017 and carry income statements only. "
             "Full statements exist from 2022, so scored dates start in 2023. Backtests cannot honestly reach further back with this data."),
    ("h2", "Freezing and the live record"),
    ("p", f"Version 1 is <b>frozen</b>: its file {C('config/scores/kasauti_v1.yaml')} is pinned by SHA-256 in {C('config/scores/FROZEN.json')} and a test fails if the file ever changes "
          "(a git rule keeps its bytes exact). Changing weights or metrics means a new file, kasauti_v2.yaml, and a new report card. Scores computed after the freeze date form the live record "
          "and are never merged with the in-sample table."),
])

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
sec("6 · Segments, decks and concalls", "Filling the gaps without a language model", [
    ("p", "Concall transcripts, presentations and annual reports are free text, and you have no LLM budget. So TRIKAL reads them with <b>rules, word lists and "
          "cross-checks</b>, shows the sentence and page for everything it extracts, and leaves out whatever it cannot read with confidence."),
    ("h2", "Segments (SEG)"),
    ("p", "The exchange's XBRL results carry each segment's real name as a text fact (\"Oil to Chemicals (O2C)\", \"Banking, Financial Services and Insurance\"). "
          "TRIKAL uses that name, so a business has the same key across filings. About 630 Ind AS companies from around FY2019 have segment tables."),
    ("ul", ["Revenue is external revenue; result is profit before tax and finance cost; plug lines (unallocated, eliminations) get no margin.",
            "<b>Reliance example (FY26):</b> O2C 50.4%, Retail 28.2%, <b>Digital Services 13.4%</b> (this is where Jio Platforms sits; Reliance does not file Jio as a separate segment), "
            "Others 6.1%, Oil and Gas 1.8%. The panel shows the company's own labels and does not rename them.",
            "Label wording changes between filings (for example Tata Motors lists sub-lines such as \"(a) Passenger Vehicle\"). Read the names, not just the numbers."]),
    ("h2", "Bank and NBFC metrics from results decks"),
    ("p", "NIM, CASA ratio, provision coverage, slippage ratio and capital adequacy are not in the results XBRL, only in the investor presentation. "
          "TRIKAL downloaded 527 decks of 50 banks and NBFCs and extracts a figure only when it sits in a table row whose header names the periods "
          "(with as many periods as numbers, one of them the deck's reporting quarter) or in a single-percentage sentence that names that quarter."),
    ("ul", ["Safeguards: plausibility ranges, a cross-check of NIM against net interest income over assets from the XBRL, CAR must not sit below CET1, rows with more than 8 columns "
            "or running prose are refused, and a figure far from the company's own median is removed.",
            "Result: 248 values for 28 companies (CAR 87, PCR 63, NIM 61, CASA 23, slippage 9); 324 decks matched nothing and stay n/a.",
            "In the terminal these metrics now show a value with its deck, page and line when one is current (within about two quarters), otherwise they still say what they need."]),
    ("warn", "Accuracy", "Rule-based extraction can still misread an unusual table (a column order that the header does not reveal). That is why every value carries the page and "
             "line, and why outliers are removed. For a number you will act on, open the deck page it points to."),
    ("h2", "Concalls (CALL)"),
    ("p", "Transcripts the company filed with the exchange are downloaded (newest 8 per Nifty 500 company; about one in six is only a one-page cover letter pointing to the company website and is skipped as too short). "
          "Two things are read:"),
    ("h3", "1. Statements with a number (the Promise Tracker)"),
    ("ul", ["A sentence counts only if it has a forward cue (expect, guide, target, will, on track ...), a metric (revenue growth, operating margin, profit growth are judged; capex, volume, "
            "debt and returns are listed), a percentage, and a year.",
            "Skipped: questions, statements about the past, negations, analysts speaking to management (\"you guided...\"), and multi-year targets (CAGR, \"next five years\"). "
            "A sentence with two figures for two metrics gives two statements; one figure shared by two metrics is left out as ambiguous.",
            "<b>Like with like.</b> Guidance in constant currency, for one business (\"services revenue\") or for an unspecified \"margin\" is listed but <b>not judged</b>, because the filings report total rupee revenue; IT-services revenue guidance is never judged for the same reason. An operating-margin statement is compared with the filing's EBIT margin, an EBITDA-margin statement with EBITDA margin.",
            "<b>Verdicts are deterministic</b> and use only results public at the as-of date: <i>kept</i> (actual at or above the low end), <i>partly</i> (within about 20% of it), "
            "<i>missed</i>, <i>pending</i> (that year's results are not out yet), <i>not judged</i> (no single financial year), <i>no data</i>.",
            "<b>Management credibility</b> = kept 1, partly 0.5, missed 0, averaged over judged statements, and shown only after 4 are judged. "
            "Most companies give no numeric guidance, so many will show n/a; IT services companies are the richest source."]),
    ("h3", "2. Tone and its drift"),
    ("ul", ["Word lists (positive, negative, hedging, deflected answers such as \"take that offline\") are counted per 1,000 words of management statements, questions excluded.",
            "The panel shows the net tone and hedging against the previous call and the average of the four before. A rising hedge rate or falling tone is a prompt to read the call, not a verdict.",
            "It is a word count, not understanding: sarcasm, negation and context are invisible to it."]),
])

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
sec("7 · Macro, transmission and exposure", "How a rupee move or an oil shock reaches a sector, and what the globe means", [
    ("h2", "MACRO"),
    ("p", "27 series (USD/INR, Brent, US and Indian yields, VIX, India CPI, 17 commodities) stored with the date each value became public. Without a FRED key the release time of some "
          "series is estimated (marked ~). Adding FRED_API_KEY to .env replaces the estimate with real first-release dates for FRED series."),
    ("h2", "TX and the SHOCK simulator"),
    ("p", "For every sector and each of 10 drivers, TRIKAL fits a monthly regression over the trailing 60 months: sector return = a + b·driver change + k·market return. "
          "The sector's response is b (relative to the market) plus the market's own response. Each estimate is usable only from the date its window ended, so rewinding never sees a later estimate."),
    ("code", ["SHOCK CRUDE +20", "SHOCK INR 90", "SHOCK REPO +50bp", "SHOCK CRUDE +20 & INR +5", "SHOCK UST +50bp & VIX +30"]),
    ("ul", ["<b>+20</b> means a 20% rise; <b>INR 90</b> means to the level 90; <b>REPO +50bp</b> uses the call-money rate as the repo proxy. Combined shocks add, and the panel warns about double counting.",
            "The table shows <b>Relative</b> (vs market), <b>Market</b> and <b>Total</b> per sector, with a confidence mark: three dots high, two medium, one low (weak statistics; the cell is dimmed).",
            "A shock far outside the history (more than 3× the driver's typical month) is flagged as a straight-line extension: read it as an order of magnitude only.",
            "At the latest as-of 160 of 190 sector-by-driver cells are low confidence. The strong one is the market's own sensitivity to USD/INR. This is an <i>estimated price response</i> "
            "from history, not an earnings forecast and not a causal channel."]),
    ("h2", "GEO, the exposure theatre"),
    ("ul", ["A dot-globe centred on India. Arcs are India's trade arteries (Gulf crude, Europe via Suez, the Cape route, East Asia, electronics), with moving light.",
            "Rings are chokepoints (Hormuz, Red Sea / Bab-el-Mandeb, Malacca, Taiwan Strait). A ring's size and colour show how many dated news items in the last three months "
            "mention the area, as a percentile of that area's own history. It measures attention, not flow.",
            "Click a ring or a table row for what it carries, the channel into Indian sectors, a sparkline of monthly mentions, the latest sourced items and, for Hormuz, the "
            "<i>measured</i> sector response to a +20% crude move. Links for the other areas are qualitative, with their source named. Company-level exposure needs export and import splits from annual reports."]),
])

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
sec("8 · Command reference", "Every trikal command, when to use it, and the order jobs depend on each other", [
    ("p", f"All commands are run from the project folder as {C('.venv\\Scripts\\trikal.exe COMMAND')} (or double-click the .cmd launchers for the long jobs). "
          "Stop the data server before any command marked W (it writes the database)."),
    ("table", ["Command", "What it does", ""], [
        ["init", "Create or upgrade the database schema.", "W"],
        ["fetch-prices / load-prices", "Download daily bhavcopies into the raw zone; load them into price_eod.", "W (load)"],
        ["update-daily", "Bring prices up to the last published session, then parse the fundamentals downloaded so far. The scheduled 19:45 task runs this.", "W"],
        ["fetch-masters / fetch-corp-actions / load-ref", "NSE symbol, name and delisting files; corporate actions month by month; load them.", "W (load)"],
        ["fetch-index / build-index", "Nifty snapshots and index press releases; rebuild point-in-time membership.", "W (build)"],
        ["build / adjust", "Rebuild the security master and adjustment events; adjust rebuilds only the adjustments (about 2 minutes).", "W"],
        ["fetch-m2", "Overnight raw download of filing lists and result XBRL (resumable). run_m2_overnight.cmd wraps it.", ""],
        ["refresh-m2 / parse-financials / parse-ownership", "Parse downloaded filings and shareholding, run the identity checks, rewrite docs/reports/coverage.md.", "W"],
        ["check-financials / coverage", "Accounting-identity pass rates; the data coverage report.", "W"],
        ["relabel-dims", "One-off: name segment and cost-breakdown members in already-loaded filings.", "W"],
        ["fetch-context / fetch-macro", "Wikipedia context layer; macro series (FRED, MOSPI, World Bank Pink Sheet).", "W (load)"],
        ["build-sensitivity", "Monthly sector returns and the point-in-time sector sensitivities.", "W"],
        ["fetch-decks / build-reported", "Download results decks of banks and NBFCs; read them into fact_reported.", "W (build)"],
        ["fetch-calls / build-calls", "Download earnings-call transcripts; read them into concall and concall_promise.", "W (build)"],
        ["fetch-calendar", "Fetch the exchange's board-meeting intimations (past 45 days to next 90) and rebuild the calendar. Run it every few days.", "W"],
        ["kasauti-score [--date]", "Score the Nifty 500 for one date and store it (the live record once frozen).", "W"],
        ["kasauti-backtest", "Score every quarterly date and rebuild the report card.", "W"],
        ["kasauti-freeze", "Pin a score version by SHA-256. Do this once per version.", ""],
        ["analyze CODE", "Print a company's playbook, allowed metrics and each metric with its reasons.", ""],
        ["show CODE --as-of DATE", "Print a security as the terminal would have seen it on a date.", ""],
        ["raw-status", "Summarise the raw-zone fetch log.", ""],
    ], [0.3, 0.62, 0.08], True),
    ("warn", "Never share .env", "It holds your broker PIN and TOTP secret, which can log in to your brokerage account. A friend does not need it: the terminal runs without it (live prices off). They can add their own keys later."),
    ("h2", "Dependencies, in one picture"),
    ("code", ["prices  ->  security master + adjustments  ->  index membership",
              "filings (fetch-m2) -> refresh-m2 -> financials, ownership, segments, classification",
              "macro + prices -> build-sensitivity -> TX / SHOCK",
              "decks -> build-reported -> bank metrics        transcripts -> build-calls -> CALL",
              "prices + filings + membership -> kasauti-score / kasauti-backtest -> KAS panel"]),
    ("h2", "Launchers"),
    ("table", ["File", "Use"], [
        ["TRIKAL.bat / STOP_TRIKAL.bat", "Start / stop the terminal and data server."],
        ["PACK_FOR_FRIEND.bat", "Makes a TRIKAL_for_friend folder beside the project: program zip (2 MB), the database and instructions. Never includes .env, your broker keys or raw downloads."],
        ["INSTALL_TRIKAL.bat", "Run once on the other laptop: installs Python and Node if missing (winget), the Python and web packages, creates .env from the template. Then TRIKAL.bat."],
        ["run_m2_overnight.cmd", "Resumable filing download (hidden window); relaunch if the laptop slept."],
        ["run_update_prices.cmd, run_update_daily.cmd", "Prices only, and prices plus parsing."],
        ["run_fetch_decks.cmd, run_build_reported.cmd", "Presentations download and parse."],
        ["run_fetch_calls.cmd", "Transcripts download (about 2 hours for 500 companies at one request a second)."],
        ["run_kasauti_backtest.cmd", "Score every quarter and rebuild the report card (about 45 minutes)."],
    ], [0.4, 0.6], True),
])

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
sec("9 · Data, time and lineage", "The model underneath, and why a rewound view can be trusted", [
    ("h2", "Two clocks"),
    ("p", "Every fact has a <b>valid time</b> (the period it describes, such as the quarter ended 30 June) and a <b>known time</b> (when it became public). "
          "A query supplies an as-of; only facts known by then are visible. A restated figure is a new row with a later known time, so you can see both the original and the restatement, and what an investor saw in between."),
    ("ul", ["If a source gives only a date, the known time is that date at 23:59; if it gives nothing, a stated conservative rule is used and the value is marked <b>imputed</b>.",
            "A backtest trades at the next session's open after a fact becomes known (ADR-003), never at the close of the day it appeared.",
            "The API has no default as-of: it is required on every data endpoint, the future is refused, and live quotes exist only for NOW."]),
    ("h2", "What is in the database (16 Oct 2026)"),
    ("table", ["Area", "Coverage"], [
        ["Prices", "28.1 million daily rows, NSE from 1994 and BSE from 2007; 9,862 securities including delisted and merged"],
        ["Corporate actions", "43,794 announcements; 2,788 confirmed adjustments applied (announcement plus observed price move)"],
        ["Index membership", "Nifty 500, exactly 500 members on every effective date since Dec-2011; earlier history is approximate and flagged"],
        ["Results", "5.4 million financial facts for about 1,000 companies; HTML pages 2008–2017, XBRL from 2022 (2018–2021 files are partial)"],
        ["Ownership", "Sixteen quarters of category detail and pledge for the downloaded companies"],
        ["Macro", "27 series, about 150,000 observations"],
        ["Decks and calls", "527 presentations (28 companies yield figures); transcripts downloading for the Nifty 500"],
    ], [0.22, 0.78]),
    ("h2", "Lineage"),
    ("p", "Click a cell in FA, or open a KAS input, a deck-derived metric or a CALL statement: the source filing or page, the extraction method and the public time are one click away. "
          "docs/reports/coverage.md lists identity pass rates (revenue less expenses equals profit before tax, assets equal equity plus liabilities, cash-flow sections sum to the net change) per filing family."),
])

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
sec("10 · Audit and known limits", "What was checked on 16 October 2026, and where the system is weaker than it looks", [
    ("h2", "What was checked"),
    ("table", ["Check", "Result"], [
        ["Automated tests", "205 tests pass: point-in-time canaries, sector rules, parsers, sensitivities, segments, KASAUTI, decks, concalls, API contracts"],
        ["as_of required", "All 30 API routes were enumerated: 29 data routes require as_of (a call without it is refused with 422); only /api/health does not"],
        ["Future refused", "as_of in the future is refused (422) on the macro, geo and transmission endpoints and on the rest by the shared validator"],
        ["Secrets", "No .env, key or token file is tracked by git; .env and data/ are git-ignored"],
        ["Frozen score", "SHA-256 of kasauti_v1.yaml equals FROZEN.json and equals the committed blob; a test enforces it"],
        ["Spot-checks on real data", "Reliance segment shares, TCS and L&T segment tables, ICICI and Axis deck figures against their pages, INFY and HCLTech guidance sentences against their calls"],
    ], [0.24, 0.76]),
    ("h2", "Bugs the audit and the testing found, and fixed"),
    ("ul", ["Bank NPA and CET1 read as 0 (consolidated placeholder zeros): now standalone with zero treated as not reported.",
            "A 5-sigma USD/INR shock produced a −11.7% market response with no warning: far-out shocks are now flagged.",
            "Peers took 20–33 seconds (DuckDB probing for pandas on every query): about 6 seconds, then cached.",
            "Foreign-investor categories were re-cut in 2026 filings and faked a 15-point institutional outflow: swings above 12 points a year are now n/a.",
            "Deck extractor read prose lines, year-level sentences and 12-column histories as quarterly figures (for example a 33% capital ratio for a bank at 15%): stricter row rules and an outlier gate.",
            "A sentence with growth and margin guidance put the growth range on the margin: sentences are now split into clauses.",
            "IT-services guidance (constant-currency revenue, EBIT margin) was first compared with total rupee revenue growth and EBITDA margin, producing false \"kept\" and \"missed\" verdicts: such statements are now not judged, and operating margin is compared with EBIT margin.",
            "Typing KAS in the command bar answered \"later milestone\": fixed with the aliases.",
            "Drawing labels crashed the 3D scenes when a panel moved: replaced by plain DOM labels."]),
    ("h2", "Where it is weaker than it looks"),
    ("table", ["Area", "Limit", "Why it matters"], [
        ["KASAUTI history", "About ten to thirteen scoring dates, one market regime, one definition tried, no dividends", "The report card is suggestive, not proof, and the edge fades by year"],
        ["Pre-2022 financials", "No full statements for 2018–2021; HTML era only income statement; identity pass rate for HTML is 63%", "No honest backtest before 2023; old ratios are lower confidence"],
        ["Sector sensitivities", "160 of 190 cells low confidence; sector labels before official history are back-projected", "Use TX as a map of direction, not a forecast"],
        ["Macro release times", "Some are estimated until a FRED key is added", "A small look-ahead risk for revised series (marked ~)"],
        ["Bank deck metrics", "28 companies; table layouts differ; a misaligned column is possible", "Open the cited page for anything you will act on"],
        ["Concalls", "Rules find only numeric guidance; many companies give none; tone is a word count", "Management credibility is n/a for most; it is not in the KASAUTI score yet"],
        ["Segments", "Labels change between filings; Jio is inside Reliance's Digital Services", "Compare by label carefully"],
        ["Peers", "Same playbook is a rule-based mapping; some companies sit in broad groups such as generic non-financial", "Percentiles are only as meaningful as the peer group"],
        ["Live prices", "Only on NOW, after market, through your broker key", "Rewound views use end-of-day prices"],
    ], [0.2, 0.45, 0.35]),
])

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
sec("11 · What comes next", "The roadmap, in the order that adds most value for least risk", [
    ("h2", "Soon: finishing what is already built"),
    ("ul", ["<b>Transcripts for the whole Nifty 500</b> (download running): read them with build-calls, then check the CALL panel on IT, auto and consumer companies where guidance is common.",
            "<b>KASAUTI live record:</b> run kasauti-score each month. After four to six quarters the live table can say whether the edge is real; it is the only evidence that counts.",
            "<b>KASAUTI v2</b> (a new file, a new report card): add Management Credibility from the Promise Tracker as a pillar once enough statements are judged; revisit weights only with the live record in hand.",
            "<b>More issuers:</b> extend decks to insurers, AMCs and the next 100 financials; add telecom (ARPU), cement (volumes) and capital-goods (order book) decks with their own labels.",
            "<b>FRED key:</b> a free key replaces estimated macro release times with real first-release dates.",
            "<b>Owner review:</b> the four pull requests and the ADR log (all ADRs are still marked proposed)."]),
    ("h2", "Milestone 8: chat, debate, thesis tracker"),
    ("p", "A research bot that answers only through read-only tools and cites every number with its source and date; a bull-versus-bear debate mode; natural-language screening; "
          "a thesis tracker with alerts; a report generator. The bot needs a language model. With no LLM budget, the plan is: build the tool layer, the thesis tracker, alerts and "
          "the report generator first (all rule-based), and add the conversational layer only when you choose a provider, a monthly cap and a hard stop, or run a small local model."),
    ("h2", "Milestone 9: forensics, calendar, screener, polish"),
    ("ul", ["<b>Forensics radar:</b> accruals, cash conversion, related-party and auditor flags, pledge stress; feeds a forensics pillar for KASAUTI v2.",
            "<b>Events calendar</b> for results, record dates, policy meetings and elections, with the Bhavishya scenario fan.",
            "<b>Screener:</b> expression-based, sector-aware (only valid metrics per sector), point-in-time and backtestable.",
            "<b>Performance and deployment:</b> pre-computed snapshots, a production build instead of the dev server, optional move from DuckDB to Postgres."]),
    ("h2", "Data gaps worth closing"),
    ("ul", ["2018–2021 full statements: look for another free source (BSE filings, the companies' own result PDFs) so the KASAUTI history can reach back to a second market regime.",
            "Dividends: add them to returns so the report card is a total-return test.",
            "A total-return Nifty 500 index as a benchmark instead of the equal-weight proxy.",
            "Annual-report extraction for export and import shares, which would turn the qualitative chokepoint links into company-level exposure."]),
    ("note", "A rule that will not change", "TRIKAL will stay a research tool: no ratings, no target prices, no recommendations. Anything that ranks, scores or simulates shows its method, its data "
             "coverage and its limits next to the number."),
])

# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
sec("12 · Appendix", "Glossary, troubleshooting and the first ten minutes", [
    ("h2", "Glossary"),
    ("table", ["Term", "Meaning"], [
        ["As-of", "The date the whole terminal is rewound to. Facts published after it do not exist."],
        ["Known time / valid time", "When a fact became public / the period it describes."],
        ["Lineage", "The chain from a displayed value back to the filing, page and extraction rule."],
        ["Playbook", "A sector's rulebook: which metrics and valuation methods are allowed, forbidden or cautioned."],
        ["Percentile", "Share of peers a company beats on a metric (0 to 1)."],
        ["Rank IC", "Correlation between rank by score and rank by later return. Near 0 is noise."],
        ["Newey-West t-stat", "A t-statistic corrected for overlapping windows, used for the IC."],
        ["Decile", "A tenth of the universe by score; decile 10 is the top."],
        ["In-sample", "Tested on the same history the design was made with: optimistic by nature."],
        ["Live record", "Scores computed after the freeze and judged afterwards: the only unbiased evidence."],
        ["Back-projected", "A label (such as a sector) assumed to hold earlier than it was officially recorded."],
        ["Imputed", "A time or value filled by a stated conservative rule, marked ~ in the terminal."],
    ], [0.24, 0.76]),
    ("h2", "Troubleshooting"),
    ("table", ["Symptom", "Likely cause and fix"], [
        ["Panels show grey bars for a long time", "The data server is busy (peers take several seconds on first load) or a pipeline job holds the write lock. Wait, or check data/logs."],
        ["\"Database busy\"", "A pipeline job is writing. It finishes and releases the lock; do not run two writers."],
        ["Command says it is waiting (\"database busy, retrying in 20 s\")", "The data server or another job holds the database. Run STOP_TRIKAL.bat, or wait for the other job."],
        ["Terminal does not open", "Look at the \"TRIKAL WEB\" and \"TRIKAL API\" windows (minimised) for the error; run STOP_TRIKAL.bat and start again."],
        ["A company shows n/a everywhere", "It may have no filings parsed yet, or it is not in the downloaded set. Check the coverage report."],
        ["Live price missing", "Only on NOW and after the broker login; check .env keys. Outside market hours the last close is shown."],
        ["Drawings disappeared", "They are saved in this browser per stock; a different browser or cleared site data starts empty."],
        ["Layout looks wrong", "Switch MODE once, or reload; PRO and CINEMA rebuild their default layouts."],
    ], [0.34, 0.66]),
    ("h2", "The first ten minutes"),
    ("ul", ["Double-click TRIKAL.bat. In PRO mode type TCS, press Enter. Read the DES line about the playbook.",
            "Drag the Time Spine back to March 2020 and watch every panel rewind; type ASOF NOW to return.",
            "Open KAS for a bank (HDFCBANK) and an IT company (INFY): compare pillars, then read \"left out, and why\".",
            "Open CALL for INFY or HCLTECH: look at the guidance statements and their verdicts.",
            "On GP click Draw, add a support zone and a trend line; reload and see them still there.",
            "Open TX, press the CRUDE +20 chip, click a sector to see its companies; open GEO and click Hormuz."]),
])
