"""Pretend to be an edge device: publish JPEGs from a folder, print alerts.

    python tools/fake_device.py --mac 0123456789ab --dir samples --interval 1
"""

import argparse
import itertools
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from master import protocol


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mac", required=True)
    ap.add_argument("--dir", required=True, type=Path, help="folder of .jpg files, sent in name order, looped")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between frames")
    ap.add_argument("--count", type=int, default=0, help="frames to send; 0 = forever")
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

    frames = itertools.cycle(files) if args.count == 0 else itertools.islice(itertools.cycle(files), args.count)
    try:
        for path in frames:
            ms = 0 if args.no_timestamp else int(time.time() * 1000)
            client.publish(protocol.topic(args.mac, "image"), protocol.pack_image(ms, path.read_bytes()), qos=0)
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
