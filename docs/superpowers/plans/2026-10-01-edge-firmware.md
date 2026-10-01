# Edge Firmware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ESP-IDF firmware for the edge device: capture JPEG frames and publish them over MQTT, receive `alert` / `cmd` / `config` messages, and play the embedded alert clip through LEDC PWM into a PAM8403. It runs over Wi-Fi on a Freenove ESP32-S3-WROOM CAM now, and the network and board sit behind interfaces so LTE can be added later.

**Architecture:** Two layers. `components/core` is pure C11 with no ESP-IDF headers (protocol, config parsing, message parsing, backoff, PCM scaling) and is unit-tested on the host with gcc. `main/` holds thin ESP-IDF modules (net, mqtt_link, cmd, camera, stream, audio, config_store, status, timesync), each behind its own header. `main.c` wires them together through those headers only.

**Tech Stack:** ESP-IDF ≥ 5.1 (C), espressif/esp32-camera ^2.0, esp-mqtt (WebSocket/TLS), cJSON (IDF `json` component; vendored v1.7.18 for host tests), gcc for host tests, Python 3 for `wav2raw.py`.

**Spec:** `docs/superpowers/specs/2026-09-29-pedestrian-alert-design.md` (§4 protocol, §6 firmware, §8 testing)

## Global Constraints

- ESP-IDF ≥ 5.1. Target `esp32s3`. Only `LEDC_LOW_SPEED_MODE` exists on the S3.
- `components/core` must not include any ESP-IDF or FreeRTOS header. It is compiled both by ESP-IDF and by host gcc with `-std=c11 -Wall -Wextra -Werror`.
- `main.c` includes only module headers: `net.h`, `mqtt_link.h`, `cmd.h`, `camera.h`, `audio.h`, `stream.h`, `status.h`, `config_store.h`, `timesync.h`, plus `core/*.h`. It never calls Wi-Fi, LTE, LEDC, camera, or NVS APIs directly.
- Pin numbers appear only in `main/boards/*.h`.
- Device ID = base MAC, lowercase hex, no separators (12 chars). It is the MQTT client ID. Topics are `{id}/{kind}`.
- Image payload = 8-byte little-endian `uint64` `capture_ms` + JPEG. `capture_ms = 0` when the clock is not synced (epoch before 2024-01-01T00:00:00Z = `1704067200000` ms).
- QoS/retain: `image` QoS 0 not retained; `status` QoS 1 retained; `online` QoS 1 retained (`"1"` on connect, `"0"` as Last Will). Subscriptions: `{id}/alert`, `{id}/cmd`, `{id}/config` at QoS 1.
- Config fields and ranges: `interval_ms` 100–3600000, `jpeg_quality` 0–63, `frame_size` one of `QVGA VGA SVGA XGA HD SXGA UXGA`, `volume` 0–100. Defaults: `interval_ms=1000`, `jpeg_quality=12`, `frame_size=VGA`, `volume=80`, `streaming=true`. Missing fields keep their current value; unknown fields are ignored; an invalid value for a known field rejects the whole update.
- `alert` `repeat` 1–10; missing or invalid → 1.
- `cmd` actions: `start`, `stop`, `reboot`, `status`.
- Status JSON: `{"rssi":<int>,"battery_mv":<int>,"uptime_s":<uint>,"streaming":<bool>,"fw":"<str>"}`, published every 60 s and on `status` command and on (re)connect.
- Network backoff: 5000, 10000, 30000, 60000 ms, then 60000 ms repeated; reset on IP acquired.
- Audio: LEDC 8-bit at 78 kHz on `BOARD_AUDIO_GPIO`; sample clock 16 kHz from gptimer; silence = duty 128.
- Kconfig defaults: `MQTT_URI="wss://mqtt.example.com:443/mqtt"`, `MQTT_USERNAME=""`, `MQTT_PASSWORD=""`, `WIFI_SSID=""`, `WIFI_PASSWORD=""`.
- This PC has no ESP-IDF. Only `components/core` and `tools/wav2raw.py` are verified here. Every `main/` file is verified by `idf.py build` and the Task 10 bring-up checklist, run on the user's ESP-IDF machine.
- Host compiler: `gcc` on PATH (MinGW GCC 6.3 at `/c/MinGW/bin/gcc`) or `CC=/c/msys64/mingw64/bin/gcc.exe` (GCC 15). Either must pass.

## Review Focus

1. **Config with one bad field** (`{"volume":20,"interval_ms":50}`): the whole update must be rejected and the device config left unchanged, not half-applied — pinned in Task 3.
2. **Retained config redelivered on every reconnect:** applying the same config twice must be harmless, and the camera must only be reconfigured when `frame_size` or `jpeg_quality` actually changed — pinned in Task 3 (`devcfg_equal`), used in Task 8.
3. **Topic or payload not NUL-terminated** (esp-mqtt passes pointer + length): parsing must respect the length and never read past it — pinned in Task 2 and Task 3.
4. **Clock not yet synced at first frames:** `capture_ms` must be 0, not a 1970 timestamp, so the server uses its own clock — pinned in Task 2.
5. **Status buffer too small or a long `fw` string:** the formatter must report failure, not write past the buffer — pinned in Task 4.

---

## File Structure

```
firmware/
  CMakeLists.txt                  # IDF project
  partitions.csv
  sdkconfig.defaults
  README.md                       # build, flash, config, bring-up checklist
  components/core/
    CMakeLists.txt
    include/core/backoff.h        # reconnect backoff steps
    include/core/proto.h          # device id, topics, image header, capture_ms
    include/core/devcfg.h         # runtime config: defaults, JSON apply, names
    include/core/msg.h            # cmd/alert parsing, status formatting
    include/core/pcm.h            # volume scaling (header-only)
    backoff.c proto.c devcfg.c msg.c
  main/
    CMakeLists.txt                # picks net backend from Kconfig
    Kconfig.projbuild
    idf_component.yml             # espressif/esp32-camera
    board.h                       # selects board header
    boards/freenove_s3cam.h
    net.h  net_wifi.c
    timesync.h  timesync.c
    config_store.h  config_store.c
    mqtt_link.h  mqtt_link.c
    cmd.h  cmd.c
    camera.h  camera.c
    stream.h  stream.c
    audio.h  audio.c
    status.h  status.c
    main.c
    assets/alert.raw              # generated by tools/wav2raw.py --demo
  test/host/
    run.sh                        # builds and runs host tests
    minitest.h  test_main.c
    test_backoff.c test_proto.c test_devcfg.c test_msg.c test_pcm.c
    third_party/cJSON.c cJSON.h   # v1.7.18, MIT
  tools/
    wav2raw.py
    test_wav2raw.py
```

---

### Task 1: Host test harness and backoff

**Files:**
- Create: `firmware/test/host/run.sh`, `firmware/test/host/minitest.h`, `firmware/test/host/test_main.c`, `firmware/test/host/test_backoff.c`
- Create: `firmware/test/host/third_party/cJSON.c`, `firmware/test/host/third_party/cJSON.h` (downloaded)
- Create: `firmware/components/core/include/core/backoff.h`, `firmware/components/core/backoff.c`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `typedef struct { uint8_t step; } backoff_t;`
  - `void backoff_reset(backoff_t *b);`
  - `uint32_t backoff_next_ms(backoff_t *b);` → 5000, 10000, 30000, 60000, 60000, …
  - Host harness: `CHECK(cond)`, `CHECK_INT(actual, expected)`, `CHECK_STR(actual, expected)`; each test file exposes `void test_<module>(void);` called from `test_main.c`.

- [ ] **Step 1: Vendor cJSON**

From `D:\pedestrian_classification`:
```bash
mkdir -p firmware/test/host/third_party
curl -fsSL -o firmware/test/host/third_party/cJSON.c https://raw.githubusercontent.com/DaveGamble/cJSON/v1.7.18/cJSON.c
curl -fsSL -o firmware/test/host/third_party/cJSON.h https://raw.githubusercontent.com/DaveGamble/cJSON/v1.7.18/cJSON.h
grep -m1 "CJSON_VERSION_PATCH" firmware/test/host/third_party/cJSON.h
```
Expected: `#define CJSON_VERSION_PATCH 18`

- [ ] **Step 2: Create the harness**

`firmware/test/host/minitest.h`:
```c
#pragma once
#include <stdio.h>
#include <string.h>

extern int mt_checks;
extern int mt_failures;

#define CHECK(cond)                                                          \
    do {                                                                     \
        mt_checks++;                                                         \
        if (!(cond)) {                                                       \
            mt_failures++;                                                   \
            printf("%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond);  \
        }                                                                    \
    } while (0)

#define CHECK_INT(actual, expected)                                          \
    do {                                                                     \
        long long a_ = (long long)(actual), e_ = (long long)(expected);      \
        mt_checks++;                                                         \
        if (a_ != e_) {                                                      \
            mt_failures++;                                                   \
            printf("%s:%d: %s == %lld, expected %lld\n", __FILE__, __LINE__, \
                   #actual, a_, e_);                                         \
        }                                                                    \
    } while (0)

#define CHECK_STR(actual, expected)                                          \
    do {                                                                     \
        const char *a_ = (actual), *e_ = (expected);                         \
        mt_checks++;                                                         \
        if (a_ == NULL || strcmp(a_, e_) != 0) {                             \
            mt_failures++;                                                   \
            printf("%s:%d: %s == \"%s\", expected \"%s\"\n", __FILE__,       \
                   __LINE__, #actual, a_ ? a_ : "(null)", e_);               \
        }                                                                    \
    } while (0)
```

`firmware/test/host/test_main.c`:
```c
#include <stdio.h>

#include "minitest.h"

int mt_checks;
int mt_failures;

void test_backoff(void);

int main(void)
{
    test_backoff();
    printf("%d checks, %d failures\n", mt_checks, mt_failures);
    return mt_failures ? 1 : 0;
}
```

`firmware/test/host/run.sh`:
```sh
#!/usr/bin/env sh
# Build and run host unit tests for components/core. Needs only a C compiler.
set -e
cd "$(dirname "$0")"
CC="${CC:-gcc}"
mkdir -p build
"$CC" -std=c11 -O1 -Ithird_party -c third_party/cJSON.c -o build/cJSON.o
"$CC" -std=c11 -Wall -Wextra -Werror -I../../components/core/include -Ithird_party \
    ../../components/core/*.c test_*.c build/cJSON.o -o build/host_tests
./build/host_tests
```

- [ ] **Step 3: Write the failing test**

`firmware/test/host/test_backoff.c`:
```c
#include "core/backoff.h"
#include "minitest.h"

void test_backoff(void)
{
    backoff_t b;
    backoff_reset(&b);
    CHECK_INT(backoff_next_ms(&b), 5000);
    CHECK_INT(backoff_next_ms(&b), 10000);
    CHECK_INT(backoff_next_ms(&b), 30000);
    CHECK_INT(backoff_next_ms(&b), 60000);
    CHECK_INT(backoff_next_ms(&b), 60000);
    CHECK_INT(backoff_next_ms(&b), 60000);

    backoff_reset(&b);
    CHECK_INT(backoff_next_ms(&b), 5000);
}
```

- [ ] **Step 4: Run to verify it fails**

Run: `sh firmware/test/host/run.sh`
Expected: compile error `core/backoff.h: No such file or directory`.

- [ ] **Step 5: Implement backoff**

`firmware/components/core/include/core/backoff.h`:
```c
#pragma once
#include <stdint.h>

/* Reconnect delays: 5 s, 10 s, 30 s, then 60 s forever. */
typedef struct {
    uint8_t step;
} backoff_t;

void backoff_reset(backoff_t *b);
uint32_t backoff_next_ms(backoff_t *b);
```

`firmware/components/core/backoff.c`:
```c
#include "core/backoff.h"

static const uint32_t STEPS_MS[] = {5000, 10000, 30000, 60000};
#define STEP_COUNT (sizeof(STEPS_MS) / sizeof(STEPS_MS[0]))

void backoff_reset(backoff_t *b)
{
    b->step = 0;
}

uint32_t backoff_next_ms(backoff_t *b)
{
    uint32_t ms = STEPS_MS[b->step];
    if (b->step < STEP_COUNT - 1) {
        b->step++;
    }
    return ms;
}
```

- [ ] **Step 6: Run to verify it passes**

Run: `sh firmware/test/host/run.sh`
Expected: `7 checks, 0 failures`

Also run with the second compiler: `CC=/c/msys64/mingw64/bin/gcc.exe sh firmware/test/host/run.sh`
Expected: `7 checks, 0 failures`

- [ ] **Step 7: Commit**

```bash
git add firmware/test/host firmware/components/core
git commit -m "feat(firmware): add host test harness and reconnect backoff"
```

---

### Task 2: Protocol helpers

**Files:**
- Create: `firmware/components/core/include/core/proto.h`, `firmware/components/core/proto.c`
- Create: `firmware/test/host/test_proto.c`
- Modify: `firmware/test/host/test_main.c`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `#define PROTO_ID_SIZE 13` (12 hex chars + NUL), `#define PROTO_HEADER_SIZE 8`, `#define PROTO_MIN_SYNCED_MS 1704067200000LL`
  - `typedef enum { PROTO_KIND_UNKNOWN, PROTO_KIND_ALERT, PROTO_KIND_CMD, PROTO_KIND_CONFIG } proto_kind_t;`
  - `void proto_mac_to_id(const uint8_t mac[6], char out[PROTO_ID_SIZE]);`
  - `bool proto_topic(char *buf, size_t len, const char *id, const char *kind);` (false if truncated)
  - `void proto_pack_header(uint8_t out[PROTO_HEADER_SIZE], uint64_t capture_ms);`
  - `uint64_t proto_capture_ms(int64_t epoch_ms);` (0 if before `PROTO_MIN_SYNCED_MS`)
  - `proto_kind_t proto_kind_of(const char *topic, size_t topic_len, const char *id);` (topic need not be NUL-terminated)

- [ ] **Step 1: Write the failing test**

`firmware/test/host/test_proto.c`:
```c
#include "core/proto.h"
#include "minitest.h"

static void test_mac_to_id(void)
{
    const uint8_t mac[6] = {0xA1, 0xB2, 0xC3, 0xD4, 0xE5, 0xF6};
    char id[PROTO_ID_SIZE];
    proto_mac_to_id(mac, id);
    CHECK_STR(id, "a1b2c3d4e5f6");
}

static void test_topic(void)
{
    char buf[32];
    CHECK(proto_topic(buf, sizeof buf, "a1b2c3d4e5f6", "image"));
    CHECK_STR(buf, "a1b2c3d4e5f6/image");

    char small[10];
    CHECK(!proto_topic(small, sizeof small, "a1b2c3d4e5f6", "image"));
}

static void test_header(void)
{
    uint8_t h[PROTO_HEADER_SIZE];
    proto_pack_header(h, 0x0102030405060708ULL);
    const uint8_t expected[8] = {0x08, 0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01};
    CHECK(memcmp(h, expected, 8) == 0);

    proto_pack_header(h, 1727600000123ULL);
    uint64_t back = 0;
    for (int i = 7; i >= 0; i--) {
        back = (back << 8) | h[i];
    }
    CHECK(back == 1727600000123ULL);
}

static void test_capture_ms(void)
{
    CHECK(proto_capture_ms(0) == 0);
    CHECK(proto_capture_ms(-5) == 0);
    CHECK(proto_capture_ms(1704067199999LL) == 0);
    CHECK(proto_capture_ms(1704067200000LL) == 1704067200000ULL);
    CHECK(proto_capture_ms(1790000000000LL) == 1790000000000ULL);
}

static void test_kind_of(void)
{
    const char *id = "a1b2c3d4e5f6";
#define KIND(t) proto_kind_of(t, strlen(t), id)
    CHECK_INT(KIND("a1b2c3d4e5f6/alert"), PROTO_KIND_ALERT);
    CHECK_INT(KIND("a1b2c3d4e5f6/cmd"), PROTO_KIND_CMD);
    CHECK_INT(KIND("a1b2c3d4e5f6/config"), PROTO_KIND_CONFIG);
    CHECK_INT(KIND("a1b2c3d4e5f6/image"), PROTO_KIND_UNKNOWN);
    CHECK_INT(KIND("a1b2c3d4e5f6/alertx"), PROTO_KIND_UNKNOWN);
    CHECK_INT(KIND("a1b2c3d4e5f6/"), PROTO_KIND_UNKNOWN);
    CHECK_INT(KIND("a1b2c3d4e5f6"), PROTO_KIND_UNKNOWN);
    CHECK_INT(KIND("000000000000/alert"), PROTO_KIND_UNKNOWN);
    CHECK_INT(KIND(""), PROTO_KIND_UNKNOWN);
#undef KIND
    /* Not NUL-terminated: only the first 16 bytes are the topic. */
    const char raw[] = "a1b2c3d4e5f6/cmdGARBAGE";
    CHECK_INT(proto_kind_of(raw, 16, id), PROTO_KIND_CMD);
}

void test_proto(void)
{
    test_mac_to_id();
    test_topic();
    test_header();
    test_capture_ms();
    test_kind_of();
}
```

Modify `firmware/test/host/test_main.c` — add the declaration and the call:
```c
void test_backoff(void);
void test_proto(void);

int main(void)
{
    test_backoff();
    test_proto();
    printf("%d checks, %d failures\n", mt_checks, mt_failures);
    return mt_failures ? 1 : 0;
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `sh firmware/test/host/run.sh`
Expected: compile error `core/proto.h: No such file or directory`.

- [ ] **Step 3: Implement**

`firmware/components/core/include/core/proto.h`:
```c
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PROTO_ID_SIZE 13            /* 12 lowercase hex chars + NUL */
#define PROTO_HEADER_SIZE 8         /* uint64 little-endian capture_ms */
#define PROTO_MIN_SYNCED_MS 1704067200000LL /* 2024-01-01T00:00:00Z */

typedef enum {
    PROTO_KIND_UNKNOWN,
    PROTO_KIND_ALERT,
    PROTO_KIND_CMD,
    PROTO_KIND_CONFIG,
} proto_kind_t;

void proto_mac_to_id(const uint8_t mac[6], char out[PROTO_ID_SIZE]);

/* Writes "{id}/{kind}". Returns false if it does not fit. */
bool proto_topic(char *buf, size_t len, const char *id, const char *kind);

void proto_pack_header(uint8_t out[PROTO_HEADER_SIZE], uint64_t capture_ms);

/* epoch_ms if the clock looks synced, otherwise 0 ("use server time"). */
uint64_t proto_capture_ms(int64_t epoch_ms);

/* Kind of an incoming topic addressed to `id`. `topic` need not be NUL-terminated. */
proto_kind_t proto_kind_of(const char *topic, size_t topic_len, const char *id);
```

`firmware/components/core/proto.c`:
```c
#include "core/proto.h"

#include <stdio.h>
#include <string.h>

void proto_mac_to_id(const uint8_t mac[6], char out[PROTO_ID_SIZE])
{
    static const char HEX[] = "0123456789abcdef";
    for (int i = 0; i < 6; i++) {
        out[2 * i] = HEX[mac[i] >> 4];
        out[2 * i + 1] = HEX[mac[i] & 0x0f];
    }
    out[12] = '\0';
}

bool proto_topic(char *buf, size_t len, const char *id, const char *kind)
{
    int n = snprintf(buf, len, "%s/%s", id, kind);
    return n > 0 && (size_t)n < len;
}

void proto_pack_header(uint8_t out[PROTO_HEADER_SIZE], uint64_t capture_ms)
{
    for (int i = 0; i < PROTO_HEADER_SIZE; i++) {
        out[i] = (uint8_t)(capture_ms >> (8 * i));
    }
}

uint64_t proto_capture_ms(int64_t epoch_ms)
{
    return epoch_ms >= PROTO_MIN_SYNCED_MS ? (uint64_t)epoch_ms : 0;
}

static bool kind_is(const char *k, size_t klen, const char *name)
{
    return klen == strlen(name) && memcmp(k, name, klen) == 0;
}

proto_kind_t proto_kind_of(const char *topic, size_t topic_len, const char *id)
{
    size_t id_len = strlen(id);
    if (topic_len <= id_len + 1 || memcmp(topic, id, id_len) != 0 || topic[id_len] != '/') {
        return PROTO_KIND_UNKNOWN;
    }
    const char *k = topic + id_len + 1;
    size_t klen = topic_len - id_len - 1;
    if (kind_is(k, klen, "alert")) {
        return PROTO_KIND_ALERT;
    }
    if (kind_is(k, klen, "cmd")) {
        return PROTO_KIND_CMD;
    }
    if (kind_is(k, klen, "config")) {
        return PROTO_KIND_CONFIG;
    }
    return PROTO_KIND_UNKNOWN;
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `sh firmware/test/host/run.sh`
Expected: `0 failures` (total checks printed; non-zero).

- [ ] **Step 5: Commit**

```bash
git add firmware/components/core firmware/test/host
git commit -m "feat(firmware): add protocol helpers"
```

---

### Task 3: Runtime config (devcfg)

**Files:**
- Create: `firmware/components/core/include/core/devcfg.h`, `firmware/components/core/devcfg.c`
- Create: `firmware/test/host/test_devcfg.c`
- Modify: `firmware/test/host/test_main.c`

**Interfaces:**
- Consumes: cJSON (`cJSON_ParseWithLength`, `cJSON_GetObjectItemCaseSensitive`, `cJSON_IsObject`, `cJSON_IsNumber`, `cJSON_IsString`, `cJSON_Delete`).
- Produces:
  - `typedef enum { DEVCFG_FRAME_QVGA, DEVCFG_FRAME_VGA, DEVCFG_FRAME_SVGA, DEVCFG_FRAME_XGA, DEVCFG_FRAME_HD, DEVCFG_FRAME_SXGA, DEVCFG_FRAME_UXGA, DEVCFG_FRAME_COUNT } devcfg_frame_t;`
  - `typedef struct { uint32_t interval_ms; uint8_t jpeg_quality; devcfg_frame_t frame_size; uint8_t volume; bool streaming; } devcfg_t;`
  - `void devcfg_defaults(devcfg_t *c);`
  - `bool devcfg_apply_json(devcfg_t *c, const char *json, size_t len);` — all-or-nothing
  - `bool devcfg_equal(const devcfg_t *a, const devcfg_t *b);`
  - `const char *devcfg_frame_name(devcfg_frame_t f);` (NULL if out of range)
  - `bool devcfg_frame_from_name(const char *name, devcfg_frame_t *out);`

- [ ] **Step 1: Write the failing test**

`firmware/test/host/test_devcfg.c`:
```c
#include "core/devcfg.h"
#include "minitest.h"

#define J(s) s, sizeof(s) - 1

static void test_defaults(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK_INT(c.interval_ms, 1000);
    CHECK_INT(c.jpeg_quality, 12);
    CHECK_INT(c.frame_size, DEVCFG_FRAME_VGA);
    CHECK_INT(c.volume, 80);
    CHECK(c.streaming);
}

static void test_partial_update_keeps_other_fields(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"volume\":60}")));
    CHECK_INT(c.volume, 60);
    CHECK_INT(c.interval_ms, 1000);
    CHECK_INT(c.frame_size, DEVCFG_FRAME_VGA);
}

static void test_full_update(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"interval_ms\":500,\"jpeg_quality\":20,"
                                  "\"frame_size\":\"SVGA\",\"volume\":10}")));
    CHECK_INT(c.interval_ms, 500);
    CHECK_INT(c.jpeg_quality, 20);
    CHECK_INT(c.frame_size, DEVCFG_FRAME_SVGA);
    CHECK_INT(c.volume, 10);
    CHECK(c.streaming);
}

static void test_bounds_accepted(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"interval_ms\":100,\"jpeg_quality\":0,\"volume\":0}")));
    CHECK(devcfg_apply_json(&c, J("{\"interval_ms\":3600000,\"jpeg_quality\":63,\"volume\":100}")));
    CHECK_INT(c.interval_ms, 3600000);
    CHECK_INT(c.jpeg_quality, 63);
    CHECK_INT(c.volume, 100);
}

static void test_unknown_fields_ignored(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"volume\":70,\"color\":\"red\",\"streaming\":false}")));
    CHECK_INT(c.volume, 70);
    CHECK(c.streaming); /* streaming is changed only by start/stop */
}

static void test_invalid_rejects_whole_update(void)
{
    static const char *const BAD[] = {
        "{\"volume\":20,\"interval_ms\":50}",
        "{\"volume\":101}",
        "{\"volume\":-1}",
        "{\"volume\":1.5}",
        "{\"volume\":\"loud\"}",
        "{\"volume\":true}",
        "{\"jpeg_quality\":64}",
        "{\"interval_ms\":3600001}",
        "{\"frame_size\":\"vga\"}",
        "{\"frame_size\":3}",
        "{",
        "[1]",
        "0",
        "",
    };
    for (size_t i = 0; i < sizeof BAD / sizeof BAD[0]; i++) {
        devcfg_t c, before;
        devcfg_defaults(&c);
        before = c;
        if (devcfg_apply_json(&c, BAD[i], strlen(BAD[i]))) {
            printf("accepted bad config: %s\n", BAD[i]);
            CHECK(0);
        }
        CHECK(devcfg_equal(&c, &before));
    }
}

static void test_respects_length(void)
{
    /* Not NUL-terminated; trailing bytes are not part of the payload. */
    const char buf[] = {'{', '"', 'v', 'o', 'l', 'u', 'm', 'e', '"', ':', '5', '}', 'x', 'x'};
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, buf, 12));
    CHECK_INT(c.volume, 5);
}

static void test_equal(void)
{
    devcfg_t a, b;
    devcfg_defaults(&a);
    devcfg_defaults(&b);
    CHECK(devcfg_equal(&a, &b));
    CHECK(devcfg_apply_json(&b, J("{\"volume\":80}")));
    CHECK(devcfg_equal(&a, &b)); /* same value re-applied */
    b.streaming = false;
    CHECK(!devcfg_equal(&a, &b));
}

static void test_frame_names(void)
{
    for (int f = 0; f < DEVCFG_FRAME_COUNT; f++) {
        devcfg_frame_t back;
        CHECK(devcfg_frame_from_name(devcfg_frame_name((devcfg_frame_t)f), &back));
        CHECK_INT(back, f);
    }
    CHECK_STR(devcfg_frame_name(DEVCFG_FRAME_HD), "HD");
    CHECK(devcfg_frame_name(DEVCFG_FRAME_COUNT) == NULL);
    devcfg_frame_t out;
    CHECK(!devcfg_frame_from_name("4K", &out));
}

void test_devcfg(void)
{
    test_defaults();
    test_partial_update_keeps_other_fields();
    test_full_update();
    test_bounds_accepted();
    test_unknown_fields_ignored();
    test_invalid_rejects_whole_update();
    test_respects_length();
    test_equal();
    test_frame_names();
}
```

Modify `firmware/test/host/test_main.c` — add `void test_devcfg(void);` to the declarations and `test_devcfg();` after `test_proto();`.

- [ ] **Step 2: Run to verify it fails**

Run: `sh firmware/test/host/run.sh`
Expected: compile error `core/devcfg.h: No such file or directory`.

- [ ] **Step 3: Implement**

`firmware/components/core/include/core/devcfg.h`:
```c
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    DEVCFG_FRAME_QVGA,
    DEVCFG_FRAME_VGA,
    DEVCFG_FRAME_SVGA,
    DEVCFG_FRAME_XGA,
    DEVCFG_FRAME_HD,
    DEVCFG_FRAME_SXGA,
    DEVCFG_FRAME_UXGA,
    DEVCFG_FRAME_COUNT,
} devcfg_frame_t;

/* Runtime config. Persisted in NVS; updated by {id}/config and start/stop. */
typedef struct {
    uint32_t interval_ms;     /* 100..3600000 */
    uint8_t jpeg_quality;     /* 0..63, lower = better */
    devcfg_frame_t frame_size;
    uint8_t volume;           /* 0..100 */
    bool streaming;
} devcfg_t;

void devcfg_defaults(devcfg_t *c);

/* Apply a {id}/config JSON object. Missing fields keep their value, unknown
 * fields are ignored. If any known field is invalid, or the JSON is not an
 * object, nothing changes and false is returned. `json` need not be
 * NUL-terminated. */
bool devcfg_apply_json(devcfg_t *c, const char *json, size_t len);

bool devcfg_equal(const devcfg_t *a, const devcfg_t *b);

const char *devcfg_frame_name(devcfg_frame_t f);
bool devcfg_frame_from_name(const char *name, devcfg_frame_t *out);
```

`firmware/components/core/devcfg.c`:
```c
#include "core/devcfg.h"

#include <string.h>

#include "cJSON.h"

static const char *const FRAME_NAMES[DEVCFG_FRAME_COUNT] = {
    "QVGA", "VGA", "SVGA", "XGA", "HD", "SXGA", "UXGA",
};

void devcfg_defaults(devcfg_t *c)
{
    c->interval_ms = 1000;
    c->jpeg_quality = 12;
    c->frame_size = DEVCFG_FRAME_VGA;
    c->volume = 80;
    c->streaming = true;
}

bool devcfg_equal(const devcfg_t *a, const devcfg_t *b)
{
    return a->interval_ms == b->interval_ms && a->jpeg_quality == b->jpeg_quality &&
           a->frame_size == b->frame_size && a->volume == b->volume &&
           a->streaming == b->streaming;
}

const char *devcfg_frame_name(devcfg_frame_t f)
{
    return (unsigned)f < DEVCFG_FRAME_COUNT ? FRAME_NAMES[f] : NULL;
}

bool devcfg_frame_from_name(const char *name, devcfg_frame_t *out)
{
    for (int i = 0; i < DEVCFG_FRAME_COUNT; i++) {
        if (strcmp(name, FRAME_NAMES[i]) == 0) {
            *out = (devcfg_frame_t)i;
            return true;
        }
    }
    return false;
}

/* Reads an optional integer field. Returns false only if present and invalid. */
static bool read_int(const cJSON *root, const char *key, long lo, long hi, bool *present, long *out)
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
    if (v < (double)lo || v > (double)hi || v != (double)(long)v) {
        return false;
    }
    *out = (long)v;
    return true;
}

bool devcfg_apply_json(devcfg_t *c, const char *json, size_t len)
{
    cJSON *root = cJSON_ParseWithLength(json, len);
    if (!cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return false;
    }

    devcfg_t next = *c;
    bool ok = true;
    bool present;
    long v = 0;

    ok = ok && read_int(root, "interval_ms", 100, 3600000, &present, &v);
    if (ok && present) {
        next.interval_ms = (uint32_t)v;
    }
    ok = ok && read_int(root, "jpeg_quality", 0, 63, &present, &v);
    if (ok && present) {
        next.jpeg_quality = (uint8_t)v;
    }
    ok = ok && read_int(root, "volume", 0, 100, &present, &v);
    if (ok && present) {
        next.volume = (uint8_t)v;
    }
    const cJSON *fs = cJSON_GetObjectItemCaseSensitive(root, "frame_size");
    if (ok && fs != NULL) {
        ok = cJSON_IsString(fs) && devcfg_frame_from_name(fs->valuestring, &next.frame_size);
    }

    cJSON_Delete(root);
    if (ok) {
        *c = next;
    }
    return ok;
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `sh firmware/test/host/run.sh`
Expected: `0 failures`. Then `CC=/c/msys64/mingw64/bin/gcc.exe sh firmware/test/host/run.sh` → `0 failures`.

- [ ] **Step 5: Commit**

```bash
git add firmware/components/core firmware/test/host
git commit -m "feat(firmware): add runtime config parsing"
```

---

### Task 4: Messages and PCM scaling

**Files:**
- Create: `firmware/components/core/include/core/msg.h`, `firmware/components/core/msg.c`, `firmware/components/core/include/core/pcm.h`
- Create: `firmware/test/host/test_msg.c`, `firmware/test/host/test_pcm.c`
- Modify: `firmware/test/host/test_main.c`

**Interfaces:**
- Consumes: cJSON.
- Produces:
  - `typedef enum { MSG_CMD_NONE, MSG_CMD_START, MSG_CMD_STOP, MSG_CMD_REBOOT, MSG_CMD_STATUS } msg_cmd_t;`
  - `msg_cmd_t msg_parse_cmd(const char *json, size_t len);`
  - `int msg_parse_alert_repeat(const char *json, size_t len);` → 1..10
  - `typedef struct { int rssi; int battery_mv; uint32_t uptime_s; bool streaming; const char *fw; } msg_status_t;`
  - `int msg_format_status(char *buf, size_t len, const msg_status_t *s);` → length, or -1 if it does not fit
  - `static inline uint8_t pcm_scale(uint8_t sample, uint8_t volume);` (in `pcm.h`)

- [ ] **Step 1: Write the failing tests**

`firmware/test/host/test_msg.c`:
```c
#include "core/msg.h"
#include "minitest.h"

#define J(s) s, sizeof(s) - 1

static void test_cmd(void)
{
    CHECK_INT(msg_parse_cmd(J("{\"action\":\"start\"}")), MSG_CMD_START);
    CHECK_INT(msg_parse_cmd(J("{\"action\":\"stop\"}")), MSG_CMD_STOP);
    CHECK_INT(msg_parse_cmd(J("{\"action\":\"reboot\"}")), MSG_CMD_REBOOT);
    CHECK_INT(msg_parse_cmd(J("{\"action\":\"status\"}")), MSG_CMD_STATUS);
    CHECK_INT(msg_parse_cmd(J("{\"action\":\"explode\"}")), MSG_CMD_NONE);
    CHECK_INT(msg_parse_cmd(J("{\"action\":1}")), MSG_CMD_NONE);
    CHECK_INT(msg_parse_cmd(J("{}")), MSG_CMD_NONE);
    CHECK_INT(msg_parse_cmd(J("{")), MSG_CMD_NONE);
    CHECK_INT(msg_parse_cmd(J("")), MSG_CMD_NONE);
    const char raw[] = "{\"action\":\"stop\"}JUNK";
    CHECK_INT(msg_parse_cmd(raw, 17), MSG_CMD_STOP);
}

static void test_alert_repeat(void)
{
    CHECK_INT(msg_parse_alert_repeat(J("{\"clip\":\"alert\",\"repeat\":3}")), 3);
    CHECK_INT(msg_parse_alert_repeat(J("{\"clip\":\"alert\",\"repeat\":10}")), 10);
    CHECK_INT(msg_parse_alert_repeat(J("{\"clip\":\"alert\"}")), 1);
    CHECK_INT(msg_parse_alert_repeat(J("{\"repeat\":0}")), 1);
    CHECK_INT(msg_parse_alert_repeat(J("{\"repeat\":11}")), 1);
    CHECK_INT(msg_parse_alert_repeat(J("{\"repeat\":2.5}")), 1);
    CHECK_INT(msg_parse_alert_repeat(J("garbage")), 1);
    CHECK_INT(msg_parse_alert_repeat(J("")), 1);
}

static void test_status(void)
{
    msg_status_t s = {.rssi = -71, .battery_mv = 0, .uptime_s = 3600, .streaming = true, .fw = "0.1.0"};
    char buf[128];
    int n = msg_format_status(buf, sizeof buf, &s);
    CHECK_STR(buf, "{\"rssi\":-71,\"battery_mv\":0,\"uptime_s\":3600,\"streaming\":true,\"fw\":\"0.1.0\"}");
    CHECK_INT(n, (long long)strlen(buf));

    s.streaming = false;
    msg_format_status(buf, sizeof buf, &s);
    CHECK(strstr(buf, "\"streaming\":false") != NULL);

    char small[16];
    CHECK_INT(msg_format_status(small, sizeof small, &s), -1);
}

void test_msg(void)
{
    test_cmd();
    test_alert_repeat();
    test_status();
}
```

`firmware/test/host/test_pcm.c`:
```c
#include "core/pcm.h"
#include "minitest.h"

void test_pcm(void)
{
    CHECK_INT(pcm_scale(255, 100), 255);
    CHECK_INT(pcm_scale(0, 100), 0);
    CHECK_INT(pcm_scale(128, 100), 128);
    CHECK_INT(pcm_scale(255, 0), 128);
    CHECK_INT(pcm_scale(0, 0), 128);
    CHECK_INT(pcm_scale(255, 50), 191);
    CHECK_INT(pcm_scale(0, 50), 64);
    CHECK_INT(pcm_scale(0, 200), 0); /* volume above 100 is clamped */
}
```

Modify `firmware/test/host/test_main.c` — add `void test_msg(void);` and `void test_pcm(void);` to the declarations and call `test_msg();` and `test_pcm();` after `test_devcfg();`.

- [ ] **Step 2: Run to verify it fails**

Run: `sh firmware/test/host/run.sh`
Expected: compile error `core/msg.h: No such file or directory`.

- [ ] **Step 3: Implement**

`firmware/components/core/include/core/msg.h`:
```c
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    MSG_CMD_NONE,
    MSG_CMD_START,
    MSG_CMD_STOP,
    MSG_CMD_REBOOT,
    MSG_CMD_STATUS,
} msg_cmd_t;

/* Parse {id}/cmd payload {"action":"..."}. MSG_CMD_NONE if invalid. */
msg_cmd_t msg_parse_cmd(const char *json, size_t len);

/* Parse {id}/alert payload; returns repeat 1..10 (1 if missing or invalid). */
int msg_parse_alert_repeat(const char *json, size_t len);

typedef struct {
    int rssi;
    int battery_mv;
    uint32_t uptime_s;
    bool streaming;
    const char *fw;   /* must not contain quotes or backslashes */
} msg_status_t;

/* Format {id}/status JSON. Returns its length, or -1 if it does not fit. */
int msg_format_status(char *buf, size_t len, const msg_status_t *s);
```

`firmware/components/core/msg.c`:
```c
#include "core/msg.h"

#include <stdio.h>
#include <string.h>

#include "cJSON.h"

msg_cmd_t msg_parse_cmd(const char *json, size_t len)
{
    static const struct {
        const char *name;
        msg_cmd_t cmd;
    } ACTIONS[] = {
        {"start", MSG_CMD_START},
        {"stop", MSG_CMD_STOP},
        {"reboot", MSG_CMD_REBOOT},
        {"status", MSG_CMD_STATUS},
    };
    msg_cmd_t result = MSG_CMD_NONE;
    cJSON *root = cJSON_ParseWithLength(json, len);
    const cJSON *action = cJSON_GetObjectItemCaseSensitive(root, "action");
    if (cJSON_IsString(action)) {
        for (size_t i = 0; i < sizeof ACTIONS / sizeof ACTIONS[0]; i++) {
            if (strcmp(action->valuestring, ACTIONS[i].name) == 0) {
                result = ACTIONS[i].cmd;
            }
        }
    }
    cJSON_Delete(root);
    return result;
}

int msg_parse_alert_repeat(const char *json, size_t len)
{
    int repeat = 1;
    cJSON *root = cJSON_ParseWithLength(json, len);
    const cJSON *r = cJSON_GetObjectItemCaseSensitive(root, "repeat");
    if (cJSON_IsNumber(r)) {
        double v = r->valuedouble;
        if (v >= 1 && v <= 10 && v == (double)(int)v) {
            repeat = (int)v;
        }
    }
    cJSON_Delete(root);
    return repeat;
}

int msg_format_status(char *buf, size_t len, const msg_status_t *s)
{
    int n = snprintf(buf, len,
                     "{\"rssi\":%d,\"battery_mv\":%d,\"uptime_s\":%lu,\"streaming\":%s,\"fw\":\"%s\"}",
                     s->rssi, s->battery_mv, (unsigned long)s->uptime_s,
                     s->streaming ? "true" : "false", s->fw);
    return (n > 0 && (size_t)n < len) ? n : -1;
}
```

`firmware/components/core/include/core/pcm.h`:
```c
#pragma once
#include <stdint.h>

/* Scale an 8-bit unsigned sample (silence = 128) by volume 0..100. */
static inline uint8_t pcm_scale(uint8_t sample, uint8_t volume)
{
    if (volume > 100) {
        volume = 100;
    }
    int centered = (int)sample - 128;
    return (uint8_t)(128 + centered * (int)volume / 100);
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `sh firmware/test/host/run.sh`
Expected: `0 failures`. Then `CC=/c/msys64/mingw64/bin/gcc.exe sh firmware/test/host/run.sh` → `0 failures`.

- [ ] **Step 5: Commit**

```bash
git add firmware/components/core firmware/test/host
git commit -m "feat(firmware): add message parsing, status format, PCM scaling"
```

---

### Task 5: Alert clip tool and asset

**Files:**
- Create: `firmware/tools/wav2raw.py`, `firmware/tools/test_wav2raw.py`
- Create: `firmware/main/assets/alert.raw` (generated)

**Interfaces:**
- Consumes: nothing.
- Produces: `wav2raw.py` with `RATE = 16000`, `to_u8(samples: list[float]) -> bytes`, `read_wav(path) -> list[float]` (mono, resampled to 16 kHz), `demo(seconds: float = 1.2) -> list[float]`, CLI `python wav2raw.py IN.wav OUT.raw` and `python wav2raw.py --demo OUT.raw`.

- [ ] **Step 1: Write the failing test**

`firmware/tools/test_wav2raw.py`:
```python
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import wav2raw  # noqa: E402


def test_to_u8_maps_range():
    assert wav2raw.to_u8([0.0, 1.0, -1.0, 2.0, -2.0]) == bytes([128, 255, 1, 255, 1])


def _write_wav(path, rate, channels, frames):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<" + "h" * channels, *f) for f in frames))


def test_read_wav_mixes_to_mono_and_resamples(tmp_path):
    path = tmp_path / "in.wav"
    # 8 kHz stereo, 100 frames: left full positive, right silent -> mono 0.5
    _write_wav(path, 8000, 2, [(32767, 0)] * 100)
    samples = wav2raw.read_wav(path)
    assert len(samples) == 200
    assert all(abs(s - 0.5) < 0.01 for s in samples)


def test_demo_length_and_range():
    samples = wav2raw.demo(1.2)
    assert len(samples) == int(1.2 * wav2raw.RATE)
    assert max(samples) <= 1.0 and min(samples) >= -1.0
    assert max(samples) > 0.5


def test_cli_demo_writes_raw(tmp_path):
    out = tmp_path / "alert.raw"
    wav2raw.main(["--demo", str(out)])
    assert out.stat().st_size == int(1.2 * wav2raw.RATE)
```

- [ ] **Step 2: Run to verify it fails**

Run: `server/.venv/Scripts/python -m pytest firmware/tools/test_wav2raw.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'wav2raw'`.

- [ ] **Step 3: Implement `firmware/tools/wav2raw.py`**

```python
"""Convert a WAV file to the firmware's alert clip: 8-bit unsigned mono PCM at 16 kHz.

    python tools/wav2raw.py input.wav main/assets/alert.raw
    python tools/wav2raw.py --demo main/assets/alert.raw     # synthesize a two-tone chime

Keep clips short: 16 KB per second of audio, embedded in the firmware image.
"""

import argparse
import math
import struct
import wave
from pathlib import Path

RATE = 16000


def to_u8(samples: list[float]) -> bytes:
    """Map floats in [-1, 1] to unsigned bytes with silence at 128 (clipped)."""
    out = bytearray()
    for s in samples:
        s = max(-1.0, min(1.0, s))
        out.append(128 + round(s * 127))
    return bytes(out)


def read_wav(path) -> list[float]:
    with wave.open(str(path), "rb") as w:
        channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    if width == 1:
        values = [(b - 128) / 128 for b in raw]
    elif width == 2:
        values = [v / 32768 for v in struct.unpack("<" + "h" * (len(raw) // 2), raw)]
    else:
        raise SystemExit(f"unsupported sample width {width * 8} bits; use 8 or 16-bit WAV")
    mono = [sum(values[i:i + channels]) / channels for i in range(0, len(values), channels)]
    if rate == RATE or not mono:
        return mono
    n_out = int(len(mono) * RATE / rate)
    out = []
    for i in range(n_out):
        t = i * rate / RATE
        j = int(t)
        frac = t - j
        a = mono[j]
        b = mono[j + 1] if j + 1 < len(mono) else a
        out.append(a + (b - a) * frac)
    return out


def demo(seconds: float = 1.2) -> list[float]:
    """Alternating 880/660 Hz tones, 150 ms each, with 5 ms fades to avoid clicks."""
    n = int(seconds * RATE)
    seg = int(0.15 * RATE)
    fade = int(0.005 * RATE)
    out = []
    for i in range(n):
        freq = 880 if (i // seg) % 2 == 0 else 660
        k = i % seg
        env = min(1.0, k / fade, (seg - k) / fade)
        out.append(0.9 * env * math.sin(2 * math.pi * freq * i / RATE))
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="synthesize a chime instead of reading a WAV")
    ap.add_argument("paths", nargs="+", metavar="PATH", help="[input.wav] output.raw")
    args = ap.parse_args(argv)
    if args.demo:
        if len(args.paths) != 1:
            ap.error("--demo takes only the output path")
        samples, out = demo(), Path(args.paths[0])
    else:
        if len(args.paths) != 2:
            ap.error("expected input.wav output.raw")
        samples, out = read_wav(args.paths[0]), Path(args.paths[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(to_u8(samples))
    print(f"wrote {out} ({len(samples)} samples, {len(samples) / RATE:.2f} s)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify it passes**

Run: `server/.venv/Scripts/python -m pytest firmware/tools/test_wav2raw.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Generate the asset**

Run: `server/.venv/Scripts/python firmware/tools/wav2raw.py --demo firmware/main/assets/alert.raw`
Expected: `wrote firmware/main/assets/alert.raw (19200 samples, 1.20 s)`

- [ ] **Step 6: Commit**

```bash
git add firmware/tools firmware/main/assets/alert.raw
git commit -m "feat(firmware): add wav2raw tool and demo alert clip"
```

---

### Task 6: ESP-IDF project skeleton and board

**Files:**
- Create: `firmware/CMakeLists.txt`, `firmware/partitions.csv`, `firmware/sdkconfig.defaults`
- Create: `firmware/components/core/CMakeLists.txt`
- Create: `firmware/main/Kconfig.projbuild`, `firmware/main/idf_component.yml`, `firmware/main/board.h`, `firmware/main/boards/freenove_s3cam.h`

**Interfaces:**
- Consumes: `components/core` sources (Tasks 1–4).
- Produces: Kconfig symbols `CONFIG_BOARD_FREENOVE_S3CAM`, `CONFIG_NET_BACKEND_WIFI`, `CONFIG_WIFI_SSID`, `CONFIG_WIFI_PASSWORD`, `CONFIG_MQTT_URI`, `CONFIG_MQTT_USERNAME`, `CONFIG_MQTT_PASSWORD`, `CONFIG_FW_VERSION`; board macros `BOARD_NAME`, `BOARD_CAM_PIN_*`, `BOARD_AUDIO_GPIO`, and `static inline int board_battery_mv(void)`.

Verification for Tasks 6–10 happens with `idf.py build` on the ESP-IDF machine (Task 10 checklist). On this PC, each task ends with a review against the Global Constraints and a commit.

- [ ] **Step 1: Project files**

`firmware/CMakeLists.txt`:
```cmake
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(pedestrian_edge)
```

`firmware/partitions.csv`:
```csv
# Name,   Type, SubType, Offset,  Size
nvs,      data, nvs,     0x9000,  0x6000
phy_init, data, phy,     0xf000,  0x1000
factory,  app,  factory, 0x10000, 0x400000
```

`firmware/sdkconfig.defaults`:
```
CONFIG_IDF_TARGET="esp32s3"

# Freenove ESP32-S3-WROOM CAM: N8R8 (8 MB flash, 8 MB octal PSRAM).
# For an N16R8 module, use CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y instead.
CONFIG_ESPTOOLPY_FLASHSIZE_8MB=y
CONFIG_PARTITION_TABLE_CUSTOM=y
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"

CONFIG_SPIRAM=y
CONFIG_SPIRAM_MODE_OCT=y
CONFIG_SPIRAM_SPEED_80M=y
CONFIG_SPIRAM_USE_MALLOC=y

CONFIG_MBEDTLS_CERTIFICATE_BUNDLE=y
CONFIG_MBEDTLS_CERTIFICATE_BUNDLE_DEFAULT_FULL=y
CONFIG_MQTT_TRANSPORT_WEBSOCKET=y
CONFIG_MQTT_TRANSPORT_WEBSOCKET_SECURE=y

CONFIG_ESP_TASK_WDT_EN=y
CONFIG_ESP_TASK_WDT_TIMEOUT_S=30
CONFIG_ESP_MAIN_TASK_STACK_SIZE=8192
CONFIG_FREERTOS_HZ=1000
```

`firmware/components/core/CMakeLists.txt`:
```cmake
# Pure C, no ESP-IDF headers. Also compiled on the host by test/host/run.sh.
# cJSON comes from the IDF "json" component (ESP-IDF 5.x). On ESP-IDF 6+,
# replace "json" with the managed component espressif/cjson.
idf_component_register(SRCS "backoff.c" "proto.c" "devcfg.c" "msg.c"
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES json)
```

`firmware/main/idf_component.yml`:
```yaml
dependencies:
  idf: ">=5.1"
  espressif/esp32-camera: "^2.0.0"
```

- [ ] **Step 2: Kconfig**

`firmware/main/Kconfig.projbuild`:
```
menu "Pedestrian Edge"

    choice BOARD
        prompt "Board"
        default BOARD_FREENOVE_S3CAM

        config BOARD_FREENOVE_S3CAM
            bool "Freenove ESP32-S3-WROOM CAM"
    endchoice

    choice NET_BACKEND
        prompt "Network backend"
        default NET_BACKEND_WIFI

        config NET_BACKEND_WIFI
            bool "Wi-Fi"
    endchoice

    config WIFI_SSID
        string "Wi-Fi SSID"
        default ""
        depends on NET_BACKEND_WIFI

    config WIFI_PASSWORD
        string "Wi-Fi password (empty = open network)"
        default ""
        depends on NET_BACKEND_WIFI

    config MQTT_URI
        string "MQTT broker URI"
        default "wss://mqtt.example.com:443/mqtt"
        help
            wss://host:443/mqtt through Cloudflare Tunnel, or for bench tests
            directly to the PC: ws://<pc-ip>:9001/mqtt or mqtt://<pc-ip>:1883
            (the PC's Mosquitto must listen on the LAN for those).

    config MQTT_USERNAME
        string "MQTT username (empty = none)"
        default ""

    config MQTT_PASSWORD
        string "MQTT password (empty = none)"
        default ""

    config FW_VERSION
        string "Firmware version reported in status"
        default "0.1.0"

endmenu
```

- [ ] **Step 3: Board headers**

`firmware/main/board.h`:
```c
#pragma once
#include "sdkconfig.h"

/* The only place that knows which board is in use. Pins live in boards/*.h. */
#if CONFIG_BOARD_FREENOVE_S3CAM
#include "boards/freenove_s3cam.h"
#else
#error "No board selected: menuconfig > Pedestrian Edge > Board"
#endif
```

`firmware/main/boards/freenove_s3cam.h`:
```c
#pragma once

#define BOARD_NAME "freenove-s3cam"

/* OV2640 on the 24-pin FPC (same pinout as ESP32-S3-EYE). */
#define BOARD_CAM_PIN_PWDN -1
#define BOARD_CAM_PIN_RESET -1
#define BOARD_CAM_PIN_XCLK 15
#define BOARD_CAM_PIN_SIOD 4
#define BOARD_CAM_PIN_SIOC 5
#define BOARD_CAM_PIN_D0 11
#define BOARD_CAM_PIN_D1 9
#define BOARD_CAM_PIN_D2 8
#define BOARD_CAM_PIN_D3 10
#define BOARD_CAM_PIN_D4 12
#define BOARD_CAM_PIN_D5 18
#define BOARD_CAM_PIN_D6 17
#define BOARD_CAM_PIN_D7 16
#define BOARD_CAM_PIN_VSYNC 6
#define BOARD_CAM_PIN_HREF 7
#define BOARD_CAM_PIN_PCLK 13

/* PWM into the RC filter and PAM8403. Free of camera, SD (38-40), RGB LED (48), USB (19/20). */
#define BOARD_AUDIO_GPIO 14

/* No battery sense on this board. */
static inline int board_battery_mv(void)
{
    return 0;
}
```

- [ ] **Step 4: Review and commit**

Check: no pin number outside `boards/`; Kconfig defaults match Global Constraints.
```bash
git add firmware/CMakeLists.txt firmware/partitions.csv firmware/sdkconfig.defaults firmware/components/core/CMakeLists.txt firmware/main/Kconfig.projbuild firmware/main/idf_component.yml firmware/main/board.h firmware/main/boards
git commit -m "feat(firmware): add ESP-IDF project skeleton and Freenove board"
```

---

### Task 7: Platform modules — config store, network, time sync

**Files:**
- Create: `firmware/main/config_store.h`, `firmware/main/config_store.c`
- Create: `firmware/main/net.h`, `firmware/main/net_wifi.c`
- Create: `firmware/main/timesync.h`, `firmware/main/timesync.c`

**Interfaces:**
- Consumes: `devcfg_t`, `devcfg_defaults` (Task 3); `backoff_t`, `backoff_reset`, `backoff_next_ms` (Task 1); `proto_capture_ms` (Task 2).
- Produces:
  - `esp_err_t config_store_init(void);` `void config_store_get(devcfg_t *out);` `esp_err_t config_store_set(const devcfg_t *c);`
  - `esp_err_t net_start(void);` `bool net_wait_connected(TickType_t timeout);` `int net_rssi(void);`
  - `void timesync_start(void);` `uint64_t timesync_capture_ms(void);`

- [ ] **Step 1: Config store**

`firmware/main/config_store.h`:
```c
#pragma once
#include "core/devcfg.h"
#include "esp_err.h"

/* Runtime config kept in RAM and NVS. Thread-safe. */
esp_err_t config_store_init(void);
void config_store_get(devcfg_t *out);
esp_err_t config_store_set(const devcfg_t *c);
```

`firmware/main/config_store.c`:
```c
#include "config_store.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "config_store";
static const char *NS = "edge";
static const char *KEY = "devcfg";

static devcfg_t s_cfg;
static SemaphoreHandle_t s_lock;

esp_err_t config_store_init(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    if (err != ESP_OK) {
        return err;
    }
    s_lock = xSemaphoreCreateMutex();
    devcfg_defaults(&s_cfg);

    nvs_handle_t h;
    if (nvs_open(NS, NVS_READONLY, &h) == ESP_OK) {
        devcfg_t stored;
        size_t size = sizeof stored;
        if (nvs_get_blob(h, KEY, &stored, &size) == ESP_OK && size == sizeof stored) {
            s_cfg = stored;
            ESP_LOGI(TAG, "loaded config from NVS");
        }
        nvs_close(h);
    }
    return ESP_OK;
}

void config_store_get(devcfg_t *out)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *out = s_cfg;
    xSemaphoreGive(s_lock);
}

esp_err_t config_store_set(const devcfg_t *c)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    bool changed = !devcfg_equal(&s_cfg, c);
    s_cfg = *c;
    xSemaphoreGive(s_lock);
    if (!changed) {
        return ESP_OK; /* avoid flash wear on redelivered retained config */
    }

    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &h);
    if (err == ESP_OK) {
        err = nvs_set_blob(h, KEY, c, sizeof *c);
        if (err == ESP_OK) {
            err = nvs_commit(h);
        }
        nvs_close(h);
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "saving config failed: %s", esp_err_to_name(err));
    }
    return err;
}
```

- [ ] **Step 2: Network interface and Wi-Fi backend**

`firmware/main/net.h`:
```c
#pragma once
#include <stdbool.h>

#include "esp_err.h"
#include "freertos/FreeRTOS.h"

/* Network link, independent of the backend (Wi-Fi now, LTE later).
 * The backend reconnects on its own with core/backoff.h delays. */
esp_err_t net_start(void);                   /* start the link; returns at once */
bool net_wait_connected(TickType_t timeout); /* true once an IP address is held */
int net_rssi(void);                          /* dBm; 0 if unknown */
```

`firmware/main/net_wifi.c`:
```c
#include <string.h>

#include "core/backoff.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/event_groups.h"
#include "net.h"
#include "sdkconfig.h"

static const char *TAG = "net_wifi";
#define BIT_UP BIT0

static EventGroupHandle_t s_events;
static esp_timer_handle_t s_retry_timer;
static backoff_t s_backoff;

static void retry_cb(void *arg)
{
    esp_wifi_connect();
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_events, BIT_UP);
        uint32_t ms = backoff_next_ms(&s_backoff);
        ESP_LOGW(TAG, "disconnected, retry in %lu ms", (unsigned long)ms);
        esp_timer_start_once(s_retry_timer, (uint64_t)ms * 1000);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = data;
        ESP_LOGI(TAG, "got ip " IPSTR, IP2STR(&e->ip_info.ip));
        backoff_reset(&s_backoff);
        xEventGroupSetBits(s_events, BIT_UP);
    }
}

esp_err_t net_start(void)
{
    s_events = xEventGroupCreate();
    backoff_reset(&s_backoff);
    const esp_timer_create_args_t targs = {.callback = retry_cb, .name = "wifi_retry"};
    ESP_ERROR_CHECK(esp_timer_create(&targs, &s_retry_timer));

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL));

    wifi_config_t wc = {0};
    strlcpy((char *)wc.sta.ssid, CONFIG_WIFI_SSID, sizeof wc.sta.ssid);
    strlcpy((char *)wc.sta.password, CONFIG_WIFI_PASSWORD, sizeof wc.sta.password);
    wc.sta.threshold.authmode = strlen(CONFIG_WIFI_PASSWORD) ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE)); /* lower latency for frame uploads */
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "connecting to \"%s\"", CONFIG_WIFI_SSID);
    return ESP_OK;
}

bool net_wait_connected(TickType_t timeout)
{
    return xEventGroupWaitBits(s_events, BIT_UP, pdFALSE, pdTRUE, timeout) & BIT_UP;
}

int net_rssi(void)
{
    wifi_ap_record_t ap;
    return esp_wifi_sta_get_ap_info(&ap) == ESP_OK ? ap.rssi : 0;
}
```

- [ ] **Step 3: Time sync**

`firmware/main/timesync.h`:
```c
#pragma once
#include <stdint.h>

void timesync_start(void);         /* start SNTP; call after the network is up */
uint64_t timesync_capture_ms(void); /* epoch ms, or 0 while the clock is not synced */
```

`firmware/main/timesync.c`:
```c
#include "timesync.h"

#include <sys/time.h>

#include "core/proto.h"
#include "esp_netif_sntp.h"

void timesync_start(void)
{
    esp_sntp_config_t cfg = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    esp_netif_sntp_init(&cfg);
}

uint64_t timesync_capture_ms(void)
{
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return proto_capture_ms((int64_t)tv.tv_sec * 1000 + tv.tv_usec / 1000);
}
```

- [ ] **Step 4: Review and commit**

Check: `net.h` exposes no Wi-Fi type; `config_store_set` skips NVS write when unchanged; all `ESP_ERROR_CHECK` uses are on init-time calls only.
```bash
git add firmware/main/config_store.h firmware/main/config_store.c firmware/main/net.h firmware/main/net_wifi.c firmware/main/timesync.h firmware/main/timesync.c
git commit -m "feat(firmware): add config store, Wi-Fi network backend, time sync"
```

---

### Task 8: MQTT link and command handling

**Files:**
- Create: `firmware/main/mqtt_link.h`, `firmware/main/mqtt_link.c`
- Create: `firmware/main/cmd.h`, `firmware/main/cmd.c`

**Interfaces:**
- Consumes: `proto_topic`, `proto_kind_of`, `proto_kind_t`, `PROTO_ID_SIZE` (Task 2); `devcfg_apply_json`, `devcfg_t` (Task 3); `msg_parse_cmd`, `msg_parse_alert_repeat` (Task 4); `config_store_get/set` (Task 7). Forward-declared from Task 9: `camera_apply(const devcfg_t *)`, `audio_play(int repeat)`, `audio_set_volume(uint8_t)`, `status_request(void)`.
- Produces:
  - `typedef struct { void (*on_message)(proto_kind_t kind, const char *data, size_t len); void (*on_connected)(void); } mqtt_link_handlers_t;`
  - `esp_err_t mqtt_link_start(const char *device_id, const mqtt_link_handlers_t *handlers);`
  - `bool mqtt_link_connected(void);`
  - `int mqtt_link_publish(const char *kind, const void *data, size_t len, int qos, bool retain);` → msg id, or -1
  - `esp_err_t cmd_start(void);` `void cmd_submit(proto_kind_t kind, const char *data, size_t len);`

- [ ] **Step 1: MQTT link**

`firmware/main/mqtt_link.h`:
```c
#pragma once
#include <stdbool.h>
#include <stddef.h>

#include "core/proto.h"
#include "esp_err.h"

typedef struct {
    /* Called on the MQTT task for {id}/alert, {id}/cmd, {id}/config.
     * `data` is not NUL-terminated. Must not block. */
    void (*on_message)(proto_kind_t kind, const char *data, size_t len);
    /* Called on the MQTT task after every (re)connect. Must not block. */
    void (*on_connected)(void);
} mqtt_link_handlers_t;

esp_err_t mqtt_link_start(const char *device_id, const mqtt_link_handlers_t *handlers);
bool mqtt_link_connected(void);
/* Publish to {id}/{kind}. Returns the message id, or -1 if not connected or failed. */
int mqtt_link_publish(const char *kind, const void *data, size_t len, int qos, bool retain);
```

`firmware/main/mqtt_link.c`:
```c
#include "mqtt_link.h"

#include <string.h>

#include "esp_crt_bundle.h"
#include "esp_log.h"
#include "mqtt_client.h"
#include "sdkconfig.h"

static const char *TAG = "mqtt_link";

static esp_mqtt_client_handle_t s_client;
static char s_id[PROTO_ID_SIZE];
static char s_will_topic[32];
static mqtt_link_handlers_t s_handlers;
static volatile bool s_connected;

static void subscribe_all(void)
{
    static const char *const KINDS[] = {"alert", "cmd", "config"};
    char topic[32];
    for (size_t i = 0; i < sizeof KINDS / sizeof KINDS[0]; i++) {
        if (proto_topic(topic, sizeof topic, s_id, KINDS[i])) {
            esp_mqtt_client_subscribe(s_client, topic, 1);
        }
    }
}

static void on_event(void *arg, esp_event_base_t base, int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t e = event_data;
    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "connected");
        s_connected = true;
        esp_mqtt_client_publish(s_client, s_will_topic, "1", 1, 1, 1);
        subscribe_all();
        if (s_handlers.on_connected) {
            s_handlers.on_connected();
        }
        break;
    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "disconnected");
        s_connected = false;
        break;
    case MQTT_EVENT_DATA:
        /* Commands are small; drop anything that arrives in fragments. */
        if (e->current_data_offset != 0 || e->data_len != e->total_data_len) {
            ESP_LOGW(TAG, "dropping fragmented message (%d bytes)", e->total_data_len);
            break;
        }
        proto_kind_t kind = proto_kind_of(e->topic, (size_t)e->topic_len, s_id);
        if (kind != PROTO_KIND_UNKNOWN && s_handlers.on_message) {
            s_handlers.on_message(kind, e->data, (size_t)e->data_len);
        }
        break;
    case MQTT_EVENT_ERROR:
        ESP_LOGW(TAG, "transport error");
        break;
    default:
        break;
    }
}

esp_err_t mqtt_link_start(const char *device_id, const mqtt_link_handlers_t *handlers)
{
    strlcpy(s_id, device_id, sizeof s_id);
    s_handlers = *handlers;
    if (!proto_topic(s_will_topic, sizeof s_will_topic, s_id, "online")) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_mqtt_client_config_t cfg = {
        .broker.address.uri = CONFIG_MQTT_URI,
        .broker.verification.crt_bundle_attach = esp_crt_bundle_attach,
        .credentials.client_id = s_id,
        .credentials.username = CONFIG_MQTT_USERNAME[0] ? CONFIG_MQTT_USERNAME : NULL,
        .credentials.authentication.password = CONFIG_MQTT_PASSWORD[0] ? CONFIG_MQTT_PASSWORD : NULL,
        .session.keepalive = 30,
        .session.last_will = {
            .topic = s_will_topic,
            .msg = "0",
            .msg_len = 1,
            .qos = 1,
            .retain = 1,
        },
        .network.reconnect_timeout_ms = 5000,
        .buffer.size = 4096,
        .buffer.out_size = 160 * 1024, /* whole JPEG frame + header; allocated in PSRAM */
    };
    s_client = esp_mqtt_client_init(&cfg);
    if (s_client == NULL) {
        return ESP_FAIL;
    }
    esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID, on_event, NULL);
    ESP_LOGI(TAG, "device id %s, broker %s", s_id, CONFIG_MQTT_URI);
    return esp_mqtt_client_start(s_client);
}

bool mqtt_link_connected(void)
{
    return s_connected;
}

int mqtt_link_publish(const char *kind, const void *data, size_t len, int qos, bool retain)
{
    char topic[32];
    if (!s_connected || !proto_topic(topic, sizeof topic, s_id, kind)) {
        return -1;
    }
    return esp_mqtt_client_publish(s_client, topic, data, (int)len, qos, retain);
}
```

- [ ] **Step 2: Command handling**

`firmware/main/cmd.h`:
```c
#pragma once
#include <stddef.h>

#include "core/proto.h"
#include "esp_err.h"

esp_err_t cmd_start(void);
/* Queue an incoming message for the command task. Safe to call from the MQTT
 * task; never blocks. Matches mqtt_link_handlers_t.on_message. */
void cmd_submit(proto_kind_t kind, const char *data, size_t len);
```

`firmware/main/cmd.c`:
```c
#include "cmd.h"

#include <string.h>

#include "audio.h"
#include "camera.h"
#include "config_store.h"
#include "core/devcfg.h"
#include "core/msg.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "status.h"

static const char *TAG = "cmd";
#define CMD_MAX_PAYLOAD 256

typedef struct {
    proto_kind_t kind;
    uint16_t len;
    char data[CMD_MAX_PAYLOAD];
} cmd_msg_t;

static QueueHandle_t s_queue;

void cmd_submit(proto_kind_t kind, const char *data, size_t len)
{
    if (len >= CMD_MAX_PAYLOAD) {
        ESP_LOGW(TAG, "dropping %u-byte message (max %d)", (unsigned)len, CMD_MAX_PAYLOAD - 1);
        return;
    }
    cmd_msg_t m = {.kind = kind, .len = (uint16_t)len};
    memcpy(m.data, data, len);
    if (xQueueSend(s_queue, &m, 0) != pdTRUE) {
        ESP_LOGW(TAG, "command queue full, dropping message");
    }
}

static void set_streaming(bool on)
{
    devcfg_t c;
    config_store_get(&c);
    c.streaming = on;
    config_store_set(&c);
    ESP_LOGI(TAG, "streaming %s", on ? "on" : "off");
}

static void handle_config(const char *data, size_t len)
{
    devcfg_t cur, next;
    config_store_get(&cur);
    next = cur;
    if (!devcfg_apply_json(&next, data, len)) {
        ESP_LOGW(TAG, "rejected config: %.*s", (int)len, data);
        return;
    }
    config_store_set(&next);
    if (next.frame_size != cur.frame_size || next.jpeg_quality != cur.jpeg_quality) {
        camera_apply(&next);
    }
    audio_set_volume(next.volume);
    ESP_LOGI(TAG, "config: interval_ms=%lu quality=%u frame=%s volume=%u",
             (unsigned long)next.interval_ms, next.jpeg_quality,
             devcfg_frame_name(next.frame_size), next.volume);
}

static void handle_cmd(const char *data, size_t len)
{
    switch (msg_parse_cmd(data, len)) {
    case MSG_CMD_START:
        set_streaming(true);
        break;
    case MSG_CMD_STOP:
        set_streaming(false);
        break;
    case MSG_CMD_STATUS:
        status_request();
        break;
    case MSG_CMD_REBOOT:
        ESP_LOGW(TAG, "reboot requested");
        vTaskDelay(pdMS_TO_TICKS(200));
        esp_restart();
        break;
    case MSG_CMD_NONE:
        ESP_LOGW(TAG, "unknown cmd: %.*s", (int)len, data);
        break;
    }
}

static void cmd_task(void *arg)
{
    cmd_msg_t m;
    for (;;) {
        if (xQueueReceive(s_queue, &m, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        switch (m.kind) {
        case PROTO_KIND_ALERT:
            audio_play(msg_parse_alert_repeat(m.data, m.len));
            break;
        case PROTO_KIND_CMD:
            handle_cmd(m.data, m.len);
            break;
        case PROTO_KIND_CONFIG:
            handle_config(m.data, m.len);
            break;
        default:
            break;
        }
    }
}

esp_err_t cmd_start(void)
{
    s_queue = xQueueCreate(8, sizeof(cmd_msg_t));
    if (s_queue == NULL) {
        return ESP_ERR_NO_MEM;
    }
    return xTaskCreate(cmd_task, "cmd", 4096, NULL, 5, NULL) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
```

- [ ] **Step 3: Review and commit**

Check: the MQTT event handler only copies into the queue (no NVS, camera, or audio work); retained-config redelivery reconfigures the camera only on change; payload length is respected everywhere (`%.*s`, `devcfg_apply_json(data, len)`).
```bash
git add firmware/main/mqtt_link.h firmware/main/mqtt_link.c firmware/main/cmd.h firmware/main/cmd.c
git commit -m "feat(firmware): add MQTT link and command handling"
```

---

### Task 9: Camera, stream, audio, status

**Files:**
- Create: `firmware/main/camera.h`, `firmware/main/camera.c`
- Create: `firmware/main/stream.h`, `firmware/main/stream.c`
- Create: `firmware/main/audio.h`, `firmware/main/audio.c`
- Create: `firmware/main/status.h`, `firmware/main/status.c`

**Interfaces:**
- Consumes: `board.h` (Task 6); `devcfg_t` (Task 3); `proto_pack_header`, `PROTO_HEADER_SIZE` (Task 2); `pcm_scale`, `msg_format_status`, `msg_status_t` (Task 4); `config_store_get` (Task 7); `net_rssi` (Task 7); `timesync_capture_ms` (Task 7); `mqtt_link_publish`, `mqtt_link_connected` (Task 8).
- Produces:
  - `esp_err_t camera_init(const devcfg_t *c);` `esp_err_t camera_apply(const devcfg_t *c);` `esp_err_t camera_reinit(const devcfg_t *c);` `camera_fb_t *camera_capture(void);` `void camera_return(camera_fb_t *fb);`
  - `esp_err_t stream_start(void);`
  - `esp_err_t audio_init(void);` `void audio_set_volume(uint8_t volume);` `void audio_play(int repeat);`
  - `esp_err_t status_start(void);` `void status_request(void);`

- [ ] **Step 1: Camera**

`firmware/main/camera.h`:
```c
#pragma once
#include "core/devcfg.h"
#include "esp_camera.h"
#include "esp_err.h"

/* Thread-safe wrapper: capture and reconfiguration never overlap. */
esp_err_t camera_init(const devcfg_t *c);
esp_err_t camera_apply(const devcfg_t *c);  /* frame size + JPEG quality */
esp_err_t camera_reinit(const devcfg_t *c); /* deinit + init, after repeated failures */
camera_fb_t *camera_capture(void);          /* NULL on failure; pair with camera_return */
void camera_return(camera_fb_t *fb);
```

`firmware/main/camera.c`:
```c
#include "camera.h"

#include "board.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "camera";
static SemaphoreHandle_t s_lock;

static framesize_t to_framesize(devcfg_frame_t f)
{
    switch (f) {
    case DEVCFG_FRAME_QVGA: return FRAMESIZE_QVGA;
    case DEVCFG_FRAME_SVGA: return FRAMESIZE_SVGA;
    case DEVCFG_FRAME_XGA: return FRAMESIZE_XGA;
    case DEVCFG_FRAME_HD: return FRAMESIZE_HD;
    case DEVCFG_FRAME_SXGA: return FRAMESIZE_SXGA;
    case DEVCFG_FRAME_UXGA: return FRAMESIZE_UXGA;
    case DEVCFG_FRAME_VGA:
    default: return FRAMESIZE_VGA;
    }
}

static esp_err_t init_locked(const devcfg_t *c)
{
    camera_config_t cfg = {
        .pin_pwdn = BOARD_CAM_PIN_PWDN,
        .pin_reset = BOARD_CAM_PIN_RESET,
        .pin_xclk = BOARD_CAM_PIN_XCLK,
        .pin_sccb_sda = BOARD_CAM_PIN_SIOD,
        .pin_sccb_scl = BOARD_CAM_PIN_SIOC,
        .pin_d7 = BOARD_CAM_PIN_D7,
        .pin_d6 = BOARD_CAM_PIN_D6,
        .pin_d5 = BOARD_CAM_PIN_D5,
        .pin_d4 = BOARD_CAM_PIN_D4,
        .pin_d3 = BOARD_CAM_PIN_D3,
        .pin_d2 = BOARD_CAM_PIN_D2,
        .pin_d1 = BOARD_CAM_PIN_D1,
        .pin_d0 = BOARD_CAM_PIN_D0,
        .pin_vsync = BOARD_CAM_PIN_VSYNC,
        .pin_href = BOARD_CAM_PIN_HREF,
        .pin_pclk = BOARD_CAM_PIN_PCLK,
        .xclk_freq_hz = 20000000,
        .ledc_timer = LEDC_TIMER_0,     /* audio uses LEDC_TIMER_1 / LEDC_CHANNEL_1 */
        .ledc_channel = LEDC_CHANNEL_0,
        .pixel_format = PIXFORMAT_JPEG,
        /* Allocate buffers for the largest size so frame_size can grow at runtime. */
        .frame_size = FRAMESIZE_UXGA,
        .jpeg_quality = c->jpeg_quality,
        .fb_count = 2,
        .fb_location = CAMERA_FB_IN_PSRAM,
        .grab_mode = CAMERA_GRAB_LATEST,
    };
    esp_err_t err = esp_camera_init(&cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "init failed: %s", esp_err_to_name(err));
        return err;
    }
    sensor_t *s = esp_camera_sensor_get();
    s->set_framesize(s, to_framesize(c->frame_size));
    s->set_quality(s, c->jpeg_quality);
    return ESP_OK;
}

esp_err_t camera_init(const devcfg_t *c)
{
    s_lock = xSemaphoreCreateMutex();
    xSemaphoreTake(s_lock, portMAX_DELAY);
    esp_err_t err = init_locked(c);
    xSemaphoreGive(s_lock);
    return err;
}

esp_err_t camera_apply(const devcfg_t *c)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    sensor_t *s = esp_camera_sensor_get();
    esp_err_t err = ESP_FAIL;
    if (s != NULL) {
        int a = s->set_framesize(s, to_framesize(c->frame_size));
        int b = s->set_quality(s, c->jpeg_quality);
        err = (a == 0 && b == 0) ? ESP_OK : ESP_FAIL;
    }
    xSemaphoreGive(s_lock);
    return err;
}

esp_err_t camera_reinit(const devcfg_t *c)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    esp_camera_deinit();
    esp_err_t err = init_locked(c);
    xSemaphoreGive(s_lock);
    return err;
}

camera_fb_t *camera_capture(void)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb == NULL) {
        xSemaphoreGive(s_lock);
    }
    return fb; /* lock is held until camera_return */
}

void camera_return(camera_fb_t *fb)
{
    esp_camera_fb_return(fb);
    xSemaphoreGive(s_lock);
}
```

- [ ] **Step 2: Stream**

`firmware/main/stream.h`:
```c
#pragma once
#include "esp_err.h"

/* Capture loop: while streaming and MQTT is connected, publish one frame per interval_ms. */
esp_err_t stream_start(void);
```

`firmware/main/stream.c`:
```c
#include "stream.h"

#include <string.h>

#include "camera.h"
#include "config_store.h"
#include "core/proto.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mqtt_link.h"
#include "timesync.h"

static const char *TAG = "stream";
#define MAX_CAPTURE_FAILURES 5
#define SLICE_MS 100

static int s_failures;

static void send_frame(const devcfg_t *cfg)
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

    size_t n = PROTO_HEADER_SIZE + fb->len;
    uint8_t *buf = heap_caps_malloc(n, MALLOC_CAP_SPIRAM);
    if (buf == NULL) {
        ESP_LOGW(TAG, "no memory for %u-byte frame", (unsigned)n);
        camera_return(fb);
        return;
    }
    proto_pack_header(buf, timesync_capture_ms());
    memcpy(buf + PROTO_HEADER_SIZE, fb->buf, fb->len);
    camera_return(fb);

    if (mqtt_link_publish("image", buf, n, 0, false) < 0) {
        ESP_LOGW(TAG, "publish failed");
    }
    heap_caps_free(buf);
}

static void stream_task(void *arg)
{
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
    for (;;) {
        devcfg_t cfg;
        config_store_get(&cfg);
        int64_t started = esp_timer_get_time();
        if (cfg.streaming && mqtt_link_connected()) {
            send_frame(&cfg);
        }
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
    return xTaskCreate(stream_task, "stream", 6144, NULL, 4, NULL) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
```

- [ ] **Step 3: Audio**

`firmware/main/audio.h`:
```c
#pragma once
#include <stdint.h>

#include "esp_err.h"

/* Plays the embedded alert clip (assets/alert.raw: 8-bit unsigned PCM, 16 kHz)
 * as PWM on BOARD_AUDIO_GPIO. */
esp_err_t audio_init(void);
void audio_set_volume(uint8_t volume); /* 0..100 */
void audio_play(int repeat);           /* restarts if already playing */
```

`firmware/main/audio.c`:
```c
#include "audio.h"

#include "board.h"
#include "core/pcm.h"
#include "driver/gptimer.h"
#include "driver/ledc.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"

static const char *TAG = "audio";

#define AUDIO_LEDC_TIMER LEDC_TIMER_1     /* camera XCLK uses LEDC_TIMER_0 */
#define AUDIO_LEDC_CHANNEL LEDC_CHANNEL_1
#define AUDIO_PWM_HZ 78000
#define AUDIO_SAMPLE_HZ 16000
#define AUDIO_SILENCE 128

extern const uint8_t alert_raw_start[] asm("_binary_alert_raw_start");
extern const uint8_t alert_raw_end[] asm("_binary_alert_raw_end");

static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;
static volatile size_t s_pos;
static volatile int s_repeats_left;
static volatile bool s_playing;
static volatile uint8_t s_volume = 80;

static void set_duty(uint32_t duty)
{
    ledc_set_duty(LEDC_LOW_SPEED_MODE, AUDIO_LEDC_CHANNEL, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, AUDIO_LEDC_CHANNEL);
}

static bool on_sample(gptimer_handle_t timer, const gptimer_alarm_event_data_t *e, void *ctx)
{
    int duty = -1; /* -1 = idle, leave the output alone */
    portENTER_CRITICAL_ISR(&s_mux);
    if (s_playing) {
        size_t len = (size_t)(alert_raw_end - alert_raw_start);
        if (s_pos >= len) {
            if (--s_repeats_left > 0) {
                s_pos = 0;
            } else {
                s_playing = false;
            }
        }
        duty = s_playing ? pcm_scale(alert_raw_start[s_pos++], s_volume) : AUDIO_SILENCE;
    }
    portEXIT_CRITICAL_ISR(&s_mux);
    if (duty >= 0) {
        set_duty((uint32_t)duty); /* outside our lock: ledc takes its own */
    }
    return false;
}

esp_err_t audio_init(void)
{
    ledc_timer_config_t t = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_8_BIT,
        .timer_num = AUDIO_LEDC_TIMER,
        .freq_hz = AUDIO_PWM_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&t));
    ledc_channel_config_t ch = {
        .gpio_num = BOARD_AUDIO_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = AUDIO_LEDC_CHANNEL,
        .timer_sel = AUDIO_LEDC_TIMER,
        .duty = AUDIO_SILENCE,
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&ch));

    gptimer_handle_t timer;
    gptimer_config_t tc = {
        .clk_src = GPTIMER_CLK_SRC_DEFAULT,
        .direction = GPTIMER_COUNT_UP,
        .resolution_hz = 1000000,
    };
    ESP_ERROR_CHECK(gptimer_new_timer(&tc, &timer));
    gptimer_event_callbacks_t cbs = {.on_alarm = on_sample};
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(timer, &cbs, NULL));
    gptimer_alarm_config_t alarm = {
        .alarm_count = 1000000 / AUDIO_SAMPLE_HZ, /* 62 us -> 16.13 kHz, pitch +0.8% */
        .reload_count = 0,
        .flags.auto_reload_on_alarm = true,
    };
    ESP_ERROR_CHECK(gptimer_set_alarm_action(timer, &alarm));
    ESP_ERROR_CHECK(gptimer_enable(timer));
    ESP_ERROR_CHECK(gptimer_start(timer));
    ESP_LOGI(TAG, "ready: %u-byte clip on GPIO %d", (unsigned)(alert_raw_end - alert_raw_start),
             BOARD_AUDIO_GPIO);
    return ESP_OK;
}

void audio_set_volume(uint8_t volume)
{
    s_volume = volume > 100 ? 100 : volume;
}

void audio_play(int repeat)
{
    portENTER_CRITICAL(&s_mux);
    s_pos = 0;
    s_repeats_left = repeat < 1 ? 1 : repeat;
    s_playing = true;
    portEXIT_CRITICAL(&s_mux);
    ESP_LOGI(TAG, "playing alert x%d", repeat);
}
```

- [ ] **Step 4: Status**

`firmware/main/status.h`:
```c
#pragma once
#include "esp_err.h"

/* Publishes {id}/status (QoS 1, retained) every 60 s and on request. */
esp_err_t status_start(void);
void status_request(void); /* safe from any task; never blocks */
```

`firmware/main/status.c`:
```c
#include "status.h"

#include "board.h"
#include "config_store.h"
#include "core/msg.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mqtt_link.h"
#include "net.h"
#include "sdkconfig.h"

static const char *TAG = "status";
#define STATUS_PERIOD_MS 60000

static TaskHandle_t s_task;

void status_request(void)
{
    if (s_task != NULL) {
        xTaskNotifyGive(s_task);
    }
}

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
    };
    char buf[160];
    int n = msg_format_status(buf, sizeof buf, &s);
    if (n < 0) {
        ESP_LOGE(TAG, "status does not fit buffer");
        return;
    }
    if (mqtt_link_publish("status", buf, (size_t)n, 1, true) < 0) {
        ESP_LOGD(TAG, "not connected, status skipped");
    }
}

static void status_task(void *arg)
{
    for (;;) {
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(STATUS_PERIOD_MS));
        publish_status();
    }
}

esp_err_t status_start(void)
{
    return xTaskCreate(status_task, "status", 4096, NULL, 3, &s_task) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
```

- [ ] **Step 5: Review and commit**

Check: camera lock is released on every path of `camera_capture`/`camera_return`; frame buffer returned before the network publish; audio LEDC timer/channel differ from the camera's; audio ISR does no allocation or logging.
```bash
git add firmware/main/camera.h firmware/main/camera.c firmware/main/stream.h firmware/main/stream.c firmware/main/audio.h firmware/main/audio.c firmware/main/status.h firmware/main/status.c
git commit -m "feat(firmware): add camera, stream, audio, and status modules"
```

---

### Task 10: main.c, build files, README, bring-up checklist

**Files:**
- Create: `firmware/main/CMakeLists.txt`, `firmware/main/main.c`, `firmware/README.md`

**Interfaces:**
- Consumes: every module header from Tasks 7–9 and `proto_mac_to_id` (Task 2).
- Produces: the firmware image; operator documentation.

- [ ] **Step 1: `firmware/main/CMakeLists.txt`**

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
    "status.c")

# Exactly one network backend implements net.h.
if(CONFIG_NET_BACKEND_WIFI)
    list(APPEND srcs "net_wifi.c")
endif()

idf_component_register(SRCS ${srcs}
                       INCLUDE_DIRS "."
                       REQUIRES core driver esp_wifi esp_netif esp_event esp_timer
                                nvs_flash mqtt mbedtls lwip efuse
                       EMBED_FILES "assets/alert.raw")
```

- [ ] **Step 2: `firmware/main/main.c`**

```c
/* Boot sequence. Only module interfaces are used here; no driver, Wi-Fi,
 * LTE, or pin details. */
#include "audio.h"
#include "camera.h"
#include "cmd.h"
#include "config_store.h"
#include "core/proto.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "mqtt_link.h"
#include "net.h"
#include "status.h"
#include "stream.h"
#include "timesync.h"

static const char *TAG = "main";

void app_main(void)
{
    ESP_ERROR_CHECK(config_store_init());
    devcfg_t cfg;
    config_store_get(&cfg);

    if (camera_init(&cfg) != ESP_OK) {
        ESP_LOGE(TAG, "camera unavailable; stream will retry and reboot if it keeps failing");
    }
    ESP_ERROR_CHECK(audio_init());
    audio_set_volume(cfg.volume);

    ESP_ERROR_CHECK(net_start());
    while (!net_wait_connected(pdMS_TO_TICKS(30000))) {
        ESP_LOGW(TAG, "waiting for network");
    }
    timesync_start();

    uint8_t mac[6];
    char id[PROTO_ID_SIZE];
    ESP_ERROR_CHECK(esp_efuse_mac_get_default(mac));
    proto_mac_to_id(mac, id);

    ESP_ERROR_CHECK(cmd_start());
    ESP_ERROR_CHECK(status_start());
    const mqtt_link_handlers_t handlers = {
        .on_message = cmd_submit,
        .on_connected = status_request,
    };
    ESP_ERROR_CHECK(mqtt_link_start(id, &handlers));
    ESP_ERROR_CHECK(stream_start());
    ESP_LOGI(TAG, "running as %s", id);
}
```

- [ ] **Step 3: `firmware/README.md`**

````markdown
# Pedestrian alert — edge firmware

ESP-IDF firmware for the edge device. It sends camera frames to the master over
MQTT and plays an alert sound when the master publishes `{id}/alert`.
Design: `docs/superpowers/specs/2026-09-29-pedestrian-alert-design.md`.

Board: Freenove ESP32-S3-WROOM CAM (Wi-Fi). Network and pins are behind
`main/net.h` and `main/board.h`; LTE (Waveshare ESP32-S3-SIM7670G-4G) is added
later as `net_lte.c` + `boards/waveshare_s3_4g.h`.

## Host tests (no ESP-IDF needed)

```sh
sh test/host/run.sh                       # components/core unit tests
python -m pytest tools/test_wav2raw.py    # clip converter
```

## Build and flash (ESP-IDF >= 5.1)

```sh
cd firmware
idf.py set-target esp32s3
idf.py menuconfig      # Pedestrian Edge: Wi-Fi SSID/password, MQTT URI
idf.py build flash monitor
```

MQTT URI choices:
- Through Cloudflare Tunnel: `wss://mqtt.<domain>:443/mqtt`
- Bench, straight to the PC's Mosquitto websockets listener: `ws://<pc-ip>:9001/mqtt`
- Bench, plain MQTT: `mqtt://<pc-ip>:1883`

For the two bench URIs, the PC's Mosquitto listener must bind to the LAN address
(the shipped `server/deploy/mosquitto.conf` binds to 127.0.0.1 only).

Flash size: `sdkconfig.defaults` assumes an N8R8 module (8 MB flash). For N16R8,
set `CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y`.

## Alert sound

```sh
python tools/wav2raw.py my_sound.wav main/assets/alert.raw   # any 8/16-bit WAV
python tools/wav2raw.py --demo main/assets/alert.raw         # built-in chime
```

The clip is embedded in the firmware (16 KB per second). Rebuild after changing it.

Wiring: GPIO 14 → 1 kΩ → (15 nF to GND) → 10 kΩ → (1.5 nF to GND) → PAM8403 L-in.
Common ground. Set the level with the module's volume knob.

## Bring-up checklist

Run in order; each step depends on the previous one.

1. `idf.py build` succeeds with no warnings in `main/` or `components/core/`.
2. Boot log shows `config_store: ...`, `audio: ready: 19200-byte clip on GPIO 14`, no camera error.
3. `net_wifi: got ip ...` within 10 s; unplug the AP → `disconnected, retry in 5000 ms`, then 10000, 30000.
4. `mqtt_link: connected` and `main: running as <id>`. On the PC:
   `mosquitto_sub -t '<id>/#' -v` shows `<id>/online 1` and `<id>/status {...}`.
5. Frames arrive: `mosquitto_sub -t '<id>/image' -C 1 | wc -c` is > 8 bytes.
   Server log shows the device; after SNTP sync, frame timestamps are current (not 0).
6. `python -m master.cli alert <id>` → chime plays once; `--repeat 3` → three times.
7. `python -m master.cli config <id> volume=30` → quieter. `frame_size=QVGA` → smaller frames.
   `volume=150` is rejected by the CLI; a hand-published `{"volume":150}` is logged as rejected by the device.
8. `python -m master.cli stop <id>` → frames stop; reboot the device → still stopped; `start` → frames resume.
9. `python -m master.cli status <id>` → new status message; `reboot <id>` → device restarts and reconnects.
10. Power off the device → `<id>/online 0` within about 45 s (keepalive 30 s × 1.5).
11. End to end with `python -m master.app` running: stand in view for `ALERT_DWELL_SECONDS` → chime; walk through quickly → no chime.
````

- [ ] **Step 4: Review and commit**

Check against the Global Constraints: `main.c` includes only module headers; no pin numbers outside `boards/`; Kconfig default credentials empty.

Run the host suites one last time:
```bash
sh firmware/test/host/run.sh
CC=/c/msys64/mingw64/bin/gcc.exe sh firmware/test/host/run.sh
server/.venv/Scripts/python -m pytest firmware/tools/test_wav2raw.py -q
```
Expected: `0 failures`, `0 failures`, `4 passed`.

```bash
git add firmware/main/CMakeLists.txt firmware/main/main.c firmware/README.md
git commit -m "feat(firmware): wire modules in main and add README with bring-up checklist"
```
