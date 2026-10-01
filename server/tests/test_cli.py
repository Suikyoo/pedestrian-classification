import json

import pytest

from master import protocol
from master.cli import build_message

MAC = "a1b2c3d4e5f6"


def test_alert_default_repeat():
    assert build_message(["alert", MAC]) == (f"{MAC}/alert", protocol.alert_payload(1), 1, False)


def test_alert_with_repeat():
    t, payload, _, _ = build_message(["alert", MAC, "--repeat", "3"])
    assert json.loads(payload)["repeat"] == 3


@pytest.mark.parametrize("action", ["start", "stop", "reboot", "status"])
def test_commands(action):
    assert build_message([action, MAC]) == (f"{MAC}/cmd", protocol.cmd_payload(action), 1, False)


def test_config_merges_into_current_and_is_retained():
    current = {**protocol.DEFAULT_CONFIG, "volume": 30}
    t, payload, qos, retain = build_message(["config", MAC, "interval_ms=500"], current)
    assert (t, qos, retain) == (f"{MAC}/config", 1, True)
    assert json.loads(payload) == {**current, "interval_ms": 500}


def test_config_without_current_publishes_only_updates():
    _, payload, _, _ = build_message(["config", MAC, "volume=60"], None)
    assert json.loads(payload) == {"volume": 60}


@pytest.mark.parametrize("args", [["volum=50"], ["volume=150"], ["frame_size=vga"], []])
def test_config_rejects_bad_values(args):
    with pytest.raises(protocol.ProtocolError):
        build_message(["config", MAC, *args], None)


@pytest.mark.parametrize("mac", ["A1B2C3D4E5F6", "a1:b2:c3:d4:e5:f6", "xyz"])
def test_rejects_malformed_mac(mac):
    with pytest.raises(protocol.ProtocolError):
        build_message(["status", mac])


def test_retained_config_accepts_object_on_own_topic():
    from master.cli import parse_retained_config

    assert parse_retained_config(f"{MAC}/config", MAC, b'{"volume": 60}') == {"volume": 60}


@pytest.mark.parametrize(
    "topic, payload",
    [
        (f"{MAC}/online", b'{"volume": 60}'),
        (f"{MAC}/config", b"0"),
        (f"{MAC}/config", b"[1, 2]"),
        (f"{MAC}/config", b"not json"),
        (f"{MAC}/config", b""),
    ],
)
def test_retained_config_rejects_other_topics_and_non_objects(topic, payload):
    from master.cli import parse_retained_config

    assert parse_retained_config(topic, MAC, payload) is None


class FakeInfo:
    def __init__(self, published):
        self.published = published

    def wait_for_publish(self, timeout=None):
        pass

    def is_published(self):
        return self.published


class FakeClient:
    def __init__(self, published):
        self.published = published

    def publish(self, topic, payload, qos=0, retain=False):
        return FakeInfo(self.published)


@pytest.mark.parametrize("published, expected", [(True, True), (False, False)])
def test_publish_confirmed_reports_delivery(published, expected):
    from master.cli import publish_confirmed

    assert publish_confirmed(FakeClient(published), f"{MAC}/cmd", b"{}", 1, False) is expected
