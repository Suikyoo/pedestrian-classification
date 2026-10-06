---
name: Pedestrian Warnings Dashboard
description: A dark Swiss timetable for a night-shift operator, with a departure-board blue band, one neo-grotesque, and red reserved for the seconds hand and warnings.
colors:
  ground: "#121417"
  panel: "#1a1d21"
  panel-raised: "#22262b"
  line: "#2c3036"
  text: "#ecece8"
  muted: "#9aa0a7"
  rest: "#858b92"
  board-blue: "#1d2858"
  board-line: "#2c3a78"
  board-text: "#f2f2ee"
  board-muted: "#c3c8de"
  signal-red: "#eb0000"
  warning-text: "#ff6b5e"
  warning-wash: "#3a1514"
typography:
  clock-time:
    fontFamily: "Arimo, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.01em"
  pane-title:
    fontFamily: "Arimo, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.45
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Arimo, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "tnum"
  button:
    fontFamily: "Arimo, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 700
  table-head:
    fontFamily: "Arimo, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 700
rounded:
  sharp: "2px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
components:
  band:
    backgroundColor: "{colors.board-blue}"
    textColor: "{colors.board-text}"
    padding: "12px 24px"
  table-head:
    backgroundColor: "{colors.board-blue}"
    textColor: "{colors.board-text}"
    typography: "{typography.table-head}"
    padding: "6px 8px"
  button:
    backgroundColor: "transparent"
    textColor: "{colors.board-text}"
    typography: "{typography.button}"
    rounded: "{rounded.sharp}"
    padding: "6px 14px"
  button-hover:
    backgroundColor: "{colors.board-line}"
  button-pressed:
    backgroundColor: "{colors.board-text}"
    textColor: "{colors.board-blue}"
  button-quiet:
    textColor: "{colors.text}"
    rounded: "{rounded.sharp}"
    padding: "4px 10px"
  row-selected:
    backgroundColor: "{colors.board-blue}"
    textColor: "{colors.board-text}"
  row-warning:
    backgroundColor: "{colors.warning-wash}"
    textColor: "{colors.text}"
  banner:
    backgroundColor: "{colors.warning-wash}"
    padding: "8px 24px"
  frame-stamp:
    backgroundColor: "{colors.signal-red}"
    textColor: "#ffffff"
    padding: "2px 6px 2px 4px"
---

# Design System: Pedestrian Warnings Dashboard

## Overview

**Creative North Star: "The Station Clock Timetable"**

A departure board seen from a dark control room. The page is a Swiss timetable: flat ruled tables on a near-black ground, one neo-grotesque (Arimo, self-hosted) at a handful of sizes, and a single saturated blue (the departure-board band) that marks every header. Information is arranged like a station concourse: a clock that tells you the system is alive, rows that tell you what each device is doing, and strips of frames underneath.

Red is the only alarm color and is scarce by construction: it appears on the station clock's seconds hand, the dwell-limit tick, and warning states. A calm screen has almost no red on it, so any red is news. Everything else is ground, grey, or board blue.

**Key Characteristics:**
- Dark-first, flat, ruled; depth comes from tone and rules, never shadow.
- One typeface, tabular numerals everywhere, weight (400 vs 700) as the main hierarchy lever.
- Board blue for structure (header band, table heads, strip heads, selected row); red for alarm only.
- Instrument metaphors do the state-telling: a station clock in the header, a dwell dial per device.
- Warning is never color alone: it also carries a triangle icon, the word "Warning", and a filled dial.

## Colors

A restrained dark palette: five greys, one board blue family, one red family.

### Primary
- **Departure-Board Blue** (`{colors.board-blue}`): header band, every table head, strip heads, selected device row. Its companion **Board Rule** (`{colors.board-line}`) is hover fill, band bottom border, text selection.
- **Board Paper** (`{colors.board-text}`) and **Board Mist** (`{colors.board-muted}`): text on blue; paper is also the focus ring and the clock face.

### Secondary
- **Signal Red** (`{colors.signal-red}`): seconds hand, dwell-limit tick, filled warning dial, warning frame outline, warning stamp, banner rule.
- **Warning Coral** (`{colors.warning-text}`): the red used for text on dark (the "Warning" word, the caret) because pure red is too dim as type.
- **Warning Wash** (`{colors.warning-wash}`): row and banner fill for warnings.

### Neutral
- **Night Ground** (`{colors.ground}`): page. **Panel** (`{colors.panel}`): hover rows, frame placeholder, viewer. **Raised Panel** (`{colors.panel-raised}`): dial face, quiet-button hover.
- **Hairline** (`{colors.line}`): row rules, confidence bar track, quiet-button border.
- **Text** (`{colors.text}`), **Muted** (`{colors.muted}`), **Rest** (`{colors.rest}`, idle dial hand and "No signal").

### Named Rules
**The Red Is News Rule.** Red marks the seconds hand and warnings, nothing else. Never use it for decoration, links, hover, or errors that are not warnings.
**The Board Blue Rule.** Blue is structure (heads, band, selection). It never carries meaning about device state.
**The Not Color Alone Rule.** Every red state pairs with an icon, a word, or a shape change.

## Typography

**Display / Body / Label Font:** Arimo (self-hosted TTF, weights 400-700, OFL) with Helvetica Neue, Helvetica, Arial, sans-serif.

**Character:** A Helvetica-metric neo-grotesque, the voice of timetables. Tabular numerals are on at the body level so times, confidences, and dwell seconds align in columns.

### Hierarchy
- **Clock time** (700, 30px, 1, -0.01em; 26px under 560px): header digital time beside the station clock.
- **Pane title** (700, 20px, -0.01em): Devices, Warnings, Frames, over a 2px text-colored rule.
- **Body** (400, 14px, 1.45): table cells, empty messages (max 60ch).
- **Table head / strip head** (700, 12px, sentence case): white on board blue.
- **Button and settings value** (700, 13px / 14px); meta and link state (400, 13px); frame meta (12px, time at 700); stamp (700, 11px).

### Named Rules
**The Weight Not Size Rule.** Differentiate with 400 versus 700 before reaching for a new size. Quiet states (Clear, No signal, meta) are 400 in muted grey; attention states are 700.
**The Tabular Rule.** Numbers stay tabular and right-aligned (`num` columns).

## Layout

A two-column grid at 5fr / 7fr with 24px gaps and padding, capped at 1680px. Left is a sticky status column (Devices over Warnings) that scrolls internally; right is the Frames pane. Under 960px it collapses to one column with a static status column and 16px padding; under 560px the less-critical columns (Last frame, Last warning, Max conf.) hide and cell padding tightens to 6px.

Spacing is a 4/8/12/16/24/32 scale. Tables are dense (cells 8px vertical, 8px horizontal); panes are separated by 32px. A sticky header band sits above everything and wraps its settings and controls when narrow. Frame strips are auto-fill grids (132px minimum tiles, 110px on narrow), one collapsed row per device, expanded fully when the device is selected.

## Elevation & Depth

Flat. There are no shadows. Depth is tonal (ground, panel, raised panel) plus ruled lines: 1px hairlines between rows, a 2px rule under each pane title, and a 1px border on the modal viewer over a darkened backdrop. A selected row becomes board blue; a selected warning row keeps its red wash and takes a 2px paper outline inset.

### Named Rules
**The Flat Timetable Rule.** Separate with rules and tone, never with shadow or blur.

## Shapes

Square and ruled. Buttons use a 2px radius, tables and tiles are rectangular, and the viewer is a plain bordered box. The round forms are instruments only: the 52px station clock and the 36px per-device dwell dial (SVG circles with 60 and 1-12 ticks). Frame thumbnails are 4:3, cover-cropped; warning frames take a 3px inset red outline.

## Components

### Station Clock (signature)
A white-faced, black-handed Swiss railway clock in the header with a red seconds hand ending in a disc. The seconds hand sweeps in 58.5 s and rests at 12 for 1.5 s. When the server is unreachable it parks at 12 and the banner explains the stop. With reduced motion it ticks in whole-second steps.

### Dwell Dial (signature)
One 36px dial per device row. Tick count equals the dwell limit in seconds (1 to 12); the tick at 12 o'clock is the limit, drawn heavy in red. The hand sweeps one revolution as dwell approaches the limit (1.9 s linear), never runs backwards, and snaps to 12 on reset. States: idle is a grey hand; pedestrian is a red hand; warning is a filled red face with a white hand; no signal is a dashed empty ring with no hand.

### Band and Table Heads
Board-blue strips with white 12px bold labels. The header band is sticky and carries the clock, title, read-only settings (label 12px, value 700), link state, and the Pause button.

### Buttons
- **Shape:** sharp (2px radius), 13px bold.
- **Default (on blue):** transparent with a 1px lavender-grey border and paper text; hover fills Board Rule; pressed state inverts to paper with blue text.
- **Quiet (on dark):** 400 weight, hairline border, raised-panel hover; used for View and Show all devices.
- **Focus:** 2px paper outline, 2px offset, on everything.

### Device and Warning Tables
Rows are ruled, 8px cell padding. Device rows are clickable and toggle selection (blue fill) to filter the frame strips. Status is a word plus detail ("Pedestrian 2.1 s of 5 s"); Warning gets a triangle icon, coral bold text, and a wash row. Sort order is warning, pedestrian, clear, no signal.

### Frame Strips
A blue strip head (device ID plus state) over a row of 4:3 tiles, newest left. Each tile has time and confidence, a 3px confidence bar (muted, or paper when positive), and a status line. Alerted frames carry a red outline and a red "Warning" stamp with icon top-left. Tiles open the modal viewer.

### Banner
Wash-red full-width bar with a red bottom rule, a triangle icon, and text; shown only while the server is unreachable.

## Do's and Don'ts

### Do:
- **Do** build new surfaces from ruled tables and strips on Night Ground, with blue heads.
- **Do** reserve Signal Red for the seconds hand, the dwell limit, and warning states; use Warning Coral for red text.
- **Do** pair every warning signal with an icon or word as well as red.
- **Do** keep numerals tabular and right-aligned, and use 400/700 weight for hierarchy.
- **Do** use the 4/8/12/16/24/32 spacing scale and 2px corners.
- **Do** honor reduced motion: no sweeping hands, no transitions.

### Don't:
- **Don't** add shadows, glows, gradients, or blur.
- **Don't** use red for hover, links, selection, or non-warning errors.
- **Don't** introduce a second typeface or load fonts from a network; Arimo is self-hosted for offline LAN use.
- **Don't** use blue to signal state; it is structural only.
- **Don't** use large bright surfaces; the clock face is the brightest object on the page.
