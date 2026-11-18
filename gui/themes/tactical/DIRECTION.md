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
