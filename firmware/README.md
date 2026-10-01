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
