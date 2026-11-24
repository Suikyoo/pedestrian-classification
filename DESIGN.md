---
name: Pedestrian safety console
description: A dark operations console with a crosswalk print, condensed display type, and a full-width live device board.
colors:
  ground: "#101110"
  surface: "#171816"
  surface-high: "#20211e"
  rule: "#373834"
  soft-rule: "#292b27"
  ink: "#e9e6dc"
  muted: "#aaa9a1"
  subtle: "#94958c"
  accent: "#e78464"
  selected: "#312721"
  live: "#a8c29b"
  person: "#ebc77e"
  alarm: "#ff8b78"
  alarm-fill: "#852e23"
  alarm-dark: "#371f1b"
  focus: "#f0cc93"
typography:
  display:
    fontFamily: "Barlow Condensed, Arimo, sans-serif"
    fontWeight: 700
    fontSize: "clamp(62px, 6.3vw, 96px)"
    lineHeight: 0.83
    letterSpacing: "-0.025em"
  section:
    fontFamily: "Barlow Condensed, Arimo, sans-serif"
    fontWeight: 700
    fontSize: "clamp(26px, 2.1vw, 36px)"
    lineHeight: 1.15
  body:
    fontFamily: "Arimo, Arial, sans-serif"
    fontSize: "14px"
    lineHeight: 1.5
  reading:
    fontFamily: "ui-monospace, Cascadia Mono, Consolas, Liberation Mono, monospace"
    fontSize: "13px"
rounded:
  control: "4px"
  panel: "5px"
spacing:
  gutter: "clamp(16px, 3.5vw, 62px)"
  panel-inset: "clamp(15px, 1.55vw, 26px)"
  gap: "clamp(16px, 1.7vw, 28px)"
components:
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
  button:
    backgroundColor: "{colors.surface-high}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "5px 13px"
  warning-row:
    backgroundColor: "{colors.alarm-dark}"
    textColor: "{colors.alarm}"
---

# Pedestrian safety console

## Overview

An original two-tone crosswalk print establishes the subject at the top of the console. Its broad diagonal stripes also inform the compact three-stripe console mark. The working area uses quiet graphite surfaces and warm off-white text for sustained night viewing.

## Colors

Copper identifies the console and the selected device. Sage accompanies the live connection label. A pedestrian approaching the dwell limit uses straw. A warning combines coral lettering, a triangle, a filled dwell dial and an oxide-tinted row. Reconnecting uses an explicit status and a full-width error message.

## Typography

Self-hosted Barlow Condensed Bold sets the two-line masthead and section titles. Self-hosted Arimo carries operational text. Local monospace faces align device IDs, timestamps, scores and measurements.

## Layout

The top navigation gives access to devices, frames and warnings while the connection indicator and pause control stay together. The masthead groups local time with the server's read-only cutoff and frame history. Every device gets a row before the evidence area. Capture frames occupy the wider evidence column. The warning log sits alongside.

At 850px the evidence panels stack. At 600px each device row groups the dial, ID and state above labeled readings. Warning records group the timestamp and device above dwell, maximum score and snapshot access. All operational fields remain available on narrow screens.

## Elevation & Depth

Hairline borders separate panels. Slightly lighter fills distinguish column headers and frame-strip headers. A darkened backdrop isolates the open snapshot viewer.

## Components

- Device rows retain a dial for dwell progress, the written status, the score, and the last-seen and last-warning timestamps. Selecting a row filters its frames.
- Frame strips put the latest capture first and open individual images in a native dialog. Alerted images carry an outlined frame, triangle and written warning.
- Empty panels describe what will populate them. The stream command appears in the frame panel. Deployment imagery and device identifiers come from the API.
- Reduced motion disables dial transitions and steps the small local clock once per second.
- The masthead print is original AI-generated editorial artwork stored locally in `server/master/static/crossing.webp`. It is decorative and never used as a capture.
