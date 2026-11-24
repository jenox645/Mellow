---
name: mellow-design
description: The owner's design standard for MellowDLP's look. Load it before any theme, page layout, animation or visual work in this repo (gui/themes/, gui/pages/, gui/components/, index.html's CSS) and run its checklist before opening the PR. It names what the owner liked, what they rejected as generic "AI design", the drawn-ornament and motion system every theme needs, and the process that proves a theme is its own app.
---

# MellowDLP design standard

The owner looked at the first themes and said they were the most generic AI design they had seen: pill buttons, rounded white cards, a friendly rounded font, blue with a yellow accent, a dock of icons, no animation worth the name, and pages that were still Classic's layout in new colours. This file exists so that doesn't happen again. Read all of it before you design anything.

## Mellow is the face of the project

The mascot (Mellow, the sheep girl with headphones) is MellowDLP's identity. **Never draw a new logo, glyph or wordmark-icon** for the app, the window, the tray, the installer or a splash: the owner rejected a drawn "M" mark for exactly that. Use her art: the mood drawings `assets/*_mellow_vector.svg` (shipped through `build_setup.py`'s `MASCOTS` table and `gui/lib/mascots.js`), `assets/mellow.ico`, and the owner's detailed line art: `assets/sleeping_mellow_vector.svg` (curled up asleep in her headphones; 286 KB) and `assets/peace_mellow_vector.svg` (looking up with a ✌ peace sign and two "!" marks, made of shapes plus hand-drawn strokes that suit a draw-on; 396 KB: a success, a victory, a greeting). Both are `currentColor`, so they take the theme's ink colour; add them to the bundle only where they're shown large (a loading screen, an empty state, an idle Feed, a victory). At small sizes (tray, title bar, favicon) use a simplified render of her existing art, for example the round sheep-face badge on her sleeve and boot, never a new drawing. **Don't make her breathe, bob or float**: the owner finds an idle scale/translate loop on her weird. She may draw on (her own lines, once, when she appears) and then she stays still; no effects laid over her either.

## What the owner likes

- **Functional menus of Japanese games**, not their lobbies: NIKKE's inventory, squad, recruit and shop screens; Blue Archive's menus for brightness and slanted shapes. High-contrast white/grey or black surfaces, black top and bottom bands, sharp geometric panels with cut corners, tall condensed caps titles with a small Japanese subtitle, compact technical labels and stats, thin rules, small status indicators, tab rows where the chosen tab is solid.
- **"White-tech" / monochromatic futurism**: slate white → cool grey → steel blue, one accent used sparingly, flat surfaces, thin borders, precise grids, modular panels, tiny technical details. Futuristic without trying too hard: no neon, no glow, no cyberpunk overload.
- **Film and game HUDs (FUI: fictional user interfaces)**, the reference the owner sent: a white field with a dotted grid and small `+` registration marks, everything drawn in thin black lines; a large ring instrument with degree ticks (0/90/180/240/360), chevrons and a filled grey band; corner brackets and crop marks framing every block; solid black label blocks with big white numerals (`01`, `06`, `08`) and a small caption under them ("LOCKED", "DISTANCE 191M"); diamond and triangle markers; a diagonal hatched band behind a "WARNING" label; a list of numbered grey rows; columns of small figures; a scale ruler with 0/5/10; a sparkline in a framed feed box; a top menu of plain words (MISSION · EDIT · PRESET · VIEW). Study real work in this family: Territory Studio (The Martian, Blade Runner 2049), GMUNK and the Oblivion UI, The Expanse's ship screens, Ghost in the Shell, Destiny's and Death Stranding's menus, NieR:Automata's UI.

What all of that has in common, and what Mellow must have: **drawn, technical, precise, alive.** Lines, ticks, numbers and instruments do the decorating; nothing is decoration for its own sake, and things move.

## Rejected: never ship these

If any of these is in your design, it's not done. Each was in a theme the owner rejected.

1. Pill-shaped buttons, chips or tabs (`border-radius` ≥ half the height). A theme may round things only as a deliberate, named part of its own language, never as the default.
2. White cards with a soft drop shadow and a 10–16 px radius, in a grid, as the main surface.
3. Friendly geometric or rounded sans as the identity font: Nunito, Poppins, Inter, Roboto, Montserrat, M PLUS Rounded, system-ui. Pick a face with character for this theme (OFL, bundled), plus a mono.
4. Blue primary + yellow call to action + green "All good!" pill: the default "friendly app" palette. Start from monochrome; add one accent, then justify any second one.
5. A bottom dock of icon-over-label buttons, or a top row of stat chips (SPEED / RECORDS / TOTAL / LIBRARY as rounded boxes with an icon).
6. Gradients as decoration, gradient-filled placeholder thumbnails, glassmorphism, glows.
7. Stock icon sets dropped in unchanged as the main visual language.
8. Classic's page layout with new colours: the same toolbar row, the same card grid, the same search bar in the same place. **A theme that only restyles is a reskin, and the owner asked for different apps.**
9. "Animation" that is only `transition: all .2s` on hover, or a fade-in.

## Required in every theme

### Its own layouts
Each theme decides where things are on every page, not just the window frame: where the URL goes in on the Feed, what the Vault's main view is (a list? a table? an index? a wall of instruments?), how a download is shown. Never copy Classic's page arrangement and recolour it.

**Prerequisite:** today a theme can only replace the window's slots (`Sidebar`, `TopBar`, `StatusBar`, `LoadingScreen`, `PageFrame` in `gui/lib/slots.js`); every page's inside is still Classic's component, which owns its own logic. Per-theme page views (a page's logic in a shared hook, each theme registering its own view) are issue #90, for the Feed and the Vault first. Until that is merged, a page view a theme writes is never rendered: build #90 first, or limit a theme to the slots and say so in the PR.

### A drawn ornament system, in inline SVG
Make a small kit in `gui/themes/<id>/ornaments.jsx`, at least eight pieces, used on every screen: for example crop marks / corner brackets, a crosshair or `+` registration mark, a ring gauge with ticks, a tick ruler / scale, a bracket frame for a block, a scan line, a hatched warning band, node markers (diamond, triangle, circle-dot), a numbered label block. Draw them with `stroke` in `currentColor` or theme tokens (`var(--…)`), 1–1.5 px lines, crisp at 1×. They take props (size, value, label) so they can show real data.

### Live data as instruments
Mellow has real numbers: download speed, progress, ETA, items done/left, disk free, records, library size, queue length, sync state. Show them as instruments (a ring that fills and ticks, a ruler with a moving marker, a segmented bar, a sparkline in a framed box, a counter that rolls), not as text in a chip.

### Motion that means something
- On page enter: SVG lines draw on (`stroke-dasharray` / `stroke-dashoffset`), brackets snap to their block, labels type or slide in, staggered 20–40 ms apart, 200–500 ms total.
- While downloading: the ring gauge sweeps with the progress, a scan line passes over the active item, numerals roll, the speed sparkline scrolls.
- On hover / focus: brackets close in, a marker slides to the item, a rule extends; press = a short snap.
- Toasts, modals, the victory overlay: their own entrances built from the same kit.
- Animate only `transform`, `opacity` and `stroke-dashoffset`; durations from the theme's `--dur-*` tokens; `prefers-reduced-motion: reduce` turns all of it off (keep the global rule winning).
- **The victory overlay is part of the theme too:** each theme makes its own (Classic's is the default), and it must run at the display's frame rate: no animating `filter`, `box-shadow`, `width`/`height` or big blurred layers; measure it in DevTools' performance panel.

### Typography
A display face with character for this theme + a mono for figures and micro-labels (OFL, woff2 Latin subset in `gui/fonts/` with the licence). Tracked caps micro-labels around 9–10 px (never under 8.5 px), tabular numerals, Japanese subtitles small and quiet. Size contrast should be large: a title or a numeral can be big.

### Colour
Monochrome base (light or dark), one accent on under ~5 % of the surface (live state, the main action, the selection), red only for danger. Every text colour keeps 4.5:1 on its background (`tests/test_themes.py`).

## Process (put the evidence in the PR)

Start every visual PR with the model and effort it was made with (for example "Opus 5.5, max effort"): the owner wants to know.

1. **References.** In `gui/themes/<id>/DIRECTION.md`, list 6–10 real references (name + what you take from each). At least half from game UI or film HUDs; none from SaaS dashboards or UI kits.
2. **Mockup first.** Build the Feed and the Vault as one static HTML file (`gui/themes/<id>/mockup.html`, using the theme's fonts and ornament kit), screenshot it at 1440×900, and put the screenshot in the PR before building the real screens.
3. **Slop check.** Go through "Rejected" item by item and write, for each, "absent" or what you changed. Then answer for each screen: "Would someone who knows Classic guess this is the same app?" The answer must be no, with the reason.
4. **Build** every screen with the theme's own views and ornaments.
5. **Critique.** Apply `.claude/skills/impeccable/reference/critique.md` and `audit.md` (and `animate.md` for the motion) to the built screens and fix what they find. (Only impeccable's text guides are in this repo; skip any step that needs its `scripts/`.) `.claude/skills/frontend-design/SKILL.md` is the short version of the same discipline.
6. **Show the motion and every screen.** `scripts/screenshots.py` only shoots Classic (no theme option, Classic-only selectors, no Config or Signal), so capture a theme with your own Playwright script on `tests/browser/conftest.py`'s fixtures: sign in as those tests do, `POST /api/config` with `{"ui_theme": "<id>"}` (and set localStorage `mellow-theme` so the first paint matches), reload, then visit every page: Feed (empty, analyzed video, playlist, downloading), Queue, Vault (folder cards, an open folder in SM/MD/LG and ☰ LIST, the sync dialog), Analytics, Signal API, Config, the GUIDE, a toast, a modal, the splash, the victory overlay. Record the Feed during a download and a Vault page entering (Playwright `record_video_dir`, a few seconds each) or attach a strip of frames. Adding a `--theme` option to `scripts/screenshots.py` is welcome in its own commit. The PR shows the owner both.

Done means the PR has: DIRECTION.md, the mockup screenshot, the slop check, the critique notes, screenshots of every screen and the motion recordings. A theme PR without them goes back with `needs-fix`.
