"""MQTT topics and payload formats shared by the server, CLI, and fake device."""

import json
import struct

HEADER = struct.Struct("<Q")
HEADER_SIZE = HEADER.size

FRAME_SIZES = ("QVGA", "VGA", "SVGA", "XGA", "HD", "SXGA", "UXGA")
ACTIONS = ("start", "stop", "reboot", "status")
DEFAULT_CONFIG = {"interval_ms": 1000, "jpeg_quality": 12, "frame_size": "VGA", "volume": 80}

# Integer fields -> (min, max), inclusive. frame_size is checked separately.
_INT_FIELDS = {
    "interval_ms": (100, 3_600_000),
    "jpeg_quality": (0, 63),
    "volume": (0, 100),
}


class ProtocolError(ValueError):
    """A payload, topic, or config value does not match the protocol."""


def topic(mac: str, kind: str) -> str:
    return f"{mac}/{kind}"


def parse_topic(t: str) -> tuple[str, str] | None:
    """Split `{mac}/{kind}`. Returns None for any other shape."""
    parts = t.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def pack_image(capture_ms: int, jpeg: bytes) -> bytes:
    return HEADER.pack(capture_ms) + jpeg


def parse_image(payload: bytes) -> tuple[int, bytes]:
    """Return (capture_ms, jpeg). capture_ms is 0 when the device clock is not synced."""
    if len(payload) <= HEADER_SIZE:
        raise ProtocolError(f"image payload too short ({len(payload)} bytes)")
    (capture_ms,) = HEADER.unpack_from(payload)
    return capture_ms, payload[HEADER_SIZE:]


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
        else:
            out[key] = raw
    return validate_config(out)


def merge_config(current: dict, updates: dict) -> dict:
    validate_config(updates)
    return {**current, **updates}
