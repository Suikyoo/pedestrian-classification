# Pedestrian Alert System — Design

Date: 2026-09-29
Status: Draft for review

## 1. Goal

A master server (PC) receives camera frames from one or more edge devices (ESP32-S3 with an LTE modem), runs pedestrian detection on each frame, and when a pedestrian has been continuously present in a device's view for more than N seconds, sends an alert to that device, which plays a recorded sound through a speaker.

The master can also send instructions to each device: start/stop streaming, change runtime configuration, request status, and reboot.

### Success criteria

- A person standing in front of a device's camera for N seconds (from the server `.env`) causes that device to play the alert clip.
- A person passing through for less than N seconds does not trigger an alert.
- One dropped or misclassified frame does not restart the dwell timer.
- The same person standing in view does not re-trigger the alert more often than the cooldown.
- The master can change capture interval, JPEG quality, frame size, and volume of any device at runtime, and the device keeps that configuration across reboots and reconnects.
- The server knows when a device goes offline.

### Out of scope (v1)

- Dashboard or web UI.
- Zone/polygon-based detection.
- Custom-trained model.
- OTA firmware updates.
- SD card usage.
- MQTT authentication (designed to be added by configuration only; see §6).

## 2. Hardware

### Edge device

- Board: **Waveshare ESP32-S3-SIM7670G-4G** (global LTE bands) or **ESP32-S3-A7670E-4G** (EMEA/Asia bands). Choose by the carrier's LTE bands.
  - ESP32-S3 with PSRAM, 24-pin camera connector (OV2640/OV5640), LTE Cat-1 modem, 18650 holder, solar input.
- Camera: OV2640 or OV5640 via `esp32-camera`.
- Audio: PAM8403 class-D amplifier module + small speaker, driven by one ESP32-S3 GPIO using LEDC PWM (the ESP32-S3 has no DAC).

### Audio circuit

Two-stage RC low-pass reconstructs audio from the 78 kHz PWM carrier (≈ 40 dB/decade roll-off, ≈ 30 dB carrier attenuation, fc ≈ 10 kHz; audio content ≤ 8 kHz at 16 kHz sample rate).

```
GPIO --1kΩ--+--10kΩ--+-- [1µF if module has no input cap] --> PAM8403 L-in
            |        |
          15nF     1.5nF
            |        |
GND --------+--------+-----------------------------------------> PAM8403 GND
PAM8403 VCC <- battery rail (2.5–5.5 V), 470 µF bulk cap near the amplifier
```

Level setting: the filtered signal is ≈ 3.3 Vpp, which clips the PAM8403 (fixed ≈ 24 dB gain). The maximum level is set in hardware:

- If the PAM8403 module has an onboard volume knob, use it.
- Otherwise, add a fixed divider after the filter (10 kΩ series, 1 kΩ to GND → ≈ 0.3 Vpp).

Software `volume` scales samples below that maximum.

### Pin assignment

All GPIO numbers live in `firmware/main/board.h` and are taken from the Waveshare schematic for the chosen board variant. The PWM audio pin must not be shared with the camera, modem UART/PWRKEY, SD card lines, or boot-strapping pins.

### Master

Any PC able to run Python 3.11+. YOLO11n runs on CPU (≈ 20–50 ms per 640 px frame); CUDA is used if configured.

## 3. Architecture

```
[ESP32-S3 + LTE modem] --PPP/LTE--> wss://mqtt.<domain>:443
                                           |
                                    Cloudflare edge
                                           |
                                    cloudflared (PC)
                                           |
                        Mosquitto :9001 (websockets, localhost only)
                        Mosquitto :1883 (plain, localhost only)
                                           |
                        master (Python): ingest -> detect -> logic -> publish
```

- The device reaches the network through the modem in PPP mode (`esp_modem`), so the standard ESP-IDF network stack, TLS, and `esp-mqtt` work over LTE unchanged.
- The broker is Mosquitto on the master PC. Neither listener is exposed on the LAN or router; `cloudflared` publishes the websockets listener on a public hostname.
- Cloudflare Tunnel public hostnames forward HTTP(S)/WebSocket only, so devices use **MQTT over WSS on port 443**. Cloudflare terminates TLS; the device verifies it with `esp_crt_bundle`.
- The master's Python service connects to Mosquitto directly on `localhost:1883`.

### Deployment config

`mosquitto.conf` (v1, no auth):

```conf
listener 1883 127.0.0.1
listener 9001 127.0.0.1
protocol websockets
allow_anonymous true
```

`cloudflared` `config.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: <path>/<TUNNEL_ID>.json
ingress:
  - hostname: mqtt.<domain>
    service: http://localhost:9001
  - service: http_status:404
```

DNS route: `cloudflared tunnel route dns <tunnel-name> mqtt.<domain>`.

## 4. MQTT protocol

Device ID `{mac}` = station MAC, lowercase hex, no separators (e.g. `a1b2c3d4e5f6`). It is also the MQTT client ID.

| Topic | Direction | QoS | Retained | Payload |
|---|---|---|---|---|
| `{mac}/image` | device → server | 0 | no | 8-byte header: `uint64` little-endian `capture_ms` (Unix epoch ms from SNTP; `0` if not synced), followed by JPEG bytes |
| `{mac}/alert` | server → device | 1 | no | JSON `{"clip":"alert","repeat":1}` |
| `{mac}/cmd` | server → device | 1 | no | JSON `{"action":"start"\|"stop"\|"reboot"\|"status"}` |
| `{mac}/config` | server → device | 1 | yes | JSON `{"interval_ms":1000,"jpeg_quality":12,"frame_size":"VGA","volume":80}` |
| `{mac}/status` | device → server | 1 | yes | JSON `{"rssi":-71,"battery_mv":3920,"uptime_s":3600,"streaming":true,"fw":"0.1.0"}` |
| `{mac}/online` | device → server | 1 | yes | `"1"` published on connect; `"0"` as Last Will |

Rules:

- Images use QoS 0: a lost frame is superseded by the next; retries would only deliver stale frames.
- Config is retained so a reconnecting or rebooted device receives its current config immediately. Config fields are all optional; missing fields keep their current value. Unknown fields are ignored.
- `frame_size` accepts `esp32-camera` names: `QVGA`, `VGA`, `SVGA`, `XGA`, `HD`, `SXGA`, `UXGA`.
- `volume` is 0–100. `repeat` is 1–10.
- Status is published every 60 s and immediately after a `status` command.

Data budget note: VGA at `jpeg_quality` 12 is roughly 30–40 KB per frame; at 1 frame/s that is ≈ 3 GB/day per device. `interval_ms`, `stop`, and `frame_size` are the levers to control LTE cost.

## 5. Master server

### Layout

```
server/
  .env.example
  pyproject.toml          # paho-mqtt>=2, ultralytics, pydantic-settings, numpy, pillow
  master/
    settings.py           # pydantic-settings, reads .env
    protocol.py           # topic builders/parsers, image header parse, JSON payload models
    detector.py           # YOLO11n wrapper: JPEG bytes -> max person confidence
    logic.py              # per-device dwell state machine (pure, no I/O)
    events.py             # SQLite event log + snapshot JPEG save
    app.py                # MQTT client, latest-frame slots, worker thread, wiring
    cli.py                # manual commands to devices
  tools/
    fake_device.py        # publishes JPEGs from a folder as a device, for testing
  tests/
```

### `.env`

```
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_USER=
MQTT_PASS=
MODEL_PATH=yolo11n.pt
DEVICE=cpu
PEDESTRIAN_CONF_THRESHOLD=0.6
ALERT_DWELL_SECONDS=5
MAX_GAP_SECONDS=3
ALERT_COOLDOWN_SECONDS=30
EVENTS_DIR=./events
```

When `MQTT_USER` and `MQTT_PASS` are both blank, the client connects without credentials.

### Detection

`detector.py` loads Ultralytics YOLO11n (COCO) and returns the highest confidence among `person` detections in a frame (`0.0` if none). A frame is **positive** when that value ≥ `PEDESTRIAN_CONF_THRESHOLD`.

Licensing: Ultralytics is AGPL-3.0. Acceptable for personal/research use; a closed-source commercial deployment requires an Ultralytics enterprise license or a swap to an Apache-licensed detector behind the same `detector.py` interface.

### Alert logic (`logic.py`)

Pure, per-device state: `first_seen`, `last_seen`, `last_alert`, `last_ts`.

`update(ts, conf) -> bool` (true = send alert). `ts` is the frame's `capture_ms` in seconds, or server receive time when `capture_ms` is 0.

1. If `ts` ≤ `last_ts`, ignore the frame (out of order); return false. Otherwise set `last_ts = ts`.
2. If `last_seen` is set and `ts - last_seen > MAX_GAP_SECONDS`, reset `first_seen` and `last_seen` (the pedestrian has been absent, or frames missing, for too long).
3. If the frame is negative: return false. A negative frame does not reset the timer by itself; the reset happens in step 2 once no positive frame has been seen for `MAX_GAP_SECONDS`. This makes single misclassified or dropped frames harmless.
4. If the frame is positive: set `first_seen = ts` if unset; set `last_seen = ts`.
5. If `ts - first_seen ≥ ALERT_DWELL_SECONDS` and (`last_alert` unset or `ts - last_alert ≥ ALERT_COOLDOWN_SECONDS`): set `last_alert = ts`; return true.
6. Otherwise return false.

When a device goes offline (`{mac}/online` = `"0"`), its state is discarded.

### Processing flow (`app.py`)

1. Subscribe to `+/image`, `+/status`, `+/online` (resubscribe in `on_connect`).
2. On an image: parse header; store `(ts, jpeg)` in a per-device latest-frame slot, overwriting any unprocessed frame; signal the worker.
3. The worker thread takes each filled slot, runs `detector`, then `logic.update`. On true: publish `{mac}/alert`, then `events.record(...)`.
4. On status/online: log. On offline: discard `logic` state for that device.

The latest-frame slot guarantees the server never builds a backlog: if inference is slower than arrival, older frames are dropped.

### Events (`events.py`)

On each alert: insert a row into SQLite `EVENTS_DIR/events.db` (`mac`, `alert_ts`, `first_seen_ts`, `dwell_s`, `max_conf`) and save the triggering JPEG to `EVENTS_DIR/<mac>/<alert_ts>.jpg`.

### CLI (`cli.py`)

```
python -m master.cli alert  <mac> [--repeat N]
python -m master.cli start  <mac>
python -m master.cli stop   <mac>
python -m master.cli reboot <mac>
python -m master.cli status <mac>
python -m master.cli config <mac> interval_ms=500 volume=60 ...
```

`config` merges the given fields into the currently retained config for that device and republishes it retained.

### Error handling

| Failure | Behavior |
|---|---|
| Broker disconnect | paho auto-reconnect; resubscribe in `on_connect` |
| Malformed header or undecodable JPEG | log warning with `mac`; drop frame |
| Detector exception | log error; drop frame; worker continues |
| SQLite/disk error in `events` | log error; the alert is still published |

## 6. Edge firmware

ESP-IDF v5.x, C.

### Layout

```
firmware/
  CMakeLists.txt
  partitions.csv          # nvs, phy_init, factory app (≥ 4 MB)
  sdkconfig.defaults      # octal PSRAM, PPP, cert bundle, task WDT
  Kconfig.projbuild       # MQTT_URI, MQTT_USERNAME, MQTT_PASSWORD, NET_WIFI, WIFI_SSID, WIFI_PASS
  main/
    main.c                # boot sequence, task start
    board.h               # all GPIO numbers
    net_lte.c/.h          # esp_modem PPP bring-up, reconnect with backoff, CSQ -> rssi
    net_wifi.c/.h         # bench-only Wi-Fi alternative (NET_WIFI)
    mqtt_link.c/.h        # esp-mqtt over wss, LWT, subscriptions, dispatch
    camera.c/.h           # esp32-camera init/reconfigure, capture -> header + JPEG
    stream.c/.h           # capture loop task
    audio.c/.h            # LEDC 78 kHz 8-bit carrier + gptimer ISR at 16 kHz
    config.c/.h           # parse config JSON (cJSON), apply, persist to NVS
    status.c/.h           # battery ADC, uptime, status publishing
    assets/alert.raw      # 8-bit unsigned PCM, mono, 16 kHz (EMBED_FILES)
  tools/
    wav2raw.py            # converts a WAV file to alert.raw
```

### Configuration and credentials

- Kconfig defaults: `MQTT_URI="wss://mqtt.example.com:443/mqtt"`, `MQTT_USERNAME=""`, `MQTT_PASSWORD=""`. Empty username/password → no credentials sent.
- Runtime config (`interval_ms`, `jpeg_quality`, `frame_size`, `volume`, `streaming`) lives in NVS and is updated by `{mac}/config` and `start`/`stop`.
- Defaults when NVS is empty: `interval_ms=1000`, `jpeg_quality=12`, `frame_size=VGA`, `volume=80`, `streaming=true`.

### Boot sequence

1. Init NVS; load runtime config.
2. Init camera with the loaded config.
3. Init audio (LEDC + gptimer, idle).
4. Network: `NET_WIFI` → Wi-Fi; otherwise pulse modem PWRKEY, start PPP, wait for IP.
5. Start SNTP. Frames before sync carry `capture_ms=0`.
6. Connect MQTT with LWT `{mac}/online="0"` (QoS 1, retained). On connect: publish `{mac}/online="1"` retained; subscribe `{mac}/alert`, `{mac}/cmd`, `{mac}/config`; publish status.
7. Start `stream` and `status` tasks.

### Tasks

- **stream:** if streaming and MQTT connected → capture → publish `{mac}/image` QoS 0 → return frame buffer → delay `interval_ms`. When disconnected, it does not capture or queue.
- **status:** publishes status every 60 s, or when signalled by the `status` command.
- **cmd:** receives parsed commands from the MQTT event handler via a FreeRTOS queue; applies config, start/stop, reboot, status, alert. The MQTT event handler never does blocking work.
- **audio ISR:** at 16 kHz, reads the next sample from the embedded clip, scales by `volume`, writes the LEDC duty. On clip end, repeats up to `repeat` times, then sets duty to mid-scale (silence). A new alert during playback restarts playback.

### Reliability

| Failure | Behavior |
|---|---|
| PPP drop | restart modem and PPP with backoff 5 s, 10 s, 30 s, 60 s (capped) |
| MQTT drop | esp-mqtt auto-reconnect |
| 5 consecutive camera capture failures | re-init camera; if re-init fails, reboot |
| Hung task | task watchdog reboots the device |
| Malformed config/cmd JSON | log and ignore |

## 7. Security

v1 runs Mosquitto with `allow_anonymous true`. Because the broker is reachable through a public hostname, **anyone who knows the hostname can read all images and send alerts, stop, or reboot commands to any device.** This is acceptable only for bench development.

Enabling auth later needs no code change:

- Mosquitto: `allow_anonymous false`, `password_file`, and an `acl_file` with `pattern readwrite %u/#` (device username = `{mac}`) plus a `server` user with `readwrite #`.
- Server: fill `MQTT_USER`/`MQTT_PASS` in `.env`.
- Firmware: set `MQTT_USERNAME` (= MAC) and `MQTT_PASSWORD` in menuconfig.

## 8. Testing

### Server

- `logic.py`: table-driven unit tests, written test-first — dwell reached, dwell not reached, gap reset, single negative frame does not reset, negatives beyond `MAX_GAP_SECONDS` reset, cooldown suppression, re-alert after cooldown, out-of-order timestamps, offline reset.
- `protocol.py`: header pack/parse round trip, topic parse, config merge.
- `detector.py`: smoke test on one image with a person and one without.
- Integration: `tools/fake_device.py` publishes a folder of JPEGs through local Mosquitto at a set interval; the test asserts an alert arrives on `{mac}/alert` after `ALERT_DWELL_SECONDS` and not before.

### Firmware

- Unity tests (on target) for config JSON parse/merge and image header packing.
- Bench bring-up over Wi-Fi (`NET_WIFI`): camera → MQTT → server detection → alert → audio.
- Then LTE bring-up with a SIM.
- End to end: a person stands in view for N seconds → sound plays; a person walks through quickly → no sound.
