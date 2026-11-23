# Tactical — design direction

An operator's console for a download tool: dark, flat, dense, exact. Nothing glows. One colour is hot.

The references below are described from knowledge of them. Web search was available while this was
written but returned little of use on game interfaces; it only confirmed the ISA-101 principles.

## References, and what is taken from each

| Reference | Taken |
|---|---|
| **NIKKE** (Shift Up): lobby, squad and outpost menus | Parallelogram tabs and slanted plates, a light plate with dark text for the chosen item, label-tape captions, the operator's portrait in a cut frame |
| **Arknights** (Hypergryph): operator and base screens | Graphite panels on near-black, a small caption above a large title, hazard striping for the one ceremonial moment (playlist complete), fine ruler ticks as decoration that also measures |
| **Armored Core VI**: garage and assembly | Tables over cards, monospace figures in aligned columns, segmented gauges, a header band on every block, no rounded corner anywhere |
| **Glass cockpits** (Garmin G1000, Airbus ECAM) | The instrument rail: a vertical speed tape with tick marks, stacked readouts with a tiny caption and a big figure; colour by meaning (green normal, amber caution, red warning) and nothing else coloured |
| **ISA-101 high-performance HMI** | Grey is the resting state; saturated colour is reserved for what needs the eye. Hence bone white for *selected* and orange-red only for *live* and *go* |
| **Annunciator panels** (industrial control rooms) | The status bar as a row of lamp cells, caption + value; lamps blink in steps, they never fade |
| **Ops dashboards** (Grafana, Datadog dark) | Hairline grids, compact stat tiles with one accent rule, step-line strip charts |
| **BIOS / POST screens** | The splash: numbered lines that report what is really happening (interface, local server, session) and a chasing segment bar |

## Layout and navigation

No sidebar. The window is three bands and a rail:

1. **Header strip** (52 px): brand plate, the six sections as numbered cut tabs (`01 FEED` … `06 CONFIG`,
   the keys 1–6), system state on the right. The chosen tab is a raised bone plate; the others sit lower.
2. **Command bar** (30 px): section number, path, a tick ruler, the key hints, GUIDE, date, clock.
3. **Page**, with the **instrument rail** (92 px) on its right: speed gauge, speed history, records,
   database size, library count, then a scale to the bottom. (The mascot as the operator on duty
   was here, but 92 px left it a 71 px box nobody could read; Mellow is on the splash.)
4. **Annunciator row** (24 px): link, yt-dlp, FFmpeg, disk, the update offer, a strip chart, the folder.

Pages keep their structure; they gain the 210 px the sidebar took and lose 16 px of padding per side.

## Density

Tight. Panel headers are 32 px bands, grids have 10 px gutters, queue rows are 48 px with 64×36
thumbnails, settings rows 8 px apart, table cells 5 px. A file list is a ruled table, not a stack of boxes.

## Type

- **Chakra Petch** 600/700, uppercase, tracked: titles, tabs, buttons, panel headers. Its letterforms have
  cut corners, which is the theme's shape in type.
- **Barlow** 400–600: sentences, file and video titles (mixed case stays mixed case).
- **JetBrains Mono** 400/500: every number, path, state, caption and key. Captions go down to 8.5 px.

## Colour

- Graphite ramp `#0D0E10` → `#141619` → `#1B1E22` → `#24282D`; hairlines `#272B30` / `#3A4047`.
- Text is warm bone, `#E9E7E1` down to `#96948E` (≥ 4.5:1 on every surface).
- **Bone white = selected** (current tab, chosen pill, checked box, selected file).
- **Orange-red `#FF5A1F` = live or go**: the running download and its gauge, the primary button, the GUIDE
  spotlight, the lit speed segments. Nothing decorative uses it.
- Sand `#D2C7A8` is the quiet second accent (audio, sync, the data pages); steel blue the third.
- Green / amber / pink-red only as status lamps and status text.

## Shape

Square everywhere, with **one corner cut** at 45°: top-right on panels, tiles, covers and portraits,
bottom-right on buttons. Tabs and plates are parallelograms. Borders are 1 px; emphasis is a 3 px bar,
never a thicker frame, never a shadow (only floating menus and dialogs cast one, hard and dark).
A 32 px grid and 3 px scan lines lie under everything at under 2 % opacity.

## Motion

Fast and mechanical: 70–320 ms, sharp ease-out, transform and opacity only.

- Start: header drops, rail slides in, page blocks lock in one after the other.
- Section change: an accent line sweeps under the command bar, the section number flips, the title rule draws.
- Live: the header's edge mark runs, gauge segments switch, lamps and the pipeline's current step blink
  in steps, a light band crosses the download block.
- Touch: tabs rise, a sheen crosses a button and it presses 1 px, cards lift and a rule draws over
  their plate, toggles snap, a chosen pill flashes once.
- Dialogs and toasts snap in; the victory screen stamps its band between two marching hazard rails.
- `prefers-reduced-motion` stops all of it.

## Iconography

The app's existing 1.5 px line icons, small (14 px) and always next to a word. Lamps and markers are
squares, never dots. Numbers (`01`–`06`, `SEC 03`) do the work icons would do elsewhere.

## What makes it its own app

Tabs across the top instead of a sidebar; instruments on the right; two-colour logic (bone = chosen,
orange = live) instead of one neon everywhere; cut corners and parallelograms instead of glow and HUD
brackets; segmented gauges instead of smooth bars; a boot log instead of a greeting.

---

# v2 — its own pages (#98)

The owner's verdict on v1: the frame was new, but every page inside was Classic's layout in graphite, so
"it still feels like the OG Mellow". v2 keeps the console (header tabs, rail, graphite + one orange-red,
cut corners, no glow) and gives the Feed, the Vault and the status bar their own layouts, drawn with an
SVG instrument kit. The mockup is `mockup.html` (static, open it from `static/themes/tactical/` after a
build); the views are `feed.jsx`, `vault.jsx` and `chrome.jsx`'s `TacticalStatusBar`; the kit is
`ornaments.jsx`.

## References for v2 (FUI and game menus first)

| Reference | Taken |
|---|---|
| **Territory Studio, The Martian** (mission control screens) | The transfer column: one big ring instrument with degree ticks and labelled stops, readouts in black label blocks under it, a framed trace beside the numbers |
| **GMUNK, Oblivion** (Bubbleship and tower UI) | Thin-line instruments that *are* the data: the ring's chevron head riding the arc, a dotted hub that turns while live, crop marks that snap onto each block |
| **The Expanse** (Rocinante ops consoles) | Numbered blocks (A–D) with a caption, a rule that runs to the edge, plain-word menus instead of button rows |
| **Death Stranding** (cargo and order menus) | The Vault as an index of numbered bays with a capacity bar each, and an order sheet (the bay's record) beside it rather than a card wall |
| **NieR:Automata** (system menu) | Bone plate = chosen (the open bay, the chosen stop), everything else grey; a hatched band only for the one warning that matters (a failed sync) |
| **NIKKE** (inventory / squad screens) | Big tracked caps titles with a small Japanese subtitle, the outlined index numeral, cut-corner label blocks |
| **Glass cockpit tapes** (Airbus PFD speed tape) | The quality and bitrate rulers: a tick scale with a triangle marker that slides to the pick; the status bar's tick tape that carries the live speed trace |
| **Armored Core VI** (assembly screen) | The loadout always on the table (mode plates, rulers, lamp switches), not hidden behind an OPTIONS button |

## Layouts

- **Feed = INTAKE.** A: the target, one command line (`>` prompt, ANALYZE / RESCAN at its end, PASTE and
  IMPORT as words above it, DEST under it). B: the loadout, always open: VID / AUD plates, the quality
  ruler (bitrate ruler for audio), container / format as a segmented selector, the extras as lamp
  switches, presets and the CHAPTERS / EXTENDED drawers. C: the dossier of the analyzed target (framed
  cover with a crosshair, the editable file name, a four-cell fact grid, DOWNLOAD as a tall plate).
  D, on the right: the transfer instrument (state lamp, ring gauge, SPEED / ETA / DONE blocks, speed
  trace, the item now, pipeline nodes, PAUSE / CANCEL, the destination disk as a ruler with this
  download's share). Idle, the ring holds Mellow asleep (her own line art) and says STANDING BY. The
  roster (pending / done) appears under the dossier only when there is one.
- **Vault = STORAGE.** A: the index, always on the left: total size, the vault's allocation as one
  segmented strip (the open bay lit), the word menu (REFRESH · SYNC ALL · DUPES · WATCH), then each
  folder as a numbered bay (label block, name, count · size, a 12-segment bar against the biggest bay,
  a sync lamp: SYNCED 2H / LINKED / FAILED / WATCHED / LOCAL / OVER BUDGET). B, on the right: the
  allocation table until a bay is opened; then the bay's record (◂ INDEX + path, the bay number and the
  name large, MEDIA / SIZE / LAST SYNC blocks, the sync report, SYNC NOW and a word menu, the
  LIST / SM / MD / LG selector) above its files: a ruled, numbered table or covers with crop marks.
- **Status bar = telemetry strip.** The link lamp; a tick tape that carries the live speed trace with
  the speed at its end (STANDBY when idle); one health lamp (SYSTEMS: yt-dlp's version and FFmpeg's path
  on hover) that turns into its action when needed (GET FFMPEG, its progress, a newer MellowDLP); the
  disk as a 10-segment log gauge; the folder, short (`…/Downloads/MellowDLP`, the full path on hover).

## The kit (`ornaments.jsx`)

Brackets (crop marks, snap in, close in on hover) · Reg (`+` mark) · Node (diamond, triangle, dot) ·
LabelBlock (big numeral + caption, rolls when its value changes) · Hatch (warning band) · Ruler (tick
scale with a sliding marker, the stops are the buttons) · RingGauge (270° dial, 51 ticks drawn in one
after another, value arc, chevron head) · SegBar · Spark (framed trace) · Caption (index, title, Japanese
subtitle, a rule that draws on) · ScanLine. 1 px strokes in `currentColor`, colours from tokens.

## Motion thesis

- **Focal moment:** the transfer ring. Its ticks draw in when the page opens; while downloading the arc
  sweeps with the progress (`stroke-dashoffset`), the chevron head rides it (`rotate`), the hub turns,
  the percentage and the readouts roll on each change, a scan band crosses the item now and the trace
  scrolls. Paused: the arc turns amber and everything holds.
- **Continuity:** the quality marker slides to the chosen stop; the opened bay's accent bar grows and
  its share in the allocation strip lights; bays and file rows come in as a list (25 / 14 ms apart,
  capped at 30 items).
- **Feedback:** plates, stops and lamp switches snap 1 px when chosen; word-menu entries draw an
  underline on hover; crop marks close in on hover / focus.
- Only `transform`, `opacity` and `stroke-dashoffset` move. `prefers-reduced-motion` ends every
  animation at once (the theme's own rule) and removes the scan band; state changes (the arc's value,
  the lit stop) stay.

## Slop check (mellow-design "Rejected")

1. Pill shapes — absent: every control is square or cut-corner.
2. White cards with soft shadows — absent: graphite blocks, 1 px hairlines, no shadow except dialogs.
3. Friendly rounded sans — absent: Chakra Petch (cut corners) + Barlow + JetBrains Mono, as v1.
4. Blue + yellow + green pill — absent: graphite and bone, orange-red only for live / go; green only as
   a 6 px sync lamp.
5. Bottom dock / stat-chip row — removed: v1's Feed had Classic's four stat tiles; they are gone (the
   rail already shows records, database and library). No dock.
6. Gradients / glass / glow — absent (the only gradient is the scan band, a moving light, not a fill).
7. Stock icons as the language — absent: the kit draws the ornaments; icons only in the header tabs (v1).
8. Classic's layout recoloured — replaced: see Layouts. Classic's Feed is URL panel → hidden options →
   info card → progress panel → queue + stat tiles; Intake is a two-column console with an always-open
   loadout and a transfer instrument. Classic's Vault is a toolbar over a card grid, then a second page
   of cards; Storage is a master-detail index that never leaves the screen.
9. Hover-only "animation" — absent: see the motion thesis.

*Would someone who knows Classic guess it's the same app?* **Feed:** no — there is no URL panel with a
hidden options drawer, no progress bar card, no stat tiles; a command line, rulers and a ring instrument
take their place. **Vault:** no — no folder cards and no breadcrumb page; the folders are an index of
numbered bays that stays beside the open bay's record. **Status bar:** no — five equal boxed facts became
a lamp, a live tape, one health indicator, a gauge and a short path.

## Critique notes (impeccable critique / audit / animate) and what changed

- *Focus:* the command line's own focus ring doubled with the field's; the line now turns orange as a
  whole when focused, the field draws none.
- *Narrow windows (1100 × 780):* the dossier stacks its actions under the cover, the transfer column and
  the index get slimmer, the bay's segment bar and the table's date column drop out (`max-width:1280px`).
- *States:* idle (Mellow asleep, STANDBY, controls disabled), paused (amber arc, RESUME), processing,
  no estimate, won't fit (the disk ruler and the fact cell turn red), empty vault, empty folder, a folder
  still loading — all drawn.
- *A11y:* rulers and selectors are radio groups, the extras are switches, the bay tools have labels;
  every text colour is a token that keeps 4.5:1 (`tests/test_themes.py`).
- *Performance:* no canvas on the new pages; the trace is one polyline; long lists cap their stagger.
- *Not done (out of scope here):* the Queue, Analytics, Signal and Config pages still use Classic's views
  in Tactical's colours; they can take their own views now that #97 split them (a second PR, as #98 allows).
