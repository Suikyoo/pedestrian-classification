"""Read-only dashboard: devices, warnings, and stream-mode frames from the master's event store.

    python -m master.web
"""

import json
import math
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


_STATUS_BOOLS = ("streaming", "detect_ok")
_STATUS_NUMBERS = ("threshold", "dwell_s", "max_gap_s", "cooldown_s")


def _status_fields(text: str | None) -> dict:
    """A device's active settings from its last status JSON. The JSON comes from the
    device and is untrusted: a missing or wrongly typed field becomes None."""
    try:
        status = json.loads(text) if text else {}
    except (ValueError, RecursionError):
        status = {}
    if not isinstance(status, dict):
        status = {}
    out = {}
    for key in _STATUS_BOOLS:
        v = status.get(key)
        out[key] = v if isinstance(v, bool) else None
    for key in _STATUS_NUMBERS:
        v = status.get(key)
        out[key] = _finite_float(v)
    return out


def _finite_float(v) -> float | None:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except OverflowError:  # an int too large for a float
        return None
    return f if math.isfinite(f) else None


def _bool_or_none(v) -> bool | None:
    return None if v is None else bool(v)


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
        return {"threshold": settings.pedestrian_conf_threshold, "history": settings.inference_history}

    @app.get("/api/devices")
    def devices() -> list[dict]:
        rows = query(
            "SELECT d.mac AS mac, d.online AS online, d.status AS status, d.last_seen_ts AS last_seen_ts,"
            " COALESCE(c.count, 0) AS count, i.ts AS last_ts, i.conf AS last_conf,"
            " i.device_score AS last_device_score, i.positive AS last_positive,"
            " i.dwell_s AS last_dwell_s, i.alerted AS last_alerted"
            " FROM devices d"
            " LEFT JOIN (SELECT mac, MAX(id) AS max_id, COUNT(*) AS count FROM inferences GROUP BY mac) c"
            " ON c.mac = d.mac"
            " LEFT JOIN inferences i ON i.id = c.max_id"
            " ORDER BY d.mac"
        )
        warnings = {
            r["mac"]: r["last_warning_ts"]
            for r in query("SELECT mac, MAX(alert_ts) AS last_warning_ts FROM events GROUP BY mac")
        }
        for r in rows:
            r["online"] = bool(r["online"])
            r["last_positive"] = _bool_or_none(r["last_positive"])
            r["last_alerted"] = _bool_or_none(r["last_alerted"])
            r.update(_status_fields(r.pop("status")))
            r["last_warning_ts"] = warnings.get(r["mac"])
        return rows

    @app.get("/api/inferences")
    def inferences(mac: str | None = None, limit: int = 100, after_id: int = 0) -> list[dict]:
        sql = "SELECT id, mac, ts, conf, positive, dwell_s, alerted, thumb, device_score FROM inferences WHERE id > ?"
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
        # Only the JPEG thumbnails and snapshots are served, never the database.
        if not target.is_relative_to(root) or target.suffix.lower() != ".jpg" or not target.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(target)

    return app


def main() -> None:
    import uvicorn

    s = Settings()
    uvicorn.run(create_app(s), host=s.web_host, port=s.web_port)


if __name__ == "__main__":
    main()
