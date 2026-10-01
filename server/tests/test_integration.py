import socket
import threading
import time

import paho.mqtt.client as mqtt
import pytest

from master import protocol
from master.app import MasterApp, connect
from master.logic import DwellLogic

pytestmark = pytest.mark.integration

HOST, PORT = "127.0.0.1", 1883
MAC = "0123456789ab"


def _broker_up() -> bool:
    try:
        socket.create_connection((HOST, PORT), timeout=1).close()
        return True
    except OSError:
        return False


class AlwaysPerson:
    def person_confidence(self, jpeg):
        return 0.9


class NoEvents:
    def record(self, mac, alert, jpeg):
        pass


@pytest.mark.skipif(not _broker_up(), reason="Mosquitto not running on 127.0.0.1:1883")
def test_alert_arrives_after_dwell_and_not_before():
    app = MasterApp(AlwaysPerson(), DwellLogic(0.6, 2.0, 3.0, 30.0), NoEvents(),
                    publish=lambda t, p, q, r: None)
    server = connect(app, HOST, PORT, "", "", client_id="master-test")
    stop = threading.Event()
    worker = threading.Thread(target=app.run_worker, args=(stop,), daemon=True)
    worker.start()

    alerts = []
    device = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MAC)
    device.on_message = lambda c, u, m: alerts.append(time.monotonic())
    device.connect(HOST, PORT)
    device.subscribe(protocol.topic(MAC, "alert"), qos=1)
    device.loop_start()
    time.sleep(1.0)  # let both clients finish subscribing

    try:
        start = time.monotonic()
        while time.monotonic() - start < 4.0:
            now_ms = int(time.time() * 1000)
            device.publish(protocol.topic(MAC, "image"), protocol.pack_image(now_ms, b"jpeg"), qos=0)
            time.sleep(0.5)
        time.sleep(0.5)
    finally:
        stop.set()
        device.loop_stop()
        device.disconnect()
        server.loop_stop()
        server.disconnect()

    assert len(alerts) == 1
    assert 1.8 <= alerts[0] - start <= 3.5
