"""Admin page and API: send commands and config to devices from the dashboard process.

Off unless ADMIN_PASSWORD is set. Uses HTTP Basic auth and needs the header
`X-Requested-With: admin-ui` on every POST, so another site cannot make a logged-in
browser send commands (browsers send Basic credentials on cross-site requests).
"""

import json
import logging
import re
import secrets
from pathlib import Path

import paho.mqtt.client as mqtt
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from master import protocol
from master.settings import Settings

log = logging.getLogger("master.admin")

STATIC_DIR = Path(__file__).parent / "static"
_ID_RE = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
CSRF_HEADER = ("x-requested-with", "admin-ui")


class AdminLink:
    """MQTT connection that publishes commands and caches each device's retained config."""

    def __init__(self, host: str, port: int, user: str, password: str):
        self._configs: dict[str, dict] = {}
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="master-admin")
        if user or password:
            self._client.username_pw_set(user, password or None)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.connect_async(host, port, keepalive=30)

    def start(self) -> None:
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def _on_connect(self, c, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.error("admin MQTT connect failed: %s", reason_code)
            return
        c.subscribe("+/config", 1)  # the broker replays each device's retained config

    def _on_message(self, c, userdata, msg) -> None:
        parsed = protocol.parse_topic(msg.topic)
        if parsed is None or parsed[1] != "config":
            return
        try:
            cfg = json.loads(msg.payload)
        except ValueError:
            cfg = None
        if isinstance(cfg, dict):
            self._configs[parsed[0]] = cfg
        else:
            self._configs.pop(parsed[0], None)

    def connected(self) -> bool:
        return self._client.is_connected()

    def config(self, mac: str) -> dict | None:
        return self._configs.get(mac)

    def publish(self, topic: str, payload: bytes, retain: bool = False, timeout: float = 5.0) -> bool:
        """Publish at QoS 1 and wait for the broker's acknowledgement."""
        info = self._client.publish(topic, payload, qos=1, retain=retain)
        try:
            info.wait_for_publish(timeout=timeout)
        except (RuntimeError, ValueError):
            return False
        return info.is_published()


def install(app: FastAPI, settings: Settings, link) -> None:
    """Mount /admin and /api/admin on `app`. `link` has config(mac), publish(...), connected()."""
    basic = HTTPBasic(realm="Pedestrian admin")
    user = settings.admin_user.encode()
    password = settings.admin_password.encode()

    def authorize(creds: HTTPBasicCredentials = Depends(basic)) -> None:
        ok_user = secrets.compare_digest(creds.username.encode(), user)
        ok_pass = secrets.compare_digest(creds.password.encode(), password)
        if not (ok_user and ok_pass):
            raise HTTPException(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Pedestrian admin"'})

    def require_csrf_header(request: Request) -> None:
        if request.headers.get(CSRF_HEADER[0]) != CSRF_HEADER[1]:
            raise HTTPException(status_code=403, detail=f"missing {CSRF_HEADER[0]} header")

    def device(mac: str) -> str:
        if not _ID_RE.match(mac):
            raise HTTPException(status_code=400, detail="invalid device id")
        return mac

    def send(topic: str, payload: bytes, retain: bool = False) -> None:
        if not link.connected():
            raise HTTPException(status_code=503, detail="not connected to the MQTT broker")
        if not link.publish(topic, payload, retain=retain):
            raise HTTPException(status_code=504, detail="broker did not confirm the message")

    async def body(request: Request) -> dict:
        try:
            data = await request.json()
        except ValueError:
            raise HTTPException(status_code=400, detail="body must be JSON") from None
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        return data

    router = APIRouter(dependencies=[Depends(authorize)])

    @router.get("/admin")
    def page() -> FileResponse:
        return FileResponse(STATIC_DIR / "admin.html")

    @router.get("/api/admin/devices/{mac}/config")
    def get_config(mac: str) -> dict:
        return {
            "config": link.config(device(mac)),
            "defaults": protocol.DEFAULT_CONFIG,
            "frame_sizes": protocol.FRAME_SIZES,
            "rotations": protocol.ROTATIONS,
            "connected": link.connected(),
        }

    @router.post("/api/admin/devices/{mac}/command", dependencies=[Depends(require_csrf_header)])
    async def command(mac: str, request: Request) -> dict:
        action = (await body(request)).get("action")
        try:
            payload = protocol.cmd_payload(action)
        except protocol.ProtocolError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        send(protocol.topic(device(mac), "cmd"), payload)
        return {"sent": action}

    @router.post("/api/admin/devices/{mac}/alert", dependencies=[Depends(require_csrf_header)])
    async def alert(mac: str, request: Request) -> dict:
        repeat = (await body(request)).get("repeat", 1)
        if not isinstance(repeat, int) or isinstance(repeat, bool):
            raise HTTPException(status_code=422, detail="repeat must be an integer")
        try:
            payload = protocol.alert_payload(repeat)
        except protocol.ProtocolError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        send(protocol.topic(device(mac), "alert"), payload)
        return {"sent": "alert", "repeat": repeat}

    @router.post("/api/admin/devices/{mac}/config", dependencies=[Depends(require_csrf_header)])
    async def set_config(mac: str, request: Request) -> dict:
        fields = (await body(request)).get("fields")
        if not isinstance(fields, dict) or not fields:
            raise HTTPException(status_code=422, detail="fields must be a non-empty object")
        mac = device(mac)
        try:
            # Same rule as the CLI: merge into the device's retained config. With none
            # known, only the given fields are sent and the device keeps the rest.
            merged = protocol.merge_config(link.config(mac) or {}, fields)
        except protocol.ProtocolError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        send(protocol.topic(mac, "config"), json.dumps(merged).encode(), retain=True)
        return {"config": merged}

    app.include_router(router)
