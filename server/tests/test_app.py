import json

from master import protocol
from master.app import Frame, FrameSlots, MasterApp
from master.events import Alert

MAC = "a1b2c3d4e5f6"
START_MS = 1_727_600_000_000


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
        self.inferences = []
        self.devices = []

    def record(self, mac, alert, jpeg, mark_frame=False):
        if self.error:
            raise self.error
        self.recorded.append({"mac": mac, "alert": alert, "jpeg": jpeg, "mark_frame": mark_frame})

    def record_inference(self, mac, ts, conf, positive, dwell_s, alerted, jpeg,
                         device_score=None, match_event=False):
        if self.error:
            raise self.error
        self.inferences.append({"mac": mac, "ts": ts, "conf": conf, "positive": positive,
                                "dwell_s": dwell_s, "alerted": alerted, "jpeg": jpeg,
                                "device_score": device_score, "match_event": match_event})

    def update_device(self, mac, *, online=None, status=None, seen_ts=None):
        if self.error:
            raise self.error
        self.devices.append({"mac": mac, "online": online, "status": status, "seen_ts": seen_ts})


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def make_app(detector=None, events=None, clock=None, verify_dwell_s=5.0, verify_max_gap_s=3.0,
             verify_alert_cooldown_s=5.0):
    published = []

    def publish(topic, payload):
        published.append((topic, payload))

    app = MasterApp(detector=detector or FakeDetector(), events=events or FakeEvents(),
                    threshold=0.6, clock=clock or Clock(),
                    verify_threshold=0.8, verify_dwell_s=verify_dwell_s,
                    verify_max_gap_s=verify_max_gap_s,
                    verify_alert_cooldown_s=verify_alert_cooldown_s, publish=publish)
    app.published = published
    return app


def send_frame(app, ms=START_MS, score=0.8, dwell_s=1.5, mac=MAC):
    app.on_message(f"{mac}/image", protocol.pack_image(ms, b"jpeg", score, dwell_s))
    app.process_pending(timeout=0)


def event_payload(alert_ms=START_MS + 5000, first_seen_ms=START_MS, dwell_s=5.0, max_score=0.83):
    return protocol.pack_event(protocol.DeviceEvent(alert_ms, first_seen_ms, dwell_s, max_score), b"snap")


def test_stream_frame_recorded_with_both_scores():
    app = make_app()
    send_frame(app)
    [row] = app.events.inferences
    assert row == {"mac": MAC, "ts": START_MS / 1000, "conf": 0.9, "positive": True, "dwell_s": 1.5,
                   "alerted": False, "jpeg": b"jpeg", "device_score": 0.8, "match_event": True}


def test_failed_device_detection_recorded_as_none():
    app = make_app()
    send_frame(app, score=None)
    assert app.events.inferences[0]["device_score"] is None


def test_yolo_threshold_decides_positive():
    app = make_app(detector=FakeDetector(conf=0.1))
    send_frame(app, score=0.95)
    assert app.events.inferences[0]["positive"] is False


def test_unsynced_frame_uses_server_clock_and_never_matches():
    app = make_app(clock=Clock(500.0))
    send_frame(app, ms=0)
    row = app.events.inferences[0]
    assert row["ts"] == 500.0 and row["match_event"] is False


def test_event_recorded_with_device_values():
    app = make_app()
    app.on_message(f"{MAC}/event", event_payload())
    [rec] = app.events.recorded
    assert rec["mac"] == MAC and rec["jpeg"] == b"snap" and rec["mark_frame"] is True
    assert rec["alert"] == Alert(first_seen=START_MS / 1000, ts=(START_MS + 5000) / 1000, max_conf=0.83)


def test_unsynced_event_uses_server_clock():
    app = make_app(clock=Clock(1000.0))
    app.on_message(f"{MAC}/event", event_payload(alert_ms=0, first_seen_ms=0, dwell_s=5.0))
    [rec] = app.events.recorded
    assert rec["alert"] == Alert(first_seen=995.0, ts=1000.0, max_conf=0.83)
    assert rec["mark_frame"] is False


def test_malformed_event_dropped():
    app = make_app()
    app.on_message(f"{MAC}/event", b"\x05\x00{bad")
    assert app.events.recorded == []


def test_frames_and_events_mark_device_seen():
    app = make_app(clock=Clock(42.0))
    send_frame(app)
    app.on_message(f"{MAC}/event", event_payload())
    assert app.events.devices == [{"mac": MAC, "online": True, "status": None, "seen_ts": 42.0}] * 2


def test_status_updates_device():
    app = make_app(clock=Clock(42.0))
    text = json.dumps({"rssi": -70, "detect_ok": True})
    app.on_message(f"{MAC}/status", text.encode())
    assert app.events.devices == [{"mac": MAC, "online": True, "status": text, "seen_ts": 42.0}]


def test_retained_status_does_not_bump_seen():
    app = make_app(clock=Clock(42.0))
    app.on_message(f"{MAC}/status", b'{"rssi":-70}', retained=True)
    assert app.events.devices == [{"mac": MAC, "online": None, "status": '{"rssi":-70}', "seen_ts": None}]


def test_invalid_status_not_stored():
    app = make_app(clock=Clock(42.0))
    app.on_message(f"{MAC}/status", b"not json")
    app.on_message(f"{MAC}/status", b"[1]")
    assert [d["status"] for d in app.events.devices] == [None, None]


def test_deeply_nested_status_not_stored():
    app = make_app(clock=Clock(42.0))
    app.on_message(f"{MAC}/status", b"[" * 100000)
    assert [d["status"] for d in app.events.devices] == [None]


def test_online_messages():
    app = make_app(clock=Clock(42.0))
    app.on_message(f"{MAC}/online", b"1")
    app.on_message(f"{MAC}/online", b"0")
    app.on_message(f"{MAC}/online", b"1", retained=True)
    app.on_message(f"{MAC}/online", b"0", retained=True)
    assert [(d["online"], d["seen_ts"]) for d in app.events.devices] == [
        (True, 42.0), (False, None), (True, None), (False, None),
    ]


def test_short_payload_dropped():
    detector = FakeDetector()
    app = make_app(detector=detector)
    app.on_message(f"{MAC}/image", b"\x00" * 12)
    app.process_pending(timeout=0)
    assert detector.calls == 0


def test_unexpected_topics_ignored():
    detector = FakeDetector()
    app = make_app(detector=detector)
    payload = protocol.pack_image(1, b"jpeg")
    for t in ("foo", "a/b/image", "/image"):
        app.on_message(t, payload)
    app.process_pending(timeout=0)
    assert detector.calls == 0 and app.events.devices == []


def test_detector_error_records_no_inference():
    app = make_app(detector=FakeDetector(error=RuntimeError("boom")))
    send_frame(app)
    assert app.events.inferences == []


def test_event_store_errors_do_not_crash():
    app = make_app(events=FakeEvents(error=OSError("disk full")))
    send_frame(app)
    app.on_message(f"{MAC}/event", event_payload())
    app.on_message(f"{MAC}/status", b'{"rssi":-1}')
    app.on_message(f"{MAC}/online", b"0")


def test_frame_slots_keep_only_latest():
    slots = FrameSlots()
    old, new = Frame(1.0, True, 0.5, 0.0, b"old"), Frame(2.0, True, 0.6, 1.0, b"new")
    other = Frame(1.0, False, None, 0.0, b"other")
    slots.put(MAC, old)
    slots.put(MAC, new)
    slots.put("bbbbbbbbbbbb", other)
    assert slots.take_all(timeout=0) == {MAC: new, "bbbbbbbbbbbb": other}
    assert slots.take_all(timeout=0) == {}


def test_on_message_never_raises(monkeypatch):
    app = make_app()

    def boom(mac, payload):
        raise RuntimeError("bug in handler")

    monkeypatch.setattr(app, "_on_image", boom)
    app.on_message(f"{MAC}/image", protocol.pack_image(1, b"jpeg"))


def candidate_event(ms=START_MS, max_score=0.5):
    return protocol.pack_event(protocol.DeviceEvent(ms, ms, 0.0, max_score), b"snap")


def test_verify_rejects_below_threshold():
    app = make_app(detector=FakeDetector(conf=0.7))
    app.on_message(f"{MAC}/event", candidate_event())
    assert app.events.recorded == [] and app.published == []
    assert app.events.inferences[0]["device_score"] == 0.5


def test_verify_confirms_after_dwell():
    app = make_app(detector=FakeDetector(conf=0.85))
    for ms in (START_MS, START_MS + 2000, START_MS + 5000):
        app.on_message(f"{MAC}/event", candidate_event(ms))
    assert app.published == [(f"{MAC}/alert", protocol.alert_payload(1))]
    [rec] = app.events.recorded
    assert rec["mac"] == MAC and rec["jpeg"] == b"snap" and rec["mark_frame"] is True
    assert rec["alert"] == Alert(first_seen=START_MS / 1000, ts=(START_MS + 5000) / 1000, max_conf=0.85)


def test_verify_gap_restarts_window():
    app = make_app(detector=FakeDetector(conf=0.85))
    app.on_message(f"{MAC}/event", candidate_event(START_MS))
    app.on_message(f"{MAC}/event", candidate_event(START_MS + 7000))
    assert app.published == [] and app.events.recorded == []


def test_verify_unsynced_clock_uses_server_time():
    app = make_app(detector=FakeDetector(conf=0.85), clock=Clock(1000.0))
    for t in (1000.0, 1003.0, 1006.0):  # gaps 3 <= 3, span 6 >= 5
        app.clock.now = t
        app.on_message(f"{MAC}/event", candidate_event(0))
    assert app.published == [(f"{MAC}/alert", protocol.alert_payload(1))]


def test_verify_legacy_event_records_directly():
    detector = FakeDetector(conf=0.85)
    app = make_app(detector=detector)
    app.on_message(f"{MAC}/event", event_payload())
    assert detector.calls == 0 and app.published == []
    [rec] = app.events.recorded
    assert rec["alert"] == Alert(first_seen=START_MS / 1000, ts=(START_MS + 5000) / 1000, max_conf=0.83)


def test_verify_cooldown_gates_second_command():
    # Dwell 1 s so a second window can confirm inside the 5 s command cooldown.
    app = make_app(detector=FakeDetector(conf=0.85), clock=Clock(1000.0),
                   verify_dwell_s=1.0, verify_max_gap_s=3.0)
    for t in (1000.0, 1001.0):  # first window confirms
        app.on_message(f"{MAC}/event", candidate_event(0))
    for t in (1002.0, 1003.0):  # second window confirms 2 s later
        app.clock.now = t
        app.on_message(f"{MAC}/event", candidate_event(0))
    assert len(app.published) == 1


def test_verify_high_device_score_still_scored_by_host():
    detector = FakeDetector(conf=0.4)
    app = make_app(detector=detector)
    app.on_message(f"{MAC}/event", candidate_event(max_score=0.95))
    assert detector.calls == 1 and app.published == [] and app.events.recorded == []
    assert app.events.inferences[0]["conf"] == 0.4


def test_verify_zero_dwell_confirms_on_first_event():
    app = make_app(detector=FakeDetector(conf=0.85), verify_dwell_s=0.0)
    app.on_message(f"{MAC}/event", candidate_event())
    assert app.published == [(f"{MAC}/alert", protocol.alert_payload(1))]


def test_verify_fresh_app_never_confirms_stale_window():
    app = make_app(detector=FakeDetector(conf=0.85))
    app.on_message(f"{MAC}/event", candidate_event())
    assert app.published == [] and app.events.recorded == []
