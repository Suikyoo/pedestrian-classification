from master.events import EventStore
from master.logic import Alert

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
            "snapshot": str(path),
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
