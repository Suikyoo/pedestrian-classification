---
name: Crossing Study
description: A pedestrian monitor for comparing camera and YOLO confidence and inspecting recorded warnings.
colors:
  ground: "#f6f6f2"
  surface: "#ffffff"
  ink: "#182844"
  muted: "#536078"
  rule: "#cbd0db"
  plate: "#1d304f"
  silver: "#c9c9e4"
  accent: "#615a91"
  wash: "#f0f0f7"
  alarm: "#ab4438"
  alarm-wash: "#f9ebe7"
  focus: "#5449b0"
typography:
  display: "Barlow Condensed, Arial Narrow, sans-serif"
  body: "Inter, Arial, sans-serif"
  reading: "ui-monospace, Cascadia Mono, Consolas, monospace"
rounded:
  panel: "6px"
  control: "4px"
spacing:
  gutter: "clamp(16px, 3.8vw, 64px)"
  panel-inset: "clamp(18px, 2vw, 32px)"
  gap: "clamp(14px, 1.4vw, 24px)"
---

# Crossing Study

## Crossing model and capture replay

The hero leads with an axonometric street section: raised concrete, dark asphalt, enamel crossing bars, a camera body, and its explicitly schematic view cone. A compact control changes the viewing angle. A fixed pedestrian silhouette appears only when the selected record's `positive` value is true; it disappears on a clear record. The caption states that its position is not tracked. The model is not a live feed or a calibrated camera view.

The adjacent camera plane shows the selected record's actual thumbnail. Previous, Replay captures, Next, and Latest all operate on the same record used by the confidence chart and detail view. Replay advances between stored captures, does not interpolate between them, and stops at a gap longer than ten seconds. Camera changes, manual sample selection, pausing, and returning to Latest stop replay. Historical readings are labeled with their capture time.

Device and YOLO confidence are shown as separately labeled percentage bars with the same 0–100 scale. Reported dwell has a distinct ruler in seconds and a mark at the configured limit. These readings follow the selected sample, while the limit follows its camera. Zero displays as `0 s`; unavailable values display as a dash.

## Confidence timeline

The camera roster selects the source for the crossing scene, readings, and timeline. Horizontal distance on the plot represents elapsed capture time. The vertical axis spans confidence from 0 to 1.

| Record | Encoding |
| --- | --- |
| Device confidence | Solid ink-blue line with filled dots |
| YOLO confidence | Dashed violet line with hollow dots |
| Selected sample | Vertical guide and larger sample dots |
| Recorded warning | Coral outlined diamond above the score traces, aligned to the warning’s own timestamp |

Each trace breaks at missing values and sampling gaps longer than ten seconds. Dots keep isolated readings visible. Selecting a sample reveals its capture time, thumbnail when available, both detector scores, reported dwell and recorded classification. Historical selection stays on the same sample as new records arrive. **Latest** resumes following captures.

When **Latest** is following a fresh, connected stream, a soft violet ring expands from the newest available point on each trace. It stops when the user pauses, inspects history, the capture goes stale, the plot leaves view or the browser tab is hidden. Reduced-motion mode keeps a still ring as the live-state cue. Capture replay uses short transitions for sample changes; reduced-motion mode removes those transitions.

## Fleet and warning records

The fleet status summarizes device reports across cameras. The adjacent latest-warning panel shows the newest recorded event across the fleet, with its timestamp, camera ID and available snapshot. A recent warning pairs a diamond with a written label. Coral ink and a pale coral wash draw attention without flashing.

The archive lists warnings newest first, with recorded time, camera ID, reported dwell, max score and snapshot availability. Activating a chart diamond or a warning’s snapshot control opens that event’s own image when available. The selected sample thumbnail opens its capture separately.

## Surfaces, type and layout

White panels sit on a warm paper ground with thin gray rules. Self-hosted Barlow Condensed Bold sets the study title, section headings and large status readings. Self-hosted Inter carries labels and instructions. A local monospace face distinguishes measurements, timestamps and identifiers. Violet identifies the selected camera and the YOLO trace. The legend also distinguishes both traces by line style.

On wide screens the crossing model and timeline share the wider left column, with the fleet summary and camera roster on the right. Inside the hero, the scene and camera readout sit side by side; on phones, the scene comes first and its measurements, preview, and replay controls stack below. The warning archive spans both columns. At 760px and below, the main sections stack, and the two fleet readings sit side by side. At phone widths the navigation wraps, sample readings form two columns and data tables scroll horizontally.

## Components

Buttons use a four-pixel radius, a thin gray border and a minimum height of 38px on the dashboard; admin buttons use 44px. Both use 8px vertical padding. The save action uses the deep blue plate, while reboot uses a coral outline and a diamond. Disabled navigation controls retain their layout and use muted text.

Panels have a six-pixel radius and a thin gray rule. Their children own the interior spacing: section headings use 17px top, 13px bottom and the shared 18–32px horizontal inset; sample details use 16px vertical padding; camera rows use 13px vertical padding. The selected camera combines a pale violet wash with a filled circular marker.

The confidence plot sits in a lightly tinted, thinly ruled frame. Device readings use a solid ink line with filled points; YOLO readings use a dashed violet line with hollow points. Warning events use coral outlined diamonds at their recorded times. The sample detail pairs a 4:3 capture thumbnail with its timestamp and detector readings; the thumbnail control’s caption sits on a deep blue plate.

Admin fields keep persistent labels above monospace controls. Inputs and selects use a 44px minimum height and 8px by 10px padding. Edited values gain a violet border and wash. Invalid numeric input uses a dashed coral border and pale coral background. Status and toast messages use text and thin, full-perimeter borders so state is not carried by a side stripe alone.

## Camera administration

The optional admin page shares the monitor’s navigation mark, fonts, borders, focus outline and panel spacing. The camera selector and command buttons occupy the left column, with settings on the right. On narrow screens camera selection, commands and settings follow in that order. Settings fields use one column at 480px and below.

Native controls pair persistent labels with monospace values and range hints. Edited fields gain a violet edge and light wash. On save, a changed, nonempty numeric field gets a dashed coral border if the client cannot parse a finite number. For a parsed value outside the allowed range, the server returns a validation message and the field keeps its edited styling. The dark primary button saves changed settings. Reboot has a coral outline, a diamond and a confirmation prompt naming the selected camera. Device status and command feedback appear as text.

## Keyboard and motion

Both pages include a skip link and a visible, three-pixel focus outline. The focused plot supports Left and Right to step through samples, Home for the earliest sample and End to resume following. Previous and Next buttons step one sample at a time; Replay advances through captures and stops at long gaps. The expandable chart data table gives timestamps, both confidence readings and record labels in text. Snapshot dialogs have a caption and support the Close button and Escape.

Live regions announce connection status, selected classifications and admin feedback. Pausing polling allows a fixed view. The crossing model changes only with the selected capture; it does not simulate a path. Reduced-motion mode removes replay transitions, angle transitions, live chart animation, and smooth scrolling.

The browser-tab icon is a compact line-art pedestrian crossing on the same deep blue plate as the 3D scene.
