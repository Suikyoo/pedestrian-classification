"""Pretend to be an edge device: publish status, optional JPEG frames, optional warning events.

    python tools/fake_device.py --mac 0123456789ab --dir samples --interval 1
    python tools/fake_device.py --mac 0123456789ab --dir samples --event --count 0 --no-frames
"""

import argparse
import itertools
import json
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from master import protocol

STATUS = {"rssi": -60, "battery_mv": 0, "uptime_s": 0, "streaming": True, "fw": "fake",
          "detect_ok": True, "threshold": 0.6, "dwell_s": 5, "max_gap_s": 3, "cooldown_s": 30,
          "temp_c": 48.0}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mac", required=True)
    ap.add_argument("--dir", required=True, type=Path, help="folder of .jpg files, sent in name order, looped")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between frames")
    ap.add_argument("--count", type=int, default=0, help="frames to send; 0 = forever")
    ap.add_argument("--score", type=float, default=0.8, help="device score sent with each frame")
    ap.add_argument("--no-frames", action="store_true", help="send no frames (a device with streaming off)")
    ap.add_argument("--event", action="store_true", help="publish one warning event first, with the first image")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--no-timestamp", action="store_true", help="send capture_ms=0 (unsynced clock)")
    args = ap.parse_args()

    files = sorted(args.dir.glob("*.jpg"))
    if not files:
        raise SystemExit(f"no .jpg files in {args.dir}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=args.mac)
    client.will_set(protocol.topic(args.mac, "online"), b"0", qos=1, retain=True)
    client.on_message = lambda c, u, m: print(f"<- {m.topic} {m.payload.decode()}")
    client.connect(args.host, args.port, keepalive=30)
    client.subscribe([(protocol.topic(args.mac, k), 1) for k in ("alert", "cmd", "config")])
    client.loop_start()
    client.publish(protocol.topic(args.mac, "online"), b"1", qos=1, retain=True)
    status = {**STATUS, "streaming": not args.no_frames}
    client.publish(protocol.topic(args.mac, "status"), json.dumps(status).encode(), qos=1, retain=True)

    def now_ms() -> int:
        return 0 if args.no_timestamp else int(time.time() * 1000)

    if args.event:
        ms = now_ms()
        event = protocol.DeviceEvent(ms, ms - 5000 if ms else 0, 5.0, args.score)
        client.publish(protocol.topic(args.mac, "event"), protocol.pack_event(event, files[0].read_bytes()), qos=1)
        print(f"-> event with {files[0].name}")

    frames = itertools.cycle(files) if args.count == 0 else itertools.islice(itertools.cycle(files), args.count)
    try:
        if args.no_frames:
            while True:
                time.sleep(60)
                client.publish(protocol.topic(args.mac, "status"), json.dumps(status).encode(), qos=1, retain=True)
        for path in frames:
            payload = protocol.pack_image(now_ms(), path.read_bytes(), args.score, 0.0)
            client.publish(protocol.topic(args.mac, "image"), payload, qos=0)
            print(f"-> {path.name}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(protocol.topic(args.mac, "online"), b"0", qos=1, retain=True).wait_for_publish(2)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
