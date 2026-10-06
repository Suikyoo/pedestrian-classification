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
