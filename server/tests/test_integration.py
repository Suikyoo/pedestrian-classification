import io
import socket
import threading
import time

import paho.mqtt.client as mqtt
import pytest
from PIL import Image

from master import protocol
from master.app import MasterApp, connect
from master.events import EventStore

pytestmark = pytest.mark.integration

HOST, PORT = "127.0.0.1", 1883
MAC = "0123456789ab"


def _broker_up() -> bool:
    try:
        socket.create_connection((HOST, PORT), timeout=1).close()
        return True
    except OSError:
        return False


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


class AlwaysPerson:
    def person_confidence(self, jpeg):
        return 0.9


@pytest.mark.skipif(not _broker_up(), reason="Mosquitto not running on 127.0.0.1:1883")
def test_device_event_recorded_and_master_never_alerts(tmp_path):
    store = EventStore(tmp_path / "events")
    app = MasterApp(AlwaysPerson(), store, threshold=0.6)
    server = connect(app, HOST, PORT, "", "", client_id="master-test")
    stop = threading.Event()
    worker = threading.Thread(target=app.run_worker, args=(stop,), daemon=True)
    worker.start()

    alerts = []
    device = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MAC)
    device.on_message = lambda c, u, m: alerts.append(m.topic)
    device.connect(HOST, PORT)
    device.subscribe(protocol.topic(MAC, "alert"), qos=1)
    device.loop_start()
    time.sleep(1.0)  # let both clients finish subscribing

    jpeg = _jpeg()
    now_ms = int(time.time() * 1000)
    try:
        device.publish(protocol.topic(MAC, "image"), protocol.pack_image(now_ms, jpeg, 0.9, 5.0), qos=0)
        time.sleep(0.5)
        event = protocol.DeviceEvent(now_ms, now_ms - 5000, 5.0, 0.9)
        device.publish(protocol.topic(MAC, "event"), protocol.pack_event(event, jpeg), qos=1)
        time.sleep(1.0)
    finally:
        stop.set()
        device.loop_stop()
        device.disconnect()
        server.loop_stop()
        server.disconnect()

    assert alerts == []
    [row] = store.recent()
    assert row["mac"] == MAC and row["dwell_s"] == 5.0 and row["max_conf"] == 0.9
    [frame] = store.inferences(MAC)
    assert frame["alerted"] == 1 and frame["device_score"] == 0.9
    store.close()
