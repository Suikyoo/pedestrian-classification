# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: an operator who keeps the inference dashboard open on a monitor, often in a dark room (control room, night shift), watching one or more camera-equipped edge devices and reacting when a pedestrian alert fires. Secondary (inferred from development history, not confirmed as a design driver): the developer tuning detection threshold and dwell time.

## Product Purpose

A pedestrian safety-warning system. Edge devices (ESP32-S3 with camera and speaker) stream frames to a master server; the server detects people and, when a pedestrian stays in a device's view longer than a configured dwell time, tells that device to play a warning sound. The dashboard lets the operator see what each device sees, what the model concluded, how close each device is to triggering a warning, and which warnings fired.

Success for the operator: knowing at a glance whether any area currently has a pedestrian, which device is about to warn, and what triggered past warnings.

## Positioning

The warning is decided by dwell, not by a single detection: a pedestrian must be continuously present for N seconds (with gap tolerance and cooldown) before the device sounds. The dashboard is the only place that dwell progress and the reasoning behind each warning are visible.

## Operating Context

- LAN only; opened in a browser at `http://<server-ip>:8000`. No login.
- Runs beside the master service; read-only; refreshes about every 2 seconds.
- Frames arrive about once per second per device; history keeps the newest 200 inferences per device.
- Devices are identified by a 12-character MAC-derived ID (e.g. `0123456789ab`); there are no human-friendly device names yet.

## Capabilities and Constraints

- Per inference: thumbnail (320 px), device ID, capture time, person confidence (0–1), pedestrian yes/no against the threshold, current dwell seconds, and whether that frame triggered a warning.
- Per warning: time, device, dwell, max confidence, full snapshot.
- Configuration shown read-only: confidence threshold, dwell seconds, gap tolerance, cooldown.
- Not available today: device online/offline status, device names or locations, bounding boxes, any control actions (the dashboard cannot send commands).
- Plain HTML/CSS/JS served by FastAPI; no build step; no external CDN or network fonts (must work on an offline LAN).
- Device IDs are untrusted input and must be rendered as text.

## Evidence on Hand

No real deployment footage, site names, or incident data exist yet. Do not invent locations, device names, or statistics.

## Product Principles

1. Status before history: the operator must see the current state of every device before scrolling past events.
2. Warnings are unmistakable; normal frames stay quiet.
3. Show why: every warning is traceable to the frames and dwell that caused it.
4. Calm for long watches: nothing flashes or moves without a reason.

## Accessibility & Inclusion

Must be comfortable in a dark room over long sessions: dark-first, low glare, no large bright surfaces. Warning states must not rely on color alone.
