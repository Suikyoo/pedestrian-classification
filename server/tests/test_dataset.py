from master import protocol
from master.dataset import DatasetSink
from tests.test_app import MAC, START_MS, FakeDetector, candidate_event, make_app


def test_sink_writes_exact_bytes_and_no_part_files(tmp_path):
    sink = DatasetSink(tmp_path / "ds")
    path = sink.save(MAC, 1234.5, b"jpegbytes")
    assert path == tmp_path / "ds" / MAC / "1234500.jpg"
    assert path.read_bytes() == b"jpegbytes"
    assert list((tmp_path / "ds").rglob("*.part")) == []


def test_sink_same_millisecond_does_not_overwrite(tmp_path):
    sink = DatasetSink(tmp_path)
    a, b = sink.save(MAC, 1.0, b"a"), sink.save(MAC, 1.0, b"b")
    assert a != b and a.read_bytes() == b"a" and b.read_bytes() == b"b"


def test_sink_sanitizes_device_id(tmp_path):
    path = DatasetSink(tmp_path).save("../../evil", 1.0, b"x")
    assert path.resolve().is_relative_to(tmp_path.resolve())


def test_app_archives_frames_and_events(tmp_path):
    app = make_app(detector=FakeDetector(conf=0.1))
    app.dataset = DatasetSink(tmp_path)
    app.on_message(f"{MAC}/image", protocol.pack_image(START_MS, b"frame", 0.8))
    app.on_message(f"{MAC}/event", candidate_event(START_MS + 1000))
    names = sorted(p.read_bytes() for p in (tmp_path / MAC).glob("*.jpg"))
    assert names == [b"frame", b"snap"]


def test_app_survives_archive_failure():
    class Broken:
        def save(self, *a):
            raise OSError("disk full")

    app = make_app()
    app.dataset = Broken()
    app.on_message(f"{MAC}/image", protocol.pack_image(START_MS, b"frame", 0.8))
    app.process_pending(timeout=0)
    assert len(app.events.inferences) == 1
