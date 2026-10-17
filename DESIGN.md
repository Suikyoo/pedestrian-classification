---
name: Pedestrian Warnings Dashboard
description: A calm consumer-grade dashboard in the spirit of Apple Home and Stripe, where the newest warning is the hero card and every camera is a home-style tile; follows system light and dark.
colors:
  accent: "#5b4ff5"
  accent-dark: "#8a83ff"
  accent-soft: "rgb(91 79 245 / 0.12)"
  page: "#f2f2f5"
  page-dark: "#000000"
  card: "#ffffff"
  card-dark: "#1c1c1e"
  card-2: "#f6f6f8"
  card-2-dark: "#242427"
  media: "#d9d9de"
  media-dark: "#2c2c2e"
  line: "rgb(16 16 20 / 0.08)"
  line-strong: "rgb(16 16 20 / 0.14)"
  line-dark: "rgb(255 255 255 / 0.08)"
  line-strong-dark: "rgb(255 255 255 / 0.16)"
  text: "#1d1d1f"
  text-dark: "#f5f5f7"
  text-2: "#5f5f66"
  text-2-dark: "#a7a7ad"
  text-3: "#707076"
  text-3-dark: "#8f8f96"
  state-red: "#e5372d"
  state-red-dark: "#ff453a"
  state-red-text: "#c4271e"
  state-red-text-dark: "#ff6b62"
  state-red-soft: "rgb(229 55 45 / 0.12)"
  state-orange: "#f08a00"
  state-orange-dark: "#ff9f0a"
  state-orange-text: "#a65c00"
  state-orange-text-dark: "#ffb340"
  state-green: "#22a447"
  state-green-dark: "#30d158"
  state-green-text: "#177a33"
  state-green-text-dark: "#4ade74"
  state-grey-soft: "rgb(120 120 128 / 0.14)"
typography:
  hero-time:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "3rem"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.035em"
    fontFeature: "\"tnum\", \"cv11\""
  hero-title:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    letterSpacing: "-0.02em"
  page-title:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "1.625rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  stat:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 650
    letterSpacing: "-0.01em"
    fontFeature: "\"tnum\", \"cv11\""
  card-title:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 700
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "\"tnum\", \"cv11\""
  meta:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
  label:
    fontFamily: "Inter, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: 1.2
rounded:
  card: "22px"
  tile: "18px"
  media: "14px"
  frame: "12px"
  thumb: "10px"
  pill: "999px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "20px"
  s6: "24px"
  s7: "32px"
components:
  card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.card}"
    padding: "20px"
  pill-button:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text}"
    typography: "{typography.meta}"
    rounded: "{rounded.pill}"
    padding: "0 16px"
    height: "36px"
  pill-button-hover:
    backgroundColor: "{colors.card-2}"
  pill-button-pressed:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
  pill-button-quiet:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
    rounded: "{rounded.pill}"
    padding: "0 16px"
    height: "36px"
  badge-warning:
    backgroundColor: "{colors.state-red-text}"
    textColor: "#ffffff"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "5px 12px 5px 9px"
  badge-in-view:
    backgroundColor: "{colors.state-orange}"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "5px 12px 5px 9px"
  badge-clear:
    backgroundColor: "{colors.card}"
    textColor: "{colors.state-green-text}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "5px 12px 5px 9px"
  badge-offline:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text-2}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "5px 12px 5px 9px"
  camera-tile:
    backgroundColor: "{colors.card-2}"
    rounded: "{rounded.tile}"
    padding: "10px 12px 12px"
  warning-row:
    rounded: "{rounded.media}"
    padding: "8px"
  banner:
    backgroundColor: "{colors.state-red-soft}"
    textColor: "{colors.state-red-text}"
    rounded: "{rounded.media}"
    padding: "12px 16px"
---

# Design System: Pedestrian Warnings Dashboard

## Overview

**Creative North Star: "The Quiet Home Screen"**

A modern consumer dashboard in the manner of Apple Home / iOS and the Stripe dashboard: a soft page, rounded cards that float on gentle shadows, photography first, one indigo accent, and system state colours. The newest warning is the hero card, with its snapshot on top and its time as the loudest number on screen; every camera is a home-style tile with its newest snapshot and a dwell meter. When nothing is happening the screen is calm: white and grey surfaces, green "Clear" badges, nothing moving.

The system follows the operating system's light/dark setting through two complete token sets. Light is a soft grey page with white cards and layered ambient shadows; dark is a black page with graphite cards held by hairline rings instead of shadows. The same layout, radii, and type carry both.

It is built to be read from across a room on a wall TV and up close at a desk. On wide screens the whole dashboard fits one viewport and no card scrolls; on narrow screens it stacks into a single column. It refuses themed costume, terminal/NOC styling, and anything that flashes without a reason.

**Key Characteristics:**
- System light and dark token sets via `prefers-color-scheme`; shadows in light, hairline rings in dark.
- Large soft radii (22px cards, 18px tiles, 14px media) with pill badges and buttons.
- One indigo accent for interaction and selection only; red, orange, green, and grey for state only.
- Inter variable, self-hosted, tabular figures everywhere.
- Fits one screen at 1100px wide and 620px tall or more; cards never scroll internally.
- One motion moment: a new warning settles into the hero card.

## Colors

A neutral Apple-like greyscale with one cool indigo accent and the iOS system state colours; every colour has a light and a dark value, switched by `prefers-color-scheme`.

### Primary
- **Interaction Indigo** (`accent`, dark `accent-dark`): focus rings, the pressed Pause pill, the selected camera tile ring, the quiet "Show all cameras" pill, and text selection (via `accent-soft`). It never signals state.

### Tertiary
- **Warning Red** (`state-red`, dark `state-red-dark`): the 2px ring on an active hero card, a warning tile, or a warning frame, and the filled dwell meter on a camera that warned. `state-red-text` carries red words (top-bar summary in warning, the offline banner); `state-red-soft` is the banner wash. Warning badges use a deeper red so their white text holds about 5:1: #c4271e in light, #cf3127 in dark (`--red-badge`).
- **In-View Orange** (`state-orange`, dark `state-orange-dark`): the "Someone in view" badge (with dark text) and the dwell meter fill while counting. `state-orange-text` colours the "Pedestrian" flag on frames.
- **Clear Green** (`state-green`, dark `state-green-dark`): the live indicator dot and the hero placeholder check when there are no warnings; `state-green-text` is the "Clear" badge word.
- **Offline Grey** (`state-grey-soft` with `text-2` / `text-3`): the "No signal" badge, paused live dot, empty meter track. Offline tile snapshots are greyscaled and faded.

### Neutral
- **Soft Page Grey** (`page`; dark: pure black `page-dark`): the page and, at 82% mix, the frosted top bar.
- **Card White** (`card`; dark: graphite `card-dark`): every card, the viewer dialog, and neutral badges.
- **Inset Grey** (`card-2`; dark `card-2-dark`): camera tiles, hover fill for pills and rows, inline code.
- **Media Grey** (`media`; dark `media-dark`): the placeholder behind every image before it loads. Snapshots in the hero and the viewer sit on pure black instead.
- **Hairline** (`line`, `line-strong`; dark variants): row dividers, scrollbar thumb, and the dark-mode card rings.
- **Ink** (`text`), **Secondary Ink** (`text-2`), **Tertiary Ink** (`text-3`): primary text; meta, labels, timestamps; and the faintest supporting metadata (score lines, "N older warnings not shown").

### Named Rules
**The Icon-and-Word Rule.** A state colour never appears alone. Red, orange, green, and grey states are always carried by a badge with an icon and a word ("Warning now", "Someone in view", "Clear", "No signal", "Earlier"); rings and meter fills only reinforce a badge already on the same element.

**The Indigo Is for Hands Rule.** Indigo means "you can act on this" or "you chose this". It is never used to flag a camera's state, and state colours are never used for buttons.

## Typography

**Display Font:** Inter variable (self-hosted `Inter-wght.woff2`, weights 100-900), with -apple-system, Segoe UI, system-ui fallback
**Body Font:** Inter (same stack)

**Character:** One neutral, highly legible grotesque at a range of weights (400, 500, 600, 650, 700), tightened with negative tracking as it grows. Tabular figures (`tnum`) and the open-digit alternate (`cv11`) are set on the body so every clock, dwell, and score aligns.

### Hierarchy
- **Hero time** (700, 3rem, line-height 1.05, -0.035em): the time of the newest warning. The loudest number on the page; 2.25rem at 640px and below.
- **Hero title** (700, 1.75rem, -0.02em): the hero card's heading when there is no warning on show; visually hidden (kept for screen readers) once a warning badge, ring, and time say it.
- **Page title** (700, 1.625rem, line-height 1.2, -0.025em): "Pedestrian warnings" in the top bar; intentionally the page's anchor.
- **Stat / clock** (650 and 600, 1.25rem, -0.01em): hero stats (Camera, Lingered, Score) and the top-bar clock (1.0625rem on phones).
- **Card title** (700, 1.0625rem, -0.01em): Cameras, Recent warnings, Frames.
- **Body** (400, 0.9375rem, line-height 1.5): default text; camera names and row times at 650. Prose capped at 52-60ch.
- **Meta** (500, 0.875rem): top-bar live state, card meta; pill buttons at 600.
- **Label** (600, 0.8125rem, line-height 1.2): badges; stat labels at 500; camera details, score lines, frame metadata. The smallest size in the system.

The root size scales up for distance: 16px base, 17px at 1600px wide, 22px at 2200px wide, so every rem value grows on large TVs.

### Named Rules
**The One Loud Number Rule.** Only the hero time reaches 3rem. Everything else stays at or below the 1.75rem hero title, so the newest warning's time wins from across the room without anything else being oversized.

## Layout

Spacing runs on a 4px-based scale (`s1`-`s7`: 4, 8, 12, 16, 20, 24, 32px). The page gutter is 32px (16px on phones); cards sit 24px apart (16px on phones).

- **Top bar:** sticky, minimum 84px tall, frosted (page colour at 82% with `saturate(1.6) blur(18px)`). Title and one-line status summary on the left; live indicator, clock, and Pause pill on the right. Wraps on phones.
- **Dashboard grid:** two columns, `minmax(0, 1.2fr)` hero and `minmax(24rem, 1fr)` side column. The side column stacks Cameras (capped at 58% of the available height) above Recent warnings.
- **One-screen fit:** at 1100px wide and 620px tall or more, the dashboard's height is the viewport minus the 84px top bar. Cards never scroll internally: Recent warnings shows only whole rows and then a line "N older warnings not shown".
- **Short screens** (1100px+ wide, 820px tall or less, e.g. 720p TVs): tile media becomes a 4:1 strip, tile score lines and media icons hide, card padding drops to 16px, and rows tighten, so every camera and at least two warnings stay visible.
- **Below 1100px:** one column; the hero media becomes a fixed 4:3 frame. **640px and below:** tiles go two-up, the score column leaves the rows, and the hero time drops to 2.25rem.
- **Frames** sit below the fold in a full-width card: one reel per camera, an auto-fill grid of 11rem frames (8.5rem on phones), collapsed to one row until expanded.

## Elevation & Depth

Hybrid. In light mode cards float on soft, layered ambient shadows over the grey page; in dark mode those shadows are replaced by 1px hairline rings, because shadows vanish on black. State rings (2px) are drawn as box-shadows so they never shift layout. The top bar is frosted glass; the viewer dialog is the one deep shadow.

### Shadow Vocabulary
- **Resting** (light `box-shadow: 0 1px 2px rgb(16 16 20 / 0.04), 0 6px 24px rgb(16 16 20 / 0.06)`; dark `0 0 0 1px` hairline): every card and the default pill button.
- **Lift** (light `box-shadow: 0 2px 6px rgb(16 16 20 / 0.06), 0 14px 36px rgb(16 16 20 / 0.1)`; dark `0 0 0 1px` strong hairline): a hovered camera tile, and under the red ring of an active hero card.
- **Ring** (`box-shadow: 0 0 0 2px` red or indigo): warning state (red) or selection (indigo); a selected warning tile adds a 5px soft-indigo halo outside the red ring.
- **Viewer** (`box-shadow: 0 30px 80px rgb(0 0 0 / 0.35)` over a blurred 55% black backdrop): the snapshot viewer dialog only.

### Named Rules
**The Hairline-in-the-Dark Rule.** Dark mode never uses drop shadows; depth there is a 1px ring at 8% (resting) or 16% (lift) white.

## Shapes

Soft, continuous, Apple-style rounding throughout, stepping down with size: cards 22px, camera tiles 18px, media and rows 14px, frame thumbnails 12px, row thumbnails 10px. Badges, buttons, the live dot, and the dwell meter are full pills or circles. There are no hard borders around cards; edges come from shadow (light) or hairline ring (dark). Media is clipped to its container's radius.

## Components

### Buttons
- **Shape:** full pill (999px), 36px tall, 16px side padding, icon + label with an 8px gap.
- **Default:** card-white fill, ink text, resting shadow, 0.875rem at 600.
- **Hover / Active / Focus:** hover fills with inset grey; press scales to 0.97; pressed (`aria-pressed`) fills indigo with white text. Focus is a 2px indigo outline at 2px offset (global).
- **Quiet:** soft-indigo fill with indigo text and no shadow ("Show all cameras").

### Badges
- **Style:** pill, 5px 12px 5px 9px, 0.8125rem at 600, an inline SVG icon at 1.1em plus a word.
- **Kinds:** Warning now (solid red, white text, alert icon), Someone in view (solid orange, dark text, walking figure), Clear (white with green text, check), No signal (white with secondary text, offline icon), Earlier (55% black glass with blur over a snapshot).
- The icon's inner mark takes the badge's fill colour (`--icon-mark`), so the cut-out reads on any background.

### Cards / Containers
- **Corner Style:** 22px.
- **Background:** card white / graphite.
- **Shadow Strategy:** Resting (see Elevation & Depth).
- **Internal Padding:** 20px (16px on short screens and phones); the Frames card uses 24px.
- **Header:** card title with baseline-aligned meta, 16px below.

### Hero Card
The newest warning. Snapshot on top in a 14px-rounded frame inset 12px, letterboxed (`object-fit: contain`) on black so it is never cropped; a badge sits top-left. Below: the time at 3rem with "N min ago", then Camera / Lingered / Score stats. "Warning now" (red badge, 2px red ring plus lift) lasts for that camera's own cooldown window, then the badge becomes "Earlier" glass and the ring drops. With no warnings it shows a large green check on media grey and a short note. A new warning settles in once: scale 0.985 to 1 and opacity 0.6 to 1 over 600ms on `cubic-bezier(0.22, 1, 0.36, 1)`.

### Camera Tiles
Home-style tiles on inset grey, 18px radius, auto-fill at 10rem minimum. Newest snapshot on top (5:2, `cover`; 4:1 on short screens) with the state badge top-left; name, detail ("In view 4 s of 8 s"), a 6px dwell meter, and a score line below. The meter fills orange toward the dwell limit with `scaleX` (2.6s linear, matching the refresh), red once warned, hidden when clear or offline. Hover lifts 1px; selection is an indigo ring; a warning tile carries a red ring.

### Recent Warning Rows
Thumbnail (4:3, 10px radius), time and camera, then right-aligned Lingered and Score columns with the value above the label. 14px-radius hover fill; hairline dividers between rows. Only whole rows are shown, followed by "N older warnings not shown".

### Navigation
The sticky frosted top bar is the only navigation: page title and status summary (turns red text at 600 when a warning is active), a live dot (green live, grey paused, red down, each with a soft 3px halo) with its word, the clock, and the Pause pill.

### Viewer
A native dialog, up to 1100px wide, 22px radius, black media area with the snapshot letterboxed, and a caption bar with a Close pill.

## Do's and Don'ts

### Do:
- **Do** define every colour as a light/dark pair under `prefers-color-scheme`, and swap shadows for 1px hairline rings in dark.
- **Do** carry every state with a badge that has an icon and a word; use red, orange, green, and grey only for state.
- **Do** keep indigo (`accent`) for focus, selection, and pressed controls.
- **Do** letterbox snapshots in the hero and viewer (`object-fit: contain` on black).
- **Do** keep the dashboard to one screen at 1100px x 620px and above: show whole rows and say how many did not fit instead of scrolling a card.
- **Do** keep the hero time (3rem) the only loud number, with the 1.625rem page title as the anchor.
- **Do** limit motion to the hero settle (600ms), the dwell meter fill, and small hover/press feedback, and disable all of it under `prefers-reduced-motion: reduce`.
- **Do** self-host Inter and keep tabular figures on.

### Don't:
- **Don't** use a state colour without its icon and word, or use indigo to signal state.
- **Don't** add drop shadows in dark mode.
- **Don't** make a card scroll internally on desktop or TV layouts.
- **Don't** crop the hero or viewer snapshot.
- **Don't** add flashing, pulsing, or looping animation; nothing moves without a reason.
- **Don't** load fonts or assets from a CDN; the dashboard runs on an offline LAN.
- **Don't** use tertiary ink (`text-3`) for anything a reader needs to make a decision; it is reserved for faint supporting metadata.
