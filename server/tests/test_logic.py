from master.logic import Alert, DwellLogic

MAC = "a1b2c3d4e5f6"
POS, NEG = 0.9, 0.1


def make():
    return DwellLogic(threshold=0.6, dwell_s=5, max_gap_s=3, cooldown_s=30)


def feed(logic, frames, mac=MAC):
    """frames: list of (ts, conf). Returns list of ts at which an alert fired."""
    return [ts for ts, conf in frames if logic.update(mac, ts, conf)]


def test_alert_when_dwell_reached():
    logic = make()
    assert feed(logic, [(t, POS) for t in range(0, 6)]) == [5]


def test_no_alert_before_dwell():
    logic = make()
    assert feed(logic, [(t, POS) for t in range(0, 5)]) == []


def test_conf_equal_to_threshold_counts_as_positive():
    logic = make()
    assert feed(logic, [(t, 0.6) for t in range(0, 6)]) == [5]


def test_gap_longer_than_max_gap_resets_timer():
    logic = make()
    frames = [(0, POS), (1, POS), (2, POS)] + [(t, POS) for t in range(6, 12)]
    assert feed(logic, frames) == [11]


def test_single_negative_frame_does_not_reset():
    logic = make()
    frames = [(0, POS), (1, POS), (2, POS), (3, NEG), (4, POS), (5, POS)]
    assert feed(logic, frames) == [5]


def test_negatives_longer_than_max_gap_reset_timer():
    logic = make()
    frames = [(0, POS), (1, POS)] + [(t, NEG) for t in range(2, 6)] + [(t, POS) for t in range(6, 12)]
    assert feed(logic, frames) == [11]


def test_cooldown_suppresses_repeat_alerts():
    logic = make()
    assert feed(logic, [(t, POS) for t in range(0, 41)]) == [5, 35]


def test_out_of_order_and_duplicate_timestamps_ignored():
    logic = make()
    frames = [(t, POS) for t in range(0, 5)] + [(3, POS), (4, POS), (5, POS)]
    assert feed(logic, frames) == [5]


def test_reset_clears_state():
    logic = make()
    feed(logic, [(t, POS) for t in range(0, 5)])
    logic.reset(MAC)
    assert feed(logic, [(t, POS) for t in range(5, 11)]) == [10]


def test_reset_unknown_device_is_noop():
    make().reset("000000000000")


def test_devices_are_independent():
    logic = make()
    for t in range(0, 6):
        a = logic.update("aaaaaaaaaaaa", t, POS)
        b = logic.update("bbbbbbbbbbbb", t, NEG)
        assert b is None
    assert a is not None


def test_alert_carries_dwell_and_max_conf():
    logic = make()
    alert = None
    for t, conf in [(10, 0.7), (11, 0.95), (12, 0.8), (13, 0.7), (14, 0.7), (15, 0.7)]:
        alert = logic.update(MAC, t, conf) or alert
    assert alert == Alert(first_seen=10, ts=15, max_conf=0.95)
    assert alert.dwell_s == 5


def test_large_backward_clock_jump_resets_and_accepts():
    logic = make()
    feed(logic, [(t, POS) for t in range(1000, 1003)])  # clock was far ahead
    assert feed(logic, [(t, POS) for t in range(10, 16)]) == [15]
