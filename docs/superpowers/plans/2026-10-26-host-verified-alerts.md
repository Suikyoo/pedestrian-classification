# Host-Verified Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the final alert decision from the edge device to the host: the device publishes candidate events, the host re-verifies with its own model plus a dwell window, and commands the alert back.

**Architecture:** Firmware replaces its dwell state machine with a threshold/cooldown publisher (plus a >0.90 immediate-alert escape hatch). The server gains a verify path in `MasterApp._on_event`: legacy events keep today's behavior, new events feed a per-device `VerifyWindow` after host-model confirmation, and a confirmed window publishes `{id}/alert`.

**Tech Stack:** ESP-IDF C firmware; Python 3.12 server (paho-mqtt, pydantic-settings, pytest, YOLO via existing `master.detector`).

**Spec:** `docs/superpowers/specs/2026-10-26-host-verified-alerts-design.md`

## Global Constraints

- Alert threshold constant `0.90` and alert cooldown `5` s are identical on device and host; they are constants, not config.
- Event-send rate cap on device = existing `cooldown_s` config, set to 1.
- Legacy events (`dwell_s > 0` or `first_seen_ms < alert_ms`) keep today's behavior: recorded directly, never verified, never commanded.
- Unsynced device timestamps (`alert_ms == 0`) use server receive time for the window; sync mid-window resets the window.
- Verified warning row: `ts` = confirming event device time (server time when unsynced), `first_seen` = window start, `max_conf` = host confidence, snapshot = confirming JPEG, `mark_frame` only when synced.
- Host alert payload = `protocol.alert_payload(1)` on `protocol.topic(mac, "alert")`.
- Device id `ctu-1` must be accepted by the CLI (no 12-hex requirement).
- All commits end with the session's attribution lines.

## Review Focus

1. **Host restart mid-window**: window state is per-process; after restart the window must reset cleanly, not confirm from stale state. Task 2 test: fresh `MasterApp` never confirms from pre-restart events.
2. **Unsynced device clock**: `alert_ms == 0` events must still be able to confirm using server time. Task 2 test: two events 6 s apart with zero timestamps confirm a 5 s window.
3. **Legacy firmware double-siren**: a legacy event must record a warning and never publish an alert command. Task 2 test: legacy event produces a warning row and `publish` is not called.
4. **Cooldown on host commands**: two qualifying windows within `verify_alert_cooldown_s` produce at most one publish. Task 2 test: second confirmation within 5 s does not publish.
5. **Event flood boundedness**: device sends at most one event per `cooldown_s`; the existing 4-deep event queue drops oldest when full. Task 4 test: host-test harness check that `cooldown_s` gates `event_raise` (if harness reaches `stream.c`; otherwise verified by manual flash smoke in Task 5).

---

### Task 1: Server verify settings

**Files:**
- Modify: `server/master/settings.py`
- Modify: `server/.env.example`
- Modify: `server/compose.yaml`
- Test: `server/tests/test_settings.py`

**Interfaces:**
- Produces: `Settings` fields `verify_threshold: float`, `verify_dwell_s: float`, `verify_max_gap_s: float`, `verify_alert_cooldown_s: float` (all `float`, env names `PEDESTRIAN_VERIFY_THRESHOLD`, `PEDESTRIAN_VERIFY_DWELL_S`, `PEDESTRIAN_VERIFY_MAX_GAP_S`, `PEDESTRIAN_VERIFY_ALERT_COOLDOWN_S`).

- [ ] **Step 1: Write failing test** — in `server/tests/test_settings.py` add a test that builds `Settings(_env_file=None)` with the four `PEDESTRIAN_VERIFY_*` env vars set and asserts the four field values (0.9, 6.0, 2.0, 7.0) and that defaults are 0.8, 5.0, 3.0, 5.0 when unset.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings.py -v`
Expected: FAIL, `Settings` has no such fields.

- [ ] **Step 3: Add the four fields to `Settings` in `server/master/settings.py`**

Defaults exactly: `verify_threshold: float = 0.8`, `verify_dwell_s: float = 5.0`, `verify_max_gap_s: float = 3.0`, `verify_alert_cooldown_s: float = 5.0`.

- [ ] **Step 4: Document in `.env.example` and pass through `compose.yaml`**

`.env.example`: add the four `PEDESTRIAN_VERIFY_*` lines with their defaults and one-line comments. `compose.yaml`: add the four env vars to the `master` service environment block.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_settings.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add server/master/settings.py server/.env.example server/compose.yaml server/tests/test_settings.py
git commit -m "feat(server): add host verify settings for alert verification"
```

---

### Task 2: Host verify flow in MasterApp

**Files:**
- Modify: `server/master/app.py`
- Test: `server/tests/test_app.py` (extend), `server/tests/test_events.py` if event fixtures live there

**Interfaces:**
- Consumes: `Settings.verify_*` fields (Task 1); `protocol.parse_event`, `protocol.alert_payload`, `protocol.topic` (existing); `self.detector.person_confidence(jpeg) -> float` (existing).
- Produces:
  - `class VerifyWindow:` constructor `VerifyWindow(dwell_s: float, max_gap_s: float)`; method `feed(ts: float) -> bool` (True = dwell met and window reset; gap > max_gap restarts the window); method `reset()`.
  - `MasterApp.__init__` gains keyword params `verify_threshold: float`, `verify_dwell_s: float`, `verify_max_gap_s: float`, `verify_alert_cooldown_s: float`, `publish: Callable[[str, bytes], None] | None = None`.
  - `_on_event` implements the spec's host flow (legacy branch, reject, window, command, immediate bypass).

- [ ] **Step 1: Write failing tests** — in `server/tests/test_app.py` add (use existing fake detector/EventStore fixtures):
  - `test_verify_rejects_below_threshold`: host score 0.7 (< 0.8) → no warning row, no publish.
  - `test_verify_confirms_after_dwell`: events at t=0,2,5 s with host score 0.85 → one publish to `ctu-1/alert` with `alert_payload(1)`, one warning row with `max_conf == 0.85`, `first_seen == window start`.
  - `test_verify_gap_restarts_window`: events t=0, 7 s (gap > max_gap 3 s) → no publish.
  - `test_verify_unsynced_clock_uses_server_time`: two events 6 s apart with `alert_ms == 0` → publish (window spans 5 s in server time).
  - `test_verify_legacy_event_records_directly`: event with `dwell_s > 0` → warning row, `publish` never called.
  - `test_verify_cooldown_gates_second_command`: two confirmed windows 2 s apart → exactly one publish.
  - `test_verify_immediate_bypass`: event `max_score > 0.90` → warning row, no host model call, no publish.
  - `test_verify_fresh_app_never_confirms_stale_window`: brand-new `MasterApp` gets no events → nothing; then first event alone → no publish (Review Focus 1).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v`
Expected: FAIL (missing `VerifyWindow`, new constructor params).

- [ ] **Step 3: Implement `VerifyWindow` and the `_on_event` verify flow in `server/master/app.py`**

Window state per device: `dict[str, VerifyWindow]`, `dict[str, bool]` (clock synced), `dict[str, float]` (last command time). Verify flow per spec: legacy check first (`ev.dwell_s > 0 or ev.first_seen_ms < ev.alert_ms`), then host model, then window feed with server time when unsynced, command gated by `verify_alert_cooldown_s`, warning row values per Global Constraints. Wire `publish` from `main()`: pass a lambda or the client's `publish` method.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_app.py tests/test_events.py -v`
Expected: PASS (old tests untouched by legacy branch).

- [ ] **Step 5: Commit**

```bash
git add server/master/app.py server/tests/test_app.py server/tests/test_events.py
git commit -m "feat(server): verify device alert candidates with host model and dwell"
```

---

### Task 3: CLI accepts any device id

**Files:**
- Modify: `server/master/cli.py`
- Test: `server/tests/test_cli.py`

**Interfaces:**
- Produces: `master.cli build_message(["alert", "ctu-1"])` returns `("ctu-1/alert", alert_payload(1), 1, False)`.

- [ ] **Step 1: Write failing test** — in `server/tests/test_cli.py`: `build_message(["alert", "ctu-1"])` succeeds and returns topic `ctu-1/alert`; `build_message(["alert", "a/b"])` raises `ProtocolError`; empty id raises `ProtocolError`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL, `mac must be 12 lowercase hex digits`.

- [ ] **Step 3: Relax `_MAC_RE` in `server/master/cli.py`**

Replace the 12-hex regex with a non-empty, no-`/` id check (e.g. `^[^/]+$`), keep the same error message style.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/master/cli.py server/tests/test_cli.py
git commit -m "fix(server): accept non-MAC device ids in CLI"
```

---

### Task 4: Firmware candidate publisher

**Files:**
- Modify: `firmware/main/event.h`, `firmware/main/event.c`
- Modify: `firmware/main/stream.c`
- Test: `firmware/test/host/` — extend if the harness reaches `event_raise`; otherwise build check only (see Step 4)

**Interfaces:**
- Consumes: `mqtt_link_publish("event", ...)` (existing), `led_person/led_alert`, `audio_play` (existing).
- Produces: `void event_raise(float score, uint64_t capture_ms, const uint8_t *jpeg, size_t len)` — always emits `alert_ms = capture_ms`, `first_seen_ms = capture_ms`, `dwell_s = 0`, `max_score = score`. Constants in `stream.c`: `ALERT_THRESHOLD 0.90f`, `ALERT_COOLDOWN_S 5`.

- [ ] **Step 1: Change `event_raise` signature in `firmware/main/event.h` + `event.c`**

Drop the `dwell_alert_t` parameter; build `msg_event_t` from `(score, capture_ms)` per the Interfaces block. Keep queue/Ack machinery unchanged. Update the only caller temporarily to compile (stream.c still uses old call shape in this step — no: change both files in this step so the tree compiles; the stream.c logic change is Step 3).

- [ ] **Step 2: Replace the dwell block in `firmware/main/stream.c` `process_frame()`**

New logic: `score >= cfg.threshold` → if `cooldown_s` elapsed since last send → `event_raise(score, capture_ms, fb->buf, fb->len)`; if `score > ALERT_THRESHOLD` and `ALERT_COOLDOWN_S` elapsed since last local alert → `led_alert()` + `audio_play(1)`. Remove `dwell_update`/`dwell_init` calls from the stream path; `send_frame` dwell argument becomes 0. Keep `led_person(score >= cfg.threshold)`.

- [ ] **Step 3: Build firmware**

Run: `idf.py build` (ESP-IDF env per repo workflow)
Expected: build succeeds, `pedestrian_edge.bin` produced.

- [ ] **Step 4: Run firmware host tests**

Run: firmware host test target (`firmware/test/host` build + run, per repo workflow)
Expected: existing tests PASS; update any test calling `event_raise` with the old signature.

- [ ] **Step 5: Commit**

```bash
git add firmware/main/event.c firmware/main/event.h firmware/main/stream.c firmware/test/host/
git commit -m "feat(firmware): publish candidate events on threshold, alert only above 0.90"
```

---

### Task 5: End-to-end smoke and deploy

**Files:**
- Modify: none (config via CLI)

**Interfaces:**
- Consumes: Task 2 server, Task 4 firmware, device on `ctu-1` topics.

- [ ] **Step 1: Flash firmware to the device (COM19)**

Run: `idf.py -p COM19 flash` per repo workflow. Device must log `running as ctu-1`, connect, and show `subscribed (msg N)` lines.

- [ ] **Step 2: Set device config**

Run: `python -m master.cli config ctu-1 threshold=0.3 cooldown_s=1`
Expected: `sent ctu-1/config {...}`.

- [ ] **Step 3: Manual scene test**

Person walks in front of camera: device sends `ctu-1/event` ~1/s, host confirms after 5 s dwell, siren plays once per 5 s cooldown. Very close object with device score > 0.90: immediate siren, warning recorded, no double siren.

- [ ] **Step 4: Deploy server changes** (user-run on the Docker host)

Run: `docker compose up -d --build` with the new `PEDESTRIAN_VERIFY_*` values in `.env`.

- [ ] **Step 5: Commit any config/doc leftovers**

```bash
git add server/.env.example docs/superpowers/specs/2026-10-26-host-verified-alerts-design.md docs/superpowers/plans/2026-10-26-host-verified-alerts.md
git commit -m "docs: host-verified alerts design and plan"
```
