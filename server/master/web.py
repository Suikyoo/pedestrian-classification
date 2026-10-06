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
        rows = query(
            "SELECT i.mac AS mac, i.ts AS last_ts, i.conf AS last_conf, c.count AS count,"
            " i.positive AS last_positive, i.dwell_s AS last_dwell_s, i.alerted AS last_alerted"
            " FROM inferences i"
            " JOIN (SELECT mac, MAX(id) AS max_id, COUNT(*) AS count FROM inferences GROUP BY mac) c"
            " ON i.id = c.max_id ORDER BY i.ts DESC"
        )
        warnings = {
            r["mac"]: r["last_warning_ts"]
            for r in query("SELECT mac, MAX(alert_ts) AS last_warning_ts FROM events GROUP BY mac")
        }
        for r in rows:
            r["last_positive"] = bool(r["last_positive"])
            r["last_alerted"] = bool(r["last_alerted"])
            r["last_warning_ts"] = warnings.get(r["mac"])
        return rows

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
