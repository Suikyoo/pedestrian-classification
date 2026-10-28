"""Optional archive of every JPEG the master receives, for labeling (e.g. CVAT)."""

import re
from pathlib import Path

_UNSAFE_CHARS = re.compile(r"[^0-9A-Za-z_-]")


class DatasetSink:
    """Writes each frame to <root>/<mac>/<ms>.jpg, the exact bytes the device sent.
    A file is written as .part and renamed, so a scraper that skips .part never reads half
    a frame. Device IDs come from MQTT topics and are untrusted."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, mac: str, ts: float, jpeg: bytes) -> Path:
        folder = self.root / (_UNSAFE_CHARS.sub("_", mac)[:64] or "_")
        folder.mkdir(exist_ok=True)
        ms = round(ts * 1000)
        path = folder / f"{ms}.jpg"
        n = 0
        while path.exists():  # unsynced clocks and event+frame pairs can share a millisecond
            n += 1
            path = folder / f"{ms}_{n}.jpg"
        tmp = path.with_suffix(".part")
        tmp.write_bytes(jpeg)
        tmp.replace(path)
        return path
