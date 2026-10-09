# TRIKAL — UI Specification (M0 draft)

Design language **Obsidian & Gold**. Dense, keyboard-first, honest about time and missing data. No galaxy or node-cloud visuals anywhere.

---

## 1. Shell anatomy

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ ◆ TRIKAL   [ / command … ]                 AS OF 14-MAR-2020 ◂gold badge▸  ● data 13-MAR 21:04   ≡ │  header 36px
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌─ Panel: TCS · FA ──────── [A]⛓ ─┐ ┌─ Panel: TCS · Cash River ─ [A]⛓ ┐ ┌─ Peers ── [A]⛓ ┐ │
│ │                                 │ │                                │ │                │ │
│ │       (dockview tiling area: any number of panels, tabs, splits,  popouts)              │ │
│ └─────────────────────────────────┘ └────────────────────────────────┘ └────────────────┘ │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ ◂ BHOOT ─────────·──·─────|·──·──·─────·───────── NOW ──── ░░ BHAVISHYA fan ░░ ▸  1Y 5Y MAX  │  Time Spine 44px (expands to 140px on hover)
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ DEMO DATA (only in DEMO_MODE)  · status: ingest ok · 3 alerts · ⌘K                          │  status bar 22px
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Header:** logo, command bar trigger, AS-OF badge (gold, only when `as_of ≠ NOW`, click = return to NOW), **data watermark** (latest `known_at` among the data on screen), desk/layout menu.
- **Status bar:** ingest health, alerts, mode indicators (`Dense`, colour mode, `DEMO`), disclaimer link.
- **Disclaimer:** persistent link in the status bar and on every exported report: "Research tool. Not investment advice. No ratings or target prices."

## 2. Panel system (dockview)

- Every panel = `{ type, params, linkGroup, asOfMode }`.
  - `type`: function code (`FA`, `DES`, `DCF`, …).
  - `linkGroup`: `A`–`F` or `none`. Panels sharing a group share the active ticker; changing it in one updates all (shown as a coloured chain chip `[A]⛓`).
  - `asOfMode`: `follow` (default, follows the global Time Spine) or `pinned` (frozen at a date, for side-by-side "then vs now" comparisons; shows its own small gold badge).
- Tabs, splits, maximise (`Ctrl+Shift+Enter`), popout to a separate window (multi-monitor).
- **Layouts** are serialised JSON, saved per desk (`Company`, `Sector`, `Macro`, …) and user-named. Ships with a default layout per desk.
- Panel header: title, link chip, as-of mode, `⋯` menu (export CSV/PNG, show lineage mode, duplicate, close).

## 3. Command grammar

Opened by `/` or `Ctrl+K` (cmdk). Fuzzy matches tickers (NSE symbol, BSE code, company name, ISIN, **including delisted and old names**, which are marked `delisted 2019` / `formerly X`).

```ebnf
command     = time_cmd | shock_cmd | global_fn | entity_fn | sector_fn | ref_fn ;
entity_fn   = entity , [ ws , fn_code ] , { ws , arg } ;         (* "TCS FA", "TCS" → DES *)
entity      = nse_symbol | bse_code | isin | quoted_name ;
fn_code     = "DES" | "FA" | "DCF" | "RV" | "CC" | "KAS" | "OWN" | "FRX" | "GP" (*price chart*)
            | "CR" (*cash river*) | "DUP" (*DuPont*) | "WC" (*what changed*) | "EVT" | "NOTE" | "RPT" ;
sector_fn   = "SEC" , ws , sector_id ;                          (* SEC CEMENT *)
global_fn   = "MACRO" | "CAL" | "SCRN" | "KAS" | "GEO" , [ ws , geo_id ] | "POL" , [ ws , policy_id ]
            | "TX" (*transmission engine*) | "HELP" | "LAYOUT" , ws , name ;
shock_cmd   = "SHOCK" , ws , shock , { ws , "&" , ws , shock } ;  (* SHOCK CRUDE +20 & INR 90 *)
shock       = driver , ws , ( delta_pct | delta_bp | level ) ;
delta_pct   = ("+"|"-") , number , ["%"] ;   delta_bp = ("+"|"-") , number , "bp" ;   level = number ;
time_cmd    = "ASOF" , ws , ( date | "NOW" | relative ) ;       (* ASOF 2020-03-14 | ASOF -5Y | ASOF NOW *)
ref_fn      = "?" , fn_code ;                                   (* help for a function *)
```

- Each fn code has a registry entry: label, description, required context, default panel size, keyboard alias.
- Unknown input → ranked suggestions, never a silent no-op.
- History (`↑`) and pinned commands.

## 4. Keyboard map (core)

| Keys | Action |
|---|---|
| `/` , `Ctrl+K` | Command bar |
| `Ctrl+1…9` | Focus panel n |
| `Ctrl+Alt+←/→/↑/↓` | Move focus between panels |
| `Ctrl+Shift+Enter` | Maximise / restore panel |
| `Ctrl+W` | Close panel |
| `Alt+A…F` | Set link group of focused panel |
| `[` / `]` | Time Spine: step back / forward one event (results, concall, …) |
| `Shift+[` / `Shift+]` | Step one quarter |
| `Ctrl+[` / `Ctrl+]` | Step one year |
| `Home` (in spine focus) / `Esc Esc` | Return to NOW |
| `L` | Toggle lineage mode (every number shows its source chip) |
| `D` | Toggle Dense / Comfort |
| `?` | Contextual shortcuts |

Every action in menus is also in the command palette. Focus rings are gold and 2 px; never removed.

## 5. Time Spine (Kaal-Rekha)

- **Scale:** log-like. The last 2 years are wide, older years compress; zoom presets `1Y 5Y 10Y MAX`; wheel = zoom, drag = pan.
- **Playhead drag:** the global `as_of` updates *on release* (with live preview of the date while dragging) to avoid refetch storms. TanStack Query keys include `as_of`, and recently visited `as_of` values stay cached.
- **Markers** (icons sized by importance, coloured by type): results, concalls, rating actions, corporate actions, index changes, policy (RBI/Budget), macro releases, geopolitical events, user notes. Hover = summary card; click = set `as_of` to just after the event's `known_at` and open the related panel.
- **NOW** is a gold tick with a subtle pulse (none under reduced motion).
- **Bhavishya (right of NOW):** scheduled events (from the calendar) + a **scenario fan** for the focused company: bear/base/bull paths from the Valuation Lab + guidance milestones from the Promise Tracker. Visually distinct (hatched, lower opacity) so future ≠ data. You cannot set `as_of` in the future; dragging right of NOW shows scenarios only.
- **Rewound state:** header badge `AS OF DD-MMM-YYYY`; a thin gold frame line around the workspace; panels whose data *ends* before as_of (e.g. company not yet listed) show "Not listed as of …" rather than empty.
- **Imputed timestamps** (ARCHITECTURE §2) show a small `≈` mark wherever they affect what is displayed.

## 6. Value states (honest data)

Every number cell renders one of:

| State | Render | Tooltip |
|---|---|---|
| `Value` | right-aligned tabular mono, unit suffix | lineage: source doc, filing time, formula, inputs |
| `Undefined` | `n.m.` (not meaningful), muted | reason, e.g. "EPS ≤ 0 → P/E undefined" |
| `NotAvailable` | `n/a`, muted | which input is missing, and from which source |
| `Forbidden` | `—` with a lock glyph | the playbook rule id + plain-language reason |
| `LowConfidence` | value + amber dot | extraction confidence / reconstructed classification |
| `Restated` | value + `R` superscript | prior value(s) and their known_at |

Never zero-fill, never blank-without-reason.

## 7. Screens / panels (by desk; milestone in brackets)

**Company desk** [M3]: `DES` overview · `GP` price (Lightweight Charts, adjusted/unadjusted toggle, corporate-action markers) · `FA` financial statements grid (Q/FY, standalone/consolidated, restated markers) · `DUP` DuPont driver tree (interactive) · `CR` Cash River · `RV` peers grid · `WC` What Changed · `OWN` ownership [M2 data] · `EVT` events.
**Valuation Lab** [M4]: `DCF` (FCFF/FCFE), reverse DCF, multiples bands, SOTP, scenarios + sensitivity heatmaps.
**Sector desk** [M4–M5]: playbook metrics grid, valuation bands, heatmaps, structure (HHI, capacity), breadth/rotation.
**Macro / Policy / Geo** [M5]: series workbench, cycle clock, policy → company map, `TX` Transmission Engine, `GEO` Exposure Theatre.
**Concall** [M6]: `CC` promise tracker table, credibility timeline, tone drift with quoted examples.
**KASAUTI** [M7–M8]: `KAS` Touchstone, pillar drill-down, Report Card, chat, debate.
**Notebook/Thesis, Reports** [M8]; **Forensics `FRX`, Calendar `CAL`, Screener `SCRN`** [M9].

## 8. Signature visuals: build notes

| Visual | Tech | 2D twin (always available) | Notes |
|---|---|---|---|
| Time Spine | SVG + CSS 3D transform for depth | itself | Must stay ≤ 2 ms per frame. |
| Cash River | ECharts Sankey, styled 2.5D (gradient banks, flow particles off by default) | plain Sankey + waterfall table | Scrubbing years animates node widths (300 ms ease). Shows `n/a` streams explicitly (grey hatched) when a segment isn't disclosed. |
| KASAUTI Touchstone | Canvas/WebGL shader: gold streak on black stone, length/brightness = score; radial pillar ring in SVG | pillar bar list | Streak redraw on score change only. Confidence shown as streak grain/fade. |
| Transmission Engine | R3F: three glass planes (MeshPhysicalMaterial transmission), instanced nodes, line edges with width = |sensitivity|, pulse = shader uniform | layered matrix (driver × sector × company) + impact table | The impact table is the source of truth; 3D is the explanation. Edge tooltips show method + confidence. |
| Exposure Theatre | R3F globe (custom low-poly, dark), corridors as great-circle arcs, chokepoints as rings | ranked exposure table + 2D map | No generic world map styling; India-centred default camera. |

GPU tier < 2 or `prefers-reduced-motion` → 2D twin by default (user can override).

## 9. Design tokens (v0)

```css
:root {
  /* surfaces: obsidian → graphite */
  --bg-0: #07080A;   /* app background */
  --bg-1: #0D0F12;   /* panel */
  --bg-2: #14171C;   /* raised / header */
  --bg-3: #1C2027;   /* hover / selected row */
  --line: #262B33;   /* hairlines, grid */
  --line-strong: #3A414C;

  /* text */
  --fg-0: #E8E6E1;   /* primary (warm white, not pure) */
  --fg-1: #A7A9AE;   /* secondary */
  --fg-2: #6B7079;   /* muted, n/a, n.m. */

  /* brand: touchstone gold */
  --gold-0: #F2D27A; /* streak highlight */
  --gold-1: #D4AF37; /* accent, focus, AS-OF badge */
  --gold-2: #8C6F1E; /* gold on dark borders */

  /* data: default palette */
  --pos: #2EC4B6;    /* teal */
  --neg: #F0577A;    /* rose */
  --neu: #8B93A1;
  --warn: #E8A33D;   /* amber: low confidence, caution */
  /* classic mode */
  --pos-classic: #26A65B; --neg-classic: #E5484D;
  /* colour-blind-safe mode (blue/orange) */
  --pos-cb: #3D8BFD; --neg-cb: #F28C28;

  /* type */
  --font-ui: "Inter Tight", "Inter", system-ui, sans-serif;            /* sharp grotesk */
  --font-num: "JetBrains Mono", "IBM Plex Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums;

  /* density */
  --row-h-dense: 20px; --row-h-comfort: 28px;
  --fs-dense: 11.5px;  --fs-comfort: 13px;
  --radius: 3px;       /* terminals are sharp */
  --dur-fast: 120ms; --dur-med: 240ms; --ease: cubic-bezier(.2,.0,.0,1);
}
```

Contrast: all text tokens ≥ 4.5:1 on `--bg-1` (verified in M3 with an automated check); data colours ≥ 3:1 against `--bg-1`, never the *only* carrier of meaning (sign glyph `▲▼`/`+−` always present).

Numbers: right-aligned, tabular mono, Indian grouping optional (`1,23,456` vs `123,456`, setting), units always visible (`₹ cr`, `x`, `%`, `bp`), negative as `−1.2` with the true minus sign, coloured by sign only where the sign is meaningful (growth, returns), not for e.g. negative tax.

## 10. Performance budgets

- Time to interactive (shell): < 2.0 s on a mid-range laptop, cached.
- `as_of` change → all visible 2D panels re-rendered: p95 < 600 ms (local API).
- Grids: 5,000 rows × 40 cols at 60 fps scroll (virtualised).
- 3D scenes: 60 fps target, 30 fps floor, else auto-fallback to the 2D twin.
- JS bundle: shell < 300 KB gz; 3D code split and lazy-loaded.

## 11. Visual regression

Playwright screenshots of key screens in both colour modes, Dense/Comfort, and one rewound `as_of`, seeded from a fixed fixture DB (fixtures are clearly marked test data and never reach the real app).
