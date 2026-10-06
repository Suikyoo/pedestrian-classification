# Pedestrian warning system

Edge cameras (ESP32-S3) stream frames to a master server over MQTT. The server
detects people with YOLO11n and, when a pedestrian stays in a device's view for
`ALERT_DWELL_SECONDS`, tells that device to play a warning sound. A LAN dashboard
shows every device, its frames, and past warnings.

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
   install ESP-IDF v5.1–v5.4, `idf.py set-target esp32s3`, set Wi-Fi and the
   broker URI in `idf.py menuconfig`, then `idf.py -p <port> flash monitor`.
3. Work through the firmware's bring-up checklist to verify the device end to end.
