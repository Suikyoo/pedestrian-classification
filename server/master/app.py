"""Master service: MQTT in, detection + dwell logic, alerts out."""

import logging
import threading
import time
from collections.abc import Callable

import paho.mqtt.client as mqtt

from master import protocol
from master.logic import DwellLogic

log = logging.getLogger("master")

Publish = Callable[[str, bytes, int, bool], None]  # (topic, payload, qos, retain)


class FrameSlots:
    """Latest unprocessed frame per device. A new frame overwrites the old one."""

    def __init__(self):
        self._slots: dict[str, tuple[float, bytes]] = {}
        self._cond = threading.Condition()

    def put(self, mac: str, ts: float, jpeg: bytes) -> None:
        with self._cond:
            self._slots[mac] = (ts, jpeg)
            self._cond.notify()

    def take_all(self, timeout: float | None) -> dict[str, tuple[float, bytes]]:
        with self._cond:
            if not self._slots:
                self._cond.wait(timeout)
            items, self._slots = self._slots, {}
            return items


class MasterApp:
    def __init__(self, detector, logic: DwellLogic, events, publish: Publish,
                 clock: Callable[[], float] = time.time):
        self.detector = detector
        self.logic = logic
        self.events = events
        self.publish = publish
        self.clock = clock
        self.slots = FrameSlots()
        self._lock = threading.Lock()  # guards logic and _ts_source across threads
        self._ts_source: dict[str, str] = {}  # mac -> "device" | "server"

    # Called on the MQTT network thread.
    def on_message(self, topic: str, payload: bytes) -> None:
        parsed = protocol.parse_topic(topic)
        if parsed is None:
            log.warning("ignoring message on unexpected topic %r", topic)
            return
        mac, kind = parsed
        if kind == "image":
            self._on_image(mac, payload)
        elif kind == "online":
            self._on_online(mac, payload)
        elif kind == "status":
            log.info("%s status %s", mac, payload.decode("utf-8", "replace"))

    def _on_image(self, mac: str, payload: bytes) -> None:
        try:
            capture_ms, jpeg = protocol.parse_image(payload)
        except protocol.ProtocolError as e:
            log.warning("%s: dropping frame: %s", mac, e)
            return
        source = "device" if capture_ms else "server"
        ts = capture_ms / 1000 if capture_ms else self.clock()
        with self._lock:
            previous = self._ts_source.get(mac)
            if previous is not None and previous != source:
                log.info("%s: timestamp source %s -> %s, resetting dwell", mac, previous, source)
                self.logic.reset(mac)
            self._ts_source[mac] = source
        self.slots.put(mac, ts, jpeg)

    def _on_online(self, mac: str, payload: bytes) -> None:
        if payload == b"0":
            log.warning("%s offline", mac)
            with self._lock:
                self.logic.reset(mac)
                self._ts_source.pop(mac, None)
        else:
            log.info("%s online", mac)

    # Called on the worker thread.
    def process(self, mac: str, ts: float, jpeg: bytes) -> None:
        try:
            conf = self.detector.person_confidence(jpeg)
        except Exception:
            log.exception("%s: detection failed, dropping frame", mac)
            return
        with self._lock:
            alert = self.logic.update(mac, ts, conf)
        if alert is None:
            return
        log.info("%s ALERT dwell=%.1fs max_conf=%.2f", mac, alert.dwell_s, alert.max_conf)
        self.publish(protocol.topic(mac, "alert"), protocol.alert_payload(1), 1, False)
        try:
            self.events.record(mac, alert, jpeg)
        except Exception:
            log.exception("%s: failed to record event", mac)

    def process_pending(self, timeout: float | None = 0.5) -> None:
        for mac, (ts, jpeg) in self.slots.take_all(timeout).items():
            self.process(mac, ts, jpeg)

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
        c.subscribe([("+/image", 0), ("+/status", 1), ("+/online", 1)])

    def on_disconnect(c, userdata, flags, reason_code, properties):
        log.warning("MQTT disconnected: %s", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = lambda c, u, m: app.on_message(m.topic, m.payload)
    app.publish = lambda t, p, q, r: client.publish(t, p, qos=q, retain=r)
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
        logic=DwellLogic(s.pedestrian_conf_threshold, s.alert_dwell_seconds,
                         s.max_gap_seconds, s.alert_cooldown_seconds),
        events=EventStore(s.events_dir),
        publish=lambda t, p, q, r: None,  # replaced by connect()
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
