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
