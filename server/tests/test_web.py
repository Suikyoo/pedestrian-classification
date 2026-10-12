import io
import json
import sqlite3
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from master.events import EventStore
from master.events import Alert
from master.settings import Settings
from master.web import create_app

MAC = "a1b2c3d4e5f6"
OTHER = "bbbbbbbbbbbb"


def _jpeg(w=64, h=48):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def root(tmp_path):
    return tmp_path / "events"


@pytest.fixture
def client(root):
    s = Settings(_env_file=None, events_dir=root, pedestrian_conf_threshold=0.6, inference_history=200)
    return TestClient(create_app(s))


STATUS = {"rssi": -60, "streaming": True, "detect_ok": True, "threshold": 0.55, "dwell_s": 4.0,
          "max_gap_s": 3.0, "cooldown_s": 20.0, "fw": "0.2.0"}


def _fill(root):
    store = EventStore(root)
    store.record_inference(MAC, 100.0, 0.9, True, 0.0, False, _jpeg(), device_score=0.7)
    store.record_inference(OTHER, 101.0, 0.1, False, 0.0, False, _jpeg())
    store.record_inference(MAC, 102.0, 0.8, True, 2.0, True, _jpeg(), device_score=0.75)
    store.record(MAC, Alert(first_seen=97.0, ts=102.0, max_conf=0.9), _jpeg())
    store.update_device(MAC, online=True, status=json.dumps(STATUS), seen_ts=103.0)
    store.update_device(OTHER, online=False, seen_ts=101.0)
    return store


def test_missing_db_returns_empty_lists(client):
    assert client.get("/api/inferences").json() == []
    assert client.get("/api/devices").json() == []
    assert client.get("/api/alerts").json() == []


def test_config(client):
    assert client.get("/api/config").json() == {"threshold": 0.6, "history": 200}


def test_inferences_newest_first_with_urls(client, root):
    _fill(root).close()
    rows = client.get("/api/inferences").json()
    assert [r["ts"] for r in rows] == [102.0, 101.0, 100.0]
    top = rows[0]
    assert top["mac"] == MAC and top["positive"] is True and top["alerted"] is True
    assert top["dwell_s"] == 2.0 and top["conf"] == 0.8
    assert top["thumb_url"] == f"/media/thumbs/{MAC}/102000.jpg"
    assert client.get(top["thumb_url"]).headers["content-type"] == "image/jpeg"


def test_inferences_filter_after_id_and_limit(client, root):
    _fill(root).close()
    mine = client.get("/api/inferences", params={"mac": MAC}).json()
    assert [r["ts"] for r in mine] == [102.0, 100.0]
    first_id = mine[-1]["id"]
    newer = client.get("/api/inferences", params={"after_id": first_id}).json()
    assert [r["ts"] for r in newer] == [102.0, 101.0]
    assert len(client.get("/api/inferences", params={"limit": 1}).json()) == 1
    assert len(client.get("/api/inferences", params={"limit": 0}).json()) == 1
    assert client.get("/api/inferences", params={"after_id": 10_000}).json() == []


def test_limit_clamped_to_500(client, root):
    store = EventStore(root, history=600)
    for t in range(510):
        store.record_inference(MAC, float(t), 0.5, False, 0.0, False, _jpeg(8, 8))
    store.close()
    assert len(client.get("/api/inferences", params={"limit": 9999}).json()) == 500


def test_devices(client, root):
    _fill(root).close()
    assert client.get("/api/devices").json() == [
        {"mac": MAC, "online": True, "last_seen_ts": 103.0, "count": 2,
         "last_ts": 102.0, "last_conf": 0.8, "last_device_score": 0.75, "last_positive": True,
         "last_dwell_s": 2.0, "last_alerted": True,
         "streaming": True, "detect_ok": True, "threshold": 0.55, "dwell_s": 4.0,
         "max_gap_s": 3.0, "cooldown_s": 20.0, "last_warning_ts": 102.0},
        {"mac": OTHER, "online": False, "last_seen_ts": 101.0, "count": 1,
         "last_ts": 101.0, "last_conf": 0.1, "last_device_score": None, "last_positive": False,
         "last_dwell_s": 0.0, "last_alerted": False,
         "streaming": None, "detect_ok": None, "threshold": None, "dwell_s": None,
         "max_gap_s": None, "cooldown_s": None, "last_warning_ts": None},
    ]


def test_device_without_frames_is_listed(client, root):
    store = EventStore(root)
    store.update_device(MAC, online=True, status=json.dumps(STATUS), seen_ts=50.0)
    store.close()
    [row] = client.get("/api/devices").json()
    assert row["mac"] == MAC and row["count"] == 0 and row["last_ts"] is None
    assert row["last_positive"] is None and row["last_alerted"] is None
    assert row["threshold"] == 0.55 and row["dwell_s"] == 4.0 and row["last_seen_ts"] == 50.0


@pytest.mark.parametrize("status", [
    '{"threshold":"high","detect_ok":1,"dwell_s":true,"streaming":"yes","cooldown_s":null}',
    "not json",
    "[1, 2]",
])
def test_status_fields_type_checked(client, root, status):
    store = EventStore(root)
    store.update_device(MAC, online=True, status=status, seen_ts=50.0)
    store.close()
    [row] = client.get("/api/devices").json()
    for key in ("threshold", "detect_ok", "dwell_s", "streaming", "cooldown_s", "max_gap_s"):
        assert row[key] is None


def test_devices_without_events_table(client, root):
    store = EventStore(root)
    store.update_device(MAC, online=True, seen_ts=1.0)
    store.close()
    con = sqlite3.connect(root / "events.db")
    con.execute("DROP TABLE events")
    con.commit()
    con.close()
    [row] = client.get("/api/devices").json()
    assert row["mac"] == MAC and row["last_warning_ts"] is None


def test_inferences_include_device_score(client, root):
    _fill(root).close()
    rows = client.get("/api/inferences").json()
    assert [r["device_score"] for r in rows] == [0.75, None, 0.7]


def test_alert_snapshot_urls_old_and_new(client, root):
    _fill(root).close()
    con = sqlite3.connect(root / "events.db")
    inside = root / MAC / "50000.jpg"
    inside.write_bytes(_jpeg())
    con.execute(
        "INSERT INTO events (mac, alert_ts, first_seen_ts, dwell_s, max_conf, snapshot)"
        " VALUES (?, 50.0, 45.0, 5.0, 0.7, ?)", (MAC, str(inside)))
    con.execute(
        "INSERT INTO events (mac, alert_ts, first_seen_ts, dwell_s, max_conf, snapshot)"
        " VALUES (?, 40.0, 35.0, 5.0, 0.7, ?)", (MAC, str(root.parent / "elsewhere.jpg")))
    con.commit()
    con.close()
    alerts = client.get("/api/alerts").json()
    by_ts = {a["ts"]: a for a in alerts}
    assert by_ts[102.0]["snapshot_url"] == f"/media/{MAC}/102000.jpg"
    assert by_ts[50.0]["snapshot_url"] == f"/media/{MAC}/50000.jpg"
    assert by_ts[40.0]["snapshot_url"] is None
    assert by_ts[102.0]["first_seen_ts"] == 97.0 and by_ts[102.0]["max_conf"] == 0.9


def test_media_rejects_escape(client, root):
    _fill(root).close()
    secret = root.parent / "secret.txt"
    secret.write_text("no")
    assert client.get("/media/..%2Fsecret.txt").status_code == 404
    assert client.get("/media/" + quote(str(secret), safe="")).status_code == 404
    assert client.get("/media/events.db-missing").status_code == 404


def test_reads_while_store_is_open(client, root):
    store = _fill(root)  # writer connection stays open
    store.record_inference(MAC, 103.0, 0.7, True, 3.0, False, _jpeg())
    assert client.get("/api/inferences").json()[0]["ts"] == 103.0
    store.close()


def test_mac_returned_verbatim(client, root):
    weird = "<img src=x onerror=alert(1)>"
    store = EventStore(root)
    store.record_inference(weird, 1.0, 0.5, False, 0.0, False, _jpeg())
    store.close()
    assert client.get("/api/inferences").json()[0]["mac"] == weird


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "/static/app.js" in r.text


def test_static_assets_served(client):
    for name, kind in (("app.js", "javascript"), ("style.css", "text/css")):
        r = client.get(f"/static/{name}")
        assert r.status_code == 200
        assert kind in r.headers["content-type"]


def test_page_has_no_external_resources(client):
    html = client.get("/").text
    js = client.get("/static/app.js").text
    assert "http://" not in html and "https://" not in html
    assert "innerHTML" not in js


def test_media_serves_only_jpeg(client, root):
    _fill(root).close()
    assert client.get("/media/events.db").status_code == 404
    (root / "notes.txt").write_text("x")
    assert client.get("/media/notes.txt").status_code == 404
