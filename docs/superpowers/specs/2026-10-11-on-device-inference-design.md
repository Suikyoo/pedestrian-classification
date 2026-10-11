# On-Device Inference and Alerting — Design

Date: 2026-10-11
Status: Draft for review
Branch: `feat/on-device-inference`
Supersedes parts of: `2026-09-29-pedestrian-alert-design.md` (§4 protocol, §5 detection and alert logic, §6 stream loop)

## 1. Goal

Move pedestrian detection and the dwell/alert decision from the master server onto each ESP32-S3 edge device. A device detects pedestrians with an INT8 model, decides by itself when a pedestrian has stayed in view long enough, and plays the alert clip without any server involvement. The master becomes optional and supervisory: configuration, status, the dashboard, and an opt-in stream mode for debugging and data collection.

### Why

1. **LTE data cost.** Today every frame goes to the master (≈ 3 GB/day per device at VGA, 1 frame/s). With on-device detection, an empty scene sends nothing except the 60 s status heartbeat.
2. **Independence from the server.** Alerts work when the network, broker, or master is down.
3. **Learning.** This is the first step of an on-device TinyML pipeline. Sub-project 2 (a separate spec) trains and quantizes our own model to replace the prebuilt one.

### Success criteria

- A person in view for `dwell_s` seconds makes the device play the alert, with the network disconnected.
- A person passing through in less than `dwell_s` seconds does not trigger an alert.
- One missed or failed detection does not restart the dwell timer (same `max_gap_s` rule as today).
- The alert does not repeat more often than `cooldown_s`.
- With `streaming` off and nobody in view, the device publishes nothing except `status` and `online`.
- Every alert reaches the dashboard as a warning with a snapshot, also when it happened while the device was offline (bounded queue, §4.3).
- A device appears on the dashboard from its status alone, without streaming frames.
- Decode plus inference takes ≤ 250 ms per frame at VGA on the ESP32-S3.

### Out of scope

- Training our own model (sub-project 2: esp-detection / ESPDet-Pico, trained on a separate NVIDIA machine).
- OTA firmware or model updates. The model is flashed into its own partition with `parttool.py`.
- Field auditing of missed detections. With nothing sent for empty scenes, misses are measured offline in sub-project 2.
- Changes to the dashboard visual design beyond the new columns and fields (DESIGN.md tokens apply).

## 2. Decisions

| Decision | Choice | Reason |
|---|---|---|
| Architecture | Full on-device alerting; master optional | Removes the server from the alert path; minimal LTE data |
| Model | Espressif `pedestrian_detect` (`pico_s8_v1_s3`, 224×224, INT8, ≈ 118 ms on S3) | Prebuilt and tuned for the S3; same interface as our own model later |
| "Classification" | Max box score of the detector | Backbone dominates cost; a 224 px detector catches small, far pedestrians better than a 96 px whole-frame classifier |
| Frame pipeline | Capture JPEG, decode at 1/2 scale for inference | Snapshot and stream frames reuse the JPEG; `frame_size` and `jpeg_quality` keep their meaning |
| Empty scene | Send nothing | Goal 1 |
| Alert ownership | Device always; master never publishes `alert` on its own | One source of truth; stream mode only observes |
| Dwell clock | Monotonic `esp_timer`, not SNTP | Alerts need no wall clock; no out-of-order or clock-jump cases |
| Model storage | Flash data partition `pedestrian_det` | Model can be replaced without rebuilding firmware (seam for sub-project 2) |

## 3. Firmware

ESP-IDF **v5.3 or later** (ESP-DL requirement; was v5.1). Development uses v5.5. `idf_component.yml` gains `espressif/esp-dl` and `espressif/pedestrian_detect`, and `idf` becomes `">=5.3"`. `firmware/README.md` changes its supported range from v5.1–v5.4 to v5.3–v5.5.

### 3.1 Data flow

```
stream task, every interval_ms:
  capture JPEG
    -> detect_score(jpeg)                      score in 0..1, or < 0 on failure
    -> dwell_update(now_ms, score)             now_ms from esp_timer
         alert? -> audio_play(1)
                -> event_publish(alert, jpeg)
    -> streaming? -> publish {mac}/image (12-byte header + JPEG)
```

The capture-and-detect loop always runs. `streaming` means only "also send frames to master".

### 3.2 Units

**`components/core/dwell.c`, `core/dwell.h`** (pure C, host-tested). A port of the server's `DwellLogic` for one device:

```c
typedef struct {
    float threshold;      /* score >= threshold is a positive frame */
    uint32_t dwell_ms;
    uint32_t max_gap_ms;
    uint32_t cooldown_ms;
} dwell_params_t;

typedef struct {
    int64_t first_seen_ms; /* -1 = none */
    int64_t last_seen_ms;  /* -1 = none */
    int64_t last_alert_ms; /* -1 = none */
    float max_score;
} dwell_t;

typedef struct {
    int64_t first_seen_ms;
    int64_t alert_ms;
    float max_score;
} dwell_alert_t;

void dwell_init(dwell_t *d);
/* Returns true and fills *out when an alert fires. now_ms must not decrease. */
bool dwell_update(dwell_t *d, const dwell_params_t *p, int64_t now_ms, float score, dwell_alert_t *out);
/* Milliseconds the current pedestrian run has lasted (0 if none). */
uint32_t dwell_current_ms(const dwell_t *d);
```

Rules, unchanged from the original spec §5 except the removed out-of-order step:

1. If a run is active and `now_ms - last_seen_ms > max_gap_ms`, end the run (clear `first_seen_ms`, `last_seen_ms`, `max_score`).
2. If `score < threshold` (including a failed detection, `score < 0`): return false.
3. Positive: set `first_seen_ms` if unset; set `last_seen_ms = now_ms`; update `max_score`.
4. If `now_ms - first_seen_ms >= dwell_ms` and (`last_alert_ms` unset or `now_ms - last_alert_ms >= cooldown_ms`): set `last_alert_ms`, fill `*out`, return true.

Changing dwell parameters at runtime does not reset the state.

**`main/detect.cpp`, `main/detect.h`** (the only C++ file). A C facade over ESP-DL:

```c
esp_err_t detect_init(void);                          /* load model from partition "pedestrian_det" */
float detect_score(const uint8_t *jpeg, size_t len);  /* max pedestrian score 0..1; < 0 on failure */
```

`detect_score` decodes the JPEG at 1/2 scale into a PSRAM RGB buffer (reused between calls), runs `PedestrianDetect`, and returns the highest result score, or 0 when there are no results. If ESP-DL's JPEG helper does not support scaled decode, the plan uses `esp_new_jpeg` directly. `detect_init` failure is logged and the device keeps running: every frame then counts as failed.

**`main/stream.c`** (changed). The loop described in §3.1. The device keeps one `dwell_t`. The current capture timestamp (`timesync_capture_ms()`) is used only for reporting. If `detect_score` fails 5 frames in a row, the device logs an error and reports `detect_ok: false` in status until a frame succeeds.

**`main/event.c`, `main/event.h`** (new). Formats and publishes `{mac}/event` (§4.2). It uses `esp_mqtt_client_enqueue` so an event raised while disconnected is delivered after reconnect. At most 4 undelivered events are kept; when a fifth is raised, the oldest is dropped and a warning is logged.

**`components/core/devcfg.c`** (changed). New fields and defaults (defaults match the current server `.env`):

| Field | Type | Range | Default |
|---|---|---|---|
| `threshold` | float | 0.05–0.99 | 0.6 |
| `dwell_s` | float | 0–600 | 5 |
| `max_gap_s` | float | 0.5–60 | 3 |
| `cooldown_s` | float | 0–3600 | 30 |

`streaming` now defaults to `false`. The NVS blob layout changes, so its version is bumped; a blob with an older version is ignored and the defaults are used.

**`components/core/msg.c`** (changed). Status JSON gains `detect_ok`, `threshold`, `dwell_s`, `max_gap_s`, `cooldown_s`. A new formatter builds the event JSON.

**`components/core/proto.c`** (changed). `PROTO_HEADER_SIZE` becomes 12; `proto_pack_header` takes `capture_ms`, `score`, and `dwell_ms` (§4.1).

**`partitions.csv`** (changed). Add a data partition named `pedestrian_det`, 1 MB, after `factory`, with the subtype the `pedestrian_detect` component's example uses. The plan checks the `.espdl` file size against 1 MB. Flash 8 MB: factory 4 MB + model 1 MB fits.

**`main.c`** (changed). Calls `detect_init()` after `camera_init()`, before the stream task starts.

## 4. Protocol changes

Firmware and server ship together from this repository, so these changes are breaking and need no compatibility mode.

### 4.1 `{mac}/image` (device → server, QoS 0)

Sent only while `streaming` is true. Header is 12 bytes, little-endian:

| Offset | Type | Field |
|---|---|---|
| 0 | `uint64` | `capture_ms` (Unix ms from SNTP; 0 if not synced) |
| 8 | `uint16` | `score` in permille (0–1000); `0xFFFF` = detection failed |
| 10 | `uint16` | `dwell_ds`: current dwell in deciseconds, saturating at 65535 |

JPEG bytes follow.

### 4.2 `{mac}/event` (new, device → server, QoS 1, not retained)

```
uint16 LE  json_len
json_len   UTF-8 JSON: {"alert_ms": 1760190000000, "first_seen_ms": 1760189994800,
                        "dwell_s": 5.2, "max_score": 0.83}
rest       snapshot JPEG (the frame that triggered the alert)
```

`alert_ms` is the `capture_ms` of the alerting frame. `first_seen_ms = alert_ms - dwell_ms`, with `dwell_ms` measured on the monotonic dwell clock. When SNTP is not synced both are 0; the server then uses its receive time for `alert_ms` and `alert_ms - dwell_s` for `first_seen_ms`.

### 4.3 Delivery while offline

The alert sound never waits for the network. The event is queued (§3.2, newest 4 kept) and delivered after reconnect.

### 4.4 `{mac}/config` and `{mac}/status`

Config gains the optional fields `threshold`, `dwell_s`, `max_gap_s`, `cooldown_s` (ranges in §3.2). Status gains `detect_ok` (bool) and the four active values. The device's status is the source of truth for its active settings.

`{mac}/alert`, `{mac}/cmd`, `{mac}/online` are unchanged. A manual `alert` from the CLI plays the clip and does not change dwell state.

## 5. Server

- **Remove `master/logic.py`** and `tests/test_logic.py`. Remove `ALERT_DWELL_SECONDS`, `MAX_GAP_SECONDS`, and `ALERT_COOLDOWN_SECONDS` from settings and `.env.example`. `PEDESTRIAN_CONF_THRESHOLD` stays: it is the YOLO cutoff for stream-mode frames.
- **`protocol.py`**: parse the 12-byte image header into `(capture_ms, score | None, dwell_s)`; parse event payloads; reject a payload shorter than its header or with a JSON length past the end. `validate_config` accepts the four new float fields with the ranges from §3.2.
- **`app.py`**: subscribe to `+/event` as well. An event is written with `events.record(mac, ...)` using the device's values (`max_conf` stores the device's `max_score`). Stream-mode frames are still scored by YOLO and written with `record_inference`, which now also stores the device score and the device's dwell. Master never publishes `alert` by itself. `status` and `online` messages update the `devices` table.
- **`events.py`**:
  - `inferences` gains a nullable `device_score` column (migration with `ALTER TABLE` when missing). `dwell_s` now comes from the device's image header. `alerted` is true when the device has an event whose `alert_ms` equals the frame's `capture_ms` (the event snapshot is that frame). Event and frame can arrive in either order: recording a frame checks for a matching event, and recording an event marks a matching frame. With `capture_ms` 0 (clock not synced) frames are never marked.
  - New `devices` table: `mac` (primary key), `online` (bool), `status` (last status JSON text), `last_seen_ts`.
- **`web.py`**:
  - `/api/devices` reads the `devices` table, joined with the latest inference (if any) and the latest warning. A device that never streamed is listed.
  - `/api/devices` exposes each device's active `threshold`, `dwell_s`, `max_gap_s`, `cooldown_s`, and `detect_ok` from its status.
  - `/api/inferences` adds `device_score`.
  - `/api/config` keeps only `threshold` (YOLO) and `history`.
- **Dashboard (`static/`)**: device rows show online state, the device's threshold and dwell, and the last warning. The frames table gains a "device score" column next to the YOLO score. Existing DESIGN.md tokens and components only.
- **`cli.py`**: `config` accepts the new fields.
- **`tools/fake_device.py`**: sends 12-byte image headers and can publish an event.

## 6. Error handling

| Failure | Behavior |
|---|---|
| Model partition missing or invalid | Log error at boot; frames count as failed; `detect_ok: false`; no alerts. Device stays online for config and streaming. |
| JPEG decode or inference failure | Frame counts as failed (negative for dwell); after 5 in a row, log error and set `detect_ok: false` |
| Network down at alert time | Clip plays; event queued (newest 4) |
| Event queue full | Oldest event dropped, warning logged |
| Malformed event or image on server | Log warning with `mac`; drop message |
| SQLite error on server | Log error; message dropped; no effect on the device |

## 7. Testing

### Host tests (`firmware/test/host/run.sh`)

- `test_dwell.c`: every relevant case from `test_logic.py`: dwell reached; short pass gives no alert; one negative or failed frame inside the gap does not reset; a gap over `max_gap_s` resets; cooldown blocks a repeat and allows one after it; parameter change keeps state.
- `test_devcfg.c`: new fields: defaults, partial JSON, out-of-range value rejects the whole update, float parsing.
- `test_proto.c`: 12-byte header packing, including `0xFFFF` and saturated `dwell_ds`.
- `test_msg.c`: status JSON with the new fields; event JSON.

### Server tests (pytest)

- `test_protocol.py`: 12-byte header; event payload parse; truncated payloads and bad JSON length rejected; new config fields validated.
- `test_app.py`: an event is recorded with the device's values; a stream frame records both YOLO and device scores; master never publishes `alert` by itself; status and online update `devices`.
- `test_events.py`: `device_score` migration on an old database; `devices` table upsert.
- `test_web.py`: a device with only status appears in `/api/devices` with its active settings; `/api/inferences` returns `device_score`.
- `test_integration.py`: `fake_device.py` sends an event; `/api/alerts` returns it with a snapshot.

### On-device checklist (added to `firmware/README.md`)

1. Flash the firmware, then the model: `parttool.py write_partition --partition-name pedestrian_det --input <model>.espdl`. Boot log shows the model loaded and the per-frame decode and inference time (target ≤ 250 ms at VGA).
2. Empty scene, `streaming` off: the broker shows only `status` and `online` traffic.
3. Stand in view for at least `dwell_s`: the clip plays; the dashboard shows a warning with a snapshot.
4. Walk through in less than `dwell_s`: no alert.
5. Disconnect the network, stand in view: the clip plays; the warning appears after reconnect.
6. `python -m master.cli start <mac>`: frames appear on the dashboard with YOLO and device scores side by side.

Accepted risk: the prebuilt model's accuracy on our camera views is judged only by watching stream-mode scores. A proper offline evaluation belongs to sub-project 2.
