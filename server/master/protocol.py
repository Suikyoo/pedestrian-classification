"""MQTT topics and payload formats shared by the server, CLI, and fake device."""

import json
import math
import struct
from dataclasses import dataclass

# {mac}/image header: capture_ms, device score in permille (SCORE_FAILED = the
# device's detection failed), device's current dwell in deciseconds.
IMAGE_HEADER = struct.Struct("<QHH")
HEADER_SIZE = IMAGE_HEADER.size
SCORE_FAILED = 0xFFFF
EVENT_JSON_LEN = struct.Struct("<H")

FRAME_SIZES = ("QVGA", "VGA", "SVGA", "XGA", "HD", "SXGA", "UXGA")
ACTIONS = ("start", "stop", "reboot", "status")
DEFAULT_CONFIG = {
    "interval_ms": 1000, "jpeg_quality": 12, "frame_size": "VGA", "volume": 80,
    "threshold": 0.6, "dwell_s": 5.0, "max_gap_s": 3.0, "cooldown_s": 30.0,
}

# Integer fields -> (min, max), inclusive. frame_size is checked separately.
_INT_FIELDS = {
    "interval_ms": (100, 3_600_000),
    "jpeg_quality": (0, 63),
    "volume": (0, 100),
}
# Number fields (int or float) -> (min, max), inclusive. Same ranges as firmware devcfg.
_FLOAT_FIELDS = {
    "threshold": (0.05, 0.99),
    "dwell_s": (0.0, 600.0),
    "max_gap_s": (0.5, 60.0),
    "cooldown_s": (0.0, 3600.0),
}


class ProtocolError(ValueError):
    """A payload, topic, or config value does not match the protocol."""


@dataclass(frozen=True)
class ImageFrame:
    capture_ms: int        # 0 when the device clock is not synced
    score: float | None    # device detector score 0..1; None when its detection failed
    dwell_s: float         # device's current dwell
    jpeg: bytes


@dataclass(frozen=True)
class DeviceEvent:
    alert_ms: int          # Unix ms of the alerting frame; 0 when the device clock is not synced
    first_seen_ms: int
    dwell_s: float
    max_score: float


def _is_number(v) -> bool:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:  # an int too large for a float
        return False


def topic(mac: str, kind: str) -> str:
    return f"{mac}/{kind}"


def parse_topic(t: str) -> tuple[str, str] | None:
    """Split `{mac}/{kind}`. Returns None for any other shape."""
    parts = t.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def pack_image(capture_ms: int, jpeg: bytes, score: float | None = None, dwell_s: float = 0.0) -> bytes:
    permille = SCORE_FAILED if score is None else round(min(max(score, 0.0), 1.0) * 1000)
    dwell_ds = min(0xFFFF, max(0, round(dwell_s * 10)))
    return IMAGE_HEADER.pack(capture_ms, permille, dwell_ds) + jpeg


def parse_image(payload: bytes) -> ImageFrame:
    if len(payload) <= HEADER_SIZE:
        raise ProtocolError(f"image payload too short ({len(payload)} bytes)")
    capture_ms, permille, dwell_ds = IMAGE_HEADER.unpack_from(payload)
    if permille == SCORE_FAILED:
        score = None
    elif permille > 1000:
        raise ProtocolError(f"image score {permille} permille out of range")
    else:
        score = permille / 1000
    return ImageFrame(capture_ms, score, dwell_ds / 10, payload[HEADER_SIZE:])


def pack_event(event: DeviceEvent, jpeg: bytes) -> bytes:
    body = json.dumps({
        "alert_ms": event.alert_ms, "first_seen_ms": event.first_seen_ms,
        "dwell_s": event.dwell_s, "max_score": event.max_score,
    }).encode()
    return EVENT_JSON_LEN.pack(len(body)) + body + jpeg


def parse_event(payload: bytes) -> tuple[DeviceEvent, bytes]:
    """Return (event, snapshot JPEG). Device payloads are untrusted: every field is checked."""
    if len(payload) < EVENT_JSON_LEN.size:
        raise ProtocolError(f"event payload too short ({len(payload)} bytes)")
    (n,) = EVENT_JSON_LEN.unpack_from(payload)
    end = EVENT_JSON_LEN.size + n
    if n == 0 or end >= len(payload):
        raise ProtocolError("event JSON length is 0 or leaves no snapshot")
    try:
        data = json.loads(payload[EVENT_JSON_LEN.size:end])
    except (ValueError, RecursionError):
        raise ProtocolError("event JSON is not valid") from None
    if not isinstance(data, dict):
        raise ProtocolError("event JSON is not an object")
    times = {}
    for key in ("alert_ms", "first_seen_ms"):
        v = data.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < 2**64:
            raise ProtocolError(f"event {key} must be an integer 0 to 2^64-1, got {v!r}")
        times[key] = v
    dwell_s, max_score = data.get("dwell_s"), data.get("max_score")
    if not _is_number(dwell_s) or dwell_s < 0:
        raise ProtocolError(f"event dwell_s must be a number >= 0, got {dwell_s!r}")
    if not _is_number(max_score) or not 0 <= max_score <= 1:
        raise ProtocolError(f"event max_score must be 0-1, got {max_score!r}")
    if times["first_seen_ms"] > times["alert_ms"]:
        raise ProtocolError("event first_seen_ms is after alert_ms")
    return DeviceEvent(times["alert_ms"], times["first_seen_ms"], float(dwell_s), float(max_score)), payload[end:]


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
        elif key in _FLOAT_FIELDS:
            lo, hi = _FLOAT_FIELDS[key]
            if not _is_number(value):
                raise ProtocolError(f"{key} must be a number, got {value!r}")
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
        elif key in _FLOAT_FIELDS:
            try:
                out[key] = float(raw)
            except ValueError:
                raise ProtocolError(f"{key} must be a number, got {raw!r}") from None
        else:
            out[key] = raw
    return validate_config(out)


def merge_config(current: dict, updates: dict) -> dict:
    validate_config(updates)
    return {**current, **updates}
