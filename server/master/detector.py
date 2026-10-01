"""YOLO person detector. The only module that imports ultralytics."""

import io

from PIL import Image

PERSON_CLASS = 0  # COCO


class Detector:
    def __init__(self, model_path: str, device: str):
        from ultralytics import YOLO

        self._model = YOLO(model_path)
        self._device = device

    def person_confidence(self, jpeg: bytes) -> float:
        """Highest person confidence in the frame, or 0.0 if no person is found."""
        img = Image.open(io.BytesIO(jpeg)).convert("RGB")
        result = self._model.predict(
            img, classes=[PERSON_CLASS], conf=0.05, device=self._device, verbose=False
        )[0]
        if result.boxes is None or len(result.boxes) == 0:
            return 0.0
        return float(result.boxes.conf.max())
