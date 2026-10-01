import io

import pytest
from PIL import Image

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def detector():
    from master.detector import Detector

    return Detector("yolo11n.pt", "cpu")


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def test_person_image_scores_high(detector):
    from ultralytics.utils import ASSETS

    jpeg = _jpeg(Image.open(ASSETS / "bus.jpg").convert("RGB"))
    assert detector.person_confidence(jpeg) > 0.6


def test_empty_image_scores_low(detector):
    jpeg = _jpeg(Image.new("RGB", (640, 480), (128, 128, 128)))
    assert detector.person_confidence(jpeg) < 0.25


def test_garbage_bytes_raise(detector):
    with pytest.raises(Exception):
        detector.person_confidence(b"not a jpeg")
