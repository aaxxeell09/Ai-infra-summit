"""UNO Q controls and fail-closed result relay. Use --simulate without hardware."""
import argparse
import http.client
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request

logger = logging.getLogger("InspectionClient")
STATUS_IDLE, STATUS_INSPECTING, STATUS_OK, STATUS_CHECK, STATUS_UNKNOWN = range(5)
STATUS_NAMES = dict(enumerate(("IDLE", "INSPECTING", "OK", "CHECK", "UNKNOWN")))
HUB_STATUS_CODES = {name: code for code, name in STATUS_NAMES.items()}
ACTION_NONE, ACTION_INSPECT, ACTION_CLEAR, ACTION_CYCLE, ACTION_KNOB = range(5)


def decode_action(raw):
    if type(raw) is not int or not 0 <= raw <= 65535:
        return ACTION_NONE, 0
    direction = (raw >> 8) & 255
    return raw & 255, direction - 256 if direction > 127 else direction


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=1.5)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class HubClient:
    def __init__(self, base_url, token="", socket_path=None):
        self.base_url, self.token = base_url.rstrip("/"), token
        self.socket_path = socket_path
        self.last_elapsed_ms = 0

    def request(self, path, payload=None):
        started = time.monotonic()
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json", "X-Device-Token": self.token}
        request = urllib.request.Request(self.base_url + path, data=data,
            headers=headers)
        try:
            if self.socket_path:
                with UnixConnection(self.socket_path) as connection:
                    connection.request("GET" if payload is None else "POST", path, data, headers)
                    with connection.getresponse() as response:
                        return response.status, self.read_body(response)
            with urllib.request.urlopen(request, timeout=1.5) as response:
                return response.status, self.read_body(response)
        except urllib.error.HTTPError as error:
            error.close()
            return error.code, None
        except (OSError, ValueError, http.client.HTTPException):
            return None, None
        finally:
            self.last_elapsed_ms = round((time.monotonic() - started) * 1000)

    @staticmethod
    def read_body(response):
        raw = response.read(100_001)
        if len(raw) > 100_000:
            raise ValueError("Oversized hub response")
        return json.loads(raw)

    def heartbeat(self, payload=None):
        body = {"device_id": "uno-q"}
        if isinstance(payload, dict):
            body.update(payload)
        return self.request("/api/board/heartbeat", body)

    def state(self):
        return self.request("/api/state")


class SimulationBridge:
    def __init__(self):
        self.queue = []

    def call(self, method, *args, **kwargs):
        if method == "get_action":
            return self.queue.pop(0) if self.queue else 0
        if method == "get_modules":
            return 0   # simulated board reports no known modules
        if method == "get_status":
            return STATUS_IDLE
        if method == "set_status":
            logger.info("[SIM] %s ttl=%s ms", STATUS_NAMES[args[0]], args[1])
            return True
        raise ValueError("Unsupported simulation RPC")


class Client:
    def __init__(self, hub, bridge, heartbeat_s=1.0):
        self.hub, self.bridge = hub, bridge
        self.heartbeat_s = heartbeat_s
        self.next_heartbeat = 0
        self.last_status = None
        # Cached inventory: get_modules is probed at the first heartbeat and
        # re-probed only while unknown, never on every 100 ms loop pass.
        self.modules_mask = None
        self.next_module_probe = 0.0
        self.mcu_status = None
        # Cumulative counts of real get_action events, never HTTP-driven calls.
        self.controls = {"inspect": 0, "clear": 0, "preset": 0}

    def telemetry(self):
        # Hub contract: modules_mask 0..63 or null, mcu_status 0..4 or null.
        # null means "not observed this cycle", never a fabricated zero.
        return {
            "modules_mask": self.modules_mask if type(self.modules_mask) is int and 0 <= self.modules_mask <= 63 else None,
            "mcu_status": self.mcu_status,
            "controls": dict(self.controls),
        }

    def probe_modules(self):
        now = time.monotonic()
        if self.modules_mask is not None and now < self.next_module_probe:
            return
        try:
            mask = self.bridge.call("get_modules", timeout=0.5)
        except Exception:
            mask = None
        if type(mask) is int and 0 <= mask <= 65535:
            if mask != self.modules_mask:
                logger.info("board modules mask: %s", mask)
            self.modules_mask = mask
            self.next_module_probe = now + 30.0
        else:
            # Unknown inventory must not be invented; retry shortly.
            self.next_module_probe = now + 3.0

    def refresh_mcu_status(self):
        try:
            status = self.bridge.call("get_status", timeout=0.5)
        except Exception:
            self.mcu_status = None
            return
        self.mcu_status = status if type(status) is int and 0 <= status <= STATUS_UNKNOWN else None

    def record_action(self, code):
        if code == ACTION_INSPECT:
            self.controls["inspect"] += 1
        elif code == ACTION_CLEAR:
            self.controls["clear"] += 1
        elif code in (ACTION_CYCLE, ACTION_KNOB):
            self.controls["preset"] += 1

    def push_status(self, status, ttl_ms=3000):
        # Retries use a NEW hub snapshot on the next heartbeat. Never resend
        # an old OK with a freshly extended deadline after a communication fault.
        try:
            if not self.bridge.call("set_status", status, ttl_ms, timeout=1):
                raise RuntimeError("Sketch rejected state")
            if status != self.last_status:
                logger.info("state -> %s", STATUS_NAMES[status])
            self.last_status = status
        except Exception as error:
            logger.warning("Bridge update failed: %s", type(error).__name__)

    def apply_hub_state(self, body):
        status = HUB_STATUS_CODES.get(body.get("status")) if isinstance(body, dict) and isinstance(body.get("status"), str) else None
        ttl = 3000
        if status in (STATUS_OK, STATUS_CHECK):
            expiry = body.get("expires_in_ms")
            if type(expiry) is not int:
                status = STATUS_UNKNOWN
            else:
                # Subtract the whole HTTP round trip plus an RPC/loop margin.
                # This is conservative: the hub computes expiry during the trip.
                ttl = min(3000, expiry - self.hub.last_elapsed_ms - 50)
                if ttl <= 0:
                    status = STATUS_UNKNOWN
        self.push_status(STATUS_UNKNOWN if status is None else status, max(0, ttl))

    def accept_response(self, code, body):
        if code in (200, 202) and isinstance(body, dict):
            self.apply_hub_state(body)
        else:
            self.push_status(STATUS_UNKNOWN)

    def poll(self):
        now = time.monotonic()
        if now >= self.next_heartbeat:
            self.next_heartbeat = now + self.heartbeat_s
            self.probe_modules()
            self.refresh_mcu_status()
            self.accept_response(*self.hub.heartbeat(self.telemetry()))
        # The sketch queues events in a small ring; drain them so a knob turn
        # and a button press inside the same 100 ms window are both handled.
        for _ in range(8):
            try:
                code, direction = decode_action(self.bridge.call("get_action", timeout=1))
            except Exception:
                return
            if code == ACTION_NONE:
                return
            self.record_action(code)
            self.handle_action(code, direction)

    def handle_action(self, code, direction):
        logger.info("physical control: action=%s direction=%s", code, direction)
        # Invalidate a displayed OK immediately on operator action.
        self.push_status(STATUS_INSPECTING if code == ACTION_INSPECT else STATUS_UNKNOWN)
        if code == ACTION_INSPECT:
            response = self.hub.request("/api/inspect", {})
            if response[0] == 409:
                response = self.hub.state()
        elif code == ACTION_CLEAR:
            response = self.hub.request("/api/clear", {})
        elif code in (ACTION_CYCLE, ACTION_KNOB):
            if code == ACTION_KNOB and direction not in (-1, 1):
                return
            response = self.hub.request("/api/preset", {"direction": 1 if code == ACTION_CYCLE else direction})
        else:
            return
        self.accept_response(*response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulate", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    url = os.getenv("INSPECTION_HUB_URL", "http://127.0.0.1:8080")
    socket_path = os.getenv("INSPECTION_HUB_SOCKET")
    if not args.simulate and not os.getenv("INSPECTION_HUB_URL"):
        socket_path = socket_path or "/app/data/hub.sock"
    hub = HubClient(url, os.getenv("INSPECTION_DEVICE_TOKEN", ""), socket_path)
    if args.simulate:
        bridge = SimulationBridge()
        logger.info("[SIM] fake controls; real HTTP to %s", url)
    else:
        from arduino.app_utils import App, Bridge
        bridge = Bridge
    client = Client(hub, bridge)
    started = time.monotonic()
    actions = [(3, ACTION_INSPECT), (8, ACTION_CYCLE), (10, ACTION_CLEAR)]
    def loop():
        if args.simulate and actions and time.monotonic() - started >= actions[0][0]:
            bridge.queue.append(actions.pop(0)[1])
        client.poll()
        time.sleep(0.1)
    if args.simulate:
        try:
            while True:
                loop()
        except KeyboardInterrupt:
            pass
    else:
        App.run(user_loop=loop)


if __name__ == "__main__":
    main()
