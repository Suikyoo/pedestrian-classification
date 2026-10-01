import json

from master import protocol
from master.app import FrameSlots, MasterApp
from master.logic import DwellLogic

MAC = "a1b2c3d4e5f6"


class FakeDetector:
    def __init__(self, conf=0.9, error=None):
        self.conf = conf
        self.error = error
        self.calls = 0

    def person_confidence(self, jpeg):
        self.calls += 1
        if self.error:
            raise self.error
        return self.conf


class FakeEvents:
    def __init__(self, error=None):
        self.error = error
        self.recorded = []

    def record(self, mac, alert, jpeg):
        if self.error:
            raise self.error
        self.recorded.append((mac, alert, jpeg))


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def make_app(detector=None, events=None, clock=None):
    published = []
    app = MasterApp(
        detector=detector or FakeDetector(),
        logic=DwellLogic(threshold=0.6, dwell_s=5, max_gap_s=3, cooldown_s=30),
        events=events or FakeEvents(),
        publish=lambda t, p, q, r: published.append((t, p, q, r)),
        clock=clock or Clock(),
    )
    return app, published


def send_frames(app, mac, seconds, start_ms=1_727_600_000_000):
    for s in seconds:
        app.on_message(f"{mac}/image", protocol.pack_image(start_ms + s * 1000, b"jpeg"))
        app.process_pending(timeout=0)


def test_alert_published_after_dwell():
    app, published = make_app()
    send_frames(app, MAC, range(0, 6))
    assert published == [(f"{MAC}/alert", protocol.alert_payload(1), 1, False)]


def test_alert_recorded_in_events():
    events = FakeEvents()
    app, _ = make_app(events=events)
    send_frames(app, MAC, range(0, 6))
    assert len(events.recorded) == 1
    mac, alert, jpeg = events.recorded[0]
    assert mac == MAC and jpeg == b"jpeg" and alert.dwell_s == 5


def test_no_alert_for_negative_frames():
    app, published = make_app(detector=FakeDetector(conf=0.1))
    send_frames(app, MAC, range(0, 10))
    assert published == []


def test_short_payload_dropped():
    detector = FakeDetector()
    app, published = make_app(detector=detector)
    app.on_message(f"{MAC}/image", b"\x00" * 8)
    app.process_pending(timeout=0)
    assert detector.calls == 0 and published == []


def test_unexpected_topics_ignored():
    detector = FakeDetector()
    app, published = make_app(detector=detector)
    payload = protocol.pack_image(1, b"jpeg")
    for t in ("foo", "a/b/image", "/image"):
        app.on_message(t, payload)
    app.process_pending(timeout=0)
    assert detector.calls == 0 and published == []


def test_detector_error_does_not_crash():
    app, published = make_app(detector=FakeDetector(error=RuntimeError("boom")))
    send_frames(app, MAC, range(0, 6))
    assert published == []


def test_event_store_error_still_publishes_alert():
    app, published = make_app(events=FakeEvents(error=OSError("disk full")))
    send_frames(app, MAC, range(0, 6))
    assert len(published) == 1


def test_capture_ms_zero_uses_server_clock():
    clock = Clock(now=500.0)
    app, published = make_app(clock=clock)
    for i in range(6):
        clock.now = 500.0 + i
        app.on_message(f"{MAC}/image", protocol.pack_image(0, b"jpeg"))
        app.process_pending(timeout=0)
    assert len(published) == 1


def test_timestamp_source_change_resets_state():
    # Server clock is far ahead of the device clock. Without a reset, device
    # timestamps would look "older" and be ignored as out of order.
    clock = Clock(now=9_999_999_999.0)
    app, published = make_app(clock=clock)
    for i in range(3):
        clock.now += 1
        app.on_message(f"{MAC}/image", protocol.pack_image(0, b"jpeg"))
        app.process_pending(timeout=0)
    send_frames(app, MAC, range(0, 6))
    assert len(published) == 1


def test_offline_resets_state():
    app, published = make_app()
    send_frames(app, MAC, range(0, 4))
    app.on_message(f"{MAC}/online", b"0")
    send_frames(app, MAC, range(4, 9))
    assert published == []
    send_frames(app, MAC, [9])
    assert len(published) == 1


def test_status_message_is_accepted():
    app, published = make_app()
    app.on_message(f"{MAC}/status", json.dumps({"rssi": -70}).encode())
    app.on_message(f"{MAC}/status", b"not json")
    assert published == []


def test_frame_slots_keep_only_latest():
    slots = FrameSlots()
    slots.put(MAC, 1.0, b"old")
    slots.put(MAC, 2.0, b"new")
    slots.put("bbbbbbbbbbbb", 1.0, b"other")
    assert slots.take_all(timeout=0) == {MAC: (2.0, b"new"), "bbbbbbbbbbbb": (1.0, b"other")}
    assert slots.take_all(timeout=0) == {}


def test_on_message_never_raises(monkeypatch):
    app, _ = make_app()

    def boom(mac, payload):
        raise RuntimeError("bug in handler")

    monkeypatch.setattr(app, "_on_image", boom)
    app.on_message(f"{MAC}/image", protocol.pack_image(1, b"jpeg"))
