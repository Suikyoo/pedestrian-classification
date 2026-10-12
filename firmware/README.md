# Pedestrian alert — edge firmware

ESP-IDF firmware for the edge device. It detects pedestrians on the device with
Espressif's INT8 `pedestrian_detect` model (ESP-DL), plays the alert sound itself
when a pedestrian stays in view for `dwell_s`, and reports each alert to the master
as `{id}/event` with a snapshot. Frames go to the master only in stream mode
(`python -m master.cli start <id>`).
Design: `docs/superpowers/specs/2026-10-11-on-device-inference-design.md`
(original: `2026-09-29-pedestrian-alert-design.md`).

Board: Freenove ESP32-S3-WROOM CAM (Wi-Fi). Network and pins are behind
`main/net.h` and `main/board.h`; LTE (Waveshare ESP32-S3-SIM7670G-4G) is added
later as `net_lte.c` + `boards/waveshare_s3_4g.h`.

## Host tests (no ESP-IDF needed)

```sh
sh test/host/run.sh                       # components/core unit tests
python -m pytest tools/test_wav2raw.py    # clip converter
```

## Compile and flash the firmware

The firmware has never been compiled on the development PC (no ESP-IDF there).
The first `idf.py build` on your ESP-IDF machine is its first real compile; use
the bring-up checklist below to verify it.

### 1. Install ESP-IDF (once per machine)

Supported: **ESP-IDF v5.3 to v5.5** (ESP-DL needs v5.3 or later; developed on v5.5). ESP-IDF 6.x is not
supported yet (see Troubleshooting).

- **Windows:** install with the ESP-IDF Windows Installer (Espressif's "ESP-IDF
  Tools Installer"), choosing v5.5. It adds an **"ESP-IDF PowerShell"** (and
  "ESP-IDF CMD") shortcut; run every `idf.py` command below from that shortcut.
- **Linux / macOS:**
  ```sh
  mkdir -p ~/esp && cd ~/esp
  git clone -b v5.5 --recursive https://github.com/espressif/esp-idf.git
  cd esp-idf && ./install.sh esp32s3
  . ./export.sh            # run this in every new terminal
  ```

Check: `idf.py --version` prints `ESP-IDF v5.x`.

### 2. Get the code

```sh
git clone git@github.com:Suikyoo/pedestrian-classification.git
cd pedestrian-classification/firmware
```

All commands below run inside `firmware/`.

### 3. Select the chip

```sh
idf.py set-target esp32s3
```

This creates `sdkconfig` from `sdkconfig.defaults` (PSRAM, flash size, partition
table, TLS bundle, watchdog). `sdkconfig` is machine-local and git-ignored.
Running `set-target` again deletes `sdkconfig` and starts from the defaults.

Flash size: the defaults assume a Freenove **N8R8** module (8 MB flash, 8 MB
PSRAM; the module marking is printed on its metal shield). For **N16R8**, change
`CONFIG_ESPTOOLPY_FLASHSIZE_8MB=y` to `CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y` in
`sdkconfig.defaults` before `set-target`, or set it in menuconfig under
*Serial flasher config → Flash size*.

### 4. Configure Wi-Fi and the broker

```sh
idf.py menuconfig
```

Open **Pedestrian Edge** and set:

| Option | Value |
|---|---|
| Board | Freenove ESP32-S3-WROOM CAM (only choice for now) |
| Network backend | Wi-Fi (only choice for now) |
| Wi-Fi SSID / Wi-Fi password | your network (empty password = open network; 2.4 GHz only) |
| MQTT broker URI | see "MQTT URI choices" below |
| MQTT username / MQTT password | leave empty unless broker auth is enabled |
| Firmware version | reported in `{id}/status`; change when you release |

Save with `S`, quit with `Q`. Settings live in `sdkconfig`.

To keep credentials out of interactive menus, put them in a git-ignored file
instead, for example `sdkconfig.local`:

```
CONFIG_WIFI_SSID="my-network"
CONFIG_WIFI_PASSWORD="my-password"
CONFIG_MQTT_URI="ws://192.168.1.20:9001/mqtt"
```

and build with both default files (delete `sdkconfig` first so they apply):

```sh
idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.local" set-target esp32s3
```

### 5. Build

```sh
idf.py build
```

The first build needs internet access once: the component manager downloads
`espressif/esp32-camera`, `espressif/esp-dl`, and `espressif/pedestrian_detect`
(declared in `main/idf_component.yml`) into `managed_components/`.
A successful build ends with
`Project build complete` and the image `build/pedestrian_edge.bin`. The build
prints the image size and the free space left in the 4 MB factory partition.

### 6. Flash and watch the log

Connect the board by USB, then find its serial port:

- Windows: Device Manager → *Ports (COM & LPT)*, e.g. `COM5`
- Linux: `ls /dev/ttyACM* /dev/ttyUSB*`; macOS: `ls /dev/cu.usb*`

```sh
idf.py -p COM5 flash monitor
```

Exit the monitor with `Ctrl+]`. If flashing cannot connect, hold **BOOT**, tap
**RST**, release **BOOT**, and run the command again.

The log should show, in order: `config_store`, `audio: ready: 19200-byte clip on
GPIO 14`, `net_wifi: got ip ...`, `mqtt_link: connected`, and
`main: running as <id>`. `<id>` is the device ID used by the server, the CLI and
the dashboard.

`idf.py flash` also writes the pedestrian model into the `pedestrian_det`
partition. The log then shows `detect: model loaded in ... ms`, and every 30th
frame `detect: 640x480: decode .. ms, inference .. ms, score ..`. `app-flash`
skips the model; a board flashed only that way logs
`pedestrian_det partition is empty` and reports `detect_ok: false`.

To try another model without rebuilding:
`parttool.py write_partition --partition-name pedestrian_det --input <model>.espdl`.

### Rebuilding after changes

| Change | Command |
|---|---|
| C code, Kconfig values, alert clip | `idf.py build flash` (or `idf.py -p COM5 flash monitor`) |
| `sdkconfig.defaults` | delete `sdkconfig` (or `idf.py set-target esp32s3`), then build |
| Something behaves stale | `idf.py fullclean`, then build |

### MQTT URI choices

- Through Cloudflare Tunnel: `wss://mqtt.<domain>:443/mqtt`
- Bench, straight to the PC's Mosquitto websockets listener: `ws://<pc-ip>:9001/mqtt`
- Bench, plain MQTT: `mqtt://<pc-ip>:1883`

For the two bench URIs, the PC's Mosquitto listener must bind to the LAN address
(the shipped `server/deploy/mosquitto.conf` binds to 127.0.0.1 only), and the
Windows firewall must allow the port.

### Troubleshooting the first build

These are the spots the code review could not confirm without a compiler:

| Symptom | Fix |
|---|---|
| `Failed to resolve component 'json'` | You are on ESP-IDF 6.x, where cJSON moved out of IDF. Use v5.x, or replace `json` with the managed component `espressif/cjson` in `components/core/CMakeLists.txt` and add it to a `components/core/idf_component.yml`. |
| `esp_camera.h: No such file` | The component manager did not run or had no internet. Run `idf.py reconfigure` with internet access. |
| Boot aborts in `audio_init` at `ledc_timer_config` (clock conflict) | The camera's XCLK timer and the audio PWM timer chose different LEDC clock sources. In `main/audio.c`, set `.clk_cfg` to the same source the camera uses (try `LEDC_USE_APB_CLK`). |
| `PSRAM ID read error` / boot loop at start | The module has no octal PSRAM or a different size. Check the module marking (N8R8 / N16R8) and the PSRAM mode in menuconfig (*Component config → ESP PSRAM*). |
| `Detected size(8192k) smaller than the size in the binary image header(16384k)` (or the reverse) | Flash size in `sdkconfig.defaults` does not match the module; see step 3. |
| `Camera init failed` | Reseat the camera ribbon (contacts facing the board) and power-cycle. The firmware retries and reboots after 5 failed captures. |
| Wi-Fi never connects | SSID is empty or wrong (the log says `WIFI_SSID is empty`), or the network is 5 GHz only. |
| `MQTT_URI is still the example value` | Set the broker URI in menuconfig (step 4). |
| `Failed to resolve component 'espressif/pedestrian_detect'` | Run `idf.py add-dependency "espressif/pedestrian_detect"` with internet access, then build. |
| `pedestrian_det partition is empty` at boot | The model was not flashed. Run `idf.py flash` (not `app-flash`). |
| `detect: ... inference` well above 250 ms | Check that `sdkconfig` has `CONFIG_COMPILER_OPTIMIZATION_PERF=y` and 64 KB data cache; delete `sdkconfig` and rebuild if it came from older defaults. |
| `detect_ok:false` or slow detection after choosing `frame_size` above VGA | Detection decodes the full frame into PSRAM (SXGA/UXGA need 4-6 MB and take much longer). Keep `frame_size` at VGA or below while alerts matter. |
| Watchdog reboots during large frame uploads | Lower `frame_size` or raise `jpeg_quality` with `python -m master.cli config <id> ...`. |

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
