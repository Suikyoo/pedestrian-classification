# Pedestrian alert — master server

Edge devices detect pedestrians and play the warning themselves. The master records
each device's warnings (`{mac}/event`, with a snapshot) and status, serves the LAN
dashboard, and, for devices in stream mode (`python -m master.cli start <mac>`),
scores their frames with YOLO11n so the dashboard shows YOLO and device scores
side by side. The master never sends `{mac}/alert` by itself; the CLI still can.
Design: `docs/superpowers/specs/2026-10-11-on-device-inference-design.md`.

## Setup

```powershell
cd server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

Install Mosquitto 2.x (https://mosquitto.org/download/) and run it with the
project config:

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -c deploy\mosquitto.conf
```

## Run

```powershell
python -m master.app
```

### Device alert settings

Each device decides warnings with its own settings, kept across reboots:

    python -m master.cli config <mac> threshold=0.6 dwell_s=5 max_gap_s=3 cooldown_s=30

`threshold` 0.05–0.99, `dwell_s` 0–600, `max_gap_s` 0.5–60, `cooldown_s` 0–3600.

## Dashboard

Shows every device (online state, its active threshold and dwell, last warning),
recent warnings with snapshots, and, for streaming devices, recent frames with
YOLO and device scores. Runs as its own read-only process next to `master.app`:

```powershell
python -m master.web
```

Open `http://<this-pc-ip>:8000` from any device on the LAN (`http://127.0.0.1:8000`
on this PC). The page refreshes every 2 seconds. Settings in `.env`:
`INFERENCE_HISTORY` (frames kept per device, default 200), `WEB_HOST`, `WEB_PORT`.

There is no login: anyone on the LAN who can reach the port sees the camera
thumbnails. Set `WEB_HOST=127.0.0.1` to allow only this PC. Windows Firewall may
ask to allow Python on private networks the first time.

## Commands

```powershell
python -m master.cli alert  <mac> [--repeat N]
python -m master.cli start  <mac>
python -m master.cli stop   <mac>
python -m master.cli reboot <mac>
python -m master.cli status <mac>
python -m master.cli config <mac> interval_ms=500 volume=60
```

`config` merges the given fields into the device's current retained config.
Fields: `interval_ms` (100–3600000), `jpeg_quality` (0–63, lower = better),
`frame_size` (QVGA, VGA, SVGA, XGA, HD, SXGA, UXGA), `volume` (0–100),
`rotation` (0 or 180; the sensor flips the image, so 90 is not possible).

## Test

```powershell
python -m pytest -m "not slow and not integration"   # fast unit tests
python -m pytest -m slow                              # detector (downloads yolo11n.pt)
python -m pytest -m integration                       # needs Mosquitto on 127.0.0.1:1883
```

Simulate a device without hardware:

```powershell
python tools/fake_device.py --mac 0123456789ab --dir samples --interval 1
```

Add `--event` to publish one warning event, and `--no-frames` to act like a device
with streaming off (status only).

## Run with Docker Compose

`compose.yaml` runs Mosquitto, the master service, and the dashboard. It publishes no
host ports. `mosquitto` and `web` join the external network `cloudflared-net`, so a
cloudflared container on that network can route:

| Hostname | Service |
|---|---|
| `mqtt.<domain>` (devices: `wss://mqtt.<domain>:443/mqtt`) | `http://mosquitto:9001` |
| dashboard hostname | `http://web:8000` |

```sh
docker network create cloudflared-net   # once, if cloudflared has not created it
docker compose up -d --build
docker compose exec master python -m master.cli status <mac>
```

The image uses CPU-only PyTorch and has `yolo11n.pt` built in. Events and snapshots
live in the `events` volume, and broker persistence in `mosquitto-data`. Optional
values (`MQTT_HOST`, `MQTT_PORT`, `DEVICE`, `PEDESTRIAN_CONF_THRESHOLD`, `INFERENCE_HISTORY`, `MQTT_USER`,
`MQTT_PASS`) are read from the environment or `.env` next to `compose.yaml`.

## Expose the broker with Cloudflare Tunnel

Devices on LTE are behind carrier NAT, so they connect out to a public hostname.
Cloudflare Tunnel forwards HTTP/WebSocket only, so devices use MQTT over WSS.

```powershell
cloudflared tunnel login
cloudflared tunnel create pedestrian
cloudflared tunnel route dns pedestrian mqtt.<domain>
```

Copy `deploy/cloudflared.example.yml` to `%USERPROFILE%\.cloudflared\config.yml`,
fill in the tunnel ID and hostname, then:

```powershell
cloudflared tunnel run pedestrian      # foreground, for testing
cloudflared service install            # run as a Windows service
```

Device URI: `wss://mqtt.<domain>:443/mqtt`.

## Security warning

`deploy/mosquitto.conf` allows anonymous access. Through the tunnel, **anyone who
knows the hostname can read every camera image and send alert, stop, or reboot
commands to any device.** Use this only for bench development.

### Enabling MQTT auth

1. Create users (device username = its MAC):
   ```powershell
   & "C:\Program Files\mosquitto\mosquitto_passwd.exe" -c deploy\passwd server
   & "C:\Program Files\mosquitto\mosquitto_passwd.exe" deploy\passwd a1b2c3d4e5f6
   ```
2. Create `deploy\acl`:
   ```
   user server
   topic readwrite #

   pattern readwrite %u/#
   ```
3. In `deploy/mosquitto.conf`, replace `allow_anonymous true` with:
   ```
   allow_anonymous false
   password_file deploy\passwd
   acl_file deploy\acl
   ```
4. Set `MQTT_USER=server` and `MQTT_PASS=...` in `.env`.
5. Set `MQTT_USERNAME` (the MAC) and `MQTT_PASSWORD` in the device firmware's menuconfig.
