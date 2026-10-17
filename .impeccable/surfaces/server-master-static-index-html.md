---
version: 1
slug: "server-master-static-index-html"
primary_target: "server/master/static/index.html"
related_targets: ["server/master/static/style.css","server/master/static/app.js"]
---

# Dashboard surface brief

Scope: `server/master/static/` (index.html, style.css, app.js) served by `master.web`. Mode: Operate.
Audience: people glancing at a wall TV from across a room; up close, the developer tuning threshold and dwell.
Task: see at a glance whether a camera just warned and which one; up close, the snapshot and every camera's state.
Constraints: no CDN or network fonts at runtime; read-only; device IDs untrusted text; warnings never colour-only; no `http://` in index.html, no innerHTML in app.js (tests).
User asks: warnings own the screen but nothing oversized; every element fits on the screen; avoid sterile, gamer/hacker, busy; "treat it as a normal website that looks modern"; references Apple Home / iOS and Stripe dashboard; follow system light/dark.

## Direction contract

THESIS: A modern consumer-grade dashboard, the category standard executed with Apple Home and Stripe craft: one calm surface where the latest warning is the hero card and every camera is a home-style tile with its live snapshot. It refuses themed costume and terminal/NOC styling.

OWN-WORLD: System-following light and dark. Light: soft grey page, white rounded cards with gentle layered shadows. Dark: black page, graphite cards with hairline borders. Large radii (20px cards, 14px media), pill badges and buttons. One indigo accent for interaction and selection; Apple system colours for state only (red warning, orange someone in view, green clear, grey offline), always paired with an icon and a word. Inter variable, self-hosted, tabular figures.

STORY: The viewer sees whether a camera warned (hero card with snapshot, time, camera, dwell), then scans camera tiles for who is clear or counting, then recent warnings; up close they open snapshots and compare YOLO with device scores below the fold.

FIRST VIEWPORT: Header bar: title with a one-line status summary, live indicator, clock, Pause pill. Main area fits the viewport: left, latest-warning hero card (snapshot on top, time, camera, dwell, score); right column, Cameras tiles then Recent warnings list, each scrolling inside its card. Frames section below the fold.

FORM: Canon (user took the standing exit after the signage build), seed key 8ad5bc60. Signature interaction: camera tiles show the newest snapshot with a dwell bar that fills toward the limit; a new warning settles into the hero card once.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
