# Pedestrian alert — master server

Receives camera frames from edge devices over MQTT, detects people with YOLO11n,
and sends `{mac}/alert` when a person stays in view for `ALERT_DWELL_SECONDS`.
Design: `docs/superpowers/specs/2026-09-29-pedestrian-alert-design.md`.

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

## Dashboard

Shows recent inferences (thumbnail, confidence, pedestrian or not, dwell progress,
alert) and recent alerts. Runs as its own read-only process next to `master.app`:

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
`frame_size` (QVGA, VGA, SVGA, XGA, HD, SXGA, UXGA), `volume` (0–100).

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
