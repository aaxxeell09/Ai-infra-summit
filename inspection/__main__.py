"""Run the local hub using Python 3.11+ and the standard library only."""
from __future__ import annotations

import argparse
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .core import GenieXClient, Hub, InspectionError

WEB = Path(__file__).resolve().parent.parent / "web"
MAX_BODY = 6_100_000


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalInspection/0.1"

    def log_message(self, fmt, *args):
        # Never log image bodies, tokens, or model text.
        if args and (len(args) < 2 or str(args[1]) != "200"):
            super().log_message(fmt, *args)

    def _reply(self, status, payload, content_type="application/json"):
        body = json.dumps(payload).encode() if content_type == "application/json" else payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _check(self):
        host = urlsplit("http://" + self.headers.get("Host", "")).hostname
        if host not in self.server.allowed_hosts:
            raise InspectionError("Unrecognized host.", 403)
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            raise InspectionError("Cross-origin requests are disabled.", 403)
        loopback = ipaddress.ip_address(self.client_address[0]).is_loopback
        if not loopback:
            supplied = self.headers.get("X-Device-Token", "")
            if not self.server.device_token or not secrets.compare_digest(supplied, self.server.device_token):
                raise InspectionError("Device authentication is required.", 401)

    def do_GET(self):
        try:
            self._check()
            path = urlsplit(self.path).path
            if path == "/api/state":
                return self._reply(200, self.server.hub.snapshot())
            static = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}
            if path not in static:
                return self._reply(404, {"error": "Not found."})
            file = WEB / static[path]
            if not file.is_file():
                return self._reply(503, {"error": "Frontend files are not installed."})
            return self._reply(200, file.read_bytes(), (mimetypes.guess_type(str(file))[0] or "application/octet-stream") + "; charset=utf-8")
        except (InspectionError, ValueError) as error:
            self._reply(getattr(error, "status", 400), {"error": str(error)})

    def do_POST(self):
        try:
            self._check()
            if self.headers.get_content_type() != "application/json":
                raise InspectionError("Use application/json.", 415)
            if self.headers.get("Transfer-Encoding"):
                raise InspectionError("Chunked request bodies are not supported.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise InspectionError("Request body is missing or too large.", 413)
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise InspectionError("Request must be a JSON object.")
            hub, path = self.server.hub, urlsplit(self.path).path
            if path == "/api/instruction":
                return self._reply(200, hub.instruction_set(data.get("instruction"), data.get("preset_id")))
            if path == "/api/preset":
                return self._reply(200, hub.preset(data.get("direction")))
            if path == "/api/frame":
                if "image" in data and data["image"] is None:
                    return self._reply(200, hub.frame_clear())
                return self._reply(200, {"frame_id": hub.frame(data.get("image"))})
            if path == "/api/inspect":
                return self._reply(202, hub.inspect(data.get("image")))
            if path == "/api/clear":
                return self._reply(200, hub.clear())
            if path == "/api/board/heartbeat":
                return self._reply(200, hub.heartbeat(data.get("device_id")))
            return self._reply(404, {"error": "Not found."})
        except (InspectionError, ValueError, UnicodeError) as error:
            self._reply(getattr(error, "status", 400), {"error": str(error)})

    def setup(self):
        super().setup()
        self.connection.settimeout(10)


def make_server(host, port, hub, token="", allowed_hosts=()):
    if not ipaddress.ip_address(host).is_loopback and not token:
        raise ValueError("Set INSPECTION_DEVICE_TOKEN before binding to the local network.")
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.hub, server.device_token = hub, token
    server.allowed_hosts = {"localhost", "127.0.0.1", "::1", host, *allowed_hosts}
    return server


def main():
    parser = argparse.ArgumentParser(description="Local visual inspection hub")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--model", default=os.getenv("INSPECTION_MODEL", "qualcomm/Qwen3-VL-4B-Instruct"))
    parser.add_argument("--geniex-url", default=os.getenv("GENIEX_BASE_URL", "http://127.0.0.1:18181/v1"))
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    address = urlsplit(args.geniex_url)
    if address.scheme != "http" or address.hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("GenieX must use a local loopback HTTP endpoint for this prototype.")
    if not 1 <= args.timeout <= 300:
        parser.error("Timeout must be between 1 and 300 seconds.")
    hub = Hub(GenieXClient(args.geniex_url, args.model, args.timeout), request_timeout=args.timeout)
    hub.backend_evidence = os.getenv("INSPECTION_BACKEND_EVIDENCE", "unverified")
    server = make_server(args.host, args.port, hub, os.getenv("INSPECTION_DEVICE_TOKEN", ""),
        os.getenv("INSPECTION_ALLOWED_HOSTS", "").split(","))
    stop = threading.Event()
    def check_runtime():
        while not stop.is_set():
            available = hub.client.available()
            with hub.lock:
                hub.runtime_connected = available
            stop.wait(5)
    threading.Thread(target=check_runtime, daemon=True).start()
    print(f"Local Inspection: http://{args.host}:{server.server_port}", flush=True)
    print(f"Model: {args.model}. Backend evidence: {hub.backend_evidence}.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
