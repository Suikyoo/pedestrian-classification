---
version: 1
slug: "server-master-static-index-html"
primary_target: "server/master/static/index.html"
related_targets: ["server/master/static/style.css","server/master/static/app.js"]
---

# Inference dashboard surface brief

Scope: `server/master/static/` (index.html, style.css, app.js) served by `master.web`. Mode: Operate.
Audience: operator watching edge cameras on a monitor in a dark room, reacting to pedestrian warnings; secondary: developer tuning threshold/dwell.
Task: know at a glance which device has a pedestrian, how close each is to warning, and what fired past warnings.
Constraints: no CDN/network fonts; read-only; device IDs untrusted text; warnings never colour-only; dark-first, low glare.

## Direction contract

THESIS: The dashboard is a Swiss station timetable: one strict grid, one sans, tabular figures, and the station clock's red seconds hand as the only moving part. It refuses the category default of KPI tiles over a camera-card wall.

OWN-WORLD: Anthracite ground, departure-board blue band for the header and table heads, warm white type, grey for rest, station red reserved for the seconds hand and warnings. Hairline rules, square corners, no shadows on content. Neo-grotesque system sans with tabular numerals.

STORY: The operator sees every device's state as a timetable row, watches a red hand sweep toward the dwell limit when someone lingers, and reads the warning log to see what fired and when.

FIRST VIEWPORT: Blue header band: title, live station clock, settings line, Pause. Left column: Devices timetable (dial, device, status word, confidence, last frame, last warning), then Warnings table. Right column: Frames grid for the selected device (or all). Primary action: selecting a device row.

FORM: Station Clock Timetable (Swiss railway information design), my grounded candidate 7 of 7, chosen in the safer re-roll; seed key c4569d71. Signature move: per-device dwell dial whose red disc hand sweeps from 0 to the dwell limit; header clock freezes at 12 when the server is unreachable.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
