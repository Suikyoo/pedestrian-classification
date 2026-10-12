# On-Device Inference and Alerting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each ESP32-S3 device detects pedestrians with Espressif's INT8 `pedestrian_detect` model, runs the dwell/alert rule itself, plays the alert locally, and reports alerts to an optional master that only records and displays.

**Architecture:** Pure, host-tested C in `firmware/components/core` gains the dwell state machine, new config fields, the 12-byte image header, and the event payload. A single C++ file (`firmware/main/detect.cpp`) wraps ESP-DL. The stream task becomes capture → detect → dwell → (alert + queued event) → (optional frame). The Python master drops its dwell logic, ingests `{mac}/event`, keeps YOLO scoring for opt-in stream frames, and tracks devices from `status`/`online`.

**Tech Stack:** ESP-IDF v5.5 (minimum v5.3), ESP-DL `~3.3`, `espressif/pedestrian_detect`, C11 host tests (MinGW gcc 6.3), Python 3.11, paho-mqtt 2, FastAPI, SQLite, vanilla JS dashboard.

**Spec:** `docs/superpowers/specs/2026-10-11-on-device-inference-design.md`

## Global Constraints

- ESP-IDF `>=5.3`; development uses v5.5. `firmware/README.md` states v5.3–v5.5.
- Model lives in a data partition named exactly `pedestrian_det`, 1 MB.
- `detect.cpp` is the only C++ file in the firmware. Everything in `components/core/` stays pure C with no ESP-IDF headers (it is compiled on the host by `firmware/test/host/run.sh` with `-std=c11 -Wall -Wextra -Werror`).
- The host compiler is MinGW gcc 6.3: `printf` has **no** `%llu`/`%lld`. Format 64-bit integers with a helper, never with `%ll*`, in `components/core/`.
- Image header: 12 bytes little-endian `uint64 capture_ms`, `uint16 score` permille (0–1000, `0xFFFF` = detection failed), `uint16 dwell_ds` (deciseconds, saturating at 65535).
- Event payload: `uint16` LE JSON length, JSON `{"alert_ms","first_seen_ms","dwell_s","max_score"}`, then the snapshot JPEG.
- Config ranges: `threshold` 0.05–0.99 (default 0.6), `dwell_s` 0–600 (5), `max_gap_s` 0.5–60 (3), `cooldown_s` 0–3600 (30). `streaming` defaults to `false`.
- Dwell uses the monotonic `esp_timer` clock in ms; SNTP time is used only for reported values.
- Master never publishes `{mac}/alert` on its own. The CLI `alert` command still exists.
- At most 4 undelivered events are kept on the device; when full, the oldest one not currently being sent is dropped.
- Dashboard: existing DESIGN.md tokens and classes only; `textContent` only (a test forbids `innerHTML`); no external resources.
- Server tests run from `server/` with the main checkout's venv: `D:/pedestrian_classification/server/.venv/Scripts/python -m pytest -q` (cwd first on `sys.path`, so the worktree's `master` package is the one imported). Below this is written `$PY -m pytest`.
- Firmware host tests: `sh firmware/test/host/run.sh`.
- ESP-IDF is **not** installed on the development PC. Firmware builds (`idf.py build`) run on the user's ESP-IDF machine; tasks 5 and 6 end with a human checkpoint.

## Review Focus

1. **Model partition empty or missing** (fresh board flashed with `app-flash` only, or a wrong partition table): the device must boot, stay online, report `detect_ok: false`, and never crash-loop. Owner: Task 5 (`detect_init` partition guard) and Task 6 (`track_detect`); checked on the device in the Task 6 checkpoint.
2. **Event raised while the previous event is being published** (cooldown 0 on a flaky link): no use-after-free; the in-flight entry is never dropped. Owner: Task 6 (`event.c` keeps `s_sending`; drop index 1 when sending). Reviewed by reading; no host test (FreeRTOS code).
3. **Retained `status`/`online` delivered when master starts**: must not make a long-dead device look "seen just now". Owner: Task 9 test `test_retained_status_does_not_bump_seen` and `test_online_messages`.
4. **Untrusted status JSON** (`"threshold": "high"`, `"detect_ok": 1`, invalid JSON): `/api/devices` returns `None` for those fields instead of crashing or passing the wrong type to the dashboard. Owner: Task 10 test `test_status_fields_type_checked`.
5. **Event and stream frame arriving in either order, or with an unsynced clock**: the frame is marked `alerted` in both orders and never when `capture_ms` is 0. Owner: Task 8 tests `test_frame_then_event_marks_frame`, `test_event_then_frame_marks_frame`; Task 9 test `test_unsynced_frame_uses_server_clock_and_never_matches`.

---

## File Map

Firmware (`firmware/`):

| File | Change | Responsibility |
|---|---|---|
| `components/core/include/core/devcfg.h`, `devcfg.c` | Modify | Detection config fields, `streaming` default false |
| `components/core/include/core/dwell.h`, `dwell.c` | Create | Pure dwell/alert state machine |
| `components/core/include/core/proto.h`, `proto.c` | Modify | 12-byte header, event payload packing |
| `components/core/include/core/msg.h`, `msg.c` | Modify | Status fields, event JSON |
| `components/core/CMakeLists.txt` | Modify | Add `dwell.c` |
| `test/host/test_dwell.c` | Create | Dwell tests |
| `test/host/test_devcfg.c`, `test_proto.c`, `test_msg.c`, `test_main.c` | Modify | Tests for the above |
| `main/detect.h`, `main/detect.cpp` | Create | ESP-DL facade: model load, JPEG → max score |
| `main/event.h`, `main/event.c` | Create | Bounded event queue and publisher task |
| `main/stream.c`, `main/stream.h` | Modify | Capture → detect → dwell → alert/event → optional frame |
| `main/status.c` | Modify | New status fields |
| `main/cmd.c` | Modify | Log new config fields |
| `main/config_store.c` | Modify | New NVS key for the new struct layout |
| `main/main.c` | Modify | `detect_init()`, `event_start()` |
| `main/CMakeLists.txt`, `main/idf_component.yml` | Modify | New sources, ESP-DL deps |
| `partitions.csv`, `sdkconfig.defaults` | Modify | Model partition, ESP-DL options |
| `README.md` | Modify | IDF range, flashing, checklist |

Server (`server/`):

| File | Change | Responsibility |
|---|---|---|
| `master/protocol.py` | Modify | `ImageFrame`, `DeviceEvent`, 12-byte header, event payload, float config fields |
| `master/events.py` | Modify | `Alert` (moved here), `device_score`, `devices` table, frame/event matching |
| `master/app.py` | Modify | Event/status/online ingest, YOLO for stream frames, no dwell, no publish |
| `master/logic.py`, `tests/test_logic.py` | Delete | Dwell moved to the device |
| `master/settings.py`, `.env.example` | Modify | Drop dwell settings |
| `master/web.py` | Modify | `/api/devices` from `devices`, `/api/config`, `device_score` |
| `master/static/app.js`, `index.html` | Modify | Per-device settings, device score, devices without frames |
| `tools/fake_device.py` | Modify | New header, status, optional event |
| `README.md` (server), `../README.md` | Modify | Describe on-device alerting |
| `tests/*` | Modify | As listed per task |

---

### Task 1: Detection fields in device config

**Files:**
- Modify: `firmware/components/core/include/core/devcfg.h`
- Modify: `firmware/components/core/devcfg.c`
- Test: `firmware/test/host/test_devcfg.c`

**Interfaces:**
- Produces: `devcfg_t` gains `float threshold, dwell_s, max_gap_s, cooldown_s`; `devcfg_defaults()` sets `streaming = false`, `threshold = 0.6f`, `dwell_s = 5.0f`, `max_gap_s = 3.0f`, `cooldown_s = 30.0f`. `devcfg_apply_json`, `devcfg_valid`, `devcfg_equal` cover the new fields.

- [ ] **Step 1: Update the existing tests and add new ones**

In `firmware/test/host/test_devcfg.c`:

Replace `test_defaults` with:

```c
static void test_defaults(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK_INT(c.interval_ms, 1000);
    CHECK_INT(c.jpeg_quality, 12);
    CHECK_INT(c.frame_size, DEVCFG_FRAME_VGA);
    CHECK_INT(c.volume, 80);
    CHECK(!c.streaming); /* empty scenes send nothing until master says start */
    CHECK(c.threshold == 0.6f);
    CHECK(c.dwell_s == 5.0f);
    CHECK(c.max_gap_s == 3.0f);
    CHECK(c.cooldown_s == 30.0f);
}
```

In `test_full_update`, change the last line `CHECK(c.streaming);` to `CHECK(!c.streaming);`.

Replace `test_unknown_fields_ignored` with:

```c
static void test_unknown_fields_ignored(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"volume\":70,\"color\":\"red\",\"streaming\":true}")));
    CHECK_INT(c.volume, 70);
    CHECK(!c.streaming); /* streaming is changed only by start/stop */
}
```

In `test_equal`, change `b.streaming = false;` to `b.streaming = true;`.

Add to the `BAD` array in `test_invalid_rejects_whole_update` (before `"{"`):

```c
        "{\"threshold\":1.0}",
        "{\"threshold\":0.01}",
        "{\"threshold\":\"high\"}",
        "{\"threshold\":true}",
        "{\"dwell_s\":600.5}",
        "{\"dwell_s\":-1}",
        "{\"max_gap_s\":0.4}",
        "{\"max_gap_s\":61}",
        "{\"cooldown_s\":3601}",
        "{\"cooldown_s\":-0.5}",
        "{\"volume\":50,\"threshold\":2}",
```

Add these functions above `void test_devcfg(void)`:

```c
static void test_detection_fields_update(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"threshold\":0.45,\"dwell_s\":2.5,"
                                  "\"max_gap_s\":1,\"cooldown_s\":0}")));
    CHECK(c.threshold == 0.45f);
    CHECK(c.dwell_s == 2.5f);
    CHECK(c.max_gap_s == 1.0f);
    CHECK(c.cooldown_s == 0.0f);
    CHECK_INT(c.volume, 80); /* untouched */
}

static void test_detection_bounds_accepted(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"threshold\":0.05,\"dwell_s\":0,\"max_gap_s\":0.5,\"cooldown_s\":0}")));
    CHECK(devcfg_valid(&c));
    CHECK(devcfg_apply_json(&c, J("{\"threshold\":0.99,\"dwell_s\":600,\"max_gap_s\":60,\"cooldown_s\":3600}")));
    CHECK(devcfg_valid(&c));
    CHECK(c.threshold == 0.99f);
    CHECK(c.cooldown_s == 3600.0f);
}

static void test_detection_fields_valid(void)
{
    devcfg_t c;
    devcfg_defaults(&c); c.threshold = 0.04f;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.threshold = 1.0f;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.threshold = 0.0f / 0.0f; /* NaN */
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.dwell_s = 601.0f;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.max_gap_s = 0.0f;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.cooldown_s = -1.0f;
    CHECK(!devcfg_valid(&c));
}

static void test_equal_covers_detection_fields(void)
{
    devcfg_t a, b;
    devcfg_defaults(&a);
    devcfg_defaults(&b);
    b.dwell_s = 6.0f;
    CHECK(!devcfg_equal(&a, &b));
    devcfg_defaults(&b);
    b.threshold = 0.7f;
    CHECK(!devcfg_equal(&a, &b));
}
```

Register them at the end of `test_devcfg()`:

```c
    test_detection_fields_update();
    test_detection_bounds_accepted();
    test_detection_fields_valid();
    test_equal_covers_detection_fields();
```

- [ ] **Step 2: Run the host tests and see them fail to compile**

Run: `sh firmware/test/host/run.sh`
Expected: compile error, `'devcfg_t {aka struct <anonymous>}' has no member named 'threshold'`.

- [ ] **Step 3: Implement**

`firmware/components/core/include/core/devcfg.h` — replace the struct with:

```c
/* Runtime config. Persisted in NVS; updated by {id}/config and start/stop. */
typedef struct {
    uint32_t interval_ms;     /* 100..3600000 */
    uint8_t jpeg_quality;     /* 0..63, lower = better */
    devcfg_frame_t frame_size;
    uint8_t volume;           /* 0..100 */
    bool streaming;           /* also send frames to master; detection always runs */
    float threshold;          /* 0.05..0.99: a frame with score >= threshold is positive */
    float dwell_s;            /* 0..600: positive run length before an alert */
    float max_gap_s;          /* 0.5..60: no positive frame for longer ends the run */
    float cooldown_s;         /* 0..3600: minimum time between alerts */
} devcfg_t;
```

`firmware/components/core/devcfg.c`:

Replace `devcfg_defaults`:

```c
void devcfg_defaults(devcfg_t *c)
{
    c->interval_ms = 1000;
    c->jpeg_quality = 12;
    c->frame_size = DEVCFG_FRAME_VGA;
    c->volume = 80;
    c->streaming = false;
    c->threshold = 0.6f;
    c->dwell_s = 5.0f;
    c->max_gap_s = 3.0f;
    c->cooldown_s = 30.0f;
}
```

Replace `devcfg_equal`:

```c
bool devcfg_equal(const devcfg_t *a, const devcfg_t *b)
{
    return a->interval_ms == b->interval_ms && a->jpeg_quality == b->jpeg_quality &&
           a->frame_size == b->frame_size && a->volume == b->volume &&
           a->streaming == b->streaming && a->threshold == b->threshold &&
           a->dwell_s == b->dwell_s && a->max_gap_s == b->max_gap_s &&
           a->cooldown_s == b->cooldown_s;
}
```

Add below `read_int`:

```c
/* Reads an optional number field. Returns false only if present and invalid. */
static bool read_float(const cJSON *root, const char *key, double lo, double hi, bool *present, float *out)
{
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(root, key);
    *present = item != NULL;
    if (item == NULL) {
        return true;
    }
    if (!cJSON_IsNumber(item)) {
        return false;
    }
    double v = item->valuedouble;
    if (!(v >= lo && v <= hi)) { /* also rejects NaN */
        return false;
    }
    *out = (float)v;
    return true;
}
```

In `devcfg_apply_json`, after the `volume` block and before the `frame_size` block, add:

```c
    float f = 0.0f;
    ok = ok && read_float(root, "threshold", 0.05, 0.99, &present, &f);
    if (ok && present) {
        next.threshold = f;
    }
    ok = ok && read_float(root, "dwell_s", 0.0, 600.0, &present, &f);
    if (ok && present) {
        next.dwell_s = f;
    }
    ok = ok && read_float(root, "max_gap_s", 0.5, 60.0, &present, &f);
    if (ok && present) {
        next.max_gap_s = f;
    }
    ok = ok && read_float(root, "cooldown_s", 0.0, 3600.0, &present, &f);
    if (ok && present) {
        next.cooldown_s = f;
    }
```

Replace `devcfg_valid`:

```c
bool devcfg_valid(const devcfg_t *c)
{
    return c->interval_ms >= 100 && c->interval_ms <= 3600000 &&
           c->jpeg_quality <= 63 &&
           (unsigned)c->frame_size < DEVCFG_FRAME_COUNT &&
           c->volume <= 100 &&
           c->threshold >= 0.05f && c->threshold <= 0.99f &&
           c->dwell_s >= 0.0f && c->dwell_s <= 600.0f &&
           c->max_gap_s >= 0.5f && c->max_gap_s <= 60.0f &&
           c->cooldown_s >= 0.0f && c->cooldown_s <= 3600.0f;
}
```

- [ ] **Step 4: Run the host tests**

Run: `sh firmware/test/host/run.sh`
Expected: last line `<N> checks, 0 failures` (N > 136).

- [ ] **Step 5: Commit**

```bash
git add firmware/components/core/include/core/devcfg.h firmware/components/core/devcfg.c firmware/test/host/test_devcfg.c
git commit -m "feat(firmware): detection settings in device config, streaming off by default"
```

---

### Task 2: Dwell state machine in core

**Files:**
- Create: `firmware/components/core/include/core/dwell.h`
- Create: `firmware/components/core/dwell.c`
- Modify: `firmware/components/core/CMakeLists.txt`
- Create: `firmware/test/host/test_dwell.c`
- Modify: `firmware/test/host/test_main.c`

**Interfaces:**
- Consumes: `devcfg_t` from Task 1.
- Produces (used by Task 6):

```c
typedef struct { float threshold; uint32_t dwell_ms, max_gap_ms, cooldown_ms; } dwell_params_t;
typedef struct { int64_t first_seen_ms, last_seen_ms, last_alert_ms; float max_score; } dwell_t;
typedef struct { int64_t first_seen_ms, alert_ms; float max_score; } dwell_alert_t;
void dwell_init(dwell_t *d);
void dwell_params_from_cfg(dwell_params_t *p, const devcfg_t *c);
bool dwell_update(dwell_t *d, const dwell_params_t *p, int64_t now_ms, float score, dwell_alert_t *out);
uint32_t dwell_current_ms(const dwell_t *d);
```

- [ ] **Step 1: Write the failing tests**

Create `firmware/test/host/test_dwell.c`:

```c
#include "core/dwell.h"
#include "minitest.h"

#define POS 0.9f
#define NEG 0.1f

static const dwell_params_t P = {.threshold = 0.6f, .dwell_ms = 5000, .max_gap_ms = 3000, .cooldown_ms = 30000};

static int s_alerts;
static int64_t s_at[8];
static dwell_alert_t s_last;

static void start(dwell_t *d)
{
    dwell_init(d);
    s_alerts = 0;
}

/* One frame at `sec` seconds on the monotonic clock. */
static void frame(dwell_t *d, int64_t sec, float score)
{
    dwell_alert_t a;
    if (dwell_update(d, &P, sec * 1000, score, &a)) {
        if (s_alerts < 8) {
            s_at[s_alerts] = a.alert_ms;
        }
        s_alerts++;
        s_last = a;
    }
}

/* One frame per second for seconds [from, to). */
static void run(dwell_t *d, int64_t from, int64_t to, float score)
{
    for (int64_t s = from; s < to; s++) {
        frame(d, s, score);
    }
}

static void test_alert_when_dwell_reached(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 6, POS);
    CHECK_INT(s_alerts, 1);
    CHECK_INT(s_at[0], 5000);
}

static void test_no_alert_before_dwell(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 5, POS);
    CHECK_INT(s_alerts, 0);
}

static void test_score_equal_to_threshold_is_positive(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 6, 0.6f);
    CHECK_INT(s_alerts, 1);
}

static void test_gap_longer_than_max_gap_resets(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 3, POS);
    run(&d, 6, 12, POS);
    CHECK_INT(s_alerts, 1);
    CHECK_INT(s_at[0], 11000);
}

static void test_single_negative_frame_does_not_reset(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 3, POS);
    frame(&d, 3, NEG);
    run(&d, 4, 6, POS);
    CHECK_INT(s_alerts, 1);
    CHECK_INT(s_at[0], 5000);
}

static void test_failed_detection_counts_as_negative(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 3, POS);
    frame(&d, 3, -1.0f);
    run(&d, 4, 6, POS);
    CHECK_INT(s_alerts, 1);
    CHECK_INT(s_at[0], 5000);
}

static void test_negatives_longer_than_max_gap_reset(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 2, POS);
    run(&d, 2, 6, NEG);
    run(&d, 6, 12, POS);
    CHECK_INT(s_alerts, 1);
    CHECK_INT(s_at[0], 11000);
}

static void test_cooldown_suppresses_repeats(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 41, POS);
    CHECK_INT(s_alerts, 2);
    CHECK_INT(s_at[0], 5000);
    CHECK_INT(s_at[1], 35000);
}

static void test_alert_carries_first_seen_and_max_score(void)
{
    dwell_t d;
    start(&d);
    frame(&d, 10, 0.7f);
    frame(&d, 11, 0.95f);
    frame(&d, 12, 0.8f);
    run(&d, 13, 16, 0.7f);
    CHECK_INT(s_alerts, 1);
    CHECK_INT(s_last.first_seen_ms, 10000);
    CHECK_INT(s_last.alert_ms, 15000);
    CHECK(s_last.max_score == 0.95f);
}

static void test_current_dwell(void)
{
    dwell_t d;
    start(&d);
    CHECK_INT(dwell_current_ms(&d), 0);
    run(&d, 0, 3, POS);
    CHECK_INT(dwell_current_ms(&d), 2000);
    frame(&d, 3, NEG); /* run continues inside the gap */
    CHECK_INT(dwell_current_ms(&d), 2000);
    frame(&d, 7, POS); /* gap 5 s > 3 s: new run */
    CHECK_INT(dwell_current_ms(&d), 0);
    frame(&d, 8, POS);
    CHECK_INT(dwell_current_ms(&d), 1000);
}

static void test_param_change_keeps_state(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 3, POS);
    dwell_params_t shorter = P;
    shorter.dwell_ms = 3000;
    dwell_alert_t a;
    CHECK(dwell_update(&d, &shorter, 3000, POS, &a));
    CHECK_INT(a.first_seen_ms, 0);
}

static void test_params_from_cfg(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    dwell_params_t p;
    dwell_params_from_cfg(&p, &c);
    CHECK(p.threshold == 0.6f);
    CHECK_INT(p.dwell_ms, 5000);
    CHECK_INT(p.max_gap_ms, 3000);
    CHECK_INT(p.cooldown_ms, 30000);
    c.dwell_s = 0.25f;
    dwell_params_from_cfg(&p, &c);
    CHECK_INT(p.dwell_ms, 250);
}

void test_dwell(void)
{
    test_alert_when_dwell_reached();
    test_no_alert_before_dwell();
    test_score_equal_to_threshold_is_positive();
    test_gap_longer_than_max_gap_resets();
    test_single_negative_frame_does_not_reset();
    test_failed_detection_counts_as_negative();
    test_negatives_longer_than_max_gap_reset();
    test_cooldown_suppresses_repeats();
    test_alert_carries_first_seen_and_max_score();
    test_current_dwell();
    test_param_change_keeps_state();
    test_params_from_cfg();
}
```

In `firmware/test/host/test_main.c`, add `void test_dwell(void);` after `void test_pcm(void);` and call `test_dwell();` after `test_pcm();`.

- [ ] **Step 2: Run and see it fail**

Run: `sh firmware/test/host/run.sh`
Expected: compile error, `core/dwell.h: No such file or directory`.

- [ ] **Step 3: Implement**

Create `firmware/components/core/include/core/dwell.h`:

```c
#pragma once
#include <stdbool.h>
#include <stdint.h>

#include "core/devcfg.h"

/* Dwell rule for one device: alert when a pedestrian is seen continuously for
 * dwell_ms. A positive frame has score >= threshold; a failed detection
 * (score < 0) is negative. Negative frames do not end a run by themselves: the
 * run ends when no positive frame was seen for longer than max_gap_ms. */

typedef struct {
    float threshold;
    uint32_t dwell_ms;
    uint32_t max_gap_ms;
    uint32_t cooldown_ms;
} dwell_params_t;

typedef struct {
    int64_t first_seen_ms; /* -1 = no run */
    int64_t last_seen_ms;  /* -1 = no run */
    int64_t last_alert_ms; /* -1 = never */
    float max_score;
} dwell_t;

typedef struct {
    int64_t first_seen_ms;
    int64_t alert_ms;
    float max_score;
} dwell_alert_t;

void dwell_init(dwell_t *d);
void dwell_params_from_cfg(dwell_params_t *p, const devcfg_t *c);

/* Feed one frame. now_ms is a monotonic clock and must not decrease. Returns
 * true and fills *out when an alert fires. Parameters may change between calls
 * without resetting the state. */
bool dwell_update(dwell_t *d, const dwell_params_t *p, int64_t now_ms, float score, dwell_alert_t *out);

/* Milliseconds the current run has lasted (0 if there is none). */
uint32_t dwell_current_ms(const dwell_t *d);
```

Create `firmware/components/core/dwell.c`:

```c
#include "core/dwell.h"

static void end_run(dwell_t *d)
{
    d->first_seen_ms = -1;
    d->last_seen_ms = -1;
    d->max_score = 0.0f;
}

void dwell_init(dwell_t *d)
{
    end_run(d);
    d->last_alert_ms = -1;
}

static uint32_t to_ms(float s)
{
    return (uint32_t)(s * 1000.0f + 0.5f);
}

void dwell_params_from_cfg(dwell_params_t *p, const devcfg_t *c)
{
    p->threshold = c->threshold;
    p->dwell_ms = to_ms(c->dwell_s);
    p->max_gap_ms = to_ms(c->max_gap_s);
    p->cooldown_ms = to_ms(c->cooldown_s);
}

bool dwell_update(dwell_t *d, const dwell_params_t *p, int64_t now_ms, float score, dwell_alert_t *out)
{
    if (d->last_seen_ms >= 0 && now_ms - d->last_seen_ms > (int64_t)p->max_gap_ms) {
        end_run(d);
    }
    if (!(score >= p->threshold)) { /* negative, failed (< 0), or NaN */
        return false;
    }
    if (d->first_seen_ms < 0) {
        d->first_seen_ms = now_ms;
    }
    d->last_seen_ms = now_ms;
    if (score > d->max_score) {
        d->max_score = score;
    }
    if (now_ms - d->first_seen_ms < (int64_t)p->dwell_ms) {
        return false;
    }
    if (d->last_alert_ms >= 0 && now_ms - d->last_alert_ms < (int64_t)p->cooldown_ms) {
        return false;
    }
    d->last_alert_ms = now_ms;
    out->first_seen_ms = d->first_seen_ms;
    out->alert_ms = now_ms;
    out->max_score = d->max_score;
    return true;
}

uint32_t dwell_current_ms(const dwell_t *d)
{
    if (d->first_seen_ms < 0 || d->last_seen_ms < 0) {
        return 0;
    }
    return (uint32_t)(d->last_seen_ms - d->first_seen_ms);
}
```

In `firmware/components/core/CMakeLists.txt`, change the `SRCS` line to:

```cmake
idf_component_register(SRCS "backoff.c" "proto.c" "devcfg.c" "msg.c" "dwell.c"
```

- [ ] **Step 4: Run the host tests**

Run: `sh firmware/test/host/run.sh`
Expected: `<N> checks, 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add firmware/components/core/include/core/dwell.h firmware/components/core/dwell.c firmware/components/core/CMakeLists.txt firmware/test/host/test_dwell.c firmware/test/host/test_main.c
git commit -m "feat(firmware): dwell state machine in core"
```

---

### Task 3: 12-byte image header and event payload packing

**Files:**
- Modify: `firmware/components/core/include/core/proto.h`
- Modify: `firmware/components/core/proto.c`
- Modify: `firmware/main/stream.c` (one call, keeps the app compiling)
- Test: `firmware/test/host/test_proto.c`

**Interfaces:**
- Produces:

```c
#define PROTO_HEADER_SIZE 12
#define PROTO_SCORE_FAILED 0xFFFF
void proto_pack_header(uint8_t out[PROTO_HEADER_SIZE], uint64_t capture_ms, float score, uint32_t dwell_ms);
size_t proto_pack_event(uint8_t *out, size_t cap, const char *json, size_t json_len,
                        const uint8_t *jpeg, size_t jpeg_len);
```

- [ ] **Step 1: Write the failing tests**

In `firmware/test/host/test_proto.c`, replace `test_header` with:

```c
static uint64_t le(const uint8_t *p, int n)
{
    uint64_t v = 0;
    for (int i = n - 1; i >= 0; i--) {
        v = (v << 8) | p[i];
    }
    return v;
}

static void test_header(void)
{
    uint8_t h[PROTO_HEADER_SIZE];
    CHECK_INT(PROTO_HEADER_SIZE, 12);

    proto_pack_header(h, 0x0102030405060708ULL, 0.5f, 2000);
    const uint8_t expected[12] = {0x08, 0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01, 0xF4, 0x01, 0x14, 0x00};
    CHECK(memcmp(h, expected, 12) == 0);

    proto_pack_header(h, 1727600000123ULL, 0.8346f, 5150);
    CHECK(le(h, 8) == 1727600000123ULL);
    CHECK_INT(le(h + 8, 2), 835);
    CHECK_INT(le(h + 10, 2), 51);
}

static void test_header_score_edges(void)
{
    uint8_t h[PROTO_HEADER_SIZE];
    proto_pack_header(h, 0, -1.0f, 0);
    CHECK_INT(le(h + 8, 2), PROTO_SCORE_FAILED);
    proto_pack_header(h, 0, 0.0f / 0.0f, 0); /* NaN counts as failed */
    CHECK_INT(le(h + 8, 2), PROTO_SCORE_FAILED);
    proto_pack_header(h, 0, 0.0f, 0);
    CHECK_INT(le(h + 8, 2), 0);
    proto_pack_header(h, 0, 1.0f, 0);
    CHECK_INT(le(h + 8, 2), 1000);
    proto_pack_header(h, 0, 1.7f, 0);
    CHECK_INT(le(h + 8, 2), 1000);
}

static void test_header_dwell_saturates(void)
{
    uint8_t h[PROTO_HEADER_SIZE];
    proto_pack_header(h, 0, 0.5f, 6553500);
    CHECK_INT(le(h + 10, 2), 65535);
    proto_pack_header(h, 0, 0.5f, 7000000);
    CHECK_INT(le(h + 10, 2), 65535);
    proto_pack_header(h, 0, 0.5f, 99);
    CHECK_INT(le(h + 10, 2), 0);
}

static void test_pack_event(void)
{
    const char json[] = "{\"a\":1}";
    const uint8_t jpeg[] = {0xFF, 0xD8, 0x01};
    uint8_t out[32];
    size_t n = proto_pack_event(out, sizeof out, json, 7, jpeg, 3);
    CHECK_INT(n, 12);
    CHECK_INT(le(out, 2), 7);
    CHECK(memcmp(out + 2, json, 7) == 0);
    CHECK(memcmp(out + 9, jpeg, 3) == 0);

    CHECK_INT(proto_pack_event(out, 11, json, 7, jpeg, 3), 0);   /* does not fit */
    CHECK_INT(proto_pack_event(out, sizeof out, json, 0, jpeg, 3), 0); /* no JSON */
    CHECK_INT(proto_pack_event(out, sizeof out, json, 7, jpeg, 0), 0); /* no snapshot */
    CHECK_INT(proto_pack_event(out, (size_t)-1, json, 70000, jpeg, 3), 0); /* JSON too long for u16 */
}
```

Register the new tests in `test_proto()` after `test_header();`:

```c
    test_header_score_edges();
    test_header_dwell_saturates();
    test_pack_event();
```

- [ ] **Step 2: Run and see it fail**

Run: `sh firmware/test/host/run.sh`
Expected: compile error, `too many arguments to function 'proto_pack_header'`.

- [ ] **Step 3: Implement**

In `firmware/components/core/include/core/proto.h`, replace the `PROTO_HEADER_SIZE` define and the `proto_pack_header` declaration with:

```c
/* {id}/image header, little-endian: uint64 capture_ms, uint16 score in permille
 * (0..1000, PROTO_SCORE_FAILED = detection failed), uint16 current dwell in
 * deciseconds (saturates at 65535). */
#define PROTO_HEADER_SIZE 12
#define PROTO_SCORE_FAILED 0xFFFF
```

```c
/* score < 0 or NaN = detection failed; scores above 1 are clamped. */
void proto_pack_header(uint8_t out[PROTO_HEADER_SIZE], uint64_t capture_ms, float score, uint32_t dwell_ms);

/* {id}/event payload: uint16 LE json_len, JSON, JPEG. Returns the total length,
 * or 0 if it does not fit in `cap`, json_len is 0 or > 65535, or jpeg_len is 0. */
size_t proto_pack_event(uint8_t *out, size_t cap, const char *json, size_t json_len,
                        const uint8_t *jpeg, size_t jpeg_len);
```

In `firmware/components/core/proto.c`, replace `proto_pack_header` with:

```c
static void put_le(uint8_t *out, uint64_t v, int n)
{
    for (int i = 0; i < n; i++) {
        out[i] = (uint8_t)(v >> (8 * i));
    }
}

void proto_pack_header(uint8_t out[PROTO_HEADER_SIZE], uint64_t capture_ms, float score, uint32_t dwell_ms)
{
    uint16_t permille;
    if (!(score >= 0.0f)) {
        permille = PROTO_SCORE_FAILED;
    } else if (score >= 1.0f) {
        permille = 1000;
    } else {
        permille = (uint16_t)(score * 1000.0f + 0.5f);
    }
    uint32_t ds = dwell_ms / 100;
    put_le(out, capture_ms, 8);
    put_le(out + 8, permille, 2);
    put_le(out + 10, ds > 0xFFFF ? 0xFFFF : ds, 2);
}

size_t proto_pack_event(uint8_t *out, size_t cap, const char *json, size_t json_len,
                        const uint8_t *jpeg, size_t jpeg_len)
{
    if (json_len == 0 || json_len > 0xFFFF || jpeg_len == 0) {
        return 0;
    }
    if (cap < 2 || json_len > cap - 2 || jpeg_len > cap - 2 - json_len) {
        return 0;
    }
    put_le(out, json_len, 2);
    memcpy(out + 2, json, json_len);
    memcpy(out + 2 + json_len, jpeg, jpeg_len);
    return 2 + json_len + jpeg_len;
}
```

In `firmware/main/stream.c`, change `proto_pack_header(buf, timesync_capture_ms());` to:

```c
    proto_pack_header(buf, timesync_capture_ms(), -1.0f, 0); /* replaced by the detect loop in a later task */
```

- [ ] **Step 4: Run the host tests**

Run: `sh firmware/test/host/run.sh`
Expected: `<N> checks, 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add firmware/components/core/include/core/proto.h firmware/components/core/proto.c firmware/main/stream.c firmware/test/host/test_proto.c
git commit -m "feat(firmware): 12-byte image header with device score, event payload packing"
```

---

### Task 4: Status and event JSON

**Files:**
- Modify: `firmware/components/core/include/core/msg.h`
- Modify: `firmware/components/core/msg.c`
- Test: `firmware/test/host/test_msg.c`

**Interfaces:**
- Produces:

```c
typedef struct { int rssi; int battery_mv; uint32_t uptime_s; bool streaming; const char *fw;
                 bool detect_ok; float threshold, dwell_s, max_gap_s, cooldown_s; } msg_status_t;
typedef struct { uint64_t alert_ms, first_seen_ms; float dwell_s, max_score; } msg_event_t;
int msg_format_status(char *buf, size_t len, const msg_status_t *s);
int msg_format_event(char *buf, size_t len, const msg_event_t *e);
```

- [ ] **Step 1: Write the failing tests**

In `firmware/test/host/test_msg.c`, replace `test_status` with:

```c
static void test_status(void)
{
    msg_status_t s = {.rssi = -71, .battery_mv = 0, .uptime_s = 3600, .streaming = true, .fw = "0.1.0",
                      .detect_ok = true, .threshold = 0.6f, .dwell_s = 5.0f, .max_gap_s = 3.0f,
                      .cooldown_s = 30.0f};
    char buf[256];
    int n = msg_format_status(buf, sizeof buf, &s);
    CHECK_STR(buf, "{\"rssi\":-71,\"battery_mv\":0,\"uptime_s\":3600,\"streaming\":true,\"fw\":\"0.1.0\","
                   "\"detect_ok\":true,\"threshold\":0.6,\"dwell_s\":5,\"max_gap_s\":3,\"cooldown_s\":30}");
    CHECK_INT(n, (long long)strlen(buf));

    s.streaming = false;
    s.detect_ok = false;
    s.dwell_s = 0.25f;
    msg_format_status(buf, sizeof buf, &s);
    CHECK(strstr(buf, "\"streaming\":false") != NULL);
    CHECK(strstr(buf, "\"detect_ok\":false") != NULL);
    CHECK(strstr(buf, "\"dwell_s\":0.25") != NULL);

    char small[16];
    CHECK_INT(msg_format_status(small, sizeof small, &s), -1);
}

static void test_event(void)
{
    msg_event_t e = {.alert_ms = 1790000000123ULL, .first_seen_ms = 1790000000123ULL - 5200,
                     .dwell_s = 5.2f, .max_score = 0.8346f};
    char buf[128];
    int n = msg_format_event(buf, sizeof buf, &e);
    CHECK_STR(buf, "{\"alert_ms\":1790000000123,\"first_seen_ms\":1789999994923,"
                   "\"dwell_s\":5.20,\"max_score\":0.835}");
    CHECK_INT(n, (long long)strlen(buf));

    msg_event_t unsynced = {.alert_ms = 0, .first_seen_ms = 0, .dwell_s = 5.0f, .max_score = 0.7f};
    msg_format_event(buf, sizeof buf, &unsynced);
    CHECK_STR(buf, "{\"alert_ms\":0,\"first_seen_ms\":0,\"dwell_s\":5.00,\"max_score\":0.700}");

    char small[20];
    CHECK_INT(msg_format_event(small, sizeof small, &e), -1);
}
```

Add `test_event();` to the end of `test_msg()`.

- [ ] **Step 2: Run and see it fail**

Run: `sh firmware/test/host/run.sh`
Expected: compile error, `'msg_status_t' has no member named 'detect_ok'`.

- [ ] **Step 3: Implement**

In `firmware/components/core/include/core/msg.h`, replace the `msg_status_t` struct and the `msg_format_status` declaration with:

```c
typedef struct {
    int rssi;
    int battery_mv;
    uint32_t uptime_s;
    bool streaming;
    const char *fw;   /* must not contain quotes or backslashes */
    bool detect_ok;   /* false after repeated detection failures */
    float threshold;  /* active detection settings, from devcfg */
    float dwell_s;
    float max_gap_s;
    float cooldown_s;
} msg_status_t;

/* Format {id}/status JSON. Returns its length, or -1 if it does not fit. */
int msg_format_status(char *buf, size_t len, const msg_status_t *s);

typedef struct {
    uint64_t alert_ms;      /* Unix ms of the alerting frame; 0 if the clock is not synced */
    uint64_t first_seen_ms; /* Unix ms; 0 if the clock is not synced */
    float dwell_s;
    float max_score;
} msg_event_t;

/* Format the JSON part of {id}/event. Returns its length, or -1 if it does not fit. */
int msg_format_event(char *buf, size_t len, const msg_event_t *e);
```

In `firmware/components/core/msg.c`, replace `msg_format_status` with:

```c
int msg_format_status(char *buf, size_t len, const msg_status_t *s)
{
    int n = snprintf(buf, len,
                     "{\"rssi\":%d,\"battery_mv\":%d,\"uptime_s\":%lu,\"streaming\":%s,\"fw\":\"%s\","
                     "\"detect_ok\":%s,\"threshold\":%g,\"dwell_s\":%g,\"max_gap_s\":%g,\"cooldown_s\":%g}",
                     s->rssi, s->battery_mv, (unsigned long)s->uptime_s,
                     s->streaming ? "true" : "false", s->fw, s->detect_ok ? "true" : "false",
                     (double)s->threshold, (double)s->dwell_s, (double)s->max_gap_s,
                     (double)s->cooldown_s);
    return (n > 0 && (size_t)n < len) ? n : -1;
}

/* Decimal text of v. The host's MinGW printf has no %llu, so format by hand. */
static const char *u64_text(uint64_t v, char buf[21])
{
    char *p = buf + 20;
    *p = '\0';
    do {
        *--p = (char)('0' + (int)(v % 10));
        v /= 10;
    } while (v != 0);
    return p;
}

int msg_format_event(char *buf, size_t len, const msg_event_t *e)
{
    char a[21], f[21];
    int n = snprintf(buf, len, "{\"alert_ms\":%s,\"first_seen_ms\":%s,\"dwell_s\":%.2f,\"max_score\":%.3f}",
                     u64_text(e->alert_ms, a), u64_text(e->first_seen_ms, f),
                     (double)e->dwell_s, (double)e->max_score);
    return (n > 0 && (size_t)n < len) ? n : -1;
}
```

Add `#include <stdint.h>` to the includes of `msg.c` if it is not already pulled in through `core/msg.h` (it is; no change needed unless the compiler says otherwise).

- [ ] **Step 4: Run the host tests**

Run: `sh firmware/test/host/run.sh`
Expected: `<N> checks, 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add firmware/components/core/include/core/msg.h firmware/components/core/msg.c firmware/test/host/test_msg.c
git commit -m "feat(firmware): detection fields in status, event JSON"
```

---

### Task 5: ESP-DL pedestrian detector module

**Files:**
- Modify: `firmware/main/idf_component.yml`
- Modify: `firmware/partitions.csv`
- Modify: `firmware/sdkconfig.defaults`
- Create: `firmware/main/detect.h`
- Create: `firmware/main/detect.cpp`
- Modify: `firmware/main/CMakeLists.txt`
- Modify: `firmware/main/main.c`

**Interfaces:**
- Produces (used by Task 6):

```c
esp_err_t detect_init(void);                          /* never aborts; logs and returns an error */
float detect_score(const uint8_t *jpeg, size_t len);  /* 0..1 max pedestrian score; < 0 on failure */
```

No host test is possible (ESP-DL is C++ and target-only). The task ends with a human build checkpoint.

- [ ] **Step 1: Dependencies**

Replace `firmware/main/idf_component.yml` with:

```yaml
dependencies:
  idf: ">=5.3"
  espressif/esp32-camera: "^2.0.0"
  espressif/esp-dl: "~3.3.0"
  espressif/pedestrian_detect: "^0.3.0"
```

- [ ] **Step 2: Partition for the model**

Replace `firmware/partitions.csv` with:

```csv
# Name,         Type, SubType, Offset,  Size
nvs,            data, nvs,     0x9000,  0x6000
phy_init,       data, phy,     0xf000,  0x1000
factory,        app,  factory, 0x10000, 0x400000
# INT8 pedestrian model (.espdl). `idf.py flash` writes the bundled model here;
# replace it without rebuilding: parttool.py write_partition --partition-name pedestrian_det --input <file>.espdl
pedestrian_det, data, spiffs,  ,        1M
```

- [ ] **Step 3: ESP-DL options**

Append to `firmware/sdkconfig.defaults`:

```
# On-device pedestrian detection (ESP-DL). The model sits in the pedestrian_det
# partition; `idf.py flash` writes it there.
CONFIG_PEDESTRIAN_DETECT_MODEL_IN_FLASH_PARTITION=y
# ESP-DL runs noticeably faster with these.
CONFIG_COMPILER_OPTIMIZATION_PERF=y
CONFIG_ESP32S3_DATA_CACHE_64KB=y
CONFIG_ESP32S3_DATA_CACHE_LINE_64B=y
CONFIG_ESP32S3_INSTRUCTION_CACHE_32KB=y
```

- [ ] **Step 4: The facade**

Create `firmware/main/detect.h`:

```c
#pragma once
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Loads the INT8 pedestrian model from the "pedestrian_det" partition. On
 * failure it logs why and returns an error; detect_score() then always fails. */
esp_err_t detect_init(void);

/* Highest pedestrian score (0..1) in a JPEG frame, 0 when nobody is found, or a
 * negative value when the frame cannot be decoded or no model is loaded.
 * Not thread-safe: call from one task only. */
float detect_score(const uint8_t *jpeg, size_t len);

#ifdef __cplusplus
}
#endif
```

Create `firmware/main/detect.cpp`:

```cpp
// The only C++ file: a C facade over ESP-DL's PedestrianDetect.
#include "detect.h"

#include <new>

#include "dl_image_jpeg.hpp"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_partition.h"
#include "esp_timer.h"
#include "pedestrian_detect.hpp"

static const char *TAG = "detect";
// The model drops boxes below its own threshold (0.7 by default). Keep nearly
// all of them so devcfg's threshold decides what counts as a pedestrian.
static constexpr float MODEL_SCORE_FLOOR = 0.05f;
static constexpr int LOG_EVERY = 30; // frames between timing logs

static PedestrianDetect *s_model;
static int s_frames;

esp_err_t detect_init(void)
{
    const esp_partition_t *part =
        esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, "pedestrian_det");
    if (part == NULL) {
        ESP_LOGE(TAG, "no pedestrian_det partition; detection disabled");
        return ESP_ERR_NOT_FOUND;
    }
    uint32_t magic = 0xFFFFFFFF;
    if (esp_partition_read(part, 0, &magic, sizeof magic) != ESP_OK || magic == 0xFFFFFFFF) {
        ESP_LOGE(TAG, "pedestrian_det partition is empty (run idf.py flash); detection disabled");
        return ESP_ERR_INVALID_STATE;
    }
    int64_t t0 = esp_timer_get_time();
    s_model = new (std::nothrow) PedestrianDetect(PedestrianDetect::PICO_S8_V1, false);
    if (s_model == NULL) {
        ESP_LOGE(TAG, "out of memory loading the model; detection disabled");
        return ESP_ERR_NO_MEM;
    }
    s_model->set_score_thr(MODEL_SCORE_FLOOR);
    ESP_LOGI(TAG, "model loaded in %d ms", (int)((esp_timer_get_time() - t0) / 1000));
    return ESP_OK;
}

float detect_score(const uint8_t *jpeg, size_t len)
{
    if (s_model == NULL) {
        return -1.0f;
    }
    int64_t t0 = esp_timer_get_time();
    dl::image::jpeg_img_t jpeg_img = {.data = (void *)jpeg, .data_len = len};
    dl::image::img_t img = dl::image::sw_decode_jpeg(jpeg_img, dl::image::DL_IMAGE_PIX_TYPE_RGB888);
    if (img.data == NULL) {
        ESP_LOGW(TAG, "JPEG decode failed (%u bytes)", (unsigned)len);
        return -1.0f;
    }
    int64_t t1 = esp_timer_get_time();
    float best = 0.0f;
    for (const auto &r : s_model->run(img)) {
        if (r.score > best) {
            best = r.score;
        }
    }
    heap_caps_free(img.data);
    if (++s_frames % LOG_EVERY == 1) {
        int64_t t2 = esp_timer_get_time();
        ESP_LOGI(TAG, "%dx%d: decode %d ms, inference %d ms, score %.2f", img.width, img.height,
                 (int)((t1 - t0) / 1000), (int)((t2 - t1) / 1000), best);
    }
    return best;
}
```

The spec allows a 1/2-scale decode if full VGA decode is too slow. `sw_decode_jpeg` has no scale option, so this task decodes at full size. If the device checkpoint below shows decode + inference above 250 ms at VGA, record the numbers and raise it with the user. Do not add a second decoder without that discussion.

- [ ] **Step 5: Build files and boot sequence**

In `firmware/main/CMakeLists.txt`, add `"detect.cpp"` to `srcs` after `"status.c"`:

```cmake
set(srcs
    "main.c"
    "config_store.c"
    "timesync.c"
    "mqtt_link.c"
    "cmd.c"
    "camera.c"
    "stream.c"
    "audio.c"
    "status.c"
    "detect.cpp")
```

and add `esp_partition` to `REQUIRES`:

```cmake
                       REQUIRES core driver esp_wifi esp_netif esp_event esp_timer
                                nvs_flash mqtt mbedtls lwip efuse esp_partition
```

The managed components `espressif__esp-dl` and `espressif__pedestrian_detect` are added to `main` automatically because `main/idf_component.yml` declares them.

In `firmware/main/main.c`, add `#include "detect.h"` to the includes (alphabetical, after `#include "core/proto.h"`), and after the `camera_init` block add:

```c
    if (detect_init() != ESP_OK) {
        ESP_LOGE(TAG, "pedestrian detection unavailable: no local alerts until the model is flashed");
    }
```

- [ ] **Step 6: Host tests still pass**

Run: `sh firmware/test/host/run.sh`
Expected: `<N> checks, 0 failures` (no core change; confirms nothing broke).

- [ ] **Step 7: Commit**

```bash
git add firmware/main/idf_component.yml firmware/partitions.csv firmware/sdkconfig.defaults firmware/main/detect.h firmware/main/detect.cpp firmware/main/CMakeLists.txt firmware/main/main.c
git commit -m "feat(firmware): ESP-DL pedestrian detector module and model partition"
```

- [ ] **Step 8: HUMAN CHECKPOINT — build on the ESP-IDF machine**

The implementer cannot run this; ask the user to run it and report the output:

```sh
cd firmware
# sdkconfig.defaults changed: start from the defaults, then re-enter Wi-Fi and the MQTT URI.
idf.py set-target esp32s3
idf.py menuconfig        # Pedestrian Edge -> WIFI_SSID, WIFI_PASSWORD, MQTT_URI
idf.py build
```

Expected: `Project build complete`. If the component manager cannot resolve `espressif/pedestrian_detect ^0.3.0`, run `idf.py add-dependency "espressif/pedestrian_detect"` and commit the version it picks. If `jpeg_img_t`, `sw_decode_jpeg`, `set_score_thr`, or `PICO_S8_V1` do not compile, compare against the installed headers in `managed_components/espressif__esp-dl/vision/image/dl_image_jpeg.hpp` and `managed_components/espressif__pedestrian_detect/pedestrian_detect.hpp`, adjust `detect.cpp` only, and commit as `fix(firmware): match ESP-DL API`.

---

### Task 6: On-device alerting loop, event queue, status

**Files:**
- Create: `firmware/main/event.h`
- Create: `firmware/main/event.c`
- Modify: `firmware/main/stream.h`
- Modify: `firmware/main/stream.c`
- Modify: `firmware/main/status.c`
- Modify: `firmware/main/cmd.c`
- Modify: `firmware/main/config_store.c`
- Modify: `firmware/main/main.c`
- Modify: `firmware/main/CMakeLists.txt`
- Modify: `firmware/README.md`

**Interfaces:**
- Consumes: Task 1 `devcfg_t` fields; Task 2 `dwell_*`; Task 3 `proto_pack_header`, `proto_pack_event`; Task 4 `msg_format_event`, `msg_status_t`; Task 5 `detect_score`.
- Produces:

```c
esp_err_t event_start(void);
void event_raise(const dwell_alert_t *a, uint64_t capture_ms, const uint8_t *jpeg, size_t len);
bool stream_detect_ok(void);
```

- [ ] **Step 1: Event queue**

Create `firmware/main/event.h`:

```c
#pragma once
#include <stddef.h>
#include <stdint.h>

#include "core/dwell.h"
#include "esp_err.h"

/* Publishes {id}/event (QoS 1) for local alerts. Events raised while offline
 * wait in a queue of 4; when it is full the oldest waiting event is dropped. */
esp_err_t event_start(void);

/* Queue an event for `a`. Copies the JPEG. capture_ms is the alerting frame's
 * Unix ms (0 if the clock is not synced). Never waits for the network. */
void event_raise(const dwell_alert_t *a, uint64_t capture_ms, const uint8_t *jpeg, size_t len);
```

Create `firmware/main/event.c`:

```c
#include "event.h"

#include <string.h>

#include "core/msg.h"
#include "core/proto.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mqtt_link.h"

static const char *TAG = "event";
#define EVENT_QUEUE_LEN 4
#define RETRY_MS 1000

typedef struct {
    uint8_t *data;
    size_t len;
} pending_t;

static pending_t s_queue[EVENT_QUEUE_LEN]; /* s_queue[0] is the oldest */
static int s_count;
static bool s_sending; /* s_queue[0] is being published: never drop it */
static SemaphoreHandle_t s_lock;
static TaskHandle_t s_task;

static void remove_at(int i)
{
    heap_caps_free(s_queue[i].data);
    memmove(&s_queue[i], &s_queue[i + 1], (size_t)(s_count - i - 1) * sizeof s_queue[0]);
    s_count--;
}

void event_raise(const dwell_alert_t *a, uint64_t capture_ms, const uint8_t *jpeg, size_t len)
{
    uint32_t dwell_ms = (uint32_t)(a->alert_ms - a->first_seen_ms);
    msg_event_t ev = {
        .alert_ms = capture_ms,
        .first_seen_ms = capture_ms ? capture_ms - dwell_ms : 0,
        .dwell_s = dwell_ms / 1000.0f,
        .max_score = a->max_score,
    };
    char json[128];
    int n = msg_format_event(json, sizeof json, &ev);
    if (n < 0) {
        ESP_LOGE(TAG, "event JSON does not fit");
        return;
    }
    size_t cap = 2 + (size_t)n + len;
    uint8_t *buf = heap_caps_malloc(cap, MALLOC_CAP_SPIRAM);
    if (buf == NULL) {
        ESP_LOGW(TAG, "no memory for %u-byte event", (unsigned)cap);
        return;
    }
    size_t total = proto_pack_event(buf, cap, json, (size_t)n, jpeg, len);
    if (total == 0) {
        heap_caps_free(buf);
        ESP_LOGE(TAG, "event packing failed");
        return;
    }

    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (s_count == EVENT_QUEUE_LEN) {
        remove_at(s_sending ? 1 : 0);
        ESP_LOGW(TAG, "event queue full: dropped the oldest waiting event");
    }
    s_queue[s_count].data = buf;
    s_queue[s_count].len = total;
    s_count++;
    xSemaphoreGive(s_lock);
    xTaskNotifyGive(s_task);
}

static void event_task(void *arg)
{
    for (;;) {
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(RETRY_MS));
        while (mqtt_link_connected()) {
            xSemaphoreTake(s_lock, portMAX_DELAY);
            pending_t head = s_count ? s_queue[0] : (pending_t){NULL, 0};
            s_sending = head.data != NULL;
            xSemaphoreGive(s_lock);
            if (head.data == NULL) {
                break;
            }
            /* Publishing a large JPEG takes a while: do it outside the lock.
             * event_raise() never drops s_queue[0] while s_sending is set. */
            int id = mqtt_link_publish("event", head.data, head.len, 1, false);
            xSemaphoreTake(s_lock, portMAX_DELAY);
            s_sending = false;
            if (id >= 0) {
                remove_at(0);
            }
            xSemaphoreGive(s_lock);
            if (id < 0) {
                ESP_LOGW(TAG, "event publish failed, retrying in %d ms", RETRY_MS);
                break;
            }
            ESP_LOGI(TAG, "event sent");
        }
    }
}

esp_err_t event_start(void)
{
    s_lock = xSemaphoreCreateMutex();
    if (s_lock == NULL) {
        return ESP_ERR_NO_MEM;
    }
    return xTaskCreate(event_task, "event", 4096, NULL, 4, &s_task) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
```

- [ ] **Step 2: Detect loop**

Replace `firmware/main/stream.h` with:

```c
#pragma once
#include <stdbool.h>

#include "esp_err.h"

/* Capture loop, every interval_ms: detect pedestrians, run the dwell rule, play
 * the alert and queue an event when it fires, and, while streaming, also
 * publish the frame to master. */
esp_err_t stream_start(void);

/* False after repeated detection failures (no model, decode errors). */
bool stream_detect_ok(void);
```

Replace `firmware/main/stream.c` with:

```c
#include "stream.h"

#include <string.h>

#include "audio.h"
#include "camera.h"
#include "config_store.h"
#include "core/dwell.h"
#include "core/proto.h"
#include "detect.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "event.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mqtt_link.h"
#include "status.h"
#include "timesync.h"

static const char *TAG = "stream";
#define MAX_CAPTURE_FAILURES 5
#define MAX_DETECT_FAILURES 5
#define SLICE_MS 100

static int s_failures;
static int s_detect_failures;
static volatile bool s_detect_ok = true;
static dwell_t s_dwell;

bool stream_detect_ok(void)
{
    return s_detect_ok;
}

static void track_detect(float score)
{
    if (score >= 0.0f) {
        s_detect_failures = 0;
        if (!s_detect_ok) {
            s_detect_ok = true;
            ESP_LOGI(TAG, "detection recovered");
            status_request();
        }
    } else if (++s_detect_failures == MAX_DETECT_FAILURES) {
        s_detect_ok = false;
        ESP_LOGE(TAG, "%d detection failures in a row", MAX_DETECT_FAILURES);
        status_request();
    }
}

static void send_frame(const camera_fb_t *fb, uint64_t capture_ms, float score, uint32_t dwell_ms)
{
    size_t n = PROTO_HEADER_SIZE + fb->len;
    uint8_t *buf = heap_caps_malloc(n, MALLOC_CAP_SPIRAM);
    if (buf == NULL) {
        ESP_LOGW(TAG, "no memory for %u-byte frame", (unsigned)n);
        return;
    }
    proto_pack_header(buf, capture_ms, score, dwell_ms);
    memcpy(buf + PROTO_HEADER_SIZE, fb->buf, fb->len);
    if (mqtt_link_publish("image", buf, n, 0, false) < 0) {
        ESP_LOGW(TAG, "publish failed");
    }
    heap_caps_free(buf);
}

static void process_frame(const devcfg_t *cfg)
{
    camera_fb_t *fb = camera_capture();
    if (fb == NULL) {
        if (++s_failures >= MAX_CAPTURE_FAILURES) {
            ESP_LOGE(TAG, "%d capture failures, re-initializing camera", s_failures);
            if (camera_reinit(cfg) != ESP_OK) {
                ESP_LOGE(TAG, "camera re-init failed, rebooting");
                esp_restart();
            }
            s_failures = 0;
        }
        return;
    }
    s_failures = 0;

    uint64_t capture_ms = timesync_capture_ms();
    float score = detect_score(fb->buf, fb->len);
    track_detect(score);

    dwell_params_t p;
    dwell_params_from_cfg(&p, cfg);
    dwell_alert_t alert;
    if (dwell_update(&s_dwell, &p, esp_timer_get_time() / 1000, score, &alert)) {
        ESP_LOGI(TAG, "ALERT dwell=%u ms max_score=%.2f",
                 (unsigned)(alert.alert_ms - alert.first_seen_ms), alert.max_score);
        audio_play(1);
        event_raise(&alert, capture_ms, fb->buf, fb->len);
    }
    if (cfg->streaming && mqtt_link_connected()) {
        send_frame(fb, capture_ms, score, dwell_current_ms(&s_dwell));
    }
    camera_return(fb);
}

static void stream_task(void *arg)
{
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
    dwell_init(&s_dwell);
    for (;;) {
        devcfg_t cfg;
        config_store_get(&cfg);
        int64_t started = esp_timer_get_time();
        process_frame(&cfg);
        /* Sleep in slices so the watchdog is fed and config changes apply quickly. */
        for (;;) {
            esp_task_wdt_reset();
            config_store_get(&cfg);
            if ((esp_timer_get_time() - started) / 1000 >= cfg.interval_ms) {
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(SLICE_MS));
        }
    }
}

esp_err_t stream_start(void)
{
    /* ESP-DL inference runs on this task: give it a larger stack. */
    return xTaskCreate(stream_task, "stream", 16384, NULL, 4, NULL) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
```

- [ ] **Step 3: Status, config log, NVS key, boot**

In `firmware/main/status.c`, add `#include "stream.h"` to the includes, and replace `publish_status` with:

```c
static void publish_status(void)
{
    devcfg_t cfg;
    config_store_get(&cfg);
    msg_status_t s = {
        .rssi = net_rssi(),
        .battery_mv = board_battery_mv(),
        .uptime_s = (uint32_t)(esp_timer_get_time() / 1000000),
        .streaming = cfg.streaming,
        .fw = CONFIG_FW_VERSION,
        .detect_ok = stream_detect_ok(),
        .threshold = cfg.threshold,
        .dwell_s = cfg.dwell_s,
        .max_gap_s = cfg.max_gap_s,
        .cooldown_s = cfg.cooldown_s,
    };
    char buf[256];
    int n = msg_format_status(buf, sizeof buf, &s);
    if (n < 0) {
        ESP_LOGE(TAG, "status does not fit buffer");
        return;
    }
    if (mqtt_link_publish("status", buf, (size_t)n, 1, true) < 0) {
        ESP_LOGD(TAG, "not connected, status skipped");
    }
}
```

In `firmware/main/cmd.c`, replace the `ESP_LOGI(TAG, "config: ...` statement at the end of `handle_config` with:

```c
    ESP_LOGI(TAG, "config: interval_ms=%lu quality=%u frame=%s volume=%u threshold=%.2f "
                  "dwell=%.1fs gap=%.1fs cooldown=%.0fs",
             (unsigned long)next.interval_ms, next.jpeg_quality,
             devcfg_frame_name(next.frame_size), next.volume, next.threshold,
             next.dwell_s, next.max_gap_s, next.cooldown_s);
    status_request(); /* report the new active settings right away */
```

In `firmware/main/config_store.c`, change the key:

```c
/* "devcfg2": devcfg_t gained the detection fields. A blob under the old key has
 * the old layout and is ignored, so such a device starts from the defaults. */
static const char *KEY = "devcfg2";
```

In `firmware/main/main.c`, add `#include "event.h"` (after `#include "esp_mac.h"`), and before `ESP_ERROR_CHECK(stream_start());` add:

```c
    ESP_ERROR_CHECK(event_start());
```

In `firmware/main/CMakeLists.txt`, add `"event.c"` to `srcs` after `"detect.cpp"`.

- [ ] **Step 4: README**

In `firmware/README.md`:

1. Replace the intro paragraph (lines 3–5) with:

```markdown
ESP-IDF firmware for the edge device. It detects pedestrians on the device with
Espressif's INT8 `pedestrian_detect` model (ESP-DL), plays the alert sound itself
when a pedestrian stays in view for `dwell_s`, and reports each alert to the master
as `{id}/event` with a snapshot. Frames go to the master only in stream mode
(`python -m master.cli start <id>`).
Design: `docs/superpowers/specs/2026-10-11-on-device-inference-design.md`
(original: `2026-09-29-pedestrian-alert-design.md`).
```

2. In "1. Install ESP-IDF", replace `Supported: **ESP-IDF v5.1 to v5.4** (v5.3 or v5.4 recommended).` with `Supported: **ESP-IDF v5.3 to v5.5** (ESP-DL needs v5.3 or later; developed on v5.5).`, and replace both `v5.3 or v5.4` / `-b v5.4` mentions in that section with `v5.5` / `-b v5.5`.

3. In "5. Build", replace the sentence about the component manager with:

```markdown
The first build needs internet access once: the component manager downloads
`espressif/esp32-camera`, `espressif/esp-dl`, and `espressif/pedestrian_detect`
(declared in `main/idf_component.yml`) into `managed_components/`.
```

4. In "6. Flash and watch the log", after the paragraph about the expected log, add:

```markdown
`idf.py flash` also writes the pedestrian model into the `pedestrian_det`
partition. The log then shows `detect: model loaded in ... ms`, and every 30th
frame `detect: 640x480: decode .. ms, inference .. ms, score ..`. `app-flash`
skips the model; a board flashed only that way logs
`pedestrian_det partition is empty` and reports `detect_ok: false`.

To try another model without rebuilding:
`parttool.py write_partition --partition-name pedestrian_det --input <model>.espdl`.
```

5. Replace the whole "Bring-up checklist" list with:

```markdown
1. `idf.py build` succeeds with no warnings in `main/` or `components/core/`.
2. Boot log shows `config_store: ...`, `audio: ready: 19200-byte clip on GPIO 14`,
   `detect: model loaded in ... ms`, no camera error.
3. `net_wifi: got ip ...` within 10 s; unplug the AP → `disconnected, retry in 5000 ms`, then 10000, 30000.
4. `mqtt_link: connected` and `main: running as <id>`. On the PC:
   `mosquitto_sub -t '<id>/#' -v` shows `<id>/online 1` and `<id>/status {...}` with
   `"detect_ok":true` and the detection settings.
5. Timing: the `detect:` log line shows decode + inference ≤ 250 ms at VGA.
6. Empty scene, streaming off (the default): `mosquitto_sub -t '<id>/#' -v` shows
   only `status` every 60 s. No `image`, no `event`.
7. Stand in view for `dwell_s` (default 5 s): the chime plays, the log shows
   `stream: ALERT ...` then `event: event sent`, and the dashboard lists a warning
   with a snapshot. Walk through quickly: no chime.
8. Network off (unplug the AP), stand in view: the chime still plays. Plug the AP
   back in: the warning appears on the dashboard after reconnect.
9. `python -m master.cli start <id>` → frames arrive; the dashboard shows YOLO and
   device scores side by side. `stop <id>` → frames stop; reboot → still stopped.
10. `python -m master.cli config <id> threshold=0.5 dwell_s=3` → the device logs the
    new config and its next status shows them. `threshold=1.5` is rejected by the CLI.
11. `python -m master.cli alert <id>` → chime plays once; `--repeat 3` → three times.
12. `python -m master.cli status <id>` → new status message; `reboot <id>` → device restarts and reconnects.
13. Power off the device → `<id>/online 0` within about 45 s (keepalive 30 s × 1.5).
```

6. In "Troubleshooting the first build", add rows:

```markdown
| `Failed to resolve component 'espressif/pedestrian_detect'` | Run `idf.py add-dependency "espressif/pedestrian_detect"` with internet access, then build. |
| `pedestrian_det partition is empty` at boot | The model was not flashed. Run `idf.py flash` (not `app-flash`). |
| `detect: ... inference` well above 250 ms | Check that `sdkconfig` has `CONFIG_COMPILER_OPTIMIZATION_PERF=y` and 64 KB data cache; delete `sdkconfig` and rebuild if it came from older defaults. |
```

- [ ] **Step 5: Host tests still pass**

Run: `sh firmware/test/host/run.sh`
Expected: `<N> checks, 0 failures`.

- [ ] **Step 6: Commit**

```bash
git add firmware/main firmware/README.md
git commit -m "feat(firmware): detect and alert on the device, report events to master"
```

- [ ] **Step 7: HUMAN CHECKPOINT — build, flash, bring-up**

Ask the user to run, on the ESP-IDF machine, `idf.py build` then `idf.py -p <port> flash monitor`, and to work through the bring-up checklist steps 1–8 (steps 9–13 need the server from Tasks 7–11). Record the reported decode and inference times. Fix any compile error in `main/` only, commit as `fix(firmware): ...`.

---

### Task 7: Server protocol: image header, events, detection config

**Files:**
- Modify: `server/master/protocol.py`
- Modify: `server/master/app.py` (one call site, keeps the app working)
- Test: `server/tests/test_protocol.py`, `server/tests/test_cli.py`

**Interfaces:**
- Produces:

```python
HEADER_SIZE = 12; SCORE_FAILED = 0xFFFF
@dataclass(frozen=True) class ImageFrame: capture_ms: int; score: float | None; dwell_s: float; jpeg: bytes
@dataclass(frozen=True) class DeviceEvent: alert_ms: int; first_seen_ms: int; dwell_s: float; max_score: float
def pack_image(capture_ms: int, jpeg: bytes, score: float | None = None, dwell_s: float = 0.0) -> bytes
def parse_image(payload: bytes) -> ImageFrame
def pack_event(event: DeviceEvent, jpeg: bytes) -> bytes
def parse_event(payload: bytes) -> tuple[DeviceEvent, bytes]
DEFAULT_CONFIG  # gains threshold, dwell_s, max_gap_s, cooldown_s
```

- [ ] **Step 1: Write the failing tests**

In `server/tests/test_protocol.py`, replace `test_image_round_trip` and `test_parse_image_rejects_short_payload` with:

```python
def test_image_round_trip():
    payload = p.pack_image(1_727_600_000_123, b"\xff\xd8jpeg", 0.8, 1.5)
    assert payload[:8] == struct.pack("<Q", 1_727_600_000_123)
    assert p.parse_image(payload) == p.ImageFrame(1_727_600_000_123, 0.8, 1.5, b"\xff\xd8jpeg")


def test_image_header_layout():
    payload = p.pack_image(0x0102030405060708, b"j", 0.5, 2.0)
    assert payload[:12] == bytes([8, 7, 6, 5, 4, 3, 2, 1, 0xF4, 0x01, 0x14, 0x00])
    assert p.HEADER_SIZE == 12


def test_image_without_score_means_detection_failed():
    payload = p.pack_image(1, b"j")
    assert payload[8:10] == b"\xff\xff"
    assert p.parse_image(payload).score is None


def test_image_score_and_dwell_clamped():
    assert p.parse_image(p.pack_image(1, b"j", 1.7)).score == 1.0
    assert p.parse_image(p.pack_image(1, b"j", -0.2)).score == 0.0
    assert p.parse_image(p.pack_image(1, b"j", 0.5, 10_000)).dwell_s == 6553.5


@pytest.mark.parametrize("payload", [b"", b"\x00" * 8, b"\x00" * 12])
def test_parse_image_rejects_short_payload(payload):
    with pytest.raises(p.ProtocolError):
        p.parse_image(payload)


def test_parse_image_rejects_score_out_of_range():
    with pytest.raises(p.ProtocolError):
        p.parse_image(struct.pack("<QHH", 1, 1001, 0) + b"j")


def test_event_round_trip():
    ev = p.DeviceEvent(alert_ms=1_790_000_005_000, first_seen_ms=1_790_000_000_000, dwell_s=5.0, max_score=0.83)
    payload = p.pack_event(ev, b"\xff\xd8snap")
    (n,) = struct.unpack_from("<H", payload)
    assert json.loads(payload[2:2 + n]) == {
        "alert_ms": 1_790_000_005_000, "first_seen_ms": 1_790_000_000_000, "dwell_s": 5.0, "max_score": 0.83,
    }
    assert p.parse_event(payload) == (ev, b"\xff\xd8snap")


def test_event_from_device_json():
    body = b'{"alert_ms":0,"first_seen_ms":0,"dwell_s":5.20,"max_score":0.835}'
    ev, jpeg = p.parse_event(struct.pack("<H", len(body)) + body + b"x")
    assert ev == p.DeviceEvent(0, 0, 5.2, 0.835) and jpeg == b"x"


def _event(body: bytes, jpeg: bytes = b"x") -> bytes:
    return struct.pack("<H", len(body)) + body + jpeg


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x01",
        struct.pack("<H", 50) + b"{}x",                        # JSON length past the end
        struct.pack("<H", 0) + b"x",                           # empty JSON
        _event(b'{"alert_ms":1,"first_seen_ms":0,"dwell_s":1,"max_score":0.5}', b""),  # no snapshot
        _event(b"not json"),
        _event(b"\xff\xfe"),
        _event(b"[1, 2]"),
        _event(b'{"alert_ms":1,"first_seen_ms":0,"dwell_s":1}'),
        _event(b'{"alert_ms":1.5,"first_seen_ms":0,"dwell_s":1,"max_score":0.5}'),
        _event(b'{"alert_ms":true,"first_seen_ms":0,"dwell_s":1,"max_score":0.5}'),
        _event(b'{"alert_ms":1,"first_seen_ms":0,"dwell_s":1,"max_score":1.5}'),
        _event(b'{"alert_ms":1,"first_seen_ms":0,"dwell_s":-1,"max_score":0.5}'),
        _event(b'{"alert_ms":1,"first_seen_ms":0,"dwell_s":NaN,"max_score":0.5}'),
        _event(b'{"alert_ms":1,"first_seen_ms":2,"dwell_s":1,"max_score":0.5}'),  # first_seen after alert
        _event(b'{"alert_ms":-1,"first_seen_ms":-2,"dwell_s":1,"max_score":0.5}'),
    ],
)
def test_parse_event_rejects(payload):
    with pytest.raises(p.ProtocolError):
        p.parse_event(payload)
```

Replace `test_validate_config_accepts_defaults` with:

```python
def test_validate_config_accepts_defaults():
    assert p.validate_config(dict(p.DEFAULT_CONFIG)) == p.DEFAULT_CONFIG
    assert {"threshold", "dwell_s", "max_gap_s", "cooldown_s"} <= set(p.DEFAULT_CONFIG)


def test_validate_config_accepts_detection_bounds():
    for cfg in ({"threshold": 0.05, "dwell_s": 0, "max_gap_s": 0.5, "cooldown_s": 0},
                {"threshold": 0.99, "dwell_s": 600, "max_gap_s": 60, "cooldown_s": 3600}):
        assert p.validate_config(cfg) == cfg
```

Add to the `cfg` parametrize list of `test_validate_config_rejects`:

```python
        {"threshold": 1.0},
        {"threshold": 0.01},
        {"threshold": "high"},
        {"threshold": True},
        {"threshold": float("nan")},
        {"dwell_s": 601},
        {"max_gap_s": 0.4},
        {"cooldown_s": -1},
```

Add after `test_parse_config_args_converts_types`:

```python
def test_parse_config_args_converts_floats():
    assert p.parse_config_args(["threshold=0.45", "dwell_s=2.5", "cooldown_s=0"]) == {
        "threshold": 0.45, "dwell_s": 2.5, "cooldown_s": 0.0,
    }
```

and extend the `test_parse_config_args_rejects` parametrize list with `["threshold=abc"], ["threshold=nan"], ["dwell_s=inf"]`.

In `server/tests/test_cli.py`, add:

```python
def test_config_detection_fields():
    _, payload, _, retain = build_message(["config", MAC, "threshold=0.5", "dwell_s=3"], None)
    assert retain is True
    assert json.loads(payload) == {"threshold": 0.5, "dwell_s": 3.0}
```

- [ ] **Step 2: Run and see them fail**

Run (from `server/`): `$PY -m pytest tests/test_protocol.py tests/test_cli.py -q`
Expected: failures, `AttributeError: module 'master.protocol' has no attribute 'ImageFrame'` and others.

- [ ] **Step 3: Implement**

In `server/master/protocol.py`:

Replace the imports and constants at the top (through `_INT_FIELDS`) with:

```python
"""MQTT topics and payload formats shared by the server, CLI, and fake device."""

import json
import math
import struct
from dataclasses import dataclass

# {mac}/image header: capture_ms, device score in permille (SCORE_FAILED = the
# device's detection failed), device's current dwell in deciseconds.
IMAGE_HEADER = struct.Struct("<QHH")
HEADER_SIZE = IMAGE_HEADER.size
SCORE_FAILED = 0xFFFF
EVENT_JSON_LEN = struct.Struct("<H")

FRAME_SIZES = ("QVGA", "VGA", "SVGA", "XGA", "HD", "SXGA", "UXGA")
ACTIONS = ("start", "stop", "reboot", "status")
DEFAULT_CONFIG = {
    "interval_ms": 1000, "jpeg_quality": 12, "frame_size": "VGA", "volume": 80,
    "threshold": 0.6, "dwell_s": 5.0, "max_gap_s": 3.0, "cooldown_s": 30.0,
}

# Integer fields -> (min, max), inclusive. frame_size is checked separately.
_INT_FIELDS = {
    "interval_ms": (100, 3_600_000),
    "jpeg_quality": (0, 63),
    "volume": (0, 100),
}
# Number fields (int or float) -> (min, max), inclusive. Same ranges as firmware devcfg.
_FLOAT_FIELDS = {
    "threshold": (0.05, 0.99),
    "dwell_s": (0.0, 600.0),
    "max_gap_s": (0.5, 60.0),
    "cooldown_s": (0.0, 3600.0),
}
```

Below `class ProtocolError`, add:

```python
@dataclass(frozen=True)
class ImageFrame:
    capture_ms: int        # 0 when the device clock is not synced
    score: float | None    # device detector score 0..1; None when its detection failed
    dwell_s: float         # device's current dwell
    jpeg: bytes


@dataclass(frozen=True)
class DeviceEvent:
    alert_ms: int          # Unix ms of the alerting frame; 0 when the device clock is not synced
    first_seen_ms: int
    dwell_s: float
    max_score: float


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
```

Replace `pack_image` and `parse_image` with:

```python
def pack_image(capture_ms: int, jpeg: bytes, score: float | None = None, dwell_s: float = 0.0) -> bytes:
    permille = SCORE_FAILED if score is None else round(min(max(score, 0.0), 1.0) * 1000)
    dwell_ds = min(0xFFFF, max(0, round(dwell_s * 10)))
    return IMAGE_HEADER.pack(capture_ms, permille, dwell_ds) + jpeg


def parse_image(payload: bytes) -> ImageFrame:
    if len(payload) <= HEADER_SIZE:
        raise ProtocolError(f"image payload too short ({len(payload)} bytes)")
    capture_ms, permille, dwell_ds = IMAGE_HEADER.unpack_from(payload)
    if permille == SCORE_FAILED:
        score = None
    elif permille > 1000:
        raise ProtocolError(f"image score {permille} permille out of range")
    else:
        score = permille / 1000
    return ImageFrame(capture_ms, score, dwell_ds / 10, payload[HEADER_SIZE:])


def pack_event(event: DeviceEvent, jpeg: bytes) -> bytes:
    body = json.dumps({
        "alert_ms": event.alert_ms, "first_seen_ms": event.first_seen_ms,
        "dwell_s": event.dwell_s, "max_score": event.max_score,
    }).encode()
    return EVENT_JSON_LEN.pack(len(body)) + body + jpeg


def parse_event(payload: bytes) -> tuple[DeviceEvent, bytes]:
    """Return (event, snapshot JPEG). Device payloads are untrusted: every field is checked."""
    if len(payload) < EVENT_JSON_LEN.size:
        raise ProtocolError(f"event payload too short ({len(payload)} bytes)")
    (n,) = EVENT_JSON_LEN.unpack_from(payload)
    end = EVENT_JSON_LEN.size + n
    if n == 0 or end >= len(payload):
        raise ProtocolError("event JSON length is 0 or leaves no snapshot")
    try:
        data = json.loads(payload[EVENT_JSON_LEN.size:end])
    except ValueError:
        raise ProtocolError("event JSON is not valid") from None
    if not isinstance(data, dict):
        raise ProtocolError("event JSON is not an object")
    times = {}
    for key in ("alert_ms", "first_seen_ms"):
        v = data.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise ProtocolError(f"event {key} must be a non-negative integer, got {v!r}")
        times[key] = v
    dwell_s, max_score = data.get("dwell_s"), data.get("max_score")
    if not _is_number(dwell_s) or dwell_s < 0:
        raise ProtocolError(f"event dwell_s must be a number >= 0, got {dwell_s!r}")
    if not _is_number(max_score) or not 0 <= max_score <= 1:
        raise ProtocolError(f"event max_score must be 0-1, got {max_score!r}")
    if times["first_seen_ms"] > times["alert_ms"]:
        raise ProtocolError("event first_seen_ms is after alert_ms")
    return DeviceEvent(times["alert_ms"], times["first_seen_ms"], float(dwell_s), float(max_score)), payload[end:]
```

In `validate_config`, add a branch before the final `else`:

```python
        elif key in _FLOAT_FIELDS:
            lo, hi = _FLOAT_FIELDS[key]
            if not _is_number(value):
                raise ProtocolError(f"{key} must be a number, got {value!r}")
            if not lo <= value <= hi:
                raise ProtocolError(f"{key} must be {lo}-{hi}, got {value}")
```

In `parse_config_args`, add a branch after the `_INT_FIELDS` branch:

```python
        elif key in _FLOAT_FIELDS:
            try:
                out[key] = float(raw)
            except ValueError:
                raise ProtocolError(f"{key} must be a number, got {raw!r}") from None
```

In `server/master/app.py`, `_on_image` unpacks the old tuple. Change the first lines of `_on_image` to:

```python
    def _on_image(self, mac: str, payload: bytes) -> None:
        try:
            frame = protocol.parse_image(payload)
        except protocol.ProtocolError as e:
            log.warning("%s: dropping frame: %s", mac, e)
            return
        capture_ms, jpeg = frame.capture_ms, frame.jpeg
```

(the rest of `_on_image` is unchanged; Task 9 rewrites it).

- [ ] **Step 4: Run the full server suite**

Run: `$PY -m pytest -q`
Expected: all pass (integration skipped without Mosquitto).

- [ ] **Step 5: Commit**

```bash
git add server/master/protocol.py server/master/app.py server/tests/test_protocol.py server/tests/test_cli.py
git commit -m "feat(server): 12-byte image header, device events, detection config fields"
```

---

### Task 8: Event store: device scores, devices table, frame/event matching

**Files:**
- Modify: `server/master/events.py`
- Test: `server/tests/test_events.py`
- Modify: `server/tests/test_web.py` (import only)

**Interfaces:**
- Consumes: nothing new.
- Produces (used by Tasks 9 and 10):

```python
@dataclass(frozen=True) class Alert: first_seen: float; ts: float; max_conf: float; dwell_s (property)
EventStore.record(mac, alert: Alert, jpeg: bytes, mark_frame: bool = False) -> Path
EventStore.record_inference(mac, ts, conf, positive, dwell_s, alerted, jpeg,
                            device_score: float | None = None, match_event: bool = False) -> Path
EventStore.update_device(mac, *, online: bool | None = None, status: str | None = None,
                         seen_ts: float | None = None) -> None
EventStore.devices() -> list[dict]   # mac, online, status, last_seen_ts
# inferences table gains device_score REAL (nullable); new table devices(mac PK, online, status, last_seen_ts)
```

- [ ] **Step 1: Write the failing tests**

In `server/tests/test_events.py`, change `from master.logic import Alert` to `from master.events import Alert` (keep `from master.events import EventStore`). In `server/tests/test_web.py`, change `from master.logic import Alert` to `from master.events import Alert`.

Append to `server/tests/test_events.py`:

```python
def test_alert_dwell():
    assert Alert(first_seen=10.0, ts=15.5, max_conf=0.9).dwell_s == 5.5


def test_device_score_stored(tmp_path):
    store = EventStore(tmp_path)
    store.record_inference(MAC, 1.0, 0.9, True, 2.0, False, _jpeg(64, 48), device_score=0.42)
    store.record_inference(MAC, 2.0, 0.9, True, 3.0, False, _jpeg(64, 48))
    rows = store.inferences(MAC)
    assert [r["device_score"] for r in rows] == [None, 0.42]
    store.close()


def test_device_score_column_added_to_old_db(tmp_path):
    con = sqlite3.connect(tmp_path / "events.db")
    con.executescript(
        "CREATE TABLE inferences (id INTEGER PRIMARY KEY AUTOINCREMENT, mac TEXT NOT NULL,"
        " ts REAL NOT NULL, conf REAL NOT NULL, positive INTEGER NOT NULL, dwell_s REAL NOT NULL,"
        " alerted INTEGER NOT NULL, thumb TEXT NOT NULL);"
        "INSERT INTO inferences (mac, ts, conf, positive, dwell_s, alerted, thumb)"
        " VALUES ('a1b2c3d4e5f6', 1.0, 0.5, 0, 0.0, 0, 'thumbs/x.jpg');"
    )
    con.commit()
    con.close()
    store = EventStore(tmp_path)
    store.record_inference(MAC, 2.0, 0.9, True, 0.0, False, _jpeg(64, 48), device_score=0.7)
    assert [r["device_score"] for r in store.inferences(MAC)] == [0.7, None]
    store.close()


def test_frame_then_event_marks_frame(tmp_path):
    store = EventStore(tmp_path)
    store.record_inference(MAC, 100.5, 0.9, True, 5.0, False, _jpeg(64, 48), match_event=True)
    store.record_inference(MAC, 101.5, 0.9, True, 6.0, False, _jpeg(64, 48), match_event=True)
    store.record(MAC, Alert(first_seen=95.5, ts=100.5, max_conf=0.8), b"\xff\xd8x", mark_frame=True)
    assert {r["ts"]: r["alerted"] for r in store.inferences(MAC)} == {100.5: 1, 101.5: 0}
    store.close()


def test_event_then_frame_marks_frame(tmp_path):
    store = EventStore(tmp_path)
    store.record(MAC, Alert(first_seen=95.5, ts=100.5, max_conf=0.8), b"\xff\xd8x", mark_frame=True)
    store.record_inference(MAC, 100.5, 0.9, True, 5.0, False, _jpeg(64, 48), match_event=True)
    store.record_inference("bbbbbbbbbbbb", 100.5, 0.9, True, 5.0, False, _jpeg(64, 48), match_event=True)
    assert store.inferences(MAC)[0]["alerted"] == 1
    assert store.inferences("bbbbbbbbbbbb")[0]["alerted"] == 0  # other device
    store.close()


def test_no_matching_without_flags(tmp_path):
    store = EventStore(tmp_path)
    store.record_inference(MAC, 100.5, 0.9, True, 5.0, False, _jpeg(64, 48))
    store.record(MAC, Alert(first_seen=95.5, ts=100.5, max_conf=0.8), b"\xff\xd8x")
    store.record_inference(MAC, 100.5, 0.9, True, 5.0, False, _jpeg(64, 48))
    assert [r["alerted"] for r in store.inferences(MAC)] == [0, 0]
    store.close()


def test_update_device_upserts_and_keeps_missing_fields(tmp_path):
    store = EventStore(tmp_path)
    store.update_device(MAC, online=True, status='{"rssi":-60}', seen_ts=10.0)
    store.update_device(MAC)  # nothing given: nothing changes
    assert store.devices() == [{"mac": MAC, "online": 1, "status": '{"rssi":-60}', "last_seen_ts": 10.0}]
    store.update_device(MAC, online=False)
    store.update_device(MAC, status='{"rssi":-70}')
    assert store.devices() == [{"mac": MAC, "online": 0, "status": '{"rssi":-70}', "last_seen_ts": 10.0}]
    store.update_device(MAC, online=True, seen_ts=20.0)
    assert store.devices()[0]["online"] == 1 and store.devices()[0]["last_seen_ts"] == 20.0
    store.close()


def test_update_device_offline_first(tmp_path):
    store = EventStore(tmp_path)
    store.update_device(MAC, online=False)
    assert store.devices() == [{"mac": MAC, "online": 0, "status": None, "last_seen_ts": None}]
    store.close()
```

- [ ] **Step 2: Run and see them fail**

Run: `$PY -m pytest tests/test_events.py -q`
Expected: `ImportError: cannot import name 'Alert' from 'master.events'`.

- [ ] **Step 3: Implement**

In `server/master/events.py`:

Replace `from master.logic import Alert` with `from dataclasses import dataclass` (placed with the stdlib imports), and add below `_UNSAFE_CHARS`:

```python
@dataclass(frozen=True)
class Alert:
    """A warning as stored: times in Unix seconds, max_conf = device's max score."""

    first_seen: float
    ts: float
    max_conf: float

    @property
    def dwell_s(self) -> float:
        return self.ts - self.first_seen
```

Replace `_SCHEMA` with:

```python
_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT NOT NULL,
    alert_ts REAL NOT NULL,
    first_seen_ts REAL NOT NULL,
    dwell_s REAL NOT NULL,
    max_conf REAL NOT NULL,
    snapshot TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT NOT NULL,
    ts REAL NOT NULL,
    conf REAL NOT NULL,
    positive INTEGER NOT NULL,
    dwell_s REAL NOT NULL,
    alerted INTEGER NOT NULL,
    thumb TEXT NOT NULL,
    device_score REAL
);
CREATE INDEX IF NOT EXISTS inferences_mac_id ON inferences (mac, id);
CREATE TABLE IF NOT EXISTS devices (
    mac TEXT PRIMARY KEY,
    online INTEGER NOT NULL,
    status TEXT,
    last_seen_ts REAL
);
"""
```

In `__init__`, after `self._migrate_snapshot_paths()` add `self._migrate_device_score()`, and add the method:

```python
    def _migrate_device_score(self) -> None:
        """Databases from before on-device detection have no device_score column."""
        cols = {row[1] for row in self._db.execute("PRAGMA table_info(inferences)")}
        if "device_score" not in cols:
            self._db.execute("ALTER TABLE inferences ADD COLUMN device_score REAL")
```

Replace `record` with:

```python
    def record(self, mac: str, alert: Alert, jpeg: bytes, mark_frame: bool = False) -> Path:
        """Save a warning. mark_frame: also flag the stream frame captured at alert.ts
        (only meaningful when the device clock was synced)."""
        rel = Path(_dir_name(mac)) / f"{round(alert.ts * 1000)}.jpg"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpeg)
        with self._lock:
            self._db.execute(
                "INSERT INTO events (mac, alert_ts, first_seen_ts, dwell_s, max_conf, snapshot)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (mac, alert.ts, alert.first_seen, alert.dwell_s, alert.max_conf, rel.as_posix()),
            )
            if mark_frame:
                self._db.execute("UPDATE inferences SET alerted = 1 WHERE mac = ? AND ts = ?", (mac, alert.ts))
            self._db.commit()
        return path
```

Replace the signature and the `with self._lock:` insert of `record_inference` with:

```python
    def record_inference(self, mac: str, ts: float, conf: float, positive: bool,
                         dwell_s: float, alerted: bool, jpeg: bytes,
                         device_score: float | None = None, match_event: bool = False) -> Path:
        """Save a thumbnail and a row, then prune this device to the newest `history` rows.
        match_event: mark the row alerted if a warning for this device has alert_ts == ts."""
```

(thumbnail code unchanged), then:

```python
        with self._lock:
            if match_event and not alerted:
                alerted = self._db.execute(
                    "SELECT 1 FROM events WHERE mac = ? AND alert_ts = ? LIMIT 1", (mac, ts)
                ).fetchone() is not None
            self._db.execute(
                "INSERT INTO inferences (mac, ts, conf, positive, dwell_s, alerted, thumb, device_score)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (mac, ts, conf, int(positive), dwell_s, int(alerted), rel.as_posix(), device_score),
            )
```

(the pruning code after it is unchanged).

In `inferences`, change the SELECT column list to
`"SELECT id, mac, ts, conf, positive, dwell_s, alerted, thumb, device_score"`.

Add after `recent`:

```python
    def update_device(self, mac: str, *, online: bool | None = None, status: str | None = None,
                      seen_ts: float | None = None) -> None:
        """Upsert a device. A None argument keeps the stored value."""
        on = None if online is None else int(online)
        with self._lock:
            self._db.execute(
                "INSERT INTO devices (mac, online, status, last_seen_ts) VALUES (?, COALESCE(?, 0), ?, ?)"
                " ON CONFLICT(mac) DO UPDATE SET"
                " online = COALESCE(?, online), status = COALESCE(?, status),"
                " last_seen_ts = COALESCE(?, last_seen_ts)",
                (mac, on, status, seen_ts, on, status, seen_ts),
            )
            self._db.commit()

    def devices(self) -> list[dict]:
        with self._lock:
            cur = self._db.execute("SELECT mac, online, status, last_seen_ts FROM devices ORDER BY mac")
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
```

- [ ] **Step 4: Run the full server suite**

Run: `$PY -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/master/events.py server/tests/test_events.py server/tests/test_web.py
git commit -m "feat(server): device scores, devices table, match frames to device events"
```

---

### Task 9: Master app: ingest device events and status, drop server-side dwell

**Files:**
- Modify: `server/master/app.py`
- Delete: `server/master/logic.py`, `server/tests/test_logic.py`
- Modify: `server/master/settings.py`, `server/.env.example`
- Modify: `server/master/web.py` (`/api/config` only)
- Test: `server/tests/test_app.py` (rewrite), `server/tests/test_integration.py` (rewrite), `server/tests/test_settings.py`, `server/tests/test_web.py`

**Interfaces:**
- Consumes: Task 7 `ImageFrame`, `DeviceEvent`, `parse_event`, `pack_event`; Task 8 `Alert`, `record(..., mark_frame)`, `record_inference(..., device_score, match_event)`, `update_device`.
- Produces:

```python
@dataclass(frozen=True) class Frame: ts: float; synced: bool; device_score: float | None; dwell_s: float; jpeg: bytes
FrameSlots.put(mac, frame: Frame); FrameSlots.take_all(timeout) -> dict[str, Frame]
MasterApp(detector, events, threshold: float, clock=time.time)
MasterApp.on_message(topic: str, payload: bytes, retained: bool = False) -> None
connect(app, host, port, user, password, client_id="master") -> mqtt.Client   # subscribes +/image, +/event, +/status, +/online
GET /api/config -> {"threshold": <YOLO cutoff>, "history": <int>}
```

- [ ] **Step 1: Write the failing tests**

Replace `server/tests/test_app.py` with:

```python
import json

from master import protocol
from master.app import Frame, FrameSlots, MasterApp
from master.events import Alert

MAC = "a1b2c3d4e5f6"
START_MS = 1_727_600_000_000


class FakeDetector:
    def __init__(self, conf=0.9, error=None):
        self.conf = conf
        self.error = error
        self.calls = 0

    def person_confidence(self, jpeg):
        self.calls += 1
        if self.error:
            raise self.error
        return self.conf


class FakeEvents:
    def __init__(self, error=None):
        self.error = error
        self.recorded = []
        self.inferences = []
        self.devices = []

    def record(self, mac, alert, jpeg, mark_frame=False):
        if self.error:
            raise self.error
        self.recorded.append({"mac": mac, "alert": alert, "jpeg": jpeg, "mark_frame": mark_frame})

    def record_inference(self, mac, ts, conf, positive, dwell_s, alerted, jpeg,
                         device_score=None, match_event=False):
        if self.error:
            raise self.error
        self.inferences.append({"mac": mac, "ts": ts, "conf": conf, "positive": positive,
                                "dwell_s": dwell_s, "alerted": alerted, "jpeg": jpeg,
                                "device_score": device_score, "match_event": match_event})

    def update_device(self, mac, *, online=None, status=None, seen_ts=None):
        if self.error:
            raise self.error
        self.devices.append({"mac": mac, "online": online, "status": status, "seen_ts": seen_ts})


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def make_app(detector=None, events=None, clock=None):
    return MasterApp(detector=detector or FakeDetector(), events=events or FakeEvents(),
                     threshold=0.6, clock=clock or Clock())


def send_frame(app, ms=START_MS, score=0.8, dwell_s=1.5, mac=MAC):
    app.on_message(f"{mac}/image", protocol.pack_image(ms, b"jpeg", score, dwell_s))
    app.process_pending(timeout=0)


def event_payload(alert_ms=START_MS + 5000, first_seen_ms=START_MS, dwell_s=5.0, max_score=0.83):
    return protocol.pack_event(protocol.DeviceEvent(alert_ms, first_seen_ms, dwell_s, max_score), b"snap")


def test_stream_frame_recorded_with_both_scores():
    app = make_app()
    send_frame(app)
    [row] = app.events.inferences
    assert row == {"mac": MAC, "ts": START_MS / 1000, "conf": 0.9, "positive": True, "dwell_s": 1.5,
                   "alerted": False, "jpeg": b"jpeg", "device_score": 0.8, "match_event": True}


def test_failed_device_detection_recorded_as_none():
    app = make_app()
    send_frame(app, score=None)
    assert app.events.inferences[0]["device_score"] is None


def test_yolo_threshold_decides_positive():
    app = make_app(detector=FakeDetector(conf=0.1))
    send_frame(app, score=0.95)
    assert app.events.inferences[0]["positive"] is False


def test_unsynced_frame_uses_server_clock_and_never_matches():
    app = make_app(clock=Clock(500.0))
    send_frame(app, ms=0)
    row = app.events.inferences[0]
    assert row["ts"] == 500.0 and row["match_event"] is False


def test_event_recorded_with_device_values():
    app = make_app()
    app.on_message(f"{MAC}/event", event_payload())
    [rec] = app.events.recorded
    assert rec["mac"] == MAC and rec["jpeg"] == b"snap" and rec["mark_frame"] is True
    assert rec["alert"] == Alert(first_seen=START_MS / 1000, ts=(START_MS + 5000) / 1000, max_conf=0.83)


def test_unsynced_event_uses_server_clock():
    app = make_app(clock=Clock(1000.0))
    app.on_message(f"{MAC}/event", event_payload(alert_ms=0, first_seen_ms=0, dwell_s=5.0))
    [rec] = app.events.recorded
    assert rec["alert"] == Alert(first_seen=995.0, ts=1000.0, max_conf=0.83)
    assert rec["mark_frame"] is False


def test_malformed_event_dropped():
    app = make_app()
    app.on_message(f"{MAC}/event", b"\x05\x00{bad")
    assert app.events.recorded == []


def test_frames_and_events_mark_device_seen():
    app = make_app(clock=Clock(42.0))
    send_frame(app)
    app.on_message(f"{MAC}/event", event_payload())
    assert app.events.devices == [{"mac": MAC, "online": True, "status": None, "seen_ts": 42.0}] * 2


def test_status_updates_device():
    app = make_app(clock=Clock(42.0))
    text = json.dumps({"rssi": -70, "detect_ok": True})
    app.on_message(f"{MAC}/status", text.encode())
    assert app.events.devices == [{"mac": MAC, "online": True, "status": text, "seen_ts": 42.0}]


def test_retained_status_does_not_bump_seen():
    app = make_app(clock=Clock(42.0))
    app.on_message(f"{MAC}/status", b'{"rssi":-70}', retained=True)
    assert app.events.devices == [{"mac": MAC, "online": None, "status": '{"rssi":-70}', "seen_ts": None}]


def test_invalid_status_not_stored():
    app = make_app(clock=Clock(42.0))
    app.on_message(f"{MAC}/status", b"not json")
    app.on_message(f"{MAC}/status", b"[1]")
    assert [d["status"] for d in app.events.devices] == [None, None]


def test_online_messages():
    app = make_app(clock=Clock(42.0))
    app.on_message(f"{MAC}/online", b"1")
    app.on_message(f"{MAC}/online", b"0")
    app.on_message(f"{MAC}/online", b"1", retained=True)
    app.on_message(f"{MAC}/online", b"0", retained=True)
    assert [(d["online"], d["seen_ts"]) for d in app.events.devices] == [
        (True, 42.0), (False, None), (True, None), (False, None),
    ]


def test_short_payload_dropped():
    detector = FakeDetector()
    app = make_app(detector=detector)
    app.on_message(f"{MAC}/image", b"\x00" * 12)
    app.process_pending(timeout=0)
    assert detector.calls == 0


def test_unexpected_topics_ignored():
    detector = FakeDetector()
    app = make_app(detector=detector)
    payload = protocol.pack_image(1, b"jpeg")
    for t in ("foo", "a/b/image", "/image"):
        app.on_message(t, payload)
    app.process_pending(timeout=0)
    assert detector.calls == 0 and app.events.devices == []


def test_detector_error_records_no_inference():
    app = make_app(detector=FakeDetector(error=RuntimeError("boom")))
    send_frame(app)
    assert app.events.inferences == []


def test_event_store_errors_do_not_crash():
    app = make_app(events=FakeEvents(error=OSError("disk full")))
    send_frame(app)
    app.on_message(f"{MAC}/event", event_payload())
    app.on_message(f"{MAC}/status", b'{"rssi":-1}')
    app.on_message(f"{MAC}/online", b"0")


def test_frame_slots_keep_only_latest():
    slots = FrameSlots()
    old, new = Frame(1.0, True, 0.5, 0.0, b"old"), Frame(2.0, True, 0.6, 1.0, b"new")
    other = Frame(1.0, False, None, 0.0, b"other")
    slots.put(MAC, old)
    slots.put(MAC, new)
    slots.put("bbbbbbbbbbbb", other)
    assert slots.take_all(timeout=0) == {MAC: new, "bbbbbbbbbbbb": other}
    assert slots.take_all(timeout=0) == {}


def test_on_message_never_raises(monkeypatch):
    app = make_app()

    def boom(mac, payload):
        raise RuntimeError("bug in handler")

    monkeypatch.setattr(app, "_on_image", boom)
    app.on_message(f"{MAC}/image", protocol.pack_image(1, b"jpeg"))
```

Replace `server/tests/test_integration.py` with:

```python
import io
import socket
import threading
import time

import paho.mqtt.client as mqtt
import pytest
from PIL import Image

from master import protocol
from master.app import MasterApp, connect
from master.events import EventStore

pytestmark = pytest.mark.integration

HOST, PORT = "127.0.0.1", 1883
MAC = "0123456789ab"


def _broker_up() -> bool:
    try:
        socket.create_connection((HOST, PORT), timeout=1).close()
        return True
    except OSError:
        return False


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


class AlwaysPerson:
    def person_confidence(self, jpeg):
        return 0.9


@pytest.mark.skipif(not _broker_up(), reason="Mosquitto not running on 127.0.0.1:1883")
def test_device_event_recorded_and_master_never_alerts(tmp_path):
    store = EventStore(tmp_path / "events")
    app = MasterApp(AlwaysPerson(), store, threshold=0.6)
    server = connect(app, HOST, PORT, "", "", client_id="master-test")
    stop = threading.Event()
    worker = threading.Thread(target=app.run_worker, args=(stop,), daemon=True)
    worker.start()

    alerts = []
    device = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MAC)
    device.on_message = lambda c, u, m: alerts.append(m.topic)
    device.connect(HOST, PORT)
    device.subscribe(protocol.topic(MAC, "alert"), qos=1)
    device.loop_start()
    time.sleep(1.0)  # let both clients finish subscribing

    jpeg = _jpeg()
    now_ms = int(time.time() * 1000)
    try:
        device.publish(protocol.topic(MAC, "image"), protocol.pack_image(now_ms, jpeg, 0.9, 5.0), qos=0)
        time.sleep(0.5)
        event = protocol.DeviceEvent(now_ms, now_ms - 5000, 5.0, 0.9)
        device.publish(protocol.topic(MAC, "event"), protocol.pack_event(event, jpeg), qos=1)
        time.sleep(1.0)
    finally:
        stop.set()
        device.loop_stop()
        device.disconnect()
        server.loop_stop()
        server.disconnect()

    assert alerts == []
    [row] = store.recent()
    assert row["mac"] == MAC and row["dwell_s"] == 5.0 and row["max_conf"] == 0.9
    [frame] = store.inferences(MAC)
    assert frame["alerted"] == 1 and frame["device_score"] == 0.9
    store.close()
```

In `server/tests/test_settings.py`:
- In `test_defaults_without_env_file`, change the key tuple to `("MQTT_USER", "MQTT_PASS", "PEDESTRIAN_CONF_THRESHOLD")` and delete the three asserts on `alert_dwell_seconds`, `max_gap_seconds`, `alert_cooldown_seconds`. Add `assert not hasattr(s, "alert_dwell_seconds")`.
- Replace `test_reads_env_file` with:

```python
def test_reads_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("PEDESTRIAN_CONF_THRESHOLD=0.5\nALERT_DWELL_SECONDS=8\nMQTT_USER=server\nMQTT_PASS=\n",
                   encoding="utf-8")
    s = Settings(_env_file=env)  # an old .env with dwell settings still loads
    assert s.pedestrian_conf_threshold == 0.5
    assert s.mqtt_user == "server"
    assert s.mqtt_pass == ""
```

In `server/tests/test_web.py`:
- Change the `client` fixture's `Settings(...)` to `Settings(_env_file=None, events_dir=root, pedestrian_conf_threshold=0.6, inference_history=200)`.
- Replace `test_config` with:

```python
def test_config(client):
    assert client.get("/api/config").json() == {"threshold": 0.6, "history": 200}
```

Delete `server/tests/test_logic.py`.

- [ ] **Step 2: Run and see them fail**

Run: `$PY -m pytest -q`
Expected: failures in `test_app.py` (`cannot import name 'Frame'`), `test_settings.py`, `test_web.py::test_config`.

- [ ] **Step 3: Implement**

Replace `server/master/app.py` with:

```python
"""Master service: records device warnings and status; scores stream-mode frames with YOLO.

Devices decide alerts themselves. The master never publishes {mac}/alert on its own.
"""

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import paho.mqtt.client as mqtt

from master import protocol
from master.events import Alert

log = logging.getLogger("master")


@dataclass(frozen=True)
class Frame:
    ts: float                    # Unix seconds: device capture time, or server time when not synced
    synced: bool                 # ts came from the device clock
    device_score: float | None
    dwell_s: float
    jpeg: bytes


class FrameSlots:
    """Latest unprocessed frame per device. A new frame overwrites the old one."""

    def __init__(self):
        self._slots: dict[str, Frame] = {}
        self._cond = threading.Condition()

    def put(self, mac: str, frame: Frame) -> None:
        with self._cond:
            self._slots[mac] = frame
            self._cond.notify()

    def take_all(self, timeout: float | None) -> dict[str, Frame]:
        with self._cond:
            if not self._slots:
                self._cond.wait(timeout)
            items, self._slots = self._slots, {}
            return items


class MasterApp:
    def __init__(self, detector, events, threshold: float, clock: Callable[[], float] = time.time):
        self.detector = detector
        self.events = events
        self.threshold = threshold  # YOLO cutoff for stream-mode frames
        self.clock = clock
        self.slots = FrameSlots()

    # Called on the MQTT network thread. Must never raise: an exception here
    # stops paho's network loop and the server would stop receiving.
    def on_message(self, topic: str, payload: bytes, retained: bool = False) -> None:
        try:
            self._dispatch(topic, payload, retained)
        except Exception:
            log.exception("error handling message on %r", topic)

    def _dispatch(self, topic: str, payload: bytes, retained: bool) -> None:
        parsed = protocol.parse_topic(topic)
        if parsed is None:
            log.warning("ignoring message on unexpected topic %r", topic)
            return
        mac, kind = parsed
        if kind == "image":
            self._on_image(mac, payload)
        elif kind == "event":
            self._on_event(mac, payload)
        elif kind == "status":
            self._on_status(mac, payload, retained)
        elif kind == "online":
            self._on_online(mac, payload, retained)

    def _update_device(self, mac: str, **fields) -> None:
        try:
            self.events.update_device(mac, **fields)
        except Exception:
            log.exception("%s: failed to update device", mac)

    def _on_image(self, mac: str, payload: bytes) -> None:
        try:
            img = protocol.parse_image(payload)
        except protocol.ProtocolError as e:
            log.warning("%s: dropping frame: %s", mac, e)
            return
        now = self.clock()
        synced = img.capture_ms != 0
        ts = img.capture_ms / 1000 if synced else now
        self.slots.put(mac, Frame(ts, synced, img.score, img.dwell_s, img.jpeg))
        self._update_device(mac, online=True, seen_ts=now)

    def _on_event(self, mac: str, payload: bytes) -> None:
        try:
            ev, jpeg = protocol.parse_event(payload)
        except protocol.ProtocolError as e:
            log.warning("%s: dropping event: %s", mac, e)
            return
        now = self.clock()
        if ev.alert_ms:
            alert = Alert(first_seen=ev.first_seen_ms / 1000, ts=ev.alert_ms / 1000, max_conf=ev.max_score)
        else:
            alert = Alert(first_seen=now - ev.dwell_s, ts=now, max_conf=ev.max_score)
        log.info("%s WARNING dwell=%.1fs max_score=%.2f", mac, alert.dwell_s, alert.max_conf)
        try:
            self.events.record(mac, alert, jpeg, mark_frame=ev.alert_ms != 0)
        except Exception:
            log.exception("%s: failed to record event", mac)
        self._update_device(mac, online=True, seen_ts=now)

    def _on_status(self, mac: str, payload: bytes, retained: bool) -> None:
        text = payload.decode("utf-8", "replace")
        try:
            ok = isinstance(json.loads(text), dict)
        except ValueError:
            ok = False
        if not ok:
            log.warning("%s: status is not a JSON object: %r", mac, text[:200])
        status = text if ok else None
        if retained:  # sent by the broker on subscribe: says nothing about now
            self._update_device(mac, status=status)
        else:
            self._update_device(mac, online=True, status=status, seen_ts=self.clock())

    def _on_online(self, mac: str, payload: bytes, retained: bool) -> None:
        if payload == b"0":
            log.warning("%s offline", mac)
            self._update_device(mac, online=False)
        else:
            log.info("%s online", mac)
            self._update_device(mac, online=True, seen_ts=None if retained else self.clock())

    # Called on the worker thread.
    def process(self, mac: str, frame: Frame) -> None:
        try:
            conf = self.detector.person_confidence(frame.jpeg)
        except Exception:
            log.exception("%s: detection failed, dropping frame", mac)
            return
        try:
            self.events.record_inference(mac, frame.ts, conf, conf >= self.threshold, frame.dwell_s,
                                         False, frame.jpeg, device_score=frame.device_score,
                                         match_event=frame.synced)
        except Exception:
            log.exception("%s: failed to record inference", mac)

    def process_pending(self, timeout: float | None = 0.5) -> None:
        for mac, frame in self.slots.take_all(timeout).items():
            self.process(mac, frame)

    def run_worker(self, stop: threading.Event) -> None:
        while not stop.is_set():
            self.process_pending()


def connect(app: MasterApp, host: str, port: int, user: str, password: str,
            client_id: str = "master") -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    if user or password:
        client.username_pw_set(user, password or None)

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("MQTT connect failed: %s", reason_code)
            return
        log.info("MQTT connected to %s:%s", host, port)
        c.subscribe([("+/image", 0), ("+/event", 1), ("+/status", 1), ("+/online", 1)])

    def on_disconnect(c, userdata, flags, reason_code, properties):
        log.warning("MQTT disconnected: %s", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = lambda c, u, m: app.on_message(m.topic, m.payload, bool(m.retain))
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(host, port, keepalive=30)
    client.loop_start()
    return client


def main() -> None:
    from master.detector import Detector
    from master.events import EventStore
    from master.settings import Settings

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = Settings()
    app = MasterApp(
        detector=Detector(s.model_path, s.device),
        events=EventStore(s.events_dir, history=s.inference_history),
        threshold=s.pedestrian_conf_threshold,
    )
    client = connect(app, s.mqtt_host, s.mqtt_port, s.mqtt_user, s.mqtt_pass)
    stop = threading.Event()
    try:
        app.run_worker(stop)
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        client.loop_stop()
        client.disconnect()
        app.events.close()


if __name__ == "__main__":
    main()
```

Delete `server/master/logic.py`.

In `server/master/settings.py`, delete the three lines `alert_dwell_seconds`, `max_gap_seconds`, `alert_cooldown_seconds`, and change the comment above `pedestrian_conf_threshold` (add one if there is none) to:

```python
    # YOLO cutoff for stream-mode frames. Alerts are decided on each device.
    pedestrian_conf_threshold: float = 0.6
```

In `server/.env.example`, replace the `# Detection` and `# Alert rule` blocks with:

```
# Detection of stream-mode frames (python -m master.cli start <mac>)
MODEL_PATH=yolo11n.pt
# cpu or cuda:0
DEVICE=cpu
# A streamed frame is "pedestrian" when YOLO's best person score is >= this.
# Alerts are decided on each device: change its threshold, dwell, gap and cooldown with
#   python -m master.cli config <mac> threshold=0.6 dwell_s=5 max_gap_s=3 cooldown_s=30
PEDESTRIAN_CONF_THRESHOLD=0.6
```

In `server/master/web.py`, replace the `config()` endpoint body with:

```python
    @app.get("/api/config")
    def config() -> dict:
        return {"threshold": settings.pedestrian_conf_threshold, "history": settings.inference_history}
```

- [ ] **Step 4: Run the full server suite**

Run: `$PY -m pytest -q`
Expected: all pass. With Mosquitto running locally, `test_integration.py` also passes; otherwise it is skipped.

- [ ] **Step 5: Commit**

```bash
git add -A server/master/app.py server/master/logic.py server/master/settings.py server/master/web.py server/.env.example server/tests
git commit -m "feat(server): ingest device events and status; dwell logic moves to the device"
```

---

### Task 10: Dashboard API: devices from status, device scores

**Files:**
- Modify: `server/master/web.py`
- Test: `server/tests/test_web.py`

**Interfaces:**
- Consumes: Task 8 `devices` table and `device_score` column.
- Produces (used by Task 11):

```
GET /api/devices -> [{mac, online: bool, last_seen_ts: float|null, count: int,
                      last_ts, last_conf, last_device_score, last_positive, last_dwell_s, last_alerted,  (null when no frames)
                      streaming, detect_ok: bool|null, threshold, dwell_s, max_gap_s, cooldown_s: float|null,
                      last_warning_ts: float|null}]   ordered by mac
GET /api/inferences -> rows gain device_score: float|null
```

- [ ] **Step 1: Write the failing tests**

In `server/tests/test_web.py`:

Add `import json` to the imports, and replace `_fill` with:

```python
STATUS = {"rssi": -60, "streaming": True, "detect_ok": True, "threshold": 0.55, "dwell_s": 4.0,
          "max_gap_s": 3.0, "cooldown_s": 20.0, "fw": "0.2.0"}


def _fill(root):
    store = EventStore(root)
    store.record_inference(MAC, 100.0, 0.9, True, 0.0, False, _jpeg(), device_score=0.7)
    store.record_inference(OTHER, 101.0, 0.1, False, 0.0, False, _jpeg())
    store.record_inference(MAC, 102.0, 0.8, True, 2.0, True, _jpeg(), device_score=0.75)
    store.record(MAC, Alert(first_seen=97.0, ts=102.0, max_conf=0.9), _jpeg())
    store.update_device(MAC, online=True, status=json.dumps(STATUS), seen_ts=103.0)
    store.update_device(OTHER, online=False, seen_ts=101.0)
    return store
```

Replace `test_devices` and `test_devices_without_events_table` with:

```python
def test_devices(client, root):
    _fill(root).close()
    assert client.get("/api/devices").json() == [
        {"mac": MAC, "online": True, "last_seen_ts": 103.0, "count": 2,
         "last_ts": 102.0, "last_conf": 0.8, "last_device_score": 0.75, "last_positive": True,
         "last_dwell_s": 2.0, "last_alerted": True,
         "streaming": True, "detect_ok": True, "threshold": 0.55, "dwell_s": 4.0,
         "max_gap_s": 3.0, "cooldown_s": 20.0, "last_warning_ts": 102.0},
        {"mac": OTHER, "online": False, "last_seen_ts": 101.0, "count": 1,
         "last_ts": 101.0, "last_conf": 0.1, "last_device_score": None, "last_positive": False,
         "last_dwell_s": 0.0, "last_alerted": False,
         "streaming": None, "detect_ok": None, "threshold": None, "dwell_s": None,
         "max_gap_s": None, "cooldown_s": None, "last_warning_ts": None},
    ]


def test_device_without_frames_is_listed(client, root):
    store = EventStore(root)
    store.update_device(MAC, online=True, status=json.dumps(STATUS), seen_ts=50.0)
    store.close()
    [row] = client.get("/api/devices").json()
    assert row["mac"] == MAC and row["count"] == 0 and row["last_ts"] is None
    assert row["last_positive"] is None and row["last_alerted"] is None
    assert row["threshold"] == 0.55 and row["dwell_s"] == 4.0 and row["last_seen_ts"] == 50.0


@pytest.mark.parametrize("status", [
    '{"threshold":"high","detect_ok":1,"dwell_s":true,"streaming":"yes","cooldown_s":null}',
    "not json",
    "[1, 2]",
])
def test_status_fields_type_checked(client, root, status):
    store = EventStore(root)
    store.update_device(MAC, online=True, status=status, seen_ts=50.0)
    store.close()
    [row] = client.get("/api/devices").json()
    for key in ("threshold", "detect_ok", "dwell_s", "streaming", "cooldown_s", "max_gap_s"):
        assert row[key] is None


def test_devices_without_events_table(client, root):
    store = EventStore(root)
    store.update_device(MAC, online=True, seen_ts=1.0)
    store.close()
    con = sqlite3.connect(root / "events.db")
    con.execute("DROP TABLE events")
    con.commit()
    con.close()
    [row] = client.get("/api/devices").json()
    assert row["mac"] == MAC and row["last_warning_ts"] is None


def test_inferences_include_device_score(client, root):
    _fill(root).close()
    rows = client.get("/api/inferences").json()
    assert [r["device_score"] for r in rows] == [0.75, None, 0.7]
```

- [ ] **Step 2: Run and see them fail**

Run: `$PY -m pytest tests/test_web.py -q`
Expected: `test_devices`, `test_device_without_frames_is_listed`, `test_status_fields_type_checked`, `test_devices_without_events_table`, `test_inferences_include_device_score` fail.

- [ ] **Step 3: Implement**

In `server/master/web.py`, add `import json` and `import math` to the imports, and add below `_clamp`:

```python
_STATUS_BOOLS = ("streaming", "detect_ok")
_STATUS_NUMBERS = ("threshold", "dwell_s", "max_gap_s", "cooldown_s")


def _status_fields(text: str | None) -> dict:
    """A device's active settings from its last status JSON. The JSON comes from the
    device and is untrusted: a missing or wrongly typed field becomes None."""
    try:
        status = json.loads(text) if text else {}
    except ValueError:
        status = {}
    if not isinstance(status, dict):
        status = {}
    out = {}
    for key in _STATUS_BOOLS:
        v = status.get(key)
        out[key] = v if isinstance(v, bool) else None
    for key in _STATUS_NUMBERS:
        v = status.get(key)
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        out[key] = float(v) if ok else None
    return out


def _bool_or_none(v) -> bool | None:
    return None if v is None else bool(v)
```

Replace the `devices()` endpoint with:

```python
    @app.get("/api/devices")
    def devices() -> list[dict]:
        rows = query(
            "SELECT d.mac AS mac, d.online AS online, d.status AS status, d.last_seen_ts AS last_seen_ts,"
            " COALESCE(c.count, 0) AS count, i.ts AS last_ts, i.conf AS last_conf,"
            " i.device_score AS last_device_score, i.positive AS last_positive,"
            " i.dwell_s AS last_dwell_s, i.alerted AS last_alerted"
            " FROM devices d"
            " LEFT JOIN (SELECT mac, MAX(id) AS max_id, COUNT(*) AS count FROM inferences GROUP BY mac) c"
            " ON c.mac = d.mac"
            " LEFT JOIN inferences i ON i.id = c.max_id"
            " ORDER BY d.mac"
        )
        warnings = {
            r["mac"]: r["last_warning_ts"]
            for r in query("SELECT mac, MAX(alert_ts) AS last_warning_ts FROM events GROUP BY mac")
        }
        for r in rows:
            r["online"] = bool(r["online"])
            r["last_positive"] = _bool_or_none(r["last_positive"])
            r["last_alerted"] = _bool_or_none(r["last_alerted"])
            r.update(_status_fields(r.pop("status")))
            r["last_warning_ts"] = warnings.get(r["mac"])
        return rows
```

In the `inferences()` endpoint, change the SQL start to
`"SELECT id, mac, ts, conf, positive, dwell_s, alerted, thumb, device_score FROM inferences WHERE id > ?"`.

Update the module docstring's first line to `"""Read-only dashboard: devices, warnings, and stream-mode frames from the master's event store.`.

- [ ] **Step 4: Run the full server suite**

Run: `$PY -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/master/web.py server/tests/test_web.py
git commit -m "feat(server): list devices from status, expose device settings and scores"
```

---

### Task 11: Dashboard, fake device, docs

**Files:**
- Modify: `server/master/static/app.js`
- Modify: `server/master/static/index.html`
- Modify: `server/tools/fake_device.py`
- Modify: `server/README.md`, `README.md`
- Test: `server/tests/test_web.py` (existing `test_page_has_no_external_resources`, `test_index_served`, `test_static_assets_served`)

**Interfaces:**
- Consumes: Task 10 `/api/devices` and `/api/inferences` shapes, Task 9 `/api/config`.

- [ ] **Step 1: HTML**

In `server/master/static/index.html`:

Replace the `<dl class="settings" ...>` element with:

```html
    <dl class="settings" id="settings" aria-label="Server settings">
      <div><dt>YOLO cutoff</dt><dd id="set-threshold">–</dd></div>
      <div><dt>History</dt><dd id="set-history">–</dd></div>
    </dl>
```

In the devices table header, change `<th scope="col" class="num">Conf.</th>` to `<th scope="col" class="num">Score</th>` and `<th scope="col" class="num hide-sm">Last frame</th>` to `<th scope="col" class="num hide-sm">Last seen</th>`.

Change the `devices-empty` text to:
`No devices yet. A device appears here within 2 seconds of its first status message reaching master.app.`

In the warnings table header, change `Max conf.` to `Max score`.

Change the `frames-empty` text to:
`No frames. Frames appear only for devices in stream mode: python -m master.cli start &lt;id&gt;.`

- [ ] **Step 2: JS**

In `server/master/static/app.js`:

Add below `const STALE_S = 10;`:

```js
const STATUS_STALE_S = 150; // devices send status every 60 s
```

Change the `cfg` line in `state` to:

```js
  cfg: { threshold: 0.6, history: 200 },
```

Replace `loadConfig` with:

```js
async function loadConfig() {
  const cfg = await getJSON("/api/config");
  state.cfg = cfg;
  state.cfgLoaded = true;
  $("#set-threshold").textContent = cfg.threshold.toFixed(2);
  $("#set-history").textContent = String(cfg.history);
}
```

Add below `const conf = ...`:

```js
const score = (s) => (s == null ? "–" : s.toFixed(2));
```

Replace `deviceState` with:

```js
// Devices decide warnings themselves. Frames (and so "Pedestrian") exist only in stream mode.
function deviceState(d, nowS) {
  if (!d.online) return { kind: "nosignal", label: "Offline", detail: "", rank: 3 };
  if (d.last_seen_ts == null || nowS - d.last_seen_ts > STATUS_STALE_S) {
    return { kind: "nosignal", label: "No signal", detail: "", rank: 3 };
  }
  if (d.detect_ok === false) return { kind: "nosignal", label: "Detector fault", detail: "", rank: 3 };
  const cooldown = d.cooldown_s ?? 30;
  if (d.last_warning_ts != null && nowS - d.last_warning_ts < Math.max(cooldown, STALE_S)) {
    return { kind: "warning", label: "Warning", detail: clock(d.last_warning_ts), rank: 0 };
  }
  const fresh = d.last_ts != null && nowS - d.last_ts <= STALE_S;
  if (fresh && d.last_device_score != null && d.threshold != null && d.last_device_score >= d.threshold) {
    const limit = d.dwell_s == null ? "" : ` of ${d.dwell_s} s`;
    return { kind: "pedestrian", label: "Pedestrian", detail: `${secs(d.last_dwell_s ?? 0)}${limit}`, rank: 1 };
  }
  return { kind: "clear", label: "Clear", detail: d.streaming ? "streaming" : "", rank: 2 };
}
```

Replace `updateDial` with:

```js
function updateDial(parts, kind, dwell, limit) {
  const count = Math.max(1, Math.min(12, Math.round(limit || 1)));
  if (parts.tickCount !== count) {
    parts.ticks.replaceChildren();
    // Tick 0 (at 12 o'clock) marks the dwell limit, where a warning fires.
    buildTicks(parts.ticks, count, 0, 36, 44, "dial__tick", "limit");
    parts.tickCount = count;
  }
  parts.dial.dataset.kind = kind;
  const progress = limit > 0 ? Math.min(dwell / limit, 1) : 1;
  const fraction = kind === "pedestrian" ? progress : kind === "warning" ? 1 : 0;
  // A station hand never runs backwards: sweep forward, snap back to 12 on reset.
  const snapping = fraction < parts.fraction;
  parts.hand.classList.toggle("is-snapping", snapping);
  parts.hand.style.transform = `rotate(${fraction * 360}deg)`;
  if (snapping) {
    parts.hand.getBoundingClientRect(); // commit the snapped position before restoring the transition
    requestAnimationFrame(() => parts.hand.classList.remove("is-snapping"));
  }
  parts.fraction = fraction;
}
```

In `renderDevices`:
- change the sort line to
  `decorated.sort((a, b) => a.st.rank - b.st.rank || (b.d.last_dwell_s ?? 0) - (a.d.last_dwell_s ?? 0) || a.d.mac.localeCompare(b.d.mac));`
- change `updateDial(parts, st.kind, d.last_dwell_s);` to `updateDial(parts, st.kind, d.last_dwell_s ?? 0, d.dwell_s ?? 0);`
- change `parts.tdConf.textContent = conf(d.last_conf);` to `parts.tdConf.textContent = score(d.last_device_score);`
- change `parts.tdLast.textContent = clock(d.last_ts);` to `parts.tdLast.textContent = d.last_seen_ts == null ? "–" : clock(d.last_seen_ts);`

In `frameItem`, replace the `caption` line and the `statusText` line with:

```js
  const caption = `${r.mac} · ${clock(r.ts)} · YOLO ${conf(r.conf)} · device ${score(r.device_score)}`;
```

```js
  const statusText = `${r.positive ? `Pedestrian · ${secs(r.dwell_s)}` : "Clear"} · device ${score(r.device_score)}`;
```

In `renderStrips`, make devices without frames skip strips. Change the loop head to:

```js
  for (const { d, st } of decorated) {
    if (!d.count) continue; // not streaming: no frames to show
    present.add(d.mac);
```

(the `present.add(d.mac);` line that was first in the loop body moves below the `continue`).

In `renderWarnings`, the `conf(a.max_conf)` cell is unchanged (now labeled "Max score").

- [ ] **Step 3: Fake device**

Replace the body of `server/tools/fake_device.py` from the module docstring through `main()` with:

```python
"""Pretend to be an edge device: publish status, optional JPEG frames, optional warning events.

    python tools/fake_device.py --mac 0123456789ab --dir samples --interval 1
    python tools/fake_device.py --mac 0123456789ab --dir samples --event --count 0 --no-frames
"""

import argparse
import itertools
import json
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from master import protocol

STATUS = {"rssi": -60, "battery_mv": 0, "uptime_s": 0, "streaming": True, "fw": "fake",
          "detect_ok": True, "threshold": 0.6, "dwell_s": 5, "max_gap_s": 3, "cooldown_s": 30}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mac", required=True)
    ap.add_argument("--dir", required=True, type=Path, help="folder of .jpg files, sent in name order, looped")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between frames")
    ap.add_argument("--count", type=int, default=0, help="frames to send; 0 = forever")
    ap.add_argument("--score", type=float, default=0.8, help="device score sent with each frame")
    ap.add_argument("--no-frames", action="store_true", help="send no frames (a device with streaming off)")
    ap.add_argument("--event", action="store_true", help="publish one warning event first, with the first image")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--no-timestamp", action="store_true", help="send capture_ms=0 (unsynced clock)")
    args = ap.parse_args()

    files = sorted(args.dir.glob("*.jpg"))
    if not files:
        raise SystemExit(f"no .jpg files in {args.dir}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=args.mac)
    client.will_set(protocol.topic(args.mac, "online"), b"0", qos=1, retain=True)
    client.on_message = lambda c, u, m: print(f"<- {m.topic} {m.payload.decode()}")
    client.connect(args.host, args.port, keepalive=30)
    client.subscribe([(protocol.topic(args.mac, k), 1) for k in ("alert", "cmd", "config")])
    client.loop_start()
    client.publish(protocol.topic(args.mac, "online"), b"1", qos=1, retain=True)
    status = {**STATUS, "streaming": not args.no_frames}
    client.publish(protocol.topic(args.mac, "status"), json.dumps(status).encode(), qos=1, retain=True)

    def now_ms() -> int:
        return 0 if args.no_timestamp else int(time.time() * 1000)

    if args.event:
        ms = now_ms()
        event = protocol.DeviceEvent(ms, ms - 5000 if ms else 0, 5.0, args.score)
        client.publish(protocol.topic(args.mac, "event"), protocol.pack_event(event, files[0].read_bytes()), qos=1)
        print(f"-> event with {files[0].name}")

    frames = itertools.cycle(files) if args.count == 0 else itertools.islice(itertools.cycle(files), args.count)
    try:
        if args.no_frames:
            while True:
                time.sleep(60)
                client.publish(protocol.topic(args.mac, "status"), json.dumps(status).encode(), qos=1, retain=True)
        for path in frames:
            payload = protocol.pack_image(now_ms(), path.read_bytes(), args.score, 0.0)
            client.publish(protocol.topic(args.mac, "image"), payload, qos=0)
            print(f"-> {path.name}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(protocol.topic(args.mac, "online"), b"0", qos=1, retain=True).wait_for_publish(2)
        client.loop_stop()
        client.disconnect()
```

(keep the `if __name__ == "__main__": main()` footer).

- [ ] **Step 4: Docs**

In `server/README.md`, replace the first paragraph (lines 3–5) with:

```markdown
Edge devices detect pedestrians and play the warning themselves. The master records
each device's warnings (`{mac}/event`, with a snapshot) and status, serves the LAN
dashboard, and, for devices in stream mode (`python -m master.cli start <mac>`),
scores their frames with YOLO11n so the dashboard shows YOLO and device scores
side by side. The master never sends `{mac}/alert` by itself; the CLI still can.
Design: `docs/superpowers/specs/2026-10-11-on-device-inference-design.md`.
```

In the "Dashboard" section, replace the sentence starting `Shows recent inferences` with:

```markdown
Shows every device (online state, its active threshold and dwell, last warning),
recent warnings with snapshots, and, for streaming devices, recent frames with
YOLO and device scores.
```

After the `fake_device.py` example line, add:

```markdown
Add `--event` to publish one warning event, and `--no-frames` to act like a device
with streaming off (status only).
```

Add a short section before "Dashboard" (or after the CLI section, wherever device commands are listed):

```markdown
### Device alert settings

Each device decides warnings with its own settings, kept across reboots:

    python -m master.cli config <mac> threshold=0.6 dwell_s=5 max_gap_s=3 cooldown_s=30

`threshold` 0.05–0.99, `dwell_s` 0–600, `max_gap_s` 0.5–60, `cooldown_s` 0–3600.
```

In the top-level `README.md`, replace the first paragraph (lines 3–6) with:

```markdown
Edge cameras (ESP32-S3) detect pedestrians on the device with an INT8 model. When a
pedestrian stays in view for the device's `dwell_s`, the device plays a warning
sound and reports the warning, with a snapshot, to the master server over MQTT. A
LAN dashboard shows every device, its warnings, and, for devices in stream mode,
live frames scored by both the device and YOLO11n on the server.
```

and in "Quick start" step 2 change `install ESP-IDF v5.1–v5.4` to `install ESP-IDF v5.3–v5.5`.

- [ ] **Step 5: Run the server suite**

Run: `$PY -m pytest -q`
Expected: all pass (`test_page_has_no_external_resources` confirms no `innerHTML` and no external URLs).

- [ ] **Step 6: Check the dashboard in a browser**

From `server/`, with Mosquitto running:

```powershell
$env:EVENTS_DIR = "$env:TEMP\ondevice-demo"
D:/pedestrian_classification/server/.venv/Scripts/python -m master.app        # terminal 1
D:/pedestrian_classification/server/.venv/Scripts/python -m master.web        # terminal 2
D:/pedestrian_classification/server/.venv/Scripts/python tools/fake_device.py --mac 0123456789ab --dir samples --event --count 20   # terminal 3
D:/pedestrian_classification/server/.venv/Scripts/python tools/fake_device.py --mac 0123456789ac --dir samples --no-frames          # terminal 4
```

Open `http://localhost:8000`. Expected: two devices listed. `...ab` shows Warning, then Clear or Pedestrian with frames carrying `device 0.80`. `...ac` shows Clear with no strip. The warnings table has one row with a working View button. The settings band shows `YOLO cutoff 0.60` and `History 200`. If `samples/` is empty, put a few JPEGs there first.

- [ ] **Step 7: Commit**

```bash
git add server/master/static/app.js server/master/static/index.html server/tools/fake_device.py server/README.md README.md
git commit -m "feat(server): dashboard for on-device warnings; fake device speaks the new protocol"
```
