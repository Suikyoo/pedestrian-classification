# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: people in a room with the dashboard on a wall-mounted TV or monitor, glancing at it from across the room to see whether any camera has warned about a pedestrian. Secondary: the developer at a desk, tuning a device's threshold and dwell and comparing the device's score with the server's YOLO score.

## Product Purpose

A pedestrian safety-warning system. Edge devices (ESP32-S3 with camera and speaker) run person detection on the device itself. When a pedestrian stays in a device's view longer than its dwell time (with gap tolerance and cooldown), the device plays the warning sound and lights its LED itself, then reports the warning with a snapshot to the master server. The master records warnings and device status, and, for devices in stream mode, scores their frames with YOLO so device and server scores can be compared. The dashboard shows which camera warned, when, and why, plus each camera's current state.

Success for the viewer: seeing from across the room, at a glance, whether a camera has just warned and which one; then, up close, what the snapshot showed and how close other cameras are to warning.

## Positioning

The warning is decided by dwell, not by a single detection: a pedestrian must be present for N seconds before the device sounds. The dashboard is the only place where warnings, their snapshots, and each camera's dwell progress are visible together.

## Operating Context

- LAN only; opened in a browser at `http://<server-ip>:8000`. No login. Often left open full-screen on a wall display.
- Runs beside the master service; read-only; refreshes about every 2 seconds.
- Devices send status about every 60 s and when settings change. In stream mode they send a frame every `interval_ms` (currently 3 s).
- History keeps the newest 200 inferences per device.
- Devices are identified by a 12-character MAC-derived ID (e.g. `288485a0c0c0`); there are no human-friendly names yet.

## Capabilities and Constraints

- Per device: online/offline, last status time, streaming on/off, detector OK or faulty, active settings (threshold, dwell, gap, cooldown), last frame's device score and YOLO score, current dwell, last warning time.
- Per frame (stream mode only): thumbnail (320 px), capture time, YOLO person confidence, device score, pedestrian yes/no, dwell, whether it triggered a warning.
- Per warning: time, device, dwell, max score, full snapshot.
- Server settings shown read-only: YOLO cutoff, history length.
- Not available: device names or locations, bounding boxes, any control actions (the dashboard cannot send commands).
- Plain HTML/CSS/JS served by FastAPI; no build step; no external CDN or network fonts at runtime (must work on an offline LAN).
- Device IDs are untrusted input and must be rendered as text.

## Brand Commitments

The dashboard looks like a modern consumer web app, alongside Apple Home / iOS and the Stripe dashboard: clean, rounded, photography-forward, clear hierarchy. It follows the system light/dark setting. (User choice, 2026-10-18, after rejecting a themed safety-signage concept as lacking design.)

## Evidence on Hand

One real device on a bench; no deployment sites, names, or incident data. Do not invent locations, device names, or statistics.

## Product Principles

1. Warnings own the screen: the newest warning is readable from across the room.
2. Warnings are unmistakable; normal states stay quiet.
3. Show why: every warning is traceable to its snapshot and dwell.
4. Calm when nothing is happening: nothing flashes or moves without a reason.

## Accessibility & Inclusion

Read at a distance on a wall display in a lit room: large type for the essentials, strong contrast, no tiny critical text. Warning states must not rely on color alone (shape and words carry them too). Respect reduced motion.
