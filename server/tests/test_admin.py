import base64
import json

import pytest
from fastapi.testclient import TestClient

from master import protocol
from master.settings import Settings
from master.web import create_app

MAC = "a1b2c3d4e5f6"
AUTH = {"Authorization": "Basic " + base64.b64encode(b"admin:secret").decode()}
POST = {**AUTH, "X-Requested-With": "admin-ui"}


class FakeLink:
    def __init__(self, config=None, connected=True, confirms=True):
        self._config, self._connected, self.confirms = config, connected, confirms
        self.sent = []

    def config(self, mac):
        return self._config

    def connected(self):
        return self._connected

    def publish(self, topic, payload, retain=False, timeout=5.0):
        self.sent.append((topic, payload, retain))
        return self.confirms


def make(tmp_path, link=None, password="secret"):
    s = Settings(_env_file=None, events_dir=tmp_path, admin_password=password)
    return TestClient(create_app(s, admin_link=link or FakeLink()))


def test_admin_off_without_password(tmp_path):
    c = make(tmp_path, password="")
    assert c.get("/admin").status_code == 404
    assert c.post(f"/api/admin/devices/{MAC}/command", json={"action": "stop"}).status_code == 404


def test_requires_auth(tmp_path):
    c = make(tmp_path)
    assert c.get("/admin").status_code == 401
    assert c.get("/admin", headers={"Authorization": "Basic " + base64.b64encode(b"admin:wrong").decode()}).status_code == 401
    assert c.get(f"/api/admin/devices/{MAC}/config").status_code == 401
    assert c.post(f"/api/admin/devices/{MAC}/command", json={"action": "stop"}).status_code == 401
    assert c.get("/admin", headers=AUTH).status_code == 200


def test_post_needs_csrf_header(tmp_path):
    link = FakeLink()
    c = make(tmp_path, link)
    r = c.post(f"/api/admin/devices/{MAC}/command", json={"action": "reboot"}, headers=AUTH)
    assert r.status_code == 403 and link.sent == []


def test_command_publishes(tmp_path):
    link = FakeLink()
    r = make(tmp_path, link).post(f"/api/admin/devices/{MAC}/command", json={"action": "start"}, headers=POST)
    assert r.status_code == 200
    assert link.sent == [(f"{MAC}/cmd", protocol.cmd_payload("start"), False)]


def test_command_rejects_unknown_action(tmp_path):
    link = FakeLink()
    r = make(tmp_path, link).post(f"/api/admin/devices/{MAC}/command", json={"action": "format"}, headers=POST)
    assert r.status_code == 422 and link.sent == []


def test_alert_publishes_and_validates(tmp_path):
    link = FakeLink()
    c = make(tmp_path, link)
    assert c.post(f"/api/admin/devices/{MAC}/alert", json={"repeat": 3}, headers=POST).status_code == 200
    assert link.sent == [(f"{MAC}/alert", protocol.alert_payload(3), False)]
    assert c.post(f"/api/admin/devices/{MAC}/alert", json={"repeat": 99}, headers=POST).status_code == 422
    assert c.post(f"/api/admin/devices/{MAC}/alert", json={"repeat": True}, headers=POST).status_code == 422


def test_config_merges_into_retained_and_publishes_retained(tmp_path):
    link = FakeLink(config={"volume": 80, "threshold": 0.6})
    r = make(tmp_path, link).post(f"/api/admin/devices/{MAC}/config", json={"fields": {"volume": 40}}, headers=POST)
    assert r.status_code == 200 and r.json()["config"] == {"volume": 40, "threshold": 0.6}
    [(topic, payload, retain)] = link.sent
    assert topic == f"{MAC}/config" and retain is True
    assert json.loads(payload) == {"volume": 40, "threshold": 0.6}


def test_config_without_retained_sends_only_given_fields(tmp_path):
    link = FakeLink()
    make(tmp_path, link).post(f"/api/admin/devices/{MAC}/config", json={"fields": {"cooldown_s": 1}}, headers=POST)
    assert json.loads(link.sent[0][1]) == {"cooldown_s": 1}


@pytest.mark.parametrize("fields", [{"volume": 500}, {"nope": 1}, {"frame_size": "HUGE"}, {}, [], "x"])
def test_config_rejects_bad_fields(tmp_path, fields):
    link = FakeLink()
    r = make(tmp_path, link).post(f"/api/admin/devices/{MAC}/config", json={"fields": fields}, headers=POST)
    assert r.status_code == 422 and link.sent == []


def test_rejects_bad_device_id_and_body(tmp_path):
    link = FakeLink()
    c = make(tmp_path, link)
    assert c.post("/api/admin/devices/a%23b/command", json={"action": "stop"}, headers=POST).status_code == 400
    assert c.post(f"/api/admin/devices/{MAC}/command", content=b"not json", headers=POST).status_code == 400
    assert c.post(f"/api/admin/devices/{MAC}/command", json=[1], headers=POST).status_code == 400
    assert link.sent == []


def test_broker_down_or_unconfirmed(tmp_path):
    body = {"action": "stop"}
    r = make(tmp_path, FakeLink(connected=False)).post(f"/api/admin/devices/{MAC}/command", json=body, headers=POST)
    assert r.status_code == 503
    r = make(tmp_path, FakeLink(confirms=False)).post(f"/api/admin/devices/{MAC}/command", json=body, headers=POST)
    assert r.status_code == 504


def test_get_config_returns_cached_and_defaults(tmp_path):
    r = make(tmp_path, FakeLink(config={"volume": 10})).get(f"/api/admin/devices/{MAC}/config", headers=AUTH)
    body = r.json()
    assert body["config"] == {"volume": 10} and body["connected"] is True
    assert body["defaults"] == protocol.DEFAULT_CONFIG and "VGA" in body["frame_sizes"]
