# Inference Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record every inference the master makes (thumbnail + result) and serve a LAN web page that shows recent inferences and alerts, refreshing every 2 s.

**Architecture:** `master.app` gains a per-frame `record_inference` into a new `inferences` SQLite table (WAL mode) plus 320 px thumbnails, pruned to the newest N per device. A separate read-only FastAPI process, `master.web`, serves a JSON API over that DB, the thumbnails and snapshots, and a static HTML/JS page that polls the API.

**Tech Stack:** Python 3.11+ (venv has 3.12), SQLite (stdlib), Pillow, FastAPI, uvicorn, httpx (tests), plain HTML/CSS/JS.

**Spec:** `docs/superpowers/specs/2026-10-06-inference-dashboard-design.md`

## Global Constraints

- Work in `server/`; run commands from `server/` with `.venv/Scripts/python` (Windows, Git Bash).
- `master.web` never writes: it opens `file:<EVENTS_DIR>/events.db?mode=ro` (URI mode) per request.
- A failure in inference recording or in the web process never blocks, delays, or stops alerts.
- New `.env` keys and defaults: `INFERENCE_HISTORY=200`, `WEB_HOST=0.0.0.0`, `WEB_PORT=8000`.
- Thumbnails: 320 px wide max, aspect kept, never upscaled, JPEG quality 70, at `EVENTS_DIR/thumbs/<mac>/<round(ts*1000)>.jpg`; stored in the DB as a path relative to `EVENTS_DIR` with `/` separators.
- New alert snapshots are stored relative to `EVENTS_DIR` (`<mac>/<ms>.jpg`); readers accept old absolute paths and serve only files inside `EVENTS_DIR`.
- API `limit` clamped to 1–500. Defaults: inferences 100, alerts 50.
- `/media/{path}` resolves under `EVENTS_DIR` only; anything else → 404.
- Missing DB file or missing table → list endpoints return `[]`, never 500.
- Page: no external CDN or network fonts; polls every 2 s; alerts every 10 s; at most 200 cards in the DOM; all device-provided text inserted with `textContent` (never `innerHTML`).

## Review Focus

1. **Dashboard started before the master has ever run** (no `events.db` yet): API returns empty lists and the page shows its empty state — pinned in Task 4 (`test_missing_db_returns_empty_lists`).
2. **Master writing while the dashboard reads** (open writer connection, WAL): reads succeed and see committed rows — pinned in Task 4 (`test_reads_while_store_is_open`).
3. **Corrupt or non-JPEG frame payload** reaching `record_inference`: it raises, the app logs it, the alert path is unaffected — pinned in Task 2 (`test_record_inference_rejects_garbage`) and Task 3 (`test_inference_record_failure_still_alerts`).
4. **Old alert rows with absolute snapshot paths** (written before this change): listed, with `snapshot_url` pointing inside `EVENTS_DIR` or `null` — pinned in Task 4 (`test_alert_snapshot_urls_old_and_new`).
5. **A device ID containing HTML** (anonymous broker: anyone can publish `<img onerror=...>/image`): the API returns it verbatim and the page renders it as text — pinned in Task 4 (`test_mac_returned_verbatim`) and the Task 5 `textContent` rule.

---

## File Structure

```
server/
  pyproject.toml                 # + fastapi, uvicorn; dev + httpx; package-data for static/
  .env.example                   # + INFERENCE_HISTORY, WEB_HOST, WEB_PORT
  README.md                      # + "Dashboard" section
  master/
    settings.py                  # + inference_history, web_host, web_port
    logic.py                     # + DwellLogic.current_dwell
    events.py                    # + WAL, inferences table, record_inference, relative snapshot paths
    app.py                       # process() records every inference; main() passes history
    web.py                       # NEW: create_app(settings), main()
    static/index.html            # NEW
    static/style.css             # NEW
    static/app.js                # NEW
  tests/
    test_settings.py             # + new defaults
    test_logic.py                # + current_dwell tests
    test_events.py               # snapshot path now relative; + record_inference tests
    test_app.py                  # FakeEvents.record_inference; + inference tests
    test_integration.py          # NoEvents.record_inference
    test_web.py                  # NEW
```

---

### Task 1: Settings and current dwell

**Files:**
- Modify: `server/master/settings.py`, `server/master/logic.py`, `server/.env.example`
- Test: `server/tests/test_settings.py`, `server/tests/test_logic.py`

**Interfaces:**
- Produces: `Settings.inference_history: int = 200`, `Settings.web_host: str = "0.0.0.0"`, `Settings.web_port: int = 8000`; `DwellLogic.current_dwell(mac: str) -> float`.

- [ ] **Step 1: Write failing tests**

Append to `server/tests/test_settings.py`:
```python


def test_dashboard_defaults():
    s = Settings(_env_file=None)
    assert s.inference_history == 200
    assert s.web_host == "0.0.0.0"
    assert s.web_port == 8000
```

Append to `server/tests/test_logic.py`:
```python


def test_current_dwell_unknown_device_is_zero():
    assert make().current_dwell("000000000000") == 0.0


def test_current_dwell_tracks_run():
    logic = make()
    feed(logic, [(0, POS), (1, POS), (2, POS)])
    assert logic.current_dwell(MAC) == 2.0


def test_current_dwell_negative_frame_keeps_run():
    logic = make()
    feed(logic, [(0, POS), (1, POS), (2, NEG)])
    assert logic.current_dwell(MAC) == 1.0


def test_current_dwell_restarts_after_gap():
    logic = make()
    feed(logic, [(0, POS), (1, POS), (7, POS)])
    assert logic.current_dwell(MAC) == 0.0
    feed(logic, [(8, POS)])
    assert logic.current_dwell(MAC) == 1.0


def test_current_dwell_zero_after_reset():
    logic = make()
    feed(logic, [(0, POS), (1, POS)])
    logic.reset(MAC)
    assert logic.current_dwell(MAC) == 0.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_settings.py tests/test_logic.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'inference_history'` and `AttributeError: 'DwellLogic' object has no attribute 'current_dwell'`.

- [ ] **Step 3: Implement**

In `server/master/settings.py`, add after `events_dir`:
```python
    inference_history: int = 200
    web_host: str = "0.0.0.0"
    web_port: int = 8000
```

In `server/master/logic.py`, add after `reset`:
```python

    def current_dwell(self, mac: str) -> float:
        """Seconds the current pedestrian run has lasted (0.0 if there is none)."""
        s = self._states.get(mac)
        if s is None or s.first_seen is None or s.last_seen is None:
            return 0.0
        return s.last_seen - s.first_seen
```

Append to `server/.env.example`:
```dotenv

# Dashboard (python -m master.web)
# Inferences kept per device (thumbnails + rows)
INFERENCE_HISTORY=200
# 0.0.0.0 = reachable from the LAN; 127.0.0.1 = this PC only
WEB_HOST=0.0.0.0
WEB_PORT=8000
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_settings.py tests/test_logic.py -q`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add master/settings.py master/logic.py .env.example tests/test_settings.py tests/test_logic.py
git commit -m "feat(server): add dashboard settings and current dwell"
```

---

### Task 2: Event store records inferences

**Files:**
- Modify: `server/master/events.py`
- Test: `server/tests/test_events.py`

**Interfaces:**
- Consumes: `Alert` (existing).
- Produces: `EventStore(root: Path, history: int = 200)`; `EventStore.record_inference(mac: str, ts: float, conf: float, positive: bool, dwell_s: float, alerted: bool, jpeg: bytes) -> Path` (absolute thumbnail path); `EventStore.inferences(mac: str) -> list[dict]` (newest first; keys `id, mac, ts, conf, positive, dwell_s, alerted, thumb`) for tests and debugging; `THUMB_WIDTH = 320`. `record()` now stores `snapshot` as `<mac>/<ms>.jpg`.

- [ ] **Step 1: Write failing tests**

In `server/tests/test_events.py`, change the expected snapshot in `test_record_writes_row_and_snapshot` from `"snapshot": str(path),` to:
```python
            "snapshot": f"{MAC}/1727600005500.jpg",
```

Append:
```python
import io
import sqlite3

import pytest
from PIL import Image


def _jpeg(w, h, color=(200, 100, 50)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG")
    return buf.getvalue()


def test_record_inference_writes_thumbnail_and_row(tmp_path):
    store = EventStore(tmp_path)
    path = store.record_inference(MAC, 1_790_000_000.25, 0.91, True, 3.0, False, _jpeg(640, 480))

    assert path == tmp_path / "thumbs" / MAC / "1790000000250.jpg"
    with Image.open(path) as img:
        assert img.size == (320, 240)
    [row] = store.inferences(MAC)
    assert row["mac"] == MAC
    assert row["ts"] == 1_790_000_000.25
    assert row["conf"] == 0.91
    assert row["positive"] == 1
    assert row["dwell_s"] == 3.0
    assert row["alerted"] == 0
    assert row["thumb"] == f"thumbs/{MAC}/1790000000250.jpg"
    store.close()


def test_small_frames_are_not_upscaled(tmp_path):
    store = EventStore(tmp_path)
    path = store.record_inference(MAC, 1.0, 0.1, False, 0.0, False, _jpeg(160, 120))
    with Image.open(path) as img:
        assert img.size == (160, 120)
    store.close()


def test_pruning_keeps_newest_per_device(tmp_path):
    store = EventStore(tmp_path, history=3)
    paths = [store.record_inference(MAC, float(t), 0.5, False, 0.0, False, _jpeg(64, 48)) for t in range(5)]
    other = store.record_inference("bbbbbbbbbbbb", 1.0, 0.5, False, 0.0, False, _jpeg(64, 48))

    assert [r["ts"] for r in store.inferences(MAC)] == [4.0, 3.0, 2.0]
    assert not paths[0].exists() and not paths[1].exists()
    assert all(p.exists() for p in paths[2:])
    assert other.exists() and len(store.inferences("bbbbbbbbbbbb")) == 1
    store.close()


def test_record_inference_rejects_garbage(tmp_path):
    store = EventStore(tmp_path)
    with pytest.raises(Exception):
        store.record_inference(MAC, 1.0, 0.5, False, 0.0, False, b"not a jpeg")
    assert store.inferences(MAC) == []
    store.close()


def test_wal_mode_enabled(tmp_path):
    EventStore(tmp_path).close()
    con = sqlite3.connect(tmp_path / "events.db")
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    con.close()
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_events.py -q`
Expected: FAIL — snapshot path mismatch, `TypeError` on `history=`, `AttributeError: 'EventStore' object has no attribute 'record_inference'`, journal mode `delete`.

- [ ] **Step 3: Implement**

Replace `server/master/events.py` with:
```python
"""Event store: alerts (row + full snapshot) and recent inferences (row + thumbnail)."""

import io
import sqlite3
import threading
from pathlib import Path

from PIL import Image

from master.logic import Alert

THUMB_WIDTH = 320

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT NOT NULL,
    alert_ts REAL NOT NULL,
    first_seen_ts REAL NOT NULL,
    dwell_s REAL NOT NULL,
    max_conf REAL NOT NULL,
    snapshot TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT NOT NULL,
    ts REAL NOT NULL,
    conf REAL NOT NULL,
    positive INTEGER NOT NULL,
    dwell_s REAL NOT NULL,
    alerted INTEGER NOT NULL,
    thumb TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS inferences_mac_id ON inferences (mac, id);
"""


class EventStore:
    def __init__(self, root: Path, history: int = 200):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.history = history
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.root / "events.db", check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")  # lets master.web read while we write
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def record(self, mac: str, alert: Alert, jpeg: bytes) -> Path:
        rel = Path(mac) / f"{round(alert.ts * 1000)}.jpg"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpeg)
        with self._lock:
            self._db.execute(
                "INSERT INTO events (mac, alert_ts, first_seen_ts, dwell_s, max_conf, snapshot)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (mac, alert.ts, alert.first_seen, alert.dwell_s, alert.max_conf, rel.as_posix()),
            )
            self._db.commit()
        return path

    def record_inference(self, mac: str, ts: float, conf: float, positive: bool,
                         dwell_s: float, alerted: bool, jpeg: bytes) -> Path:
        """Save a thumbnail and a row, then prune this device to the newest `history` rows."""
        rel = Path("thumbs") / mac / f"{round(ts * 1000)}.jpg"
        path = self.root / rel
        img = Image.open(io.BytesIO(jpeg)).convert("RGB")
        if img.width > THUMB_WIDTH:
            height = max(1, round(img.height * THUMB_WIDTH / img.width))
            img = img.resize((THUMB_WIDTH, height))
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, format="JPEG", quality=70)

        with self._lock:
            self._db.execute(
                "INSERT INTO inferences (mac, ts, conf, positive, dwell_s, alerted, thumb)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mac, ts, conf, int(positive), dwell_s, int(alerted), rel.as_posix()),
            )
            old = self._db.execute(
                "SELECT id, thumb FROM inferences WHERE mac = ? ORDER BY id DESC LIMIT -1 OFFSET ?",
                (mac, self.history),
            ).fetchall()
            if old:
                self._db.executemany("DELETE FROM inferences WHERE id = ?", [(i,) for i, _ in old])
            self._db.commit()
        for _, thumb in old:
            (self.root / thumb).unlink(missing_ok=True)
        return path

    def inferences(self, mac: str) -> list[dict]:
        with self._lock:
            cur = self._db.execute(
                "SELECT id, mac, ts, conf, positive, dwell_s, alerted, thumb"
                " FROM inferences WHERE mac = ? ORDER BY id DESC",
                (mac,),
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

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

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_events.py -q`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add master/events.py tests/test_events.py
git commit -m "feat(server): record inferences with pruned thumbnails"
```

---

### Task 3: Master records every inference

**Files:**
- Modify: `server/master/app.py` (`MasterApp.process`, `main`)
- Test: `server/tests/test_app.py`, `server/tests/test_integration.py`

**Interfaces:**
- Consumes: `DwellLogic.current_dwell` (Task 1), `DwellLogic.threshold`, `EventStore.record_inference` and `EventStore(root, history=...)` (Task 2), `Settings.inference_history` (Task 1).

- [ ] **Step 1: Write failing tests**

In `server/tests/test_app.py`, replace the `FakeEvents` class with:
```python
class FakeEvents:
    def __init__(self, error=None, inference_error=None):
        self.error = error
        self.inference_error = inference_error
        self.recorded = []
        self.inferences = []

    def record(self, mac, alert, jpeg):
        if self.error:
            raise self.error
        self.recorded.append((mac, alert, jpeg))

    def record_inference(self, mac, ts, conf, positive, dwell_s, alerted, jpeg):
        if self.inference_error:
            raise self.inference_error
        self.inferences.append(
            {"mac": mac, "ts": ts, "conf": conf, "positive": positive,
             "dwell_s": dwell_s, "alerted": alerted, "jpeg": jpeg}
        )
```

Append to `server/tests/test_app.py`:
```python


def test_every_frame_recorded_as_inference():
    events = FakeEvents()
    app, _ = make_app(events=events)
    send_frames(app, MAC, range(0, 6))
    rows = events.inferences
    assert len(rows) == 6
    assert [r["dwell_s"] for r in rows] == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    assert [r["alerted"] for r in rows] == [False] * 5 + [True]
    assert all(r["positive"] and r["conf"] == 0.9 and r["jpeg"] == b"jpeg" for r in rows)


def test_negative_frames_recorded_as_negative():
    events = FakeEvents()
    app, _ = make_app(detector=FakeDetector(conf=0.1), events=events)
    send_frames(app, MAC, range(0, 3))
    assert [r["positive"] for r in events.inferences] == [False, False, False]
    assert all(r["dwell_s"] == 0.0 and not r["alerted"] for r in events.inferences)


def test_detector_failure_records_no_inference():
    events = FakeEvents()
    app, _ = make_app(detector=FakeDetector(error=RuntimeError("boom")), events=events)
    send_frames(app, MAC, range(0, 3))
    assert events.inferences == []


def test_inference_record_failure_still_alerts():
    events = FakeEvents(inference_error=OSError("disk full"))
    app, published = make_app(events=events)
    send_frames(app, MAC, range(0, 6))
    assert len(published) == 1
    assert len(events.recorded) == 1
```

In `server/tests/test_integration.py`, add to class `NoEvents`:
```python

    def record_inference(self, mac, ts, conf, positive, dwell_s, alerted, jpeg):
        pass
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -q`
Expected: FAIL — `test_every_frame_recorded_as_inference` and `test_negative_frames_recorded_as_negative` find `events.inferences == []`.

- [ ] **Step 3: Implement**

In `server/master/app.py`, replace the body of `MasterApp.process` with:
```python
    def process(self, mac: str, ts: float, jpeg: bytes) -> None:
        try:
            conf = self.detector.person_confidence(jpeg)
        except Exception:
            log.exception("%s: detection failed, dropping frame", mac)
            return
        with self._lock:
            alert = self.logic.update(mac, ts, conf)
            dwell = self.logic.current_dwell(mac)
        if alert is not None:
            log.info("%s ALERT dwell=%.1fs max_conf=%.2f", mac, alert.dwell_s, alert.max_conf)
            self.publish(protocol.topic(mac, "alert"), protocol.alert_payload(1), 1, False)
            try:
                self.events.record(mac, alert, jpeg)
            except Exception:
                log.exception("%s: failed to record event", mac)
        try:
            self.events.record_inference(mac, ts, conf, conf >= self.logic.threshold, dwell,
                                         alert is not None, jpeg)
        except Exception:
            log.exception("%s: failed to record inference", mac)
```

In `main()`, change `events=EventStore(s.events_dir),` to:
```python
        events=EventStore(s.events_dir, history=s.inference_history),
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/python -m pytest -m "not integration" -q`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add master/app.py tests/test_app.py tests/test_integration.py
git commit -m "feat(server): record every inference for the dashboard"
```

---

### Task 4: Dashboard API

**Files:**
- Modify: `server/pyproject.toml`
- Create: `server/master/web.py`, `server/master/static/index.html` (placeholder, replaced in Task 5)
- Test: `server/tests/test_web.py`

**Interfaces:**
- Consumes: `Settings` (Task 1), `EventStore` (Task 2) in tests.
- Produces: `master.web.create_app(settings: Settings) -> FastAPI`; `master.web.main() -> None`; `STATIC_DIR`; endpoints `/`, `/static/*`, `/api/config`, `/api/devices`, `/api/inferences`, `/api/alerts`, `/media/{path}` as in the spec §4.2.

- [ ] **Step 1: Dependencies and placeholder page**

In `server/pyproject.toml` set:
```toml
dependencies = [
    "paho-mqtt>=2.0",
    "ultralytics>=8.3",
    "pydantic-settings>=2.0",
    "pillow>=10",
    "numpy",
    "fastapi>=0.110",
    "uvicorn>=0.29",
]

[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27"]
```
and add after `[tool.setuptools.packages.find]` block:
```toml
[tool.setuptools.package-data]
master = ["static/*"]
```

Create `server/master/static/index.html` (placeholder; Task 5 replaces it):
```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Pedestrian inference</title></head>
<body><script src="/static/app.js"></script></body></html>
```

Run: `.venv/Scripts/python -m pip install -q -e ".[dev]"`
Expected: installs fastapi, uvicorn, httpx without errors.

- [ ] **Step 2: Write failing tests**

`server/tests/test_web.py`:
```python
import io
import sqlite3
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from master.events import EventStore
from master.logic import Alert
from master.settings import Settings
from master.web import create_app

MAC = "a1b2c3d4e5f6"
OTHER = "bbbbbbbbbbbb"


def _jpeg(w=64, h=48):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def root(tmp_path):
    return tmp_path / "events"


@pytest.fixture
def client(root):
    s = Settings(_env_file=None, events_dir=root, pedestrian_conf_threshold=0.6,
                 alert_dwell_seconds=5, max_gap_seconds=3, alert_cooldown_seconds=30,
                 inference_history=200)
    return TestClient(create_app(s))


def _fill(root):
    store = EventStore(root)
    store.record_inference(MAC, 100.0, 0.9, True, 0.0, False, _jpeg())
    store.record_inference(OTHER, 101.0, 0.1, False, 0.0, False, _jpeg())
    store.record_inference(MAC, 102.0, 0.8, True, 2.0, True, _jpeg())
    store.record(MAC, Alert(first_seen=97.0, ts=102.0, max_conf=0.9), _jpeg())
    return store


def test_missing_db_returns_empty_lists(client):
    assert client.get("/api/inferences").json() == []
    assert client.get("/api/devices").json() == []
    assert client.get("/api/alerts").json() == []


def test_config(client):
    assert client.get("/api/config").json() == {
        "threshold": 0.6, "dwell_s": 5.0, "max_gap_s": 3.0, "cooldown_s": 30.0, "history": 200,
    }


def test_inferences_newest_first_with_urls(client, root):
    _fill(root).close()
    rows = client.get("/api/inferences").json()
    assert [r["ts"] for r in rows] == [102.0, 101.0, 100.0]
    top = rows[0]
    assert top["mac"] == MAC and top["positive"] is True and top["alerted"] is True
    assert top["dwell_s"] == 2.0 and top["conf"] == 0.8
    assert top["thumb_url"] == f"/media/thumbs/{MAC}/102000.jpg"
    assert client.get(top["thumb_url"]).headers["content-type"] == "image/jpeg"


def test_inferences_filter_after_id_and_limit(client, root):
    _fill(root).close()
    mine = client.get("/api/inferences", params={"mac": MAC}).json()
    assert [r["ts"] for r in mine] == [102.0, 100.0]
    first_id = mine[-1]["id"]
    newer = client.get("/api/inferences", params={"after_id": first_id}).json()
    assert [r["ts"] for r in newer] == [102.0, 101.0]
    assert len(client.get("/api/inferences", params={"limit": 1}).json()) == 1
    assert len(client.get("/api/inferences", params={"limit": 0}).json()) == 1
    assert client.get("/api/inferences", params={"after_id": 10_000}).json() == []


def test_limit_clamped_to_500(client, root):
    store = EventStore(root, history=600)
    for t in range(510):
        store.record_inference(MAC, float(t), 0.5, False, 0.0, False, _jpeg(8, 8))
    store.close()
    assert len(client.get("/api/inferences", params={"limit": 9999}).json()) == 500


def test_devices(client, root):
    _fill(root).close()
    assert client.get("/api/devices").json() == [
        {"mac": MAC, "last_ts": 102.0, "last_conf": 0.8, "count": 2},
        {"mac": OTHER, "last_ts": 101.0, "last_conf": 0.1, "count": 1},
    ]


def test_alert_snapshot_urls_old_and_new(client, root):
    _fill(root).close()
    con = sqlite3.connect(root / "events.db")
    inside = root / MAC / "50000.jpg"
    inside.write_bytes(_jpeg())
    con.execute(
        "INSERT INTO events (mac, alert_ts, first_seen_ts, dwell_s, max_conf, snapshot)"
        " VALUES (?, 50.0, 45.0, 5.0, 0.7, ?)", (MAC, str(inside)))
    con.execute(
        "INSERT INTO events (mac, alert_ts, first_seen_ts, dwell_s, max_conf, snapshot)"
        " VALUES (?, 40.0, 35.0, 5.0, 0.7, ?)", (MAC, str(root.parent / "elsewhere.jpg")))
    con.commit()
    con.close()
    alerts = client.get("/api/alerts").json()
    by_ts = {a["ts"]: a for a in alerts}
    assert by_ts[102.0]["snapshot_url"] == f"/media/{MAC}/102000.jpg"
    assert by_ts[50.0]["snapshot_url"] == f"/media/{MAC}/50000.jpg"
    assert by_ts[40.0]["snapshot_url"] is None
    assert by_ts[102.0]["first_seen_ts"] == 97.0 and by_ts[102.0]["max_conf"] == 0.9


def test_media_rejects_escape(client, root):
    _fill(root).close()
    secret = root.parent / "secret.txt"
    secret.write_text("no")
    assert client.get("/media/..%2Fsecret.txt").status_code == 404
    assert client.get("/media/" + quote(str(secret), safe="")).status_code == 404
    assert client.get("/media/events.db-missing").status_code == 404


def test_reads_while_store_is_open(client, root):
    store = _fill(root)  # writer connection stays open
    store.record_inference(MAC, 103.0, 0.7, True, 3.0, False, _jpeg())
    assert client.get("/api/inferences").json()[0]["ts"] == 103.0
    store.close()


def test_mac_returned_verbatim(client, root):
    weird = "<img src=x onerror=alert(1)>"
    store = EventStore(root)
    store.record_inference(weird, 1.0, 0.5, False, 0.0, False, _jpeg())
    store.close()
    assert client.get("/api/inferences").json()[0]["mac"] == weird


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "/static/app.js" in r.text
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_web.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'master.web'`.

- [ ] **Step 4: Implement `server/master/web.py`**

```python
"""Read-only dashboard: recent inferences and alerts from the master's event store.

    python -m master.web
"""

import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from master.settings import Settings

STATIC_DIR = Path(__file__).parent / "static"
MAX_LIMIT = 500


def _clamp(limit: int) -> int:
    return max(1, min(MAX_LIMIT, limit))


def create_app(settings: Settings) -> FastAPI:
    root = Path(settings.events_dir).resolve()
    db_path = root / "events.db"
    app = FastAPI(title="Pedestrian inference dashboard")

    def query(sql: str, params: tuple = ()) -> list[dict]:
        """Run a read-only query; a missing DB or table yields []."""
        if not db_path.exists():
            return []
        try:
            con = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
        except sqlite3.Error:
            return []
        try:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute(sql, params).fetchall()]
        except sqlite3.OperationalError:
            return []
        finally:
            con.close()

    def media_url(stored: str) -> str | None:
        """URL for a stored file path (relative to root, or an old absolute path)."""
        p = Path(stored)
        if p.is_absolute():
            try:
                p = p.resolve().relative_to(root)
            except ValueError:
                return None
        return "/media/" + p.as_posix()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/api/config")
    def config() -> dict:
        return {
            "threshold": settings.pedestrian_conf_threshold,
            "dwell_s": settings.alert_dwell_seconds,
            "max_gap_s": settings.max_gap_seconds,
            "cooldown_s": settings.alert_cooldown_seconds,
            "history": settings.inference_history,
        }

    @app.get("/api/devices")
    def devices() -> list[dict]:
        return query(
            "SELECT i.mac AS mac, i.ts AS last_ts, i.conf AS last_conf, c.count AS count"
            " FROM inferences i"
            " JOIN (SELECT mac, MAX(id) AS max_id, COUNT(*) AS count FROM inferences GROUP BY mac) c"
            " ON i.id = c.max_id ORDER BY i.ts DESC"
        )

    @app.get("/api/inferences")
    def inferences(mac: str | None = None, limit: int = 100, after_id: int = 0) -> list[dict]:
        sql = "SELECT id, mac, ts, conf, positive, dwell_s, alerted, thumb FROM inferences WHERE id > ?"
        params: list = [after_id]
        if mac:
            sql += " AND mac = ?"
            params.append(mac)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(_clamp(limit))
        rows = query(sql, tuple(params))
        for r in rows:
            r["positive"] = bool(r["positive"])
            r["alerted"] = bool(r["alerted"])
            r["thumb_url"] = media_url(r.pop("thumb"))
        return rows

    @app.get("/api/alerts")
    def alerts(limit: int = 50) -> list[dict]:
        rows = query(
            "SELECT id, mac, alert_ts AS ts, first_seen_ts, dwell_s, max_conf, snapshot"
            " FROM events ORDER BY id DESC LIMIT ?",
            (_clamp(limit),),
        )
        for r in rows:
            r["snapshot_url"] = media_url(r.pop("snapshot"))
        return rows

    @app.get("/media/{path:path}")
    def media(path: str) -> FileResponse:
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(target)

    return app


def main() -> None:
    import uvicorn

    s = Settings()
    uvicorn.run(create_app(s), host=s.web_host, port=s.web_port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_web.py -q`
Expected: all passed.

Then the full suite: `.venv/Scripts/python -m pytest -q`
Expected: all passed (integration test may be skipped if no broker is running).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml master/web.py master/static/index.html tests/test_web.py
git commit -m "feat(server): add read-only dashboard API"
```

---

### Task 5: Dashboard page and docs

**Files:**
- Modify: `server/master/static/index.html` (replace placeholder), `server/README.md`
- Create: `server/master/static/style.css`, `server/master/static/app.js`
- Test: `server/tests/test_web.py` (append)

**Interfaces:**
- Consumes: the API from Task 4 (field names exactly: `id, mac, ts, conf, positive, dwell_s, alerted, thumb_url`; alerts `id, mac, ts, first_seen_ts, dwell_s, max_conf, snapshot_url`; config `threshold, dwell_s, max_gap_s, cooldown_s, history`; devices `mac, last_ts, last_conf, count`).

- [ ] **Step 1: Write failing tests**

Append to `server/tests/test_web.py`:
```python


def test_static_assets_served(client):
    for name, kind in (("app.js", "javascript"), ("style.css", "text/css")):
        r = client.get(f"/static/{name}")
        assert r.status_code == 200
        assert kind in r.headers["content-type"]


def test_page_has_no_external_resources(client):
    html = client.get("/").text
    js = client.get("/static/app.js").text
    assert "http://" not in html and "https://" not in html
    assert "innerHTML" not in js
```

Run: `.venv/Scripts/python -m pytest tests/test_web.py -q`
Expected: FAIL — `/static/app.js` and `/static/style.css` return 404.

- [ ] **Step 2: Write the page**

`server/master/static/index.html`:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pedestrian inference</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <h1>Pedestrian inference</h1>
    <label>Device
      <select id="device"><option value="">All devices</option></select>
    </label>
    <span id="config" class="muted"></span>
    <button id="pause" type="button">Pause</button>
  </header>
  <div id="banner" class="banner" hidden>Cannot reach server — retrying</div>
  <main>
    <section aria-label="Recent inferences">
      <p id="empty" class="muted">No inferences yet. Start master.app and a device.</p>
      <div id="grid" class="grid"></div>
    </section>
    <aside aria-label="Recent alerts">
      <h2>Recent alerts</h2>
      <ol id="alerts" class="alerts"></ol>
    </aside>
  </main>
  <dialog id="viewer"><img alt="Enlarged frame"></dialog>
  <script src="/static/app.js"></script>
</body>
</html>
```

`server/master/static/style.css`:
```css
:root {
  --bg: #f6f7f9; --panel: #ffffff; --text: #1d2330; --muted: #677085; --line: #dde1e8;
  --pos: #1f7a4d; --neg: #9aa1b0; --alert: #c62828; --bar: #3b6fd8;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12151b; --panel: #1b2029; --text: #e6e9ef; --muted: #8d95a6; --line: #2b3240;
    --pos: #4cc38a; --neg: #5b6375; --alert: #ff6b6b; --bar: #6d9cff;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 14px/1.4 system-ui, sans-serif; }
header { display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center; padding: 12px 16px;
  background: var(--panel); border-bottom: 1px solid var(--line); position: sticky; top: 0; z-index: 1; }
h1 { font-size: 16px; margin: 0 auto 0 0; }
h2 { font-size: 14px; margin: 0 0 8px; }
select, button { font: inherit; padding: 4px 8px; }
.muted { color: var(--muted); }
.banner { background: var(--alert); color: #fff; padding: 8px 16px; }
main { display: grid; grid-template-columns: 1fr 280px; gap: 16px; padding: 16px; }
@media (max-width: 800px) { main { grid-template-columns: 1fr; } }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.card.alert { border: 2px solid var(--alert); }
.card img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; cursor: zoom-in; background: var(--line); }
.card .meta { padding: 8px; display: grid; gap: 4px; }
.row { display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.conf { font-variant-numeric: tabular-nums; font-weight: 600; }
.bar { height: 4px; background: var(--line); border-radius: 2px; overflow: hidden; }
.bar > span { display: block; height: 100%; background: var(--bar); }
.badge { font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 4px; color: #fff; }
.badge.pos { background: var(--pos); }
.badge.neg { background: var(--neg); }
.badge.alert { background: var(--alert); }
.small { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
aside { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; align-self: start; }
.alerts { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.alerts li { padding: 6px; border-radius: 4px; cursor: pointer; }
.alerts li:hover { background: var(--bg); }
dialog { border: none; padding: 0; background: transparent; max-width: 95vw; }
dialog img { max-width: 95vw; max-height: 90vh; display: block; }
dialog::backdrop { background: rgb(0 0 0 / 0.7); }
```

`server/master/static/app.js`:
```javascript
// Dashboard: polls the read-only API. Device-provided text is set with textContent only.
const POLL_MS = 2000;
const SIDE_MS = 10000;
const MAX_CARDS = 200;

const state = { lastId: 0, paused: false, mac: "", cfg: null };
const $ = (sel) => document.querySelector(sel);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

function setReachable(ok) {
  $("#banner").hidden = ok;
}

function timeOf(ts) {
  return new Date(ts * 1000).toLocaleTimeString();
}

function openViewer(url) {
  if (!url) return;
  const dialog = $("#viewer");
  dialog.querySelector("img").src = url;
  dialog.showModal();
}

function card(r) {
  const node = el("article", "card" + (r.alerted ? " alert" : ""));
  const img = el("img");
  img.src = r.thumb_url;
  img.loading = "lazy";
  img.alt = "Frame";
  img.addEventListener("click", () => openViewer(r.thumb_url));
  node.append(img);

  const meta = el("div", "meta");
  const top = el("div", "row");
  top.append(el("span", "conf", r.conf.toFixed(2)));
  top.append(el("span", "badge " + (r.positive ? "pos" : "neg"), r.positive ? "PED" : "–"));
  if (r.alerted) top.append(el("span", "badge alert", "ALERT"));
  meta.append(top);

  const bar = el("div", "bar");
  const fill = el("span");
  fill.style.width = `${Math.round(Math.min(1, Math.max(0, r.conf)) * 100)}%`;
  bar.append(fill);
  meta.append(bar);

  if (r.positive && state.cfg) {
    meta.append(el("div", "small", `dwell ${r.dwell_s.toFixed(1)} / ${state.cfg.dwell_s} s`));
  }
  const foot = el("div", "row small");
  foot.append(el("span", "", r.mac));
  foot.append(el("span", "", timeOf(r.ts)));
  meta.append(foot);
  node.append(meta);
  return node;
}

async function pollInferences(limit = 100) {
  const mac = state.mac;
  const params = new URLSearchParams({ limit: String(limit), after_id: String(state.lastId) });
  if (mac) params.set("mac", mac);
  const rows = await getJSON(`/api/inferences?${params}`);
  if (mac !== state.mac) return; // filter changed while the request was in flight
  const grid = $("#grid");
  for (const r of rows.slice().reverse()) {
    grid.prepend(card(r));
    state.lastId = Math.max(state.lastId, r.id);
  }
  while (grid.children.length > MAX_CARDS) grid.lastElementChild.remove();
  $("#empty").hidden = grid.children.length > 0;
}

async function refreshSide() {
  const [devices, alerts] = await Promise.all([getJSON("/api/devices"), getJSON("/api/alerts")]);

  const select = $("#device");
  const current = select.value;
  select.replaceChildren(el("option", "", "All devices"));
  select.firstChild.value = "";
  for (const d of devices) {
    const opt = el("option", "", `${d.mac} (${d.count})`);
    opt.value = d.mac;
    select.append(opt);
  }
  select.value = current;

  const list = $("#alerts");
  list.replaceChildren();
  if (alerts.length === 0) list.append(el("li", "muted", "No alerts yet"));
  for (const a of alerts) {
    const item = el("li");
    item.append(el("div", "row", ""));
    item.firstChild.append(el("span", "", timeOf(a.ts)));
    item.firstChild.append(el("span", "conf", a.max_conf.toFixed(2)));
    item.append(el("div", "small", `${a.mac} · ${a.dwell_s.toFixed(1)} s`));
    item.addEventListener("click", () => openViewer(a.snapshot_url));
    list.append(item);
  }
}

async function loop(fn, ms) {
  if (!state.paused) {
    try {
      await fn();
      setReachable(true);
    } catch (err) {
      console.warn(err);
      setReachable(false);
    }
  }
  setTimeout(() => loop(fn, ms), ms);
}

async function init() {
  try {
    state.cfg = await getJSON("/api/config");
    $("#config").textContent = `threshold ${state.cfg.threshold} · dwell ${state.cfg.dwell_s} s`;
  } catch (err) {
    setReachable(false);
  }
  $("#device").addEventListener("change", (e) => {
    state.mac = e.target.value;
    state.lastId = 0;
    $("#grid").replaceChildren();
    pollInferences().catch(() => setReachable(false));
  });
  $("#pause").addEventListener("click", (e) => {
    state.paused = !state.paused;
    e.target.textContent = state.paused ? "Resume" : "Pause";
  });
  $("#viewer").addEventListener("click", () => $("#viewer").close());
  loop(pollInferences, POLL_MS);
  loop(refreshSide, SIDE_MS);
}

init();
```

- [ ] **Step 3: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_web.py -q`
Expected: all passed.

- [ ] **Step 4: Manual check in a browser**

Needs a broker on `127.0.0.1:1883` (Mosquitto, see README). Three terminals in `server/`:
```bash
.venv/Scripts/python -m master.app
.venv/Scripts/python -m master.web
.venv/Scripts/python tools/fake_device.py --mac 0123456789ab --dir samples --interval 1 --count 10
```
Open `http://127.0.0.1:8000`. Expected: cards appear about every second with `PED`, dwell counting 0.0 → 5.0 s; the card at 5 s has the `ALERT` badge and red border; the alert appears in the side panel within 10 s and clicking it opens the snapshot; stopping `master.web` shows the red "Cannot reach server" banner, restarting it hides it.

If no broker is installed, run only `master.web` against an `EVENTS_DIR` filled by a short script using `EventStore.record_inference` and check the page renders the cards.

- [ ] **Step 5: Document in `server/README.md`**

Add after the `## Run` section:
````markdown
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
````

- [ ] **Step 6: Commit**

```bash
git add master/static tests/test_web.py README.md
git commit -m "feat(server): add dashboard page"
```
