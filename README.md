# Pedestrian warning system

Edge cameras (ESP32-S3) detect pedestrians on the device with an INT8 model. When a
pedestrian stays in view for the device's `dwell_s`, the device plays a warning
sound and reports the warning, with a snapshot, to the master server over MQTT. A
LAN dashboard shows every device, its warnings, and, for devices in stream mode,
live frames scored by both the device and YOLO11n on the server.

| Part | Folder | Guide |
|---|---|---|
| Master server, CLI, dashboard | `server/` | [server/README.md](server/README.md) |
| Edge device firmware (ESP-IDF) | `firmware/` | [firmware/README.md](firmware/README.md) |
| Design and plans | `docs/superpowers/` | specs and implementation plans |
| Product and visual system | `PRODUCT.md`, `DESIGN.md` | dashboard context and design tokens |

## Quick start

1. **Server PC:** follow [server/README.md](server/README.md): install the Python
   environment, run Mosquitto with `server/deploy/mosquitto.conf`, start
   `python -m master.app`, and open the dashboard with `python -m master.web`.
2. **ESP-IDF machine:** follow
   [firmware/README.md → Compile and flash the firmware](firmware/README.md#compile-and-flash-the-firmware):
   install ESP-IDF v5.3–v5.5, `idf.py set-target esp32s3`, set Wi-Fi and the
   broker URI in `idf.py menuconfig`, then `idf.py -p <port> flash monitor`.
3. Work through the firmware's bring-up checklist to verify the device end to end.
