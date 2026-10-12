import json
import struct

import pytest

from master import protocol as p


def test_topic_builds_two_levels():
    assert p.topic("a1b2c3d4e5f6", "alert") == "a1b2c3d4e5f6/alert"


@pytest.mark.parametrize(
    "t, expected",
    [
        ("a1b2c3d4e5f6/image", ("a1b2c3d4e5f6", "image")),
        ("a1b2c3d4e5f6/online", ("a1b2c3d4e5f6", "online")),
        ("foo", None),
        ("a/b/image", None),
        ("/image", None),
        ("a1b2c3d4e5f6/", None),
    ],
)
def test_parse_topic(t, expected):
    assert p.parse_topic(t) == expected


def test_image_round_trip():
    payload = p.pack_image(1_727_600_000_123, b"\xff\xd8jpeg", 0.8, 1.5)
    assert payload[:8] == struct.pack("<Q", 1_727_600_000_123)
    assert p.parse_image(payload) == p.ImageFrame(1_727_600_000_123, 0.8, 1.5, b"\xff\xd8jpeg")


def test_image_header_layout():
    payload = p.pack_image(0x0102030405060708, b"j", 0.5, 2.0)
    assert payload[:12] == bytes([8, 7, 6, 5, 4, 3, 2, 1, 0xF4, 0x01, 0x14, 0x00])
    assert p.HEADER_SIZE == 12


def test_image_without_score_means_detection_failed():
    payload = p.pack_image(1, b"j")
    assert payload[8:10] == b"\xff\xff"
    assert p.parse_image(payload).score is None


def test_image_score_and_dwell_clamped():
    assert p.parse_image(p.pack_image(1, b"j", 1.7)).score == 1.0
    assert p.parse_image(p.pack_image(1, b"j", -0.2)).score == 0.0
    assert p.parse_image(p.pack_image(1, b"j", 0.5, 10_000)).dwell_s == 6553.5


@pytest.mark.parametrize("payload", [b"", b"\x00" * 8, b"\x00" * 12])
def test_parse_image_rejects_short_payload(payload):
    with pytest.raises(p.ProtocolError):
        p.parse_image(payload)


def test_parse_image_rejects_score_out_of_range():
    with pytest.raises(p.ProtocolError):
        p.parse_image(struct.pack("<QHH", 1, 1001, 0) + b"j")


def test_event_round_trip():
    ev = p.DeviceEvent(alert_ms=1_790_000_005_000, first_seen_ms=1_790_000_000_000, dwell_s=5.0, max_score=0.83)
    payload = p.pack_event(ev, b"\xff\xd8snap")
    (n,) = struct.unpack_from("<H", payload)
    assert json.loads(payload[2:2 + n]) == {
        "alert_ms": 1_790_000_005_000, "first_seen_ms": 1_790_000_000_000, "dwell_s": 5.0, "max_score": 0.83,
    }
    assert p.parse_event(payload) == (ev, b"\xff\xd8snap")


def test_event_from_device_json():
    body = b'{"alert_ms":0,"first_seen_ms":0,"dwell_s":5.20,"max_score":0.835}'
    ev, jpeg = p.parse_event(struct.pack("<H", len(body)) + body + b"x")
    assert ev == p.DeviceEvent(0, 0, 5.2, 0.835) and jpeg == b"x"


def _event(body: bytes, jpeg: bytes = b"x") -> bytes:
    return struct.pack("<H", len(body)) + body + jpeg


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x01",
        struct.pack("<H", 50) + b"{}x",                        # JSON length past the end
        struct.pack("<H", 0) + b"x",                           # empty JSON
        _event(b'{"alert_ms":1,"first_seen_ms":0,"dwell_s":1,"max_score":0.5}', b""),  # no snapshot
        _event(b"not json"),
        _event(b"\xff\xfe"),
        _event(b"[1, 2]"),
        _event(b'{"alert_ms":1,"first_seen_ms":0,"dwell_s":1}'),
        _event(b'{"alert_ms":1.5,"first_seen_ms":0,"dwell_s":1,"max_score":0.5}'),
        _event(b'{"alert_ms":true,"first_seen_ms":0,"dwell_s":1,"max_score":0.5}'),
        _event(b'{"alert_ms":1,"first_seen_ms":0,"dwell_s":1,"max_score":1.5}'),
        _event(b'{"alert_ms":1,"first_seen_ms":0,"dwell_s":-1,"max_score":0.5}'),
        _event(b'{"alert_ms":1,"first_seen_ms":0,"dwell_s":NaN,"max_score":0.5}'),
        _event(b'{"alert_ms":1,"first_seen_ms":2,"dwell_s":1,"max_score":0.5}'),  # first_seen after alert
        _event(b'{"alert_ms":-1,"first_seen_ms":-2,"dwell_s":1,"max_score":0.5}'),
    ],
)
def test_parse_event_rejects(payload):
    with pytest.raises(p.ProtocolError):
        p.parse_event(payload)


def test_alert_payload():
    assert json.loads(p.alert_payload()) == {"clip": "alert", "repeat": 1}
    assert json.loads(p.alert_payload(3)) == {"clip": "alert", "repeat": 3}


@pytest.mark.parametrize("repeat", [0, 11])
def test_alert_payload_rejects_bad_repeat(repeat):
    with pytest.raises(p.ProtocolError):
        p.alert_payload(repeat)


def test_cmd_payload():
    for action in ("start", "stop", "reboot", "status"):
        assert json.loads(p.cmd_payload(action)) == {"action": action}
    with pytest.raises(p.ProtocolError):
        p.cmd_payload("explode")


def test_validate_config_accepts_defaults():
    assert p.validate_config(dict(p.DEFAULT_CONFIG)) == p.DEFAULT_CONFIG
    assert {"threshold", "dwell_s", "max_gap_s", "cooldown_s"} <= set(p.DEFAULT_CONFIG)


def test_validate_config_accepts_detection_bounds():
    for cfg in ({"threshold": 0.05, "dwell_s": 0, "max_gap_s": 0.5, "cooldown_s": 0},
                {"threshold": 0.99, "dwell_s": 600, "max_gap_s": 60, "cooldown_s": 3600}):
        assert p.validate_config(cfg) == cfg


@pytest.mark.parametrize(
    "cfg",
    [
        {"volum": 50},
        {"volume": 150},
        {"volume": -1},
        {"jpeg_quality": 64},
        {"interval_ms": 50},
        {"frame_size": "vga"},
        {"volume": "loud"},
        {"volume": True},
        {"threshold": 1.0},
        {"threshold": 0.01},
        {"threshold": "high"},
        {"threshold": True},
        {"threshold": float("nan")},
        {"dwell_s": 601},
        {"max_gap_s": 0.4},
        {"cooldown_s": -1},
    ],
)
def test_validate_config_rejects(cfg):
    with pytest.raises(p.ProtocolError):
        p.validate_config(cfg)


def test_parse_config_args_converts_types():
    assert p.parse_config_args(["interval_ms=500", "frame_size=SVGA", "volume=60"]) == {
        "interval_ms": 500,
        "frame_size": "SVGA",
        "volume": 60,
    }


def test_parse_config_args_converts_floats():
    assert p.parse_config_args(["threshold=0.45", "dwell_s=2.5", "cooldown_s=0"]) == {
        "threshold": 0.45, "dwell_s": 2.5, "cooldown_s": 0.0,
    }


@pytest.mark.parametrize(
    "args",
    [["volume"], ["volume=abc"], ["=5"], ["volum=5"], ["threshold=abc"], ["threshold=nan"], ["dwell_s=inf"]],
)
def test_parse_config_args_rejects(args):
    with pytest.raises(p.ProtocolError):
        p.parse_config_args(args)


def test_merge_config_overrides_only_given_fields():
    merged = p.merge_config(p.DEFAULT_CONFIG, {"volume": 60})
    assert merged == {**p.DEFAULT_CONFIG, "volume": 60}


def test_merge_config_rejects_bad_update():
    with pytest.raises(p.ProtocolError):
        p.merge_config(p.DEFAULT_CONFIG, {"volume": 150})
