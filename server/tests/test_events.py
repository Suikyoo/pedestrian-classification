from pathlib import Path
from master.events import Alert, EventStore

MAC = "a1b2c3d4e5f6"


def test_record_writes_row_and_snapshot(tmp_path):
    store = EventStore(tmp_path / "events")
    alert = Alert(first_seen=1_727_600_000.0, ts=1_727_600_005.5, max_conf=0.91)

    path = store.record(MAC, alert, b"\xff\xd8jpeg")

    assert path == tmp_path / "events" / MAC / "1727600005500.jpg"
    assert path.read_bytes() == b"\xff\xd8jpeg"
    rows = store.recent()
    assert rows == [
        {
            "mac": MAC,
            "alert_ts": 1_727_600_005.5,
            "first_seen_ts": 1_727_600_000.0,
            "dwell_s": 5.5,
            "max_conf": 0.91,
            "snapshot": f"{MAC}/1727600005500.jpg",
        }
    ]
    store.close()


def test_recent_is_newest_first_and_limited(tmp_path):
    store = EventStore(tmp_path)
    for i in range(3):
        store.record(MAC, Alert(first_seen=i, ts=i + 5, max_conf=0.8), b"x")
    rows = store.recent(limit=2)
    assert [r["alert_ts"] for r in rows] == [7, 6]
    store.close()


def test_data_survives_reopen(tmp_path):
    store = EventStore(tmp_path)
    store.record(MAC, Alert(first_seen=0, ts=5, max_conf=0.8), b"x")
    store.close()
    store = EventStore(tmp_path)
    assert len(store.recent()) == 1
    store.close()
import io
import sqlite3

import pytest
from PIL import Image


def _jpeg(w, h, color=(200, 100, 50)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG")
    return buf.getvalue()


def test_record_inference_writes_thumbnail_and_row(tmp_path):
    store = EventStore(tmp_path)
    path = store.record_inference(MAC, 1_790_000_000.25, 0.91, True, 3.0, False, _jpeg(640, 480))

    assert path == tmp_path / "thumbs" / MAC / "1790000000250.jpg"
    with Image.open(path) as img:
        assert img.size == (320, 240)
    [row] = store.inferences(MAC)
    assert row["mac"] == MAC
    assert row["ts"] == 1_790_000_000.25
    assert row["conf"] == 0.91
    assert row["positive"] == 1
    assert row["dwell_s"] == 3.0
    assert row["alerted"] == 0
    assert row["thumb"] == f"thumbs/{MAC}/1790000000250.jpg"
    store.close()


def test_small_frames_are_not_upscaled(tmp_path):
    store = EventStore(tmp_path)
    path = store.record_inference(MAC, 1.0, 0.1, False, 0.0, False, _jpeg(160, 120))
    with Image.open(path) as img:
        assert img.size == (160, 120)
    store.close()


def test_pruning_keeps_newest_per_device(tmp_path):
    store = EventStore(tmp_path, history=3)
    paths = [store.record_inference(MAC, float(t), 0.5, False, 0.0, False, _jpeg(64, 48)) for t in range(5)]
    other = store.record_inference("bbbbbbbbbbbb", 1.0, 0.5, False, 0.0, False, _jpeg(64, 48))

    assert [r["ts"] for r in store.inferences(MAC)] == [4.0, 3.0, 2.0]
    assert not paths[0].exists() and not paths[1].exists()
    assert all(p.exists() for p in paths[2:])
    assert other.exists() and len(store.inferences("bbbbbbbbbbbb")) == 1
    store.close()


def test_record_inference_rejects_garbage(tmp_path):
    store = EventStore(tmp_path)
    with pytest.raises(Exception):
        store.record_inference(MAC, 1.0, 0.5, False, 0.0, False, b"not a jpeg")
    assert store.inferences(MAC) == []
    store.close()


def test_wal_mode_enabled(tmp_path):
    EventStore(tmp_path).close()
    con = sqlite3.connect(tmp_path / "events.db")
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    con.close()


@pytest.mark.parametrize("mac", ["../../evil", "<img src=x onerror=alert(1)>", "a/b", ""])
def test_unsafe_device_ids_stay_inside_root(tmp_path, mac):
    root = tmp_path / "events"
    store = EventStore(root)
    thumb = store.record_inference(mac, 1.0, 0.5, False, 0.0, False, _jpeg(64, 48))
    snap = store.record(mac, Alert(first_seen=0.0, ts=1.0, max_conf=0.5), b"\xff\xd8x")
    for p in (thumb, snap):
        assert p.resolve().is_relative_to(root.resolve())
        assert p.exists()
    assert store.inferences(mac)[0]["mac"] == mac
    store.close()


def test_old_snapshot_paths_migrated_to_root_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "events"
    EventStore(root).close()
    (root / MAC).mkdir()
    for name in ("1.jpg", "2.jpg", "3.jpg"):
        (root / MAC / name).write_bytes(b"x")
    con = sqlite3.connect(root / "events.db")
    old_rows = [
        str(Path("events") / MAC / "1.jpg"),  # old default EVENTS_DIR=./events: cwd-relative
        str(root / MAC / "2.jpg"),            # old absolute EVENTS_DIR
        f"{MAC}/3.jpg",                       # already root-relative
    ]
    for snap in old_rows:
        con.execute(
            "INSERT INTO events (mac, alert_ts, first_seen_ts, dwell_s, max_conf, snapshot)"
            " VALUES (?, 1.0, 0.0, 1.0, 0.5, ?)", (MAC, snap))
    con.commit()
    con.close()

    store = EventStore(root)
    snaps = sorted(r["snapshot"] for r in store.recent())
    assert snaps == [f"{MAC}/1.jpg", f"{MAC}/2.jpg", f"{MAC}/3.jpg"]
    store.close()


def test_alert_dwell():
    assert Alert(first_seen=10.0, ts=15.5, max_conf=0.9).dwell_s == 5.5


def test_device_score_stored(tmp_path):
    store = EventStore(tmp_path)
    store.record_inference(MAC, 1.0, 0.9, True, 2.0, False, _jpeg(64, 48), device_score=0.42)
    store.record_inference(MAC, 2.0, 0.9, True, 3.0, False, _jpeg(64, 48))
    rows = store.inferences(MAC)
    assert [r["device_score"] for r in rows] == [None, 0.42]
    store.close()


def test_device_score_column_added_to_old_db(tmp_path):
    con = sqlite3.connect(tmp_path / "events.db")
    con.executescript(
        "CREATE TABLE inferences (id INTEGER PRIMARY KEY AUTOINCREMENT, mac TEXT NOT NULL,"
        " ts REAL NOT NULL, conf REAL NOT NULL, positive INTEGER NOT NULL, dwell_s REAL NOT NULL,"
        " alerted INTEGER NOT NULL, thumb TEXT NOT NULL);"
        "INSERT INTO inferences (mac, ts, conf, positive, dwell_s, alerted, thumb)"
        " VALUES ('a1b2c3d4e5f6', 1.0, 0.5, 0, 0.0, 0, 'thumbs/x.jpg');"
    )
    con.commit()
    con.close()
    store = EventStore(tmp_path)
    store.record_inference(MAC, 2.0, 0.9, True, 0.0, False, _jpeg(64, 48), device_score=0.7)
    assert [r["device_score"] for r in store.inferences(MAC)] == [0.7, None]
    store.close()


def test_frame_then_event_marks_frame(tmp_path):
    store = EventStore(tmp_path)
    store.record_inference(MAC, 100.5, 0.9, True, 5.0, False, _jpeg(64, 48), match_event=True)
    store.record_inference(MAC, 101.5, 0.9, True, 6.0, False, _jpeg(64, 48), match_event=True)
    store.record(MAC, Alert(first_seen=95.5, ts=100.5, max_conf=0.8), b"\xff\xd8x", mark_frame=True)
    assert {r["ts"]: r["alerted"] for r in store.inferences(MAC)} == {100.5: 1, 101.5: 0}
    store.close()


def test_event_then_frame_marks_frame(tmp_path):
    store = EventStore(tmp_path)
    store.record(MAC, Alert(first_seen=95.5, ts=100.5, max_conf=0.8), b"\xff\xd8x", mark_frame=True)
    store.record_inference(MAC, 100.5, 0.9, True, 5.0, False, _jpeg(64, 48), match_event=True)
    store.record_inference("bbbbbbbbbbbb", 100.5, 0.9, True, 5.0, False, _jpeg(64, 48), match_event=True)
    assert store.inferences(MAC)[0]["alerted"] == 1
    assert store.inferences("bbbbbbbbbbbb")[0]["alerted"] == 0  # other device
    store.close()


def test_no_matching_without_flags(tmp_path):
    store = EventStore(tmp_path)
    store.record_inference(MAC, 100.5, 0.9, True, 5.0, False, _jpeg(64, 48))
    store.record(MAC, Alert(first_seen=95.5, ts=100.5, max_conf=0.8), b"\xff\xd8x")
    store.record_inference(MAC, 100.5, 0.9, True, 5.0, False, _jpeg(64, 48))
    assert [r["alerted"] for r in store.inferences(MAC)] == [0, 0]
    store.close()


def test_duplicate_synced_event_recorded_once(tmp_path):
    store = EventStore(tmp_path)
    alert = Alert(first_seen=95.5, ts=100.5, max_conf=0.8)
    p1 = store.record(MAC, alert, b"\xff\xd8x", mark_frame=True)
    p2 = store.record(MAC, alert, b"\xff\xd8x", mark_frame=True)
    assert p1 == p2
    assert len(store.recent()) == 1
    store.close()


def test_unsynced_events_not_deduped(tmp_path):
    store = EventStore(tmp_path)
    alert = Alert(first_seen=95.5, ts=100.5, max_conf=0.8)
    store.record(MAC, alert, b"\xff\xd8x", mark_frame=False)
    store.record(MAC, alert, b"\xff\xd8x", mark_frame=False)
    assert len(store.recent()) == 2
    store.close()


def test_update_device_upserts_and_keeps_missing_fields(tmp_path):
    store = EventStore(tmp_path)
    store.update_device(MAC, online=True, status='{"rssi":-60}', seen_ts=10.0)
    store.update_device(MAC)  # nothing given: nothing changes
    assert store.devices() == [{"mac": MAC, "online": 1, "status": '{"rssi":-60}', "last_seen_ts": 10.0}]
    store.update_device(MAC, online=False)
    store.update_device(MAC, status='{"rssi":-70}')
    assert store.devices() == [{"mac": MAC, "online": 0, "status": '{"rssi":-70}', "last_seen_ts": 10.0}]
    store.update_device(MAC, online=True, seen_ts=20.0)
    assert store.devices()[0]["online"] == 1 and store.devices()[0]["last_seen_ts"] == 20.0
    store.close()


def test_update_device_offline_first(tmp_path):
    store = EventStore(tmp_path)
    store.update_device(MAC, online=False)
    assert store.devices() == [{"mac": MAC, "online": 0, "status": None, "last_seen_ts": None}]
    store.close()
