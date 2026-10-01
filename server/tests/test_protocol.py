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
    payload = p.pack_image(1_727_600_000_123, b"\xff\xd8jpeg")
    assert payload[:8] == struct.pack("<Q", 1_727_600_000_123)
    assert p.parse_image(payload) == (1_727_600_000_123, b"\xff\xd8jpeg")


@pytest.mark.parametrize("payload", [b"", b"\x00" * 7, b"\x00" * 8])
def test_parse_image_rejects_short_payload(payload):
    with pytest.raises(p.ProtocolError):
        p.parse_image(payload)


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


@pytest.mark.parametrize("args", [["volume"], ["volume=abc"], ["=5"], ["volum=5"]])
def test_parse_config_args_rejects(args):
    with pytest.raises(p.ProtocolError):
        p.parse_config_args(args)


def test_merge_config_overrides_only_given_fields():
    merged = p.merge_config(p.DEFAULT_CONFIG, {"volume": 60})
    assert merged == {**p.DEFAULT_CONFIG, "volume": 60}


def test_merge_config_rejects_bad_update():
    with pytest.raises(p.ProtocolError):
        p.merge_config(p.DEFAULT_CONFIG, {"volume": 150})
