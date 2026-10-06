# Inference Dashboard — Design

Date: 2026-10-06
Status: Draft for review
Parent spec: `docs/superpowers/specs/2026-09-29-pedestrian-alert-design.md`

## 1. Goal

A web page, served on the LAN, that shows the master server's recent inferences: for every processed frame, a thumbnail, the device, the time, the person confidence, whether it counted as a pedestrian, the dwell progress, and whether it triggered an alert. It also lists recent alerts.

Primary use: watching the system work and tuning `PEDESTRIAN_CONF_THRESHOLD`, `ALERT_DWELL_SECONDS`, `MAX_GAP_SECONDS`.

### Success criteria

- With `master.app` and `master.web` running and a device (or `tools/fake_device.py`) streaming, a browser at `http://<pc-ip>:8000` shows each new frame within about 2 s of its inference.
- Each card shows: thumbnail, device, capture time, confidence, positive/negative, dwell seconds against `ALERT_DWELL_SECONDS`, and an alert badge on the frame that triggered one.
- Disk use is bounded: only the last `INFERENCE_HISTORY` inferences per device are kept.
- A failure in inference recording or in the web process never blocks, delays, or stops alerts.

### Out of scope

- Bounding boxes (the detector's per-frame result stays a single confidence).
- Access from outside the LAN, login, Cloudflare Access.
- Live push (SSE/WebSocket); the page polls.
- Changing settings or sending device commands from the page.
- Device online/offline status (not persisted today).

## 2. Architecture

```
master.app (existing process)                master.web (new process)
  MQTT -> detector -> logic -> alert           FastAPI + uvicorn on WEB_HOST:WEB_PORT
                         |                        reads (read-only)
                         v                            |
        EVENTS_DIR/events.db  (SQLite, WAL) <---------+
          table events      (alerts, existing)
          table inferences  (new)
        EVENTS_DIR/<mac>/<ms>.jpg         alert snapshots (existing)
        EVENTS_DIR/thumbs/<mac>/<ms>.jpg  inference thumbnails (new)
                                                   ^
        browser --(poll every 2 s)--> /api/* and /media/* ---+
```

The two processes share only the SQLite file and the thumbnail directory. `master.web` never writes.

## 3. Changes to the master

### 3.1 `logic.py`

Add `DwellLogic.current_dwell(mac: str) -> float`: `last_seen - first_seen` of the device's current pedestrian run, or `0.0` if there is no run or the device is unknown. Pure; no change to `update()`.

### 3.2 `events.py` (`EventStore`)

- On open: `PRAGMA journal_mode=WAL`.
- New table and index:
  ```sql
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
  ```
- `EventStore(root, history: int = 200)`.
- New `record_inference(mac, ts, conf, positive, dwell_s, alerted, jpeg) -> Path`:
  1. Decode the JPEG, resize to 320 px wide (keep aspect; never upscale), save as JPEG quality 70 to `root/thumbs/<mac>/<round(ts*1000)>.jpg`.
  2. Insert the row. `thumb` stores the path relative to `root`, with `/` separators (e.g. `thumbs/a1b2c3d4e5f6/1790838126186.jpg`).
  3. Prune: delete that device's rows older than its newest `history` rows, and delete their thumbnail files (a missing file is ignored).
  4. Errors propagate to the caller.
- Existing `record()` (alerts) is unchanged except that its `snapshot` column also becomes relative to `root` for new rows. The web reader accepts both absolute (old rows) and relative paths, but serves only files inside `root`.

### 3.3 `app.py` (`MasterApp.process`)

New order:

1. `conf = detector.person_confidence(jpeg)` (on exception: log, drop the frame, no inference row — unchanged).
2. Under the lock: `alert = logic.update(mac, ts, conf)`; `dwell = logic.current_dwell(mac)`.
3. If `alert`: publish `{mac}/alert`; then `events.record(...)` in try/except (unchanged).
4. `events.record_inference(mac, ts, conf, conf >= threshold, dwell, alert is not None, jpeg)` in try/except; failures are logged and never re-raised.

`threshold` is `logic.threshold`.

### 3.4 Settings (`.env`)

```
INFERENCE_HISTORY=200   # inferences kept per device (thumbnails + rows)
WEB_HOST=0.0.0.0        # 127.0.0.1 to allow only this PC
WEB_PORT=8000
```

## 4. Web process (`master/web.py`)

Run: `python -m master.web` (uvicorn, `WEB_HOST:WEB_PORT`). Dependencies added to `pyproject.toml`: `fastapi`, `uvicorn`; dev: `httpx`.

`create_app(settings) -> FastAPI` builds the app (testable without a server).

### 4.1 Database access

Each request opens `file:<EVENTS_DIR>/events.db?mode=ro` (URI mode) and closes it. If the file or the `inferences` table does not exist yet, list endpoints return empty lists (never 500).

### 4.2 Endpoints

| Endpoint | Response |
|---|---|
| `GET /` | `master/static/index.html` |
| `GET /static/{file}` | page assets (`app.js`, `style.css`) |
| `GET /api/config` | `{"threshold", "dwell_s", "max_gap_s", "cooldown_s", "history"}` from settings |
| `GET /api/devices` | `[{"mac", "last_ts", "last_conf", "count"}]`, newest `last_ts` first |
| `GET /api/inferences?mac=&limit=100&after_id=0` | newest first; `limit` clamped to 1–500; `mac` optional; `after_id` returns only rows with `id > after_id`. Each row: `{"id", "mac", "ts", "conf", "positive", "dwell_s", "alerted", "thumb_url"}` |
| `GET /api/alerts?limit=50` | newest first from `events`; `limit` clamped 1–500; each `{"id", "mac", "ts", "first_seen_ts", "dwell_s", "max_conf", "snapshot_url"}` |
| `GET /media/{path}` | file under `EVENTS_DIR`; the resolved path must stay inside `EVENTS_DIR` or the response is 404; non-existent → 404 |

`thumb_url` / `snapshot_url` are `/media/<path relative to EVENTS_DIR>`. For old alert rows with absolute snapshot paths outside `EVENTS_DIR`, `snapshot_url` is `null`.

### 4.3 Page (`master/static/`)

Plain HTML/CSS/JS, no build step, no external CDN (works offline on the LAN).

- Header: title, device filter (from `/api/devices`, plus "all"), current threshold and dwell (from `/api/config`), pause/resume button.
- Main grid, newest first; each card: thumbnail, confidence value and bar, `PED` or `–` badge, dwell `x.x / N s` (only when positive), `ALERT` badge when `alerted`, device MAC, local time. At most 200 cards kept in the DOM.
- Side panel: recent alerts (time, device, dwell, max confidence); clicking opens the full snapshot.
- Clicking a card opens the thumbnail enlarged.
- Polling: on load fetch the newest 100; then every 2 s fetch `after_id=<highest id seen>` (with the current device filter) and prepend. Alerts panel refreshes every 10 s. Changing the device filter reloads the grid.
- If a request fails: show a banner "Cannot reach server — retrying" and keep polling; hide the banner on the next success.

## 5. Security

No authentication. Anyone on the LAN who can reach `WEB_HOST:WEB_PORT` can see camera thumbnails and alert snapshots. Set `WEB_HOST=127.0.0.1` to restrict to the server PC. The API is read-only and `/media` cannot escape `EVENTS_DIR`. Exposing the dashboard through the tunnel is out of scope and needs access control first.

## 6. Testing

- `logic.current_dwell`: no run → 0; during a run; after gap reset → 0 then new run; unknown device → 0; after `reset`.
- `EventStore.record_inference`: thumbnail exists, ≤ 320 px wide, small images not upscaled; row values; relative `thumb` path; pruning keeps exactly `history` newest rows per device and deletes old files; other devices untouched; WAL mode on.
- `MasterApp.process`: one inference row per processed frame with correct `positive`, `dwell_s`, `alerted`; detector failure → no row; `record_inference` raising → alert still published and worker continues.
- Web API (FastAPI `TestClient`, temp `EVENTS_DIR`): empty/missing DB → empty lists; `mac` filter; `after_id`; `limit` clamping; ordering; URLs; `/media` serves a thumbnail, rejects `../` and absolute escapes with 404; old absolute snapshot path → `snapshot_url` null; `/api/config` values; `/` serves HTML.
- Manual: `master.app` + `master.web` + `tools/fake_device.py`, open the page, confirm cards appear and an alert card/badge shows after `ALERT_DWELL_SECONDS`.
