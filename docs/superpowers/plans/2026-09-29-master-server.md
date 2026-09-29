# Master Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python master server that receives JPEG frames from edge devices over MQTT, runs YOLO11n person detection, applies the dwell rule, and publishes `{mac}/alert`; plus a CLI for manual commands, a fake device for testing, and Mosquitto/cloudflared deployment config.

**Architecture:** A single process with a paho-mqtt client (network thread) that parses messages into per-device latest-frame slots, and one worker thread that runs detection → dwell logic → alert publish → event log. Pure modules (`protocol`, `logic`) hold all rules and are unit-tested; I/O modules (`detector`, `events`, `app`, `cli`) are thin and injected so `app` is testable with fakes.

**Tech Stack:** Python 3.11+, paho-mqtt ≥ 2.0, ultralytics (YOLO11n), pydantic-settings ≥ 2, Pillow, SQLite (stdlib), pytest. Mosquitto 2.x, cloudflared.

**Spec:** `docs/superpowers/specs/2026-09-29-pedestrian-alert-design.md`

## Global Constraints

- Python ≥ 3.11; paho-mqtt ≥ 2.0 using `mqtt.CallbackAPIVersion.VERSION2`.
- Device ID `{mac}` = lowercase hex, no separators, e.g. `a1b2c3d4e5f6`. Topics are exactly two levels: `{mac}/{kind}`.
- Image payload = 8-byte `uint64` little-endian `capture_ms` + JPEG bytes. `capture_ms == 0` means "device clock not synced; use server receive time".
- QoS: `image` 0; `alert`, `cmd`, `config`, `status`, `online` 1. `config`, `status`, `online` are retained; `alert` and `cmd` are not.
- `alert` payload: `{"clip":"alert","repeat":N}`, `1 ≤ N ≤ 10`.
- `cmd` payload: `{"action": one of "start","stop","reboot","status"}`.
- `config` fields: `interval_ms` int, `jpeg_quality` int 0–63, `frame_size` one of `QVGA, VGA, SVGA, XGA, HD, SXGA, UXGA`, `volume` int 0–100. Defaults `{"interval_ms":1000,"jpeg_quality":12,"frame_size":"VGA","volume":80}`.
- `.env` keys and defaults: `MQTT_HOST=127.0.0.1`, `MQTT_PORT=1883`, `MQTT_USER=`, `MQTT_PASS=`, `MODEL_PATH=yolo11n.pt`, `DEVICE=cpu`, `PEDESTRIAN_CONF_THRESHOLD=0.6`, `ALERT_DWELL_SECONDS=5`, `MAX_GAP_SECONDS=3`, `ALERT_COOLDOWN_SECONDS=30`, `EVENTS_DIR=./events`.
- Blank `MQTT_USER` and `MQTT_PASS` → connect without credentials.
- Mosquitto v1 config: `allow_anonymous true`, both listeners bound to `127.0.0.1`.
- All commands run from `server/` with the venv active unless stated otherwise. Platform is Windows (PowerShell); paths use `\` in shell commands.

## Review Focus

1. **Short or empty image payload** (≤ 8 bytes, e.g. a firmware bug publishing only the header): expect a warning log and the frame dropped, no crash — pinned in Task 2 (`parse_image`) and Task 6 (`on_message`).
2. **Device clock syncs mid-stream** (`capture_ms` switches from 0 to real epoch): device and server clocks differ, so new timestamps may be "older" than the last one and be dropped as out-of-order forever. Expect dwell state for that device to reset when the timestamp source changes — pinned in Task 6.
3. **Typos or out-of-range values in `cli config`** (`volum=50`, `volume=150`, `frame_size=vga`): expect a clear error and nothing published, because a retained bad config would be re-delivered to the device on every reconnect — pinned in Task 2 and Task 7.
4. **Event storage failure** (disk full, DB locked): expect the alert still published — pinned in Task 6.
5. **Unexpected topics** (`foo`, `a/b/image`, `/image`): expect them ignored with a warning — pinned in Task 2 and Task 6.

---

## File Structure

```
.gitignore                         # repo root
server/
  pyproject.toml                   # package + deps + pytest config
  .env.example                     # documented defaults
  README.md                        # setup, run, deploy
  master/
    __init__.py
    settings.py                    # Settings (pydantic-settings)
    protocol.py                    # topics, image header, payloads, config validation
    logic.py                       # DwellLogic, Alert
    detector.py                    # Detector (YOLO11n)
    events.py                      # EventStore (SQLite + snapshots)
    app.py                         # FrameSlots, MasterApp, connect(), main()
    cli.py                         # manual commands
  tools/
    fake_device.py                 # publishes a folder of JPEGs as a device
  deploy/
    mosquitto.conf
    cloudflared.example.yml
  tests/
    test_settings.py
    test_protocol.py
    test_logic.py
    test_detector.py
    test_events.py
    test_app.py
    test_cli.py
    test_integration.py
```

---

### Task 1: Repository scaffold and settings

**Files:**
- Create: `.gitignore`
- Create: `server/pyproject.toml`
- Create: `server/.env.example`
- Create: `server/master/__init__.py`
- Create: `server/master/settings.py`
- Test: `server/tests/test_settings.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `master.settings.Settings` with fields `mqtt_host: str`, `mqtt_port: int`, `mqtt_user: str`, `mqtt_pass: str`, `model_path: str`, `device: str`, `pedestrian_conf_threshold: float`, `alert_dwell_seconds: float`, `max_gap_seconds: float`, `alert_cooldown_seconds: float`, `events_dir: pathlib.Path`.

- [ ] **Step 1: Initialize git and ignore file**

Run from `D:\pedestrian_classification`:
```powershell
git init
```

Create `.gitignore`:
```gitignore
# Python
.venv/
__pycache__/
*.egg-info/
.pytest_cache/

# Server runtime
server/.env
server/events/
*.pt

# Firmware
firmware/build/
firmware/sdkconfig
firmware/sdkconfig.old
firmware/managed_components/
```

- [ ] **Step 2: Create `server/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "pedestrian-master"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "paho-mqtt>=2.0",
    "ultralytics>=8.3",
    "pydantic-settings>=2.0",
    "pillow>=10",
    "numpy",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
pedestrian-master = "master.app:main"

[tool.setuptools.packages.find]
include = ["master*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: loads the YOLO model (downloads yolo11n.pt on first run)",
    "integration: needs Mosquitto listening on 127.0.0.1:1883",
]
```

Create empty `server/master/__init__.py`.

- [ ] **Step 3: Create venv and install**

```powershell
cd server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```
Expected: install finishes without errors.

- [ ] **Step 4: Write the failing test**

`server/tests/test_settings.py`:
```python
from pathlib import Path

from master.settings import Settings


def test_defaults_without_env_file(monkeypatch):
    for key in ("MQTT_USER", "MQTT_PASS", "ALERT_DWELL_SECONDS"):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.mqtt_host == "127.0.0.1"
    assert s.mqtt_port == 1883
    assert s.mqtt_user == ""
    assert s.mqtt_pass == ""
    assert s.model_path == "yolo11n.pt"
    assert s.device == "cpu"
    assert s.pedestrian_conf_threshold == 0.6
    assert s.alert_dwell_seconds == 5
    assert s.max_gap_seconds == 3
    assert s.alert_cooldown_seconds == 30
    assert s.events_dir == Path("./events")


def test_reads_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ALERT_DWELL_SECONDS=8\nMQTT_USER=server\nMQTT_PASS=\n", encoding="utf-8")
    s = Settings(_env_file=env)
    assert s.alert_dwell_seconds == 8
    assert s.mqtt_user == "server"
    assert s.mqtt_pass == ""
```

- [ ] **Step 5: Run test to verify it fails**

Run: `python -m pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'master.settings'`

- [ ] **Step 6: Implement `server/master/settings.py`**

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server configuration, read from environment variables and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_pass: str = ""
    model_path: str = "yolo11n.pt"
    device: str = "cpu"
    pedestrian_conf_threshold: float = 0.6
    alert_dwell_seconds: float = 5.0
    max_gap_seconds: float = 3.0
    alert_cooldown_seconds: float = 30.0
    events_dir: Path = Path("./events")
```

- [ ] **Step 7: Create `server/.env.example`**

```dotenv
# MQTT broker (the server connects locally, not through the tunnel)
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
# Leave both blank to connect without credentials
MQTT_USER=
MQTT_PASS=

# Detection
MODEL_PATH=yolo11n.pt
# cpu or cuda:0
DEVICE=cpu
# A frame is "pedestrian" when the best person score is >= this
PEDESTRIAN_CONF_THRESHOLD=0.6

# Alert rule
# Continuous pedestrian time (seconds) before an alert
ALERT_DWELL_SECONDS=5
# No pedestrian frame for longer than this resets the timer
MAX_GAP_SECONDS=3
# Minimum seconds between alerts for the same device
ALERT_COOLDOWN_SECONDS=30

# Alert log (SQLite) and snapshots
EVENTS_DIR=./events
```

- [ ] **Step 8: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py -v`
Expected: 2 passed.

- [ ] **Step 9: Commit**

```powershell
cd ..
git add .gitignore server/pyproject.toml server/.env.example server/master/__init__.py server/master/settings.py server/tests/test_settings.py
git commit -m "feat(server): scaffold package and settings"
```

---

### Task 2: Protocol module

**Files:**
- Create: `server/master/protocol.py`
- Test: `server/tests/test_protocol.py`

**Interfaces:**
- Consumes: nothing.
- Produces (`master.protocol`):
  - `class ProtocolError(ValueError)`
  - `HEADER_SIZE: int` (= 8)
  - `FRAME_SIZES: tuple[str, ...]`, `ACTIONS: tuple[str, ...]`, `DEFAULT_CONFIG: dict`
  - `topic(mac: str, kind: str) -> str`
  - `parse_topic(t: str) -> tuple[str, str] | None`
  - `pack_image(capture_ms: int, jpeg: bytes) -> bytes`
  - `parse_image(payload: bytes) -> tuple[int, bytes]` (raises `ProtocolError`)
  - `alert_payload(repeat: int = 1) -> bytes` (raises `ProtocolError`)
  - `cmd_payload(action: str) -> bytes` (raises `ProtocolError`)
  - `validate_config(cfg: dict) -> dict` (raises `ProtocolError`)
  - `parse_config_args(args: list[str]) -> dict` (raises `ProtocolError`)
  - `merge_config(current: dict, updates: dict) -> dict` (raises `ProtocolError`)

- [ ] **Step 1: Write the failing tests**

`server/tests/test_protocol.py`:
```python
import json
import struct

import pytest

from master import protocol as p


def test_topic_builds_two_levels():
    assert p.topic("a1b2c3d4e5f6", "alert") == "a1b2c3d4e5f6/alert"


@pytest.mark.parametrize(
    "t, expected",
    [
        ("a1b2c3d4e5f6/image", ("a1b2c3d4e5f6", "image")),
        ("a1b2c3d4e5f6/online", ("a1b2c3d4e5f6", "online")),
        ("foo", None),
        ("a/b/image", None),
        ("/image", None),
        ("a1b2c3d4e5f6/", None),
    ],
)
def test_parse_topic(t, expected):
    assert p.parse_topic(t) == expected


def test_image_round_trip():
    payload = p.pack_image(1_727_600_000_123, b"\xff\xd8jpeg")
    assert payload[:8] == struct.pack("<Q", 1_727_600_000_123)
    assert p.parse_image(payload) == (1_727_600_000_123, b"\xff\xd8jpeg")


@pytest.mark.parametrize("payload", [b"", b"\x00" * 7, b"\x00" * 8])
def test_parse_image_rejects_short_payload(payload):
    with pytest.raises(p.ProtocolError):
        p.parse_image(payload)


def test_alert_payload():
    assert json.loads(p.alert_payload()) == {"clip": "alert", "repeat": 1}
    assert json.loads(p.alert_payload(3)) == {"clip": "alert", "repeat": 3}


@pytest.mark.parametrize("repeat", [0, 11])
def test_alert_payload_rejects_bad_repeat(repeat):
    with pytest.raises(p.ProtocolError):
        p.alert_payload(repeat)


def test_cmd_payload():
    for action in ("start", "stop", "reboot", "status"):
        assert json.loads(p.cmd_payload(action)) == {"action": action}
    with pytest.raises(p.ProtocolError):
        p.cmd_payload("explode")


def test_validate_config_accepts_defaults():
    assert p.validate_config(dict(p.DEFAULT_CONFIG)) == p.DEFAULT_CONFIG


@pytest.mark.parametrize(
    "cfg",
    [
        {"volum": 50},
        {"volume": 150},
        {"volume": -1},
        {"jpeg_quality": 64},
        {"interval_ms": 50},
        {"frame_size": "vga"},
        {"volume": "loud"},
        {"volume": True},
    ],
)
def test_validate_config_rejects(cfg):
    with pytest.raises(p.ProtocolError):
        p.validate_config(cfg)


def test_parse_config_args_converts_types():
    assert p.parse_config_args(["interval_ms=500", "frame_size=SVGA", "volume=60"]) == {
        "interval_ms": 500,
        "frame_size": "SVGA",
        "volume": 60,
    }


@pytest.mark.parametrize("args", [["volume"], ["volume=abc"], ["=5"], ["volum=5"]])
def test_parse_config_args_rejects(args):
    with pytest.raises(p.ProtocolError):
        p.parse_config_args(args)


def test_merge_config_overrides_only_given_fields():
    merged = p.merge_config(p.DEFAULT_CONFIG, {"volume": 60})
    assert merged == {**p.DEFAULT_CONFIG, "volume": 60}


def test_merge_config_rejects_bad_update():
    with pytest.raises(p.ProtocolError):
        p.merge_config(p.DEFAULT_CONFIG, {"volume": 150})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_protocol.py -v`
Expected: FAIL with `ImportError: cannot import name 'protocol' from 'master'`

- [ ] **Step 3: Implement `server/master/protocol.py`**

```python
"""MQTT topics and payload formats shared by the server, CLI, and fake device."""

import json
import struct

HEADER = struct.Struct("<Q")
HEADER_SIZE = HEADER.size

FRAME_SIZES = ("QVGA", "VGA", "SVGA", "XGA", "HD", "SXGA", "UXGA")
ACTIONS = ("start", "stop", "reboot", "status")
DEFAULT_CONFIG = {"interval_ms": 1000, "jpeg_quality": 12, "frame_size": "VGA", "volume": 80}

# Integer fields -> (min, max), inclusive. frame_size is checked separately.
_INT_FIELDS = {
    "interval_ms": (100, 3_600_000),
    "jpeg_quality": (0, 63),
    "volume": (0, 100),
}


class ProtocolError(ValueError):
    """A payload, topic, or config value does not match the protocol."""


def topic(mac: str, kind: str) -> str:
    return f"{mac}/{kind}"


def parse_topic(t: str) -> tuple[str, str] | None:
    """Split `{mac}/{kind}`. Returns None for any other shape."""
    parts = t.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def pack_image(capture_ms: int, jpeg: bytes) -> bytes:
    return HEADER.pack(capture_ms) + jpeg


def parse_image(payload: bytes) -> tuple[int, bytes]:
    """Return (capture_ms, jpeg). capture_ms is 0 when the device clock is not synced."""
    if len(payload) <= HEADER_SIZE:
        raise ProtocolError(f"image payload too short ({len(payload)} bytes)")
    (capture_ms,) = HEADER.unpack_from(payload)
    return capture_ms, payload[HEADER_SIZE:]


def alert_payload(repeat: int = 1) -> bytes:
    if not 1 <= repeat <= 10:
        raise ProtocolError(f"repeat must be 1-10, got {repeat}")
    return json.dumps({"clip": "alert", "repeat": repeat}).encode()


def cmd_payload(action: str) -> bytes:
    if action not in ACTIONS:
        raise ProtocolError(f"unknown action {action!r}; expected one of {ACTIONS}")
    return json.dumps({"action": action}).encode()


def validate_config(cfg: dict) -> dict:
    """Check every field in `cfg`. Unknown fields are rejected to catch typos."""
    for key, value in cfg.items():
        if key == "frame_size":
            if value not in FRAME_SIZES:
                raise ProtocolError(f"frame_size must be one of {FRAME_SIZES}, got {value!r}")
        elif key in _INT_FIELDS:
            lo, hi = _INT_FIELDS[key]
            if not isinstance(value, int) or isinstance(value, bool):
                raise ProtocolError(f"{key} must be an integer, got {value!r}")
            if not lo <= value <= hi:
                raise ProtocolError(f"{key} must be {lo}-{hi}, got {value}")
        else:
            raise ProtocolError(f"unknown config field {key!r}")
    return cfg


def parse_config_args(args: list[str]) -> dict:
    """Turn ["volume=60", "frame_size=SVGA"] into a validated dict."""
    out: dict = {}
    for arg in args:
        key, sep, raw = arg.partition("=")
        if not sep or not key:
            raise ProtocolError(f"expected key=value, got {arg!r}")
        if key in _INT_FIELDS:
            try:
                out[key] = int(raw)
            except ValueError:
                raise ProtocolError(f"{key} must be an integer, got {raw!r}") from None
        else:
            out[key] = raw
    return validate_config(out)


def merge_config(current: dict, updates: dict) -> dict:
    validate_config(updates)
    return {**current, **updates}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_protocol.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```powershell
cd ..
git add server/master/protocol.py server/tests/test_protocol.py
git commit -m "feat(server): add MQTT protocol helpers"
```

---

### Task 3: Dwell logic

**Files:**
- Create: `server/master/logic.py`
- Test: `server/tests/test_logic.py`

**Interfaces:**
- Consumes: nothing.
- Produces (`master.logic`):
  - `@dataclass(frozen=True) class Alert: first_seen: float; ts: float; max_conf: float` with property `dwell_s -> float`
  - `class DwellLogic(threshold: float, dwell_s: float, max_gap_s: float, cooldown_s: float)`
    - `update(mac: str, ts: float, conf: float) -> Alert | None`
    - `reset(mac: str) -> None`

Note: the spec describes `update(ts, conf) -> bool`. This plan returns `Alert | None` (truthy/falsy the same way) because the event log needs `first_seen` and `max_conf`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_logic.py`:
```python
from master.logic import Alert, DwellLogic

MAC = "a1b2c3d4e5f6"
POS, NEG = 0.9, 0.1


def make():
    return DwellLogic(threshold=0.6, dwell_s=5, max_gap_s=3, cooldown_s=30)


def feed(logic, frames, mac=MAC):
    """frames: list of (ts, conf). Returns list of ts at which an alert fired."""
    return [ts for ts, conf in frames if logic.update(mac, ts, conf)]


def test_alert_when_dwell_reached():
    logic = make()
    assert feed(logic, [(t, POS) for t in range(0, 6)]) == [5]


def test_no_alert_before_dwell():
    logic = make()
    assert feed(logic, [(t, POS) for t in range(0, 5)]) == []


def test_conf_equal_to_threshold_counts_as_positive():
    logic = make()
    assert feed(logic, [(t, 0.6) for t in range(0, 6)]) == [5]


def test_gap_longer_than_max_gap_resets_timer():
    logic = make()
    frames = [(0, POS), (1, POS), (2, POS)] + [(t, POS) for t in range(6, 12)]
    assert feed(logic, frames) == [11]


def test_single_negative_frame_does_not_reset():
    logic = make()
    frames = [(0, POS), (1, POS), (2, POS), (3, NEG), (4, POS), (5, POS)]
    assert feed(logic, frames) == [5]


def test_negatives_longer_than_max_gap_reset_timer():
    logic = make()
    frames = [(0, POS), (1, POS)] + [(t, NEG) for t in range(2, 6)] + [(t, POS) for t in range(6, 12)]
    assert feed(logic, frames) == [11]


def test_cooldown_suppresses_repeat_alerts():
    logic = make()
    assert feed(logic, [(t, POS) for t in range(0, 41)]) == [5, 35]


def test_out_of_order_and_duplicate_timestamps_ignored():
    logic = make()
    frames = [(t, POS) for t in range(0, 5)] + [(3, POS), (4, POS), (5, POS)]
    assert feed(logic, frames) == [5]


def test_reset_clears_state():
    logic = make()
    feed(logic, [(t, POS) for t in range(0, 5)])
    logic.reset(MAC)
    assert feed(logic, [(t, POS) for t in range(5, 11)]) == [10]


def test_reset_unknown_device_is_noop():
    make().reset("000000000000")


def test_devices_are_independent():
    logic = make()
    for t in range(0, 6):
        a = logic.update("aaaaaaaaaaaa", t, POS)
        b = logic.update("bbbbbbbbbbbb", t, NEG)
        assert b is None
    assert a is not None


def test_alert_carries_dwell_and_max_conf():
    logic = make()
    alert = None
    for t, conf in [(10, 0.7), (11, 0.95), (12, 0.8), (13, 0.7), (14, 0.7), (15, 0.7)]:
        alert = logic.update(MAC, t, conf) or alert
    assert alert == Alert(first_seen=10, ts=15, max_conf=0.95)
    assert alert.dwell_s == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_logic.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'master.logic'`

- [ ] **Step 3: Implement `server/master/logic.py`**

```python
"""Dwell rule: alert when a device sees a pedestrian continuously for N seconds."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Alert:
    first_seen: float
    ts: float
    max_conf: float

    @property
    def dwell_s(self) -> float:
        return self.ts - self.first_seen


@dataclass
class _State:
    first_seen: float | None = None
    last_seen: float | None = None
    last_alert: float | None = None
    last_ts: float | None = None
    max_conf: float = 0.0


class DwellLogic:
    """Per-device dwell state machine. Pure: no I/O, no clock. Not thread-safe."""

    def __init__(self, threshold: float, dwell_s: float, max_gap_s: float, cooldown_s: float):
        self.threshold = threshold
        self.dwell_s = dwell_s
        self.max_gap_s = max_gap_s
        self.cooldown_s = cooldown_s
        self._states: dict[str, _State] = {}

    def update(self, mac: str, ts: float, conf: float) -> Alert | None:
        s = self._states.setdefault(mac, _State())

        if s.last_ts is not None and ts <= s.last_ts:
            return None
        s.last_ts = ts

        if s.last_seen is not None and ts - s.last_seen > self.max_gap_s:
            s.first_seen = None
            s.last_seen = None
            s.max_conf = 0.0

        if conf < self.threshold:
            return None

        if s.first_seen is None:
            s.first_seen = ts
        s.last_seen = ts
        s.max_conf = max(s.max_conf, conf)

        if ts - s.first_seen < self.dwell_s:
            return None
        if s.last_alert is not None and ts - s.last_alert < self.cooldown_s:
            return None
        s.last_alert = ts
        return Alert(first_seen=s.first_seen, ts=ts, max_conf=s.max_conf)

    def reset(self, mac: str) -> None:
        self._states.pop(mac, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_logic.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```powershell
cd ..
git add server/master/logic.py server/tests/test_logic.py
git commit -m "feat(server): add dwell alert logic"
```

---

### Task 4: Detector

**Files:**
- Create: `server/master/detector.py`
- Test: `server/tests/test_detector.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `master.detector.Detector(model_path: str, device: str)` with `person_confidence(jpeg: bytes) -> float` (highest `person` score in the frame, `0.0` if none; raises on undecodable JPEG).

- [ ] **Step 1: Write the failing tests**

`server/tests/test_detector.py`:
```python
import io

import pytest
from PIL import Image

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def detector():
    from master.detector import Detector

    return Detector("yolo11n.pt", "cpu")


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def test_person_image_scores_high(detector):
    from ultralytics.utils import ASSETS

    jpeg = _jpeg(Image.open(ASSETS / "bus.jpg").convert("RGB"))
    assert detector.person_confidence(jpeg) > 0.6


def test_empty_image_scores_low(detector):
    jpeg = _jpeg(Image.new("RGB", (640, 480), (128, 128, 128)))
    assert detector.person_confidence(jpeg) < 0.25


def test_garbage_bytes_raise(detector):
    with pytest.raises(Exception):
        detector.person_confidence(b"not a jpeg")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_detector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'master.detector'`

- [ ] **Step 3: Implement `server/master/detector.py`**

```python
"""YOLO person detector. The only module that imports ultralytics."""

import io

from PIL import Image

PERSON_CLASS = 0  # COCO


class Detector:
    def __init__(self, model_path: str, device: str):
        from ultralytics import YOLO

        self._model = YOLO(model_path)
        self._device = device

    def person_confidence(self, jpeg: bytes) -> float:
        """Highest person confidence in the frame, or 0.0 if no person is found."""
        img = Image.open(io.BytesIO(jpeg)).convert("RGB")
        result = self._model.predict(
            img, classes=[PERSON_CLASS], conf=0.05, device=self._device, verbose=False
        )[0]
        if result.boxes is None or len(result.boxes) == 0:
            return 0.0
        return float(result.boxes.conf.max())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_detector.py -v`
Expected: 3 passed. The first run downloads `yolo11n.pt` (≈ 5 MB) into `server/`.

- [ ] **Step 5: Commit**

```powershell
cd ..
git add server/master/detector.py server/tests/test_detector.py
git commit -m "feat(server): add YOLO11n person detector"
```

---

### Task 5: Event store

**Files:**
- Create: `server/master/events.py`
- Test: `server/tests/test_events.py`

**Interfaces:**
- Consumes: `master.logic.Alert`.
- Produces: `master.events.EventStore(root: pathlib.Path)` with `record(mac: str, alert: Alert, jpeg: bytes) -> pathlib.Path` (snapshot path), `recent(limit: int = 10) -> list[dict]`, `close() -> None`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_events.py`:
```python
from master.events import EventStore
from master.logic import Alert

MAC = "a1b2c3d4e5f6"


def test_record_writes_row_and_snapshot(tmp_path):
    store = EventStore(tmp_path / "events")
    alert = Alert(first_seen=1_727_600_000.0, ts=1_727_600_005.5, max_conf=0.91)

    path = store.record(MAC, alert, b"\xff\xd8jpeg")

    assert path == tmp_path / "events" / MAC / "1727600005500.jpg"
    assert path.read_bytes() == b"\xff\xd8jpeg"
    rows = store.recent()
    assert rows == [
        {
            "mac": MAC,
            "alert_ts": 1_727_600_005.5,
            "first_seen_ts": 1_727_600_000.0,
            "dwell_s": 5.5,
            "max_conf": 0.91,
            "snapshot": str(path),
        }
    ]
    store.close()


def test_recent_is_newest_first_and_limited(tmp_path):
    store = EventStore(tmp_path)
    for i in range(3):
        store.record(MAC, Alert(first_seen=i, ts=i + 5, max_conf=0.8), b"x")
    rows = store.recent(limit=2)
    assert [r["alert_ts"] for r in rows] == [7, 6]
    store.close()


def test_data_survives_reopen(tmp_path):
    store = EventStore(tmp_path)
    store.record(MAC, Alert(first_seen=0, ts=5, max_conf=0.8), b"x")
    store.close()
    store = EventStore(tmp_path)
    assert len(store.recent()) == 1
    store.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'master.events'`

- [ ] **Step 3: Implement `server/master/events.py`**

```python
"""Alert log: one SQLite row plus one JPEG snapshot per alert."""

import sqlite3
import threading
from pathlib import Path

from master.logic import Alert

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT NOT NULL,
    alert_ts REAL NOT NULL,
    first_seen_ts REAL NOT NULL,
    dwell_s REAL NOT NULL,
    max_conf REAL NOT NULL,
    snapshot TEXT NOT NULL
)
"""


class EventStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.root / "events.db", check_same_thread=False)
        self._db.execute(_SCHEMA)
        self._db.commit()

    def record(self, mac: str, alert: Alert, jpeg: bytes) -> Path:
        path = self.root / mac / f"{round(alert.ts * 1000)}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpeg)
        with self._lock:
            self._db.execute(
                "INSERT INTO events (mac, alert_ts, first_seen_ts, dwell_s, max_conf, snapshot)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (mac, alert.ts, alert.first_seen, alert.dwell_s, alert.max_conf, str(path)),
            )
            self._db.commit()
        return path

    def recent(self, limit: int = 10) -> list[dict]:
        with self._lock:
            cur = self._db.execute(
                "SELECT mac, alert_ts, first_seen_ts, dwell_s, max_conf, snapshot"
                " FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close(self) -> None:
        with self._lock:
            self._db.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_events.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```powershell
cd ..
git add server/master/events.py server/tests/test_events.py
git commit -m "feat(server): add SQLite alert event store"
```

---

### Task 6: Application wiring

**Files:**
- Create: `server/master/app.py`
- Test: `server/tests/test_app.py`

**Interfaces:**
- Consumes: `Settings` (Task 1); `protocol.parse_topic`, `protocol.parse_image`, `protocol.topic`, `protocol.alert_payload`, `protocol.ProtocolError` (Task 2); `DwellLogic`, `Alert` (Task 3); `Detector` (Task 4); `EventStore` (Task 5).
- Produces (`master.app`):
  - `class FrameSlots` with `put(mac: str, ts: float, jpeg: bytes) -> None`, `take_all(timeout: float | None) -> dict[str, tuple[float, bytes]]`
  - `Publish = Callable[[str, bytes, int, bool], None]` — `(topic, payload, qos, retain)`
  - `class MasterApp(detector, logic: DwellLogic, events, publish: Publish, clock: Callable[[], float] = time.time)` with `on_message(topic: str, payload: bytes) -> None`, `process(mac: str, ts: float, jpeg: bytes) -> None`, `process_pending(timeout: float | None = 0.5) -> None`, `run_worker(stop: threading.Event) -> None`, attribute `slots: FrameSlots`
  - `connect(app: MasterApp, host: str, port: int, user: str, password: str, client_id: str = "master") -> paho.mqtt.client.Client` — sets callbacks, starts the network loop, returns the client
  - `main() -> None`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_app.py`:
```python
import json

from master import protocol
from master.app import FrameSlots, MasterApp
from master.logic import DwellLogic

MAC = "a1b2c3d4e5f6"


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

    def record(self, mac, alert, jpeg):
        if self.error:
            raise self.error
        self.recorded.append((mac, alert, jpeg))


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def make_app(detector=None, events=None, clock=None):
    published = []
    app = MasterApp(
        detector=detector or FakeDetector(),
        logic=DwellLogic(threshold=0.6, dwell_s=5, max_gap_s=3, cooldown_s=30),
        events=events or FakeEvents(),
        publish=lambda t, p, q, r: published.append((t, p, q, r)),
        clock=clock or Clock(),
    )
    return app, published


def send_frames(app, mac, seconds, start_ms=1_727_600_000_000):
    for s in seconds:
        app.on_message(f"{mac}/image", protocol.pack_image(start_ms + s * 1000, b"jpeg"))
        app.process_pending(timeout=0)


def test_alert_published_after_dwell():
    app, published = make_app()
    send_frames(app, MAC, range(0, 6))
    assert published == [(f"{MAC}/alert", protocol.alert_payload(1), 1, False)]


def test_alert_recorded_in_events():
    events = FakeEvents()
    app, _ = make_app(events=events)
    send_frames(app, MAC, range(0, 6))
    assert len(events.recorded) == 1
    mac, alert, jpeg = events.recorded[0]
    assert mac == MAC and jpeg == b"jpeg" and alert.dwell_s == 5


def test_no_alert_for_negative_frames():
    app, published = make_app(detector=FakeDetector(conf=0.1))
    send_frames(app, MAC, range(0, 10))
    assert published == []


def test_short_payload_dropped():
    detector = FakeDetector()
    app, published = make_app(detector=detector)
    app.on_message(f"{MAC}/image", b"\x00" * 8)
    app.process_pending(timeout=0)
    assert detector.calls == 0 and published == []


def test_unexpected_topics_ignored():
    detector = FakeDetector()
    app, published = make_app(detector=detector)
    payload = protocol.pack_image(1, b"jpeg")
    for t in ("foo", "a/b/image", "/image"):
        app.on_message(t, payload)
    app.process_pending(timeout=0)
    assert detector.calls == 0 and published == []


def test_detector_error_does_not_crash():
    app, published = make_app(detector=FakeDetector(error=RuntimeError("boom")))
    send_frames(app, MAC, range(0, 6))
    assert published == []


def test_event_store_error_still_publishes_alert():
    app, published = make_app(events=FakeEvents(error=OSError("disk full")))
    send_frames(app, MAC, range(0, 6))
    assert len(published) == 1


def test_capture_ms_zero_uses_server_clock():
    clock = Clock(now=500.0)
    app, published = make_app(clock=clock)
    for i in range(6):
        clock.now = 500.0 + i
        app.on_message(f"{MAC}/image", protocol.pack_image(0, b"jpeg"))
        app.process_pending(timeout=0)
    assert len(published) == 1


def test_timestamp_source_change_resets_state():
    # Server clock is far ahead of the device clock. Without a reset, device
    # timestamps would look "older" and be ignored as out of order.
    clock = Clock(now=9_999_999_999.0)
    app, published = make_app(clock=clock)
    for i in range(3):
        clock.now += 1
        app.on_message(f"{MAC}/image", protocol.pack_image(0, b"jpeg"))
        app.process_pending(timeout=0)
    send_frames(app, MAC, range(0, 6))
    assert len(published) == 1


def test_offline_resets_state():
    app, published = make_app()
    send_frames(app, MAC, range(0, 4))
    app.on_message(f"{MAC}/online", b"0")
    send_frames(app, MAC, range(4, 9))
    assert published == []
    send_frames(app, MAC, [9])
    assert len(published) == 1


def test_status_message_is_accepted():
    app, published = make_app()
    app.on_message(f"{MAC}/status", json.dumps({"rssi": -70}).encode())
    app.on_message(f"{MAC}/status", b"not json")
    assert published == []


def test_frame_slots_keep_only_latest():
    slots = FrameSlots()
    slots.put(MAC, 1.0, b"old")
    slots.put(MAC, 2.0, b"new")
    slots.put("bbbbbbbbbbbb", 1.0, b"other")
    assert slots.take_all(timeout=0) == {MAC: (2.0, b"new"), "bbbbbbbbbbbb": (1.0, b"other")}
    assert slots.take_all(timeout=0) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'master.app'`

- [ ] **Step 3: Implement `server/master/app.py`**

```python
"""Master service: MQTT in, detection + dwell logic, alerts out."""

import logging
import threading
import time
from collections.abc import Callable

import paho.mqtt.client as mqtt

from master import protocol
from master.logic import DwellLogic

log = logging.getLogger("master")

Publish = Callable[[str, bytes, int, bool], None]  # (topic, payload, qos, retain)


class FrameSlots:
    """Latest unprocessed frame per device. A new frame overwrites the old one."""

    def __init__(self):
        self._slots: dict[str, tuple[float, bytes]] = {}
        self._cond = threading.Condition()

    def put(self, mac: str, ts: float, jpeg: bytes) -> None:
        with self._cond:
            self._slots[mac] = (ts, jpeg)
            self._cond.notify()

    def take_all(self, timeout: float | None) -> dict[str, tuple[float, bytes]]:
        with self._cond:
            if not self._slots:
                self._cond.wait(timeout)
            items, self._slots = self._slots, {}
            return items


class MasterApp:
    def __init__(self, detector, logic: DwellLogic, events, publish: Publish,
                 clock: Callable[[], float] = time.time):
        self.detector = detector
        self.logic = logic
        self.events = events
        self.publish = publish
        self.clock = clock
        self.slots = FrameSlots()
        self._lock = threading.Lock()  # guards logic and _ts_source across threads
        self._ts_source: dict[str, str] = {}  # mac -> "device" | "server"

    # Called on the MQTT network thread.
    def on_message(self, topic: str, payload: bytes) -> None:
        parsed = protocol.parse_topic(topic)
        if parsed is None:
            log.warning("ignoring message on unexpected topic %r", topic)
            return
        mac, kind = parsed
        if kind == "image":
            self._on_image(mac, payload)
        elif kind == "online":
            self._on_online(mac, payload)
        elif kind == "status":
            log.info("%s status %s", mac, payload.decode("utf-8", "replace"))

    def _on_image(self, mac: str, payload: bytes) -> None:
        try:
            capture_ms, jpeg = protocol.parse_image(payload)
        except protocol.ProtocolError as e:
            log.warning("%s: dropping frame: %s", mac, e)
            return
        source = "device" if capture_ms else "server"
        ts = capture_ms / 1000 if capture_ms else self.clock()
        with self._lock:
            previous = self._ts_source.get(mac)
            if previous is not None and previous != source:
                log.info("%s: timestamp source %s -> %s, resetting dwell", mac, previous, source)
                self.logic.reset(mac)
            self._ts_source[mac] = source
        self.slots.put(mac, ts, jpeg)

    def _on_online(self, mac: str, payload: bytes) -> None:
        if payload == b"0":
            log.warning("%s offline", mac)
            with self._lock:
                self.logic.reset(mac)
                self._ts_source.pop(mac, None)
        else:
            log.info("%s online", mac)

    # Called on the worker thread.
    def process(self, mac: str, ts: float, jpeg: bytes) -> None:
        try:
            conf = self.detector.person_confidence(jpeg)
        except Exception:
            log.exception("%s: detection failed, dropping frame", mac)
            return
        with self._lock:
            alert = self.logic.update(mac, ts, conf)
        if alert is None:
            return
        log.info("%s ALERT dwell=%.1fs max_conf=%.2f", mac, alert.dwell_s, alert.max_conf)
        self.publish(protocol.topic(mac, "alert"), protocol.alert_payload(1), 1, False)
        try:
            self.events.record(mac, alert, jpeg)
        except Exception:
            log.exception("%s: failed to record event", mac)

    def process_pending(self, timeout: float | None = 0.5) -> None:
        for mac, (ts, jpeg) in self.slots.take_all(timeout).items():
            self.process(mac, ts, jpeg)

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
        c.subscribe([("+/image", 0), ("+/status", 1), ("+/online", 1)])

    def on_disconnect(c, userdata, flags, reason_code, properties):
        log.warning("MQTT disconnected: %s", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = lambda c, u, m: app.on_message(m.topic, m.payload)
    app.publish = lambda t, p, q, r: client.publish(t, p, qos=q, retain=r)
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
        logic=DwellLogic(s.pedestrian_conf_threshold, s.alert_dwell_seconds,
                         s.max_gap_seconds, s.alert_cooldown_seconds),
        events=EventStore(s.events_dir),
        publish=lambda t, p, q, r: None,  # replaced by connect()
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_app.py -v`
Expected: all passed.

- [ ] **Step 5: Run the full non-integration suite**

Run: `python -m pytest -m "not integration" -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```powershell
cd ..
git add server/master/app.py server/tests/test_app.py
git commit -m "feat(server): wire MQTT ingest, detection, and alerts"
```

---

### Task 7: CLI

**Files:**
- Create: `server/master/cli.py`
- Test: `server/tests/test_cli.py`

**Interfaces:**
- Consumes: `Settings` (Task 1); `protocol.topic`, `protocol.alert_payload`, `protocol.cmd_payload`, `protocol.parse_config_args`, `protocol.merge_config`, `protocol.DEFAULT_CONFIG`, `protocol.ProtocolError` (Task 2).
- Produces (`master.cli`):
  - `build_message(argv: list[str], current_config: dict | None = None) -> tuple[str, bytes, int, bool]` — pure; `(topic, payload, qos, retain)`
  - `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_cli.py`:
```python
import json

import pytest

from master import protocol
from master.cli import build_message

MAC = "a1b2c3d4e5f6"


def test_alert_default_repeat():
    assert build_message(["alert", MAC]) == (f"{MAC}/alert", protocol.alert_payload(1), 1, False)


def test_alert_with_repeat():
    t, payload, _, _ = build_message(["alert", MAC, "--repeat", "3"])
    assert json.loads(payload)["repeat"] == 3


@pytest.mark.parametrize("action", ["start", "stop", "reboot", "status"])
def test_commands(action):
    assert build_message([action, MAC]) == (f"{MAC}/cmd", protocol.cmd_payload(action), 1, False)


def test_config_merges_into_current_and_is_retained():
    current = {**protocol.DEFAULT_CONFIG, "volume": 30}
    t, payload, qos, retain = build_message(["config", MAC, "interval_ms=500"], current)
    assert (t, qos, retain) == (f"{MAC}/config", 1, True)
    assert json.loads(payload) == {**current, "interval_ms": 500}


def test_config_without_current_uses_defaults():
    _, payload, _, _ = build_message(["config", MAC, "volume=60"], None)
    assert json.loads(payload) == {**protocol.DEFAULT_CONFIG, "volume": 60}


@pytest.mark.parametrize("args", [["volum=50"], ["volume=150"], ["frame_size=vga"], []])
def test_config_rejects_bad_values(args):
    with pytest.raises(protocol.ProtocolError):
        build_message(["config", MAC, *args], None)


@pytest.mark.parametrize("mac", ["A1B2C3D4E5F6", "a1:b2:c3:d4:e5:f6", "xyz"])
def test_rejects_malformed_mac(mac):
    with pytest.raises(protocol.ProtocolError):
        build_message(["status", mac])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'master.cli'`

- [ ] **Step 3: Implement `server/master/cli.py`**

```python
"""Manual commands to devices.

    python -m master.cli alert  <mac> [--repeat N]
    python -m master.cli start|stop|reboot|status <mac>
    python -m master.cli config <mac> key=value [key=value ...]
"""

import argparse
import json
import re
import sys
import threading

import paho.mqtt.client as mqtt

from master import protocol
from master.settings import Settings

_MAC_RE = re.compile(r"^[0-9a-f]{12}$")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m master.cli")
    sub = ap.add_subparsers(dest="command", required=True)
    alert = sub.add_parser("alert", help="play the alert sound")
    alert.add_argument("mac")
    alert.add_argument("--repeat", type=int, default=1)
    for action in protocol.ACTIONS:
        sub.add_parser(action, help=f"send '{action}' command").add_argument("mac")
    config = sub.add_parser("config", help="merge fields into the device's retained config")
    config.add_argument("mac")
    config.add_argument("fields", nargs="*", metavar="key=value")
    return ap


def build_message(argv: list[str], current_config: dict | None = None) -> tuple[str, bytes, int, bool]:
    args = _parser().parse_args(argv)
    if not _MAC_RE.match(args.mac):
        raise protocol.ProtocolError(f"mac must be 12 lowercase hex digits, got {args.mac!r}")
    if args.command == "alert":
        return protocol.topic(args.mac, "alert"), protocol.alert_payload(args.repeat), 1, False
    if args.command == "config":
        if not args.fields:
            raise protocol.ProtocolError("config needs at least one key=value")
        updates = protocol.parse_config_args(args.fields)
        merged = protocol.merge_config(current_config or protocol.DEFAULT_CONFIG, updates)
        return protocol.topic(args.mac, "config"), json.dumps(merged).encode(), 1, True
    return protocol.topic(args.mac, "cmd"), protocol.cmd_payload(args.command), 1, False


def _fetch_retained_config(client: mqtt.Client, mac: str, timeout: float = 2.0) -> dict | None:
    """Read the retained {mac}/config, or None if there is none."""
    got = threading.Event()
    result: dict = {}

    def on_message(c, u, m):
        try:
            result["cfg"] = json.loads(m.payload)
        except ValueError:
            pass
        got.set()

    client.on_message = on_message
    client.subscribe(protocol.topic(mac, "config"), qos=1)
    got.wait(timeout)
    client.unsubscribe(protocol.topic(mac, "config"))
    return result.get("cfg")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    s = Settings()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="")
    if s.mqtt_user or s.mqtt_pass:
        client.username_pw_set(s.mqtt_user, s.mqtt_pass or None)
    client.connect(s.mqtt_host, s.mqtt_port, keepalive=30)
    client.loop_start()
    try:
        current = None
        if argv and argv[0] == "config" and len(argv) > 1:
            current = _fetch_retained_config(client, argv[1])
        try:
            t, payload, qos, retain = build_message(argv, current)
        except protocol.ProtocolError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        client.publish(t, payload, qos=qos, retain=retain).wait_for_publish(timeout=5)
        print(f"sent {t} {payload.decode()}")
        return 0
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```powershell
cd ..
git add server/master/cli.py server/tests/test_cli.py
git commit -m "feat(server): add CLI for device commands and config"
```

---

### Task 8: Broker config, fake device, and integration test

**Files:**
- Create: `server/deploy/mosquitto.conf`
- Create: `server/tools/fake_device.py`
- Test: `server/tests/test_integration.py`

**Interfaces:**
- Consumes: `protocol.pack_image`, `protocol.topic` (Task 2); `DwellLogic` (Task 3); `MasterApp`, `connect` (Task 6).
- Produces: `tools/fake_device.py` CLI: `python tools/fake_device.py --mac <mac> --dir <folder> [--interval 1.0] [--count 0] [--host 127.0.0.1] [--port 1883] [--no-timestamp]`.

- [ ] **Step 1: Create `server/deploy/mosquitto.conf`**

```conf
# Mosquitto config for the master PC. Neither listener is reachable from the LAN;
# devices reach port 9001 only through cloudflared.

# Plain MQTT for the master service and CLI
listener 1883 127.0.0.1

# MQTT over WebSocket, published by cloudflared as wss://mqtt.<domain>
listener 9001 127.0.0.1
protocol websockets

# v1: no authentication. Anyone who knows the public hostname can read images
# and send commands. To enable auth, see server/README.md "Enabling MQTT auth".
allow_anonymous true

persistence true
```

- [ ] **Step 2: Install and start Mosquitto with this config**

Install Mosquitto 2.x from https://mosquitto.org/download/ (Windows installer). Then, in a separate terminal from `server/`:
```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -c deploy\mosquitto.conf -v
```
Expected: log lines `Opening ipv4 listen socket on port 1883.` and `Opening websockets listen socket on port 9001.`

If the Mosquitto Windows service is already running on 1883, stop it first: `Stop-Service mosquitto`.

- [ ] **Step 3: Write the failing integration test**

`server/tests/test_integration.py`:
```python
import socket
import threading
import time

import paho.mqtt.client as mqtt
import pytest

from master import protocol
from master.app import MasterApp, connect
from master.logic import DwellLogic

pytestmark = pytest.mark.integration

HOST, PORT = "127.0.0.1", 1883
MAC = "0123456789ab"


def _broker_up() -> bool:
    try:
        socket.create_connection((HOST, PORT), timeout=1).close()
        return True
    except OSError:
        return False


class AlwaysPerson:
    def person_confidence(self, jpeg):
        return 0.9


class NoEvents:
    def record(self, mac, alert, jpeg):
        pass


@pytest.mark.skipif(not _broker_up(), reason="Mosquitto not running on 127.0.0.1:1883")
def test_alert_arrives_after_dwell_and_not_before():
    app = MasterApp(AlwaysPerson(), DwellLogic(0.6, 2.0, 3.0, 30.0), NoEvents(),
                    publish=lambda t, p, q, r: None)
    server = connect(app, HOST, PORT, "", "", client_id="master-test")
    stop = threading.Event()
    worker = threading.Thread(target=app.run_worker, args=(stop,), daemon=True)
    worker.start()

    alerts = []
    device = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MAC)
    device.on_message = lambda c, u, m: alerts.append(time.monotonic())
    device.connect(HOST, PORT)
    device.subscribe(protocol.topic(MAC, "alert"), qos=1)
    device.loop_start()
    time.sleep(1.0)  # let both clients finish subscribing

    try:
        start = time.monotonic()
        while time.monotonic() - start < 4.0:
            now_ms = int(time.time() * 1000)
            device.publish(protocol.topic(MAC, "image"), protocol.pack_image(now_ms, b"jpeg"), qos=0)
            time.sleep(0.5)
        time.sleep(0.5)
    finally:
        stop.set()
        device.loop_stop()
        device.disconnect()
        server.loop_stop()
        server.disconnect()

    assert len(alerts) == 1
    assert 1.8 <= alerts[0] - start <= 3.5
```

- [ ] **Step 4: Run the integration test**

Run: `python -m pytest tests/test_integration.py -v`
Expected: 1 passed (with Mosquitto running). If it reports `skipped`, Mosquitto is not listening on 1883 — go back to Step 2.

This test exercises code from Task 6 over a real broker, so it should pass on first run. If it fails, the failure points at `connect()` wiring (subscriptions, callback signature, publish replacement).

- [ ] **Step 5: Create `server/tools/fake_device.py`**

```python
"""Pretend to be an edge device: publish JPEGs from a folder, print alerts.

    python tools/fake_device.py --mac 0123456789ab --dir samples --interval 1
"""

import argparse
import itertools
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from master import protocol


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mac", required=True)
    ap.add_argument("--dir", required=True, type=Path, help="folder of .jpg files, sent in name order, looped")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between frames")
    ap.add_argument("--count", type=int, default=0, help="frames to send; 0 = forever")
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

    frames = itertools.cycle(files) if args.count == 0 else itertools.islice(itertools.cycle(files), args.count)
    try:
        for path in frames:
            ms = 0 if args.no_timestamp else int(time.time() * 1000)
            client.publish(protocol.topic(args.mac, "image"), protocol.pack_image(ms, path.read_bytes()), qos=0)
            print(f"-> {path.name}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(protocol.topic(args.mac, "online"), b"0", qos=1, retain=True).wait_for_publish(2)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Manual end-to-end check with the real detector**

```powershell
mkdir samples
python -c "from ultralytics.utils import ASSETS; import shutil; shutil.copy(ASSETS / 'bus.jpg', 'samples/bus.jpg')"
```
Terminal A: `python -m master.app`
Terminal B: `python tools/fake_device.py --mac 0123456789ab --dir samples --interval 1 --count 8`

Expected: Terminal A logs `0123456789ab ALERT dwell=5.0s ...` about 5 s after the first frame; Terminal B prints `<- 0123456789ab/alert {"clip": "alert", "repeat": 1}`; `events/0123456789ab/*.jpg` exists.

Then check the CLI (Terminal B):
```powershell
python -m master.cli config 0123456789ab volume=60
python -m master.cli config 0123456789ab interval_ms=500
python -m master.cli config 0123456789ab volume=150
```
Expected: first two print `sent 0123456789ab/config {...}`, and the second output still contains `"volume": 60` (merge read the retained config). The third prints `error: volume must be 0-100, got 150` and exits 2.

Clean up the retained test config: `& "C:\Program Files\mosquitto\mosquitto_pub.exe" -t 0123456789ab/config -r -n`

- [ ] **Step 7: Commit**

```powershell
cd ..
git add server/deploy/mosquitto.conf server/tools/fake_device.py server/tests/test_integration.py
git commit -m "feat(server): add broker config, fake device, integration test"
```

---

### Task 9: Tunnel config and README

**Files:**
- Create: `server/deploy/cloudflared.example.yml`
- Create: `server/README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: operator documentation.

- [ ] **Step 1: Create `server/deploy/cloudflared.example.yml`**

```yaml
# Copy to %USERPROFILE%\.cloudflared\config.yml and fill in the tunnel ID and hostname.
# Devices connect to wss://mqtt.<domain>:443/mqtt
tunnel: <TUNNEL_ID>
credentials-file: C:\Users\<you>\.cloudflared\<TUNNEL_ID>.json
ingress:
  - hostname: mqtt.<domain>
    service: http://localhost:9001
  - service: http_status:404
```

- [ ] **Step 2: Create `server/README.md`**

````markdown
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
````

- [ ] **Step 3: Verify the whole suite**

Run (Mosquitto running): `python -m pytest -v`
Expected: all passed, none skipped.

- [ ] **Step 4: Commit**

```powershell
cd ..
git add server/deploy/cloudflared.example.yml server/README.md
git commit -m "docs(server): add tunnel config and README"
```
