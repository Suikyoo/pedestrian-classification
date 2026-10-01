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
