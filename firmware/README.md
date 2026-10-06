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

## Compile and flash the firmware

The firmware has never been compiled on the development PC (no ESP-IDF there).
The first `idf.py build` on your ESP-IDF machine is its first real compile; use
the bring-up checklist below to verify it.

### 1. Install ESP-IDF (once per machine)

Supported: **ESP-IDF v5.1 to v5.4** (v5.3 or v5.4 recommended). ESP-IDF 6.x is not
supported yet (see Troubleshooting).

- **Windows:** install with the ESP-IDF Windows Installer (Espressif's "ESP-IDF
  Tools Installer"), choosing v5.3 or v5.4. It adds an **"ESP-IDF PowerShell"** (and
  "ESP-IDF CMD") shortcut; run every `idf.py` command below from that shortcut.
- **Linux / macOS:**
  ```sh
  mkdir -p ~/esp && cd ~/esp
  git clone -b v5.4 --recursive https://github.com/espressif/esp-idf.git
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
`espressif/esp32-camera` (declared in `main/idf_component.yml`) into
`managed_components/`. A successful build ends with
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
