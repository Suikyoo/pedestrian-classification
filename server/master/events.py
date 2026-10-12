"""Event store: alerts (row + full snapshot) and recent inferences (row + thumbnail)."""

import io
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

THUMB_WIDTH = 320
_UNSAFE_CHARS = re.compile(r"[^0-9A-Za-z_-]")


def _dir_name(mac: str) -> str:
    """Folder name for a device. Device IDs come from MQTT topics and are untrusted."""
    return _UNSAFE_CHARS.sub("_", mac)[:64] or "_"


@dataclass(frozen=True)
class Alert:
    """A warning as stored: times in Unix seconds, max_conf = device's max score."""

    first_seen: float
    ts: float
    max_conf: float

    @property
    def dwell_s(self) -> float:
        return self.ts - self.first_seen


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
    thumb TEXT NOT NULL,
    device_score REAL
);
CREATE INDEX IF NOT EXISTS inferences_mac_id ON inferences (mac, id);
CREATE TABLE IF NOT EXISTS devices (
    mac TEXT PRIMARY KEY,
    online INTEGER NOT NULL,
    status TEXT,
    last_seen_ts REAL
);
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
        self._migrate_snapshot_paths()
        self._migrate_device_score()
        self._db.commit()

    def _migrate_snapshot_paths(self) -> None:
        """Rewrite snapshot paths stored by older versions (cwd-relative or absolute,
        e.g. "events\\<mac>\\<ms>.jpg") to the root-relative form "<mac>/<ms>.jpg"."""
        root = self.root.resolve()
        rows = self._db.execute("SELECT id, snapshot FROM events").fetchall()
        for row_id, snap in rows:
            if not Path(snap).is_absolute() and (root / snap).is_file():
                continue  # already root-relative
            try:
                rel = Path(snap).resolve().relative_to(root).as_posix()
            except ValueError:
                continue  # outside root: leave it; the dashboard shows no image
            self._db.execute("UPDATE events SET snapshot = ? WHERE id = ?", (rel, row_id))

    def _migrate_device_score(self) -> None:
        """Databases from before on-device detection have no device_score column."""
        cols = {row[1] for row in self._db.execute("PRAGMA table_info(inferences)")}
        if "device_score" not in cols:
            self._db.execute("ALTER TABLE inferences ADD COLUMN device_score REAL")

    def record(self, mac: str, alert: Alert, jpeg: bytes, mark_frame: bool = False) -> Path:
        """Save a warning. mark_frame: also flag the stream frame captured at alert.ts
        (only meaningful when the device clock was synced). Because a synced alert.ts is
        the device's own timestamp, a resent event (same mac and alert_ts) is recorded
        once: no second row, snapshot left untouched. Without mark_frame, always insert."""
        rel = Path(_dir_name(mac)) / f"{round(alert.ts * 1000)}.jpg"
        path = self.root / rel
        with self._lock:
            duplicate = mark_frame and self._db.execute(
                "SELECT 1 FROM events WHERE mac = ? AND alert_ts = ? LIMIT 1", (mac, alert.ts)
            ).fetchone() is not None
            if not duplicate:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(jpeg)
                self._db.execute(
                    "INSERT INTO events (mac, alert_ts, first_seen_ts, dwell_s, max_conf, snapshot)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (mac, alert.ts, alert.first_seen, alert.dwell_s, alert.max_conf, rel.as_posix()),
                )
            if mark_frame:
                self._db.execute("UPDATE inferences SET alerted = 1 WHERE mac = ? AND ts = ?", (mac, alert.ts))
            self._db.commit()
        return path

    def record_inference(self, mac: str, ts: float, conf: float, positive: bool,
                         dwell_s: float, alerted: bool, jpeg: bytes,
                         device_score: float | None = None, match_event: bool = False) -> Path:
        """Save a thumbnail and a row, then prune this device to the newest `history` rows.
        match_event: mark the row alerted if a warning for this device has alert_ts == ts."""
        rel = Path("thumbs") / _dir_name(mac) / f"{round(ts * 1000)}.jpg"
        path = self.root / rel
        img = Image.open(io.BytesIO(jpeg)).convert("RGB")
        if img.width > THUMB_WIDTH:
            height = max(1, round(img.height * THUMB_WIDTH / img.width))
            img = img.resize((THUMB_WIDTH, height))
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, format="JPEG", quality=70)

        with self._lock:
            if match_event and not alerted:
                alerted = self._db.execute(
                    "SELECT 1 FROM events WHERE mac = ? AND alert_ts = ? LIMIT 1", (mac, ts)
                ).fetchone() is not None
            self._db.execute(
                "INSERT INTO inferences (mac, ts, conf, positive, dwell_s, alerted, thumb, device_score)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (mac, ts, conf, int(positive), dwell_s, int(alerted), rel.as_posix(), device_score),
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
                "SELECT id, mac, ts, conf, positive, dwell_s, alerted, thumb, device_score"
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

    def update_device(self, mac: str, *, online: bool | None = None, status: str | None = None,
                      seen_ts: float | None = None) -> None:
        """Upsert a device. A None argument keeps the stored value."""
        on = None if online is None else int(online)
        with self._lock:
            self._db.execute(
                "INSERT INTO devices (mac, online, status, last_seen_ts) VALUES (?, COALESCE(?, 0), ?, ?)"
                " ON CONFLICT(mac) DO UPDATE SET"
                " online = COALESCE(?, online), status = COALESCE(?, status),"
                " last_seen_ts = COALESCE(?, last_seen_ts)",
                (mac, on, status, seen_ts, on, status, seen_ts),
            )
            self._db.commit()

    def devices(self) -> list[dict]:
        with self._lock:
            cur = self._db.execute("SELECT mac, online, status, last_seen_ts FROM devices ORDER BY mac")
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close(self) -> None:
        with self._lock:
            self._db.close()
