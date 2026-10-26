# Host-Verified Alerts — Design

Date: 2026-10-26
Status: draft for review

## Intent and why

The edge device false-alerts too much. Its on-device model (ESP-DL) fires on
things that are not pedestrians, and every false fire plays the siren.

Move the final alert decision to the host. The device keeps running its own
detection with a lowered threshold, but instead of alerting locally it sends
candidate events to the host over the existing MQTT link. The host re-runs
detection with its own (stronger) model, applies a dwell window on top, and
only then commands the device to play the alert.

One escape hatch stays on the device: a very confident local score still
alerts immediately, so a genuine pedestrian in front of the camera never
waits on the network or the host.

## Goals

- Device publishes an event for every positive frame above its (lowered)
  threshold, rate-capped by `cooldown_s` (set to 1 s). No local dwell.
- Device score above the device alert threshold (default 0.90) publishes the
  event AND plays the alert immediately, without waiting for the host.
- Host receives events, runs its own model on the JPEG, and applies a dwell
  window computed from the device timestamps. Only a verified, sustained
  detection makes the host send `{id}/alert` back to the device.
- The existing MQTT topics, ACL, and config paths stay unchanged.

## Non-goals

- No change to the MQTT topic layout or payload formats.
- No change to stream mode (`{id}/image` frames scored by the host).
- No change to the dashboard UI.
- No battery/motion-sensor work (PIR gating is a later project).
- Camera heat mitigation is not part of this change.

## Anti-goals

- A host crash must not make the device mute forever: device-side >90
  immediate alert stays as the safety net, and the device keeps working if
  the host is down (it just never gets host-confirmed alerts).
- No breaking the protocol between device and server; old firmware must keep
  working against the new server and vice versa.

## Constraints

- Device events are QoS 1 with a JPEG snapshot; event rate is ~1/s per device
  after the cooldown. Host YOLO inference on CPU must keep up with that.
- Device id may be any short string (currently `ctu-1`), not necessarily a
  12-hex MAC. Server internals already treat it as an opaque string; the CLI
  regex must be relaxed to match.
- The device keeps dwell code compiled (tests depend on it) but the stream
  loop stops calling it.

## Current state

- Device: `firmware/main/stream.c` runs detection every `interval_ms`, feeds a
  `dwell_t` state machine, and on a dwell alert plays audio locally and
  publishes `{id}/event` (JPEG + JSON with `alert_ms`, `first_seen_ms`,
  `dwell_s`, `max_score`). `firmware/main/cmd.c` already plays the alert on
  `{id}/alert` commands (payload `{"clip":"alert","repeat":N}`).
- Host: `server/master/app.py` (`MasterApp`) subscribes to `+/event` and
  records every event as a warning immediately. Stream-mode frames
  (`+/image`) are scored with YOLO (`yolo11n.pt`) on a worker thread. The
  master deliberately never publishes `{id}/alert`; only `master.cli alert`
  does.
- Config: device `devcfg_t` has `threshold`, `dwell_s`, `max_gap_s`,
  `cooldown_s`, `streaming`. Server `Settings` reads `.env` via pydantic.

## New flow

### Device

For each captured frame with score `s`:

1. `s >= threshold` (lowered, e.g. 0.3, set via `{id}/config`):
   - publish `{id}/event` with `max_score = s`, `alert_ms = capture_ms`,
     `first_seen_ms = capture_ms`, `dwell_s = 0` (no dwell on device);
   - rate-cap these publishes with `cooldown_s` (set to 1 s);
   - if `s > ALERT_THRESHOLD` (firmware constant, 0.90): also
     `led_alert()` + `audio_play(1)` immediately, at most once per
     `ALERT_COOLDOWN_S` (firmware constant, 5 s).
2. `s < threshold`: nothing (as today).

`dwell_update()` is no longer called from `stream.c`. `dwell_s` and
`max_gap_s` config fields are kept for protocol compatibility but ignored.

### Host

For each `{id}/event`:

0. Legacy firmware (event with `dwell_s > 0` or
   `first_seen_ms < alert_ms`): record the warning row directly, exactly
   as the server does today. No verification, no host command. This is
   the backward-compatibility branch.
1. Parse the event, run the host model on the JPEG.
2. Host score `< verify_threshold` (`.env`, default 0.8): record the
   inference (thumbnail + row, `device_score` set) and stop. No warning row,
   no command.
3. Host score `>= verify_threshold`: feed the verify dwell window (per
   device, keyed by id) using the event timestamps:
   - window starts at the first qualifying event's `first_seen_ms`;
   - a gap larger than `max_gap_s` (`.env`) restarts the window;
   - unsynced device timestamps (`alert_ms == 0`) use server receive time
     for the window; a sync mid-window resets the window (never mix the
     two clocks);
   - when the window spans `dwell_s` (`.env`): publish
     `{id}/alert` with `repeat = 1` (same payload as `master.cli alert`),
     record the warning row (snapshot + Alert), and reset the window;
   - at most one host command per device per `verify_alert_cooldown_s`
     (`.env`, 5 s).
4. Event with `max_score > ALERT_THRESHOLD` (device already alerted): record
   the warning row immediately, no host command, no verify run. The device
   already played.

The master's "never publishes alert" policy is replaced by the verify path
above. The CLI keeps working as a manual override.

Warning row values for host-verified alerts: `ts` = the confirming event's
device capture time (server time when unsynced), `first_seen` = the window
start, `max_conf` = the host model confidence, snapshot = the confirming
event's JPEG, `mark_frame` only when the device clock was synced.

The master's "never publishes alert" policy is replaced by the verify path
above. The CLI keeps working as a manual override.

## Firmware changes

- `main/stream.c` `process_frame()`: replace the dwell block with the
  threshold/cooldown/event logic above. Constants `ALERT_THRESHOLD = 0.90f`
  and `ALERT_COOLDOWN_S = 5` live in `stream.c` (or `board.h` style header —
  builder's choice). `dwell_current_ms()` for stream-mode frames becomes 0.
- `main/event.c`: `event_raise()` currently takes a `dwell_alert_t`; change
  it to take `(score, capture_ms, jpeg, len)` and always emit
  `dwell_s = 0`, `first_seen_ms = capture_ms`. Queue/Ack machinery
  unchanged.
- `main/led.h/led.c`: `led_person()` still mirrors `score >= threshold`.
- `main/cmd.c`: unchanged (alert command path already exists).
- No `devcfg` changes: `dwell_s`/`max_gap_s` stay but are ignored;
  `cooldown_s` is repurposed as the event-send rate cap.
- Tests: update host tests that call `event_raise`; add a firmware test for
  the threshold/cooldown branch if the host-test harness allows it.

## Server changes

- `master/settings.py`: add `verify_threshold: float = 0.8`,
  `verify_dwell_s: float = 5.0`, `verify_max_gap_s: float = 3.0`,
  `verify_alert_cooldown_s: float = 5.0` (all `.env`-overridable; document
  in `.env.example`).
- `master/app.py`: `MasterApp` gains the verify parameters and a publish
  callback (the MQTT client, or a narrow `publish(topic, payload)` callable)
  so `main()` can hand it the client. `_on_event` implements the host flow
  above. A small `VerifyWindow` class holds per-device window state
  (start ts, last ts, clock source). Verification runs inline on the paho
  network thread: fine for the current single-device deployment (YOLO
  ~200–400 ms, events ≤ 1/s). Multi-device deployments need a lossless
  queue + worker; out of scope, noted here.
- `master/cli.py`: relax `_MAC_RE` to accept any non-empty id without `/`
  (or reuse the topic-safety rule from `events._dir_name`). `ctu-1` must be
  usable as `<mac>`.
- `compose.yaml`: pass the new `PEDESTRIAN_VERIFY_*` env vars to `master`.
- Tests: extend `test_app.py`/`test_events.py` for the verify path
  (confirm, reject, dwell window, gap restart, unsynced clock, legacy
  event, alert cooldown, device-immediate bypass).

## Config surface

| Where | Key | Default | Meaning |
|---|---|---|---|
| device (NVS) | `threshold` | 0.6 (lowered to ~0.3 by config) | candidate cutoff |
| device (NVS) | `cooldown_s` | set to 1 | min time between event sends |
| firmware constant | `ALERT_THRESHOLD` | 0.90 | immediate local alert cutoff |
| firmware constant | `ALERT_COOLDOWN_S` | 5 s | min time between local alerts |
| server `.env` | `PEDESTRIAN_VERIFY_THRESHOLD` | 0.8 | host model confirm cutoff |
| server `.env` | `PEDESTRIAN_VERIFY_DWELL_S` | 5.0 | host dwell window |
| server `.env` | `PEDESTRIAN_VERIFY_MAX_GAP_S` | 3.0 | host gap that restarts the window |
| server `.env` | `PEDESTRIAN_VERIFY_ALERT_COOLDOWN_S` | 5.0 | min time between host alert commands |

Host alert command repeat is fixed at 1 (matches current device behavior).

## My calls (change if you disagree)

- Alert threshold 0.90 and alert cooldown 5 s are constants on both sides,
  not config fields. The host always knows the device's value because they
  are the same constant. (Builder question 1.)
- Alert cooldown: 5 s between alerts on device and host. (User decision.)
- Legacy events (`dwell_s > 0`) keep today's behavior: recorded directly,
  never verified, never commanded. (Builder question 3.)
- Single-device deployment: verification runs inline on the MQTT network
  thread. Multi-device would need a queue + worker. (Builder question 4.)
- Unsynced device clock: window uses server receive time; sync mid-window
  resets it. (Builder question 5.)
- Verified warning row: `ts` = confirming event's device time (server time
  when unsynced), `first_seen` = window start, `max_conf` = host
  confidence, snapshot = confirming JPEG, `mark_frame` only when synced.
  (Builder question 6.)
- Host dwell window defaults 5 s / gap 3 s (same spirit as old device
  defaults).
- Host command repeat = 1.
- `dwell_s`/`max_gap_s` stay in the device config but are ignored (keeps the
  protocol and NVS compatible).
- Warning rows are recorded only on host confirmation or device-immediate
  alerts; rejected candidates appear as inference rows only.

## Open questions

- None.
