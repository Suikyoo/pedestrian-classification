"""Manual commands to devices.

    python -m master.cli alert  <mac> [--repeat N]
    python -m master.cli start|stop|reboot|status <mac>
    python -m master.cli config <mac> key=value [key=value ...]
"""

import argparse
import json
import re
import sys
import threading

import paho.mqtt.client as mqtt

from master import protocol
from master.settings import Settings

_MAC_RE = re.compile(r"^[0-9a-f]{12}$")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m master.cli")
    sub = ap.add_subparsers(dest="command", required=True)
    alert = sub.add_parser("alert", help="play the alert sound")
    alert.add_argument("mac")
    alert.add_argument("--repeat", type=int, default=1)
    for action in protocol.ACTIONS:
        sub.add_parser(action, help=f"send '{action}' command").add_argument("mac")
    config = sub.add_parser("config", help="merge fields into the device's retained config")
    config.add_argument("mac")
    config.add_argument("fields", nargs="*", metavar="key=value")
    return ap


def build_message(argv: list[str], current_config: dict | None = None) -> tuple[str, bytes, int, bool]:
    args = _parser().parse_args(argv)
    if not _MAC_RE.match(args.mac):
        raise protocol.ProtocolError(f"mac must be 12 lowercase hex digits, got {args.mac!r}")
    if args.command == "alert":
        return protocol.topic(args.mac, "alert"), protocol.alert_payload(args.repeat), 1, False
    if args.command == "config":
        if not args.fields:
            raise protocol.ProtocolError("config needs at least one key=value")
        updates = protocol.parse_config_args(args.fields)
        merged = protocol.merge_config(current_config or protocol.DEFAULT_CONFIG, updates)
        return protocol.topic(args.mac, "config"), json.dumps(merged).encode(), 1, True
    return protocol.topic(args.mac, "cmd"), protocol.cmd_payload(args.command), 1, False


def _fetch_retained_config(client: mqtt.Client, mac: str, timeout: float = 2.0) -> dict | None:
    """Read the retained {mac}/config, or None if there is none."""
    got = threading.Event()
    result: dict = {}

    def on_message(c, u, m):
        try:
            result["cfg"] = json.loads(m.payload)
        except ValueError:
            pass
        got.set()

    client.on_message = on_message
    client.subscribe(protocol.topic(mac, "config"), qos=1)
    got.wait(timeout)
    client.unsubscribe(protocol.topic(mac, "config"))
    return result.get("cfg")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    s = Settings()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="")
    if s.mqtt_user or s.mqtt_pass:
        client.username_pw_set(s.mqtt_user, s.mqtt_pass or None)
    client.connect(s.mqtt_host, s.mqtt_port, keepalive=30)
    client.loop_start()
    try:
        current = None
        if argv and argv[0] == "config" and len(argv) > 1:
            current = _fetch_retained_config(client, argv[1])
        try:
            t, payload, qos, retain = build_message(argv, current)
        except protocol.ProtocolError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        client.publish(t, payload, qos=qos, retain=retain).wait_for_publish(timeout=5)
        print(f"sent {t} {payload.decode()}")
        return 0
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    sys.exit(main())
