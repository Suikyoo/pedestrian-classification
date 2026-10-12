"""Master service: records device warnings and status; scores stream-mode frames with YOLO.

Devices decide alerts themselves. The master never publishes {mac}/alert on its own.
"""

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import paho.mqtt.client as mqtt

from master import protocol
from master.events import Alert

log = logging.getLogger("master")


@dataclass(frozen=True)
class Frame:
    ts: float                    # Unix seconds: device capture time, or server time when not synced
    synced: bool                 # ts came from the device clock
    device_score: float | None
    dwell_s: float
    jpeg: bytes


class FrameSlots:
    """Latest unprocessed frame per device. A new frame overwrites the old one."""

    def __init__(self):
        self._slots: dict[str, Frame] = {}
        self._cond = threading.Condition()

    def put(self, mac: str, frame: Frame) -> None:
        with self._cond:
            self._slots[mac] = frame
            self._cond.notify()

    def take_all(self, timeout: float | None) -> dict[str, Frame]:
        with self._cond:
            if not self._slots:
                self._cond.wait(timeout)
            items, self._slots = self._slots, {}
            return items


class MasterApp:
    def __init__(self, detector, events, threshold: float, clock: Callable[[], float] = time.time):
        self.detector = detector
        self.events = events
        self.threshold = threshold  # YOLO cutoff for stream-mode frames
        self.clock = clock
        self.slots = FrameSlots()

    # Called on the MQTT network thread. Must never raise: an exception here
    # stops paho's network loop and the server would stop receiving.
    def on_message(self, topic: str, payload: bytes, retained: bool = False) -> None:
        try:
            self._dispatch(topic, payload, retained)
        except Exception:
            log.exception("error handling message on %r", topic)

    def _dispatch(self, topic: str, payload: bytes, retained: bool) -> None:
        parsed = protocol.parse_topic(topic)
        if parsed is None:
            log.warning("ignoring message on unexpected topic %r", topic)
            return
        mac, kind = parsed
        if kind == "image":
            self._on_image(mac, payload)
        elif kind == "event":
            self._on_event(mac, payload)
        elif kind == "status":
            self._on_status(mac, payload, retained)
        elif kind == "online":
            self._on_online(mac, payload, retained)

    def _update_device(self, mac: str, **fields) -> None:
        try:
            self.events.update_device(mac, **fields)
        except Exception:
            log.exception("%s: failed to update device", mac)

    def _on_image(self, mac: str, payload: bytes) -> None:
        try:
            img = protocol.parse_image(payload)
        except protocol.ProtocolError as e:
            log.warning("%s: dropping frame: %s", mac, e)
            return
        now = self.clock()
        synced = img.capture_ms != 0
        ts = img.capture_ms / 1000 if synced else now
        self.slots.put(mac, Frame(ts, synced, img.score, img.dwell_s, img.jpeg))
        self._update_device(mac, online=True, seen_ts=now)

    def _on_event(self, mac: str, payload: bytes) -> None:
        try:
            ev, jpeg = protocol.parse_event(payload)
        except protocol.ProtocolError as e:
            log.warning("%s: dropping event: %s", mac, e)
            return
        now = self.clock()
        if ev.alert_ms:
            alert = Alert(first_seen=ev.first_seen_ms / 1000, ts=ev.alert_ms / 1000, max_conf=ev.max_score)
        else:
            alert = Alert(first_seen=now - ev.dwell_s, ts=now, max_conf=ev.max_score)
        log.info("%s WARNING dwell=%.1fs max_score=%.2f", mac, alert.dwell_s, alert.max_conf)
        try:
            self.events.record(mac, alert, jpeg, mark_frame=ev.alert_ms != 0)
        except Exception:
            log.exception("%s: failed to record event", mac)
        self._update_device(mac, online=True, seen_ts=now)

    def _on_status(self, mac: str, payload: bytes, retained: bool) -> None:
        text = payload.decode("utf-8", "replace")
        try:
            ok = isinstance(json.loads(text), dict)
        except (ValueError, RecursionError):
            ok = False
        if not ok:
            log.warning("%s: status is not a JSON object: %r", mac, text[:200])
        status = text if ok else None
        if retained:  # sent by the broker on subscribe: says nothing about now
            self._update_device(mac, status=status)
        else:
            self._update_device(mac, online=True, status=status, seen_ts=self.clock())

    def _on_online(self, mac: str, payload: bytes, retained: bool) -> None:
        if payload == b"0":
            log.warning("%s offline", mac)
            self._update_device(mac, online=False)
        else:
            log.info("%s online", mac)
            self._update_device(mac, online=True, seen_ts=None if retained else self.clock())

    # Called on the worker thread.
    def process(self, mac: str, frame: Frame) -> None:
        try:
            conf = self.detector.person_confidence(frame.jpeg)
        except Exception:
            log.exception("%s: detection failed, dropping frame", mac)
            return
        try:
            self.events.record_inference(mac, frame.ts, conf, conf >= self.threshold, frame.dwell_s,
                                         False, frame.jpeg, device_score=frame.device_score,
                                         match_event=frame.synced)
        except Exception:
            log.exception("%s: failed to record inference", mac)

    def process_pending(self, timeout: float | None = 0.5) -> None:
        for mac, frame in self.slots.take_all(timeout).items():
            self.process(mac, frame)

    def run_worker(self, stop: threading.Event) -> None:
        while not stop.is_set():
            self.process_pending()


def connect(app: MasterApp, host: str, port: int, user: str, password: str,
            client_id: str = "master") -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    if user or password:
        client.username_pw_set(user, password or None)

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("MQTT connect failed: %s", reason_code)
            return
        log.info("MQTT connected to %s:%s", host, port)
        c.subscribe([("+/image", 0), ("+/event", 1), ("+/status", 1), ("+/online", 1)])

    def on_disconnect(c, userdata, flags, reason_code, properties):
        log.warning("MQTT disconnected: %s", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = lambda c, u, m: app.on_message(m.topic, m.payload, bool(m.retain))
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(host, port, keepalive=30)
    client.loop_start()
    return client


def main() -> None:
    from master.detector import Detector
    from master.events import EventStore
    from master.settings import Settings

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = Settings()
    app = MasterApp(
        detector=Detector(s.model_path, s.device),
        events=EventStore(s.events_dir, history=s.inference_history),
        threshold=s.pedestrian_conf_threshold,
    )
    client = connect(app, s.mqtt_host, s.mqtt_port, s.mqtt_user, s.mqtt_pass)
    stop = threading.Event()
    try:
        app.run_worker(stop)
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        client.loop_stop()
        client.disconnect()
        app.events.close()


if __name__ == "__main__":
    main()
