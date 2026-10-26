# One image for both server processes: `python -m master.app` and `python -m master.web`.
FROM python:3.12-slim

# OpenCV (pulled in by ultralytics) needs these shared libraries at import time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

# CPU-only PyTorch first, so ultralytics does not pull the multi-GB CUDA wheels.
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

WORKDIR /app

# Dependencies from pyproject.toml, in their own layer so code changes do not reinstall them.
COPY pyproject.toml ./
RUN mkdir master && touch master/__init__.py && pip install . && pip uninstall -y pedestrian-master

COPY master ./master
RUN pip install --no-deps . && rm -rf build master

# Bake the YOLO weights into the image: *.pt files are not in git.
# MODEL defaults to the small variant (nano was too weak on real scenes);
# override at build time to fall back: docker build --build-arg MODEL=yolo11n.pt
ARG MODEL=yolo11s.pt
RUN mkdir -p /opt/models \
    && cd /opt/models \
    && python -c "from ultralytics import YOLO; YOLO('$MODEL')" \
    && rm -rf /root/.config/Ultralytics

RUN useradd --uid 1000 --create-home app \
    && mkdir -p /data/events \
    && chown app:app /data/events
USER app

ENV MODEL_PATH=/opt/models/$MODEL \
    EVENTS_DIR=/data/events \
    YOLO_CONFIG_DIR=/home/app/.config

CMD ["python", "-m", "master.app"]
