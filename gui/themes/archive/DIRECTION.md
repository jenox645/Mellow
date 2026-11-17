# Archive — direction

**One line:** MellowDLP as the menu of a bright school-life mobile game. A sunny sky-blue lobby you
tap around in, not a dashboard you operate.

Classic is a dark sci-fi data terminal with a left sidebar. Tactical is a dense dark operator console
with header tabs. Archive must share nothing with either: it is **light, round, roomy and playful**,
and its navigation is a **dock of big buttons at the bottom of the screen**, the way phone games put
their main menu under the thumb.

## References (and what each one gives)

1. **Blue Archive** (Nexon Games / Yostar), lobby and menus: the white and sky-blue palette, the
   title plate at the top left of every menu (a slanted white plate with a back chevron), the
   resource capsules at the top right, slanted parallelogram buttons, the **yellow call to action**,
   the halo ring as a motif, MomoTalk's chat bubbles. → palette, title plate, resource capsules,
   slanted buttons, yellow primary, halo rings, the assistant's speech bubble.
2. **Princess Connect! Re:Dive**: the bottom dock of big rounded icon tiles with a label under the
   icon; the selected tile rises. → the dock, the raised active tile.
3. **Uma Musume Pretty Derby**: big white rounded cards with a coloured strip on top, chunky friendly
   numerals, a springy press on every button. → stat tiles with a top strip, bouncy presses.
4. **Project SEKAI**: soft diagonal stripes behind everything, pastel tags, pages that slide in.
   → the striped canvas, pastel capsules, the page entrance.
5. **Nintendo Switch HOME / Animal Crossing's NookPhone**: rounded app tiles, soft shadows, a little
   pop when something is chosen. → dock tile shapes and their pop.
6. **The iDOLM@STER Shiny Colors**: tilted ribbon labels on cards. → panel tags as slanted ribbons.
7. **Gacha title screens** (Blue Archive, Princess Connect): the logo over the sky, the character in
   the middle, a blinking **TOUCH TO START**. → the splash.

## The window

- **Lobby header (top, 64 px):** the brand on the left (logo, "Mellow**DLP**" in a heavy rounded
  face, a halo behind it), and on the right **resource capsules** like a game's currency counters:
  download speed (with a tiny sparkline), records, total size, library playlists, then a status
  capsule ("All good!" in green, amber when ffmpeg is missing or a download failed).
- **Title row:** a slanted white **title plate** with a sky chevron, the page name in mixed case
  ("Feed", "Vault") and its Japanese name; on the right the **assistant**: the mascot's face in a
  round frame with a chat bubble that says one friendly line per page; a round **? Guide** button;
  the date in a capsule.
- **The page** sits on a pale sky canvas with faint diagonal stripes and two slowly turning halo
  rings in the corners.
- **Notice tray (bottom):** a soft white bar holding small pastel chips (link state, yt-dlp,
  ffmpeg with GET IT, free disk) on the left, and the update offer and the download folder on the
  right.
- **The dock** floats in the middle of the tray: six big rounded tiles (icon over label, the 1–6
  key in a small badge), a gap between the core sections and the data ones. The current section's
  tile is sky blue, raised, with a yellow bar under it.

## Density

Low. Cards are big and rounded with room inside; fewer things per row; spacing in steps of 8. The
pages' own big headers ("FEED COMMAND") are hidden where the title plate already names the page;
their controls stay.

## Type

**Nunito** (OFL, bundled, one variable woff2 for weights 200–1000) everywhere: 900 for titles and
numbers, 800 for buttons and labels, 600 to read. Rounded terminals make it friendly. Numbers are
tabular. Japanese falls back to the system's rounded or UI gothic. Code (Signal's SQL) stays in
JetBrains Mono.

## Colour

Sky canvas `#EEF5FC`, white cards, navy text `#16264A`. The theme's blue `#1769C9` is the accent
for text and selected states (it keeps 4.5:1 on every surface); a brighter sky gradient fills the
selected dock tile, the progress bar and the header strips. **Yellow `#FFD43B` is the call to
action** (ANALYZE, DOWNLOAD) and only ever a fill with navy text; where Classic's amber is text, a
deep honey `#9A6200` reads instead. Lavender, mint and pink appear only as pastel tints of tags
and sparkles. No glow anywhere.

## Shape

Rounded everything (cards 18 px, fields 14 px, capsules fully round), except the buttons and
ribbon tags, which are slanted parallelograms, the one sharp shape, like Blue Archive's. Soft blue
shadows lift cards off the canvas.

## Motion

Short and bouncy (ease-out-back): pages slide up into place block by block, the title plate slides
in from the left and the assistant's bubble pops; dock tiles rise on hover, squash on press and the
chosen one bobs once; cards lift on hover; the progress bar has moving candy stripes; the halo rings
turn slowly; the splash's TOUCH TO START blinks. Only `transform` and `opacity` animate.
`prefers-reduced-motion: reduce` ends every animation, as Classic does.

## Iconography

Classic's line icons, larger (22 px) in the dock, plus small rounded glyphs in the capsules
(bolt, list, disk, note). Status dots are round and pulse.

## What makes it its own app

A light, round, bouncy game menu with the navigation at the bottom, resource capsules at the top, a
title plate and a talking assistant. Next to Classic (dark, square, sidebar, monospace caps) or
Tactical (dark, dense, header tabs, cut corners), nobody would guess it's the same program.
