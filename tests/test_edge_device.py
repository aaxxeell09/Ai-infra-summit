"""Tests for the board device registry, routing and inference client."""
import io
import json
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

from turbo.edge_device import (BoardInferenceClient, EdgeDeviceError,
                               escalate_to_laptop, register_device,
                               route, uno_q_board)


def board(endpoint="http://192.168.1.50:8080", status="verified", caps=("llm",)):
    entry = uno_q_board(endpoint=endpoint)
    entry["status"] = status
    entry["capabilities"] = list(caps)
    entry["context_tokens"] = 4096
    return entry


def laptop(device_id="latitude", status="verified"):
    return {"device_id": device_id, "kind": "laptop", "arch": "windows-arm64",
            "compute": "gpu", "status": status, "endpoint": "http://127.0.0.1:8080",
            "capabilities": ["llm"], "context_tokens": 8192,
            "measured_profiles": {"fast": {"decode_tps": 40}}}


class RegistryTests(unittest.TestCase):
    def test_uno_q_template_is_unverified_without_private_facts(self):
        entry = uno_q_board()
        self.assertEqual(entry["compute"], "cpu")
        self.assertFalse(entry["use_npu"])
        self.assertEqual(entry["status"], "unverified")
        self.assertIsNone(entry["endpoint"])
        conn = entry["connectivity"]
        self.assertFalse(conn["verified"])
        self.assertNotIn("serial", conn)
        for measured in ("ram_total_mb", "ram_available_mb", "swap_mb", "disk_free_gb"):
            self.assertNotIn(measured, conn)

    def test_connectivity_evidence_is_caller_supplied(self):
        evidence = {"method": "ssh", "verified": True, "arch_confirmed": "aarch64"}
        self.assertTrue(uno_q_board(connectivity=evidence)["connectivity"]["verified"])
        for bad in ({"verified": "yes"}, {"method": "ssh"}, "verified", 7):
            with self.assertRaises(ValueError, msg=repr(bad)):
                uno_q_board(connectivity=bad)
        # None means "no evidence given", not invalid.
        self.assertFalse(uno_q_board(connectivity=None)["connectivity"]["verified"])

    def test_register_validates_entries(self):
        registry = register_device([], laptop())
        with self.assertRaises(ValueError):
            register_device(registry, {"device_id": "latitude"})
        with self.assertRaises(ValueError):
            register_device([], dict(laptop(), compute="tpu"))
        with self.assertRaises(ValueError):
            register_device([], dict(laptop(), compute="npu", measured_profiles={}))
        npu = dict(laptop(), device_id="other", compute="npu",
                   measured_profiles={"x": {"decode_tps": 1}})
        self.assertEqual(register_device([], npu)[0]["compute"], "npu")
        with self.assertRaises(ValueError):
            register_device(registry, laptop())


class RouteTests(unittest.TestCase):
    def test_prefers_verified_board_and_escalates(self):
        registry = [board(status="unverified"), laptop()]
        self.assertEqual(route(64, registry), "latitude")
        registry[0]["status"] = "verified"
        self.assertEqual(route(64, registry), "uno-q")

    def test_verified_connectivity_does_not_imply_verified_inference(self):
        registry = [uno_q_board(endpoint="http://192.168.1.50:8080"), laptop()]
        self.assertEqual(route(64, registry), "latitude")

    def test_oversized_prompt_escalates_past_context_limit(self):
        registry = [board(), laptop()]
        self.assertEqual(route(8192, registry), "latitude")

    def test_output_budget_counts_against_context(self):
        registry = [board(), laptop()]
        self.assertEqual(route(4000, registry, output_tokens=96), "uno-q")
        self.assertEqual(route(4000, registry, output_tokens=97), "latitude")

    def test_invalid_token_counts_rejected(self):
        registry = [board(), laptop()]
        for prompt in (-1, 1.5, "100", True, None):
            with self.assertRaises(ValueError, msg=repr(prompt)):
                route(prompt, registry)
        for output in (-1, 2.5, "10", False):
            with self.assertRaises(ValueError, msg=repr(output)):
                route(1, registry, output_tokens=output)

    def test_no_verified_device_raises(self):
        with self.assertRaises(EdgeDeviceError):
            route(1, [])
        with self.assertRaises(EdgeDeviceError):
            route(1, [board(status="unverified"), laptop(status="unverified")])

    def test_missing_context_is_not_unlimited(self):
        no_context = board()
        del no_context["context_tokens"]
        # Without a recorded context the board is ineligible even when verified.
        with self.assertRaises(EdgeDeviceError):
            route(64, [no_context])
        # ...but the verified laptop with a recorded context still serves.
        self.assertEqual(route(64, [no_context, laptop()]), "latitude")

    def test_fallback_laptop_requires_verified_llm_and_fitting_context(self):
        oversized = board()
        oversized["context_tokens"] = 128
        for tweak in ({"status": "unverified"}, {"capabilities": ["vision"]},
                      {"context_tokens": None}, {"context_tokens": 0},
                      {"context_tokens": -1}, {"context_tokens": "8192"},
                      {"context_tokens": True}, {"context_tokens": 8192.0}):
            with self.assertRaises(EdgeDeviceError, msg=repr(tweak)):
                route(5000, [oversized, dict(laptop(), **tweak)])


class FakeResponse:
    def __init__(self, body):
        if isinstance(body, bytes):
            self.body = body
        else:
            self.body = json.dumps(body).encode()
        self.offset = 0

    def read(self, size=-1):
        if size is None or size < 0:
            chunk = self.body[self.offset:]
        else:
            chunk = self.body[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ClientTests(unittest.TestCase):
    def chat_payload(self):
        return {"choices": [{"message": {"content": "hello"}}]}

    def test_endpoint_must_be_configured_http(self):
        for bad in ("", "ftp://x", "/dev/ttyUSB0", None):
            with self.assertRaises(ValueError):
                BoardInferenceClient(bad)

    def test_timeout_must_be_finite_and_positive(self):
        url = "http://192.168.1.50:8080"
        for bad in (0, -1, -0.5, float("nan"), float("inf"), float("-inf"), "5", True, None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                BoardInferenceClient(url, timeout_s=bad)
        client = BoardInferenceClient(url, timeout_s=0.5)
        self.assertEqual(client.timeout_s, 0.5)

    def test_chat_round_trip_counts_total_latency(self):
        seen = {}

        def opener(request, timeout):
            seen["url"] = request.full_url
            seen["body"] = json.loads(request.data)
            seen["timeout"] = timeout
            return FakeResponse(self.chat_payload())

        client = BoardInferenceClient("http://192.168.1.50:8080/", opener=opener)
        result = client.chat("tiny-gguf", [{"role": "user", "content": "hi"}])
        self.assertEqual(seen["url"], "http://192.168.1.50:8080/v1/chat/completions")
        self.assertFalse(seen["body"]["stream"])
        self.assertEqual(result["text"], "hello")
        self.assertEqual(result["device"], "board")
        self.assertGreaterEqual(result["latency_ms"], 0)

    def test_transport_and_body_failures_surface(self):
        def refusing(request, timeout):
            raise urllib.error.URLError("connection refused")

        client = BoardInferenceClient("http://192.168.1.50:8080", opener=refusing)
        with self.assertRaises(EdgeDeviceError):
            client.chat("m", [])
        bad = BoardInferenceClient(
            "http://192.168.1.50:8080",
            opener=lambda r, timeout: FakeResponse({"choices": "nope"}))
        with self.assertRaises(EdgeDeviceError):
            bad.chat("m", [])

    def test_non_string_content_rejected(self):
        for content in (42, None, ["hi"], {"text": "hi"}):
            body = {"choices": [{"message": {"content": content}}]}
            client = BoardInferenceClient(
                "http://192.168.1.50:8080",
                opener=lambda r, timeout, b=body: FakeResponse(b))
            with self.assertRaises(EdgeDeviceError, msg=repr(content)):
                client.chat("m", [])

    def test_non_dict_body_rejected(self):
        client = BoardInferenceClient(
            "http://192.168.1.50:8080", opener=lambda r, timeout: FakeResponse(["nope"]))
        with self.assertRaises(EdgeDeviceError):
            client.chat("m", [])

    def test_failure_latency_is_recorded_on_error(self):
        def refusing(request, timeout):
            raise urllib.error.URLError("connection refused")

        client = BoardInferenceClient("http://192.168.1.50:8080", opener=refusing)
        with self.assertRaises(EdgeDeviceError) as caught:
            client.chat("m", [])
        self.assertGreaterEqual(caught.exception.latency_ms, 0)

    def test_every_error_path_carries_failed_attempt_latency(self):
        def refused(request, timeout):
            raise urllib.error.URLError("refused")

        cases = [
            ("transport", refused),
            ("oversized", lambda r, timeout: FakeResponse(b"x" * 5_000_000)),
            ("non-dict body", lambda r, timeout: FakeResponse(["nope"])),
            ("malformed choices", lambda r, timeout: FakeResponse({"choices": "nope"})),
            ("non-string content", lambda r, timeout: FakeResponse(
                {"choices": [{"message": {"content": 7}}]})),
        ]
        for name, opener in cases:
            client = BoardInferenceClient("http://192.168.1.50:8080", opener=opener)
            with self.assertRaises(EdgeDeviceError, msg=name) as caught:
                client.chat("m", [])
            self.assertIsInstance(caught.exception.latency_ms, float, msg=name)
            self.assertGreaterEqual(caught.exception.latency_ms, 0.0, msg=name)

    def test_timeout_reaches_opener_as_keyword_only(self):
        seen = {}

        def keyword_only_opener(request, *, timeout):
            seen["timeout"] = timeout
            return FakeResponse(self.chat_payload())

        client = BoardInferenceClient(
            "http://192.168.1.50:8080", timeout_s=1.25, opener=keyword_only_opener)
        result = client.chat("m", [])
        self.assertEqual(seen["timeout"], 1.25)
        self.assertEqual(result["text"], "hello")


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = self.server.payload
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class LoopbackServerTests(unittest.TestCase):
    """Drive the default urllib opener against a real local HTTP server.

    Mock openers accept any argument order, so they cannot catch a call
    like opener(request, timeout_s) that lands the timeout in urlopen's
    data parameter. A real loopback socket does.
    """

    def setUp(self):
        try:
            self.server = HTTPServer(("127.0.0.1", 0), _Handler)
        except PermissionError:
            raise unittest.SkipTest(
                "socket bind denied in this sandbox; loopback tests need a "
                "network-permitted environment") from None
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_real_urlopen_round_trip_with_keyword_timeout(self):
        self.server.payload = json.dumps(
            {"choices": [{"message": {"content": "board says hi"}}]}).encode()
        client = BoardInferenceClient("http://127.0.0.1:%d" % self.server.server_address[1])
        result = client.chat("tiny-gguf", [{"role": "user", "content": "hi"}])
        self.assertEqual(result["text"], "board says hi")
        self.assertGreaterEqual(result["latency_ms"], 0)

    def test_oversized_response_is_rejected(self):
        from turbo.edge_device import MAX_RESPONSE_BYTES
        self.server.payload = b"x" * (MAX_RESPONSE_BYTES + 1)
        client = BoardInferenceClient("http://127.0.0.1:%d" % self.server.server_address[1])
        with self.assertRaises(EdgeDeviceError):
            client.chat("m", [])


class EscalationTests(unittest.TestCase):
    def test_board_failure_falls_back_to_laptop(self):
        registry = [board(), laptop()]
        calls = []

        def call(device_id):
            calls.append(device_id)
            if device_id == "uno-q":
                raise EdgeDeviceError("down")
            return {"device": device_id}

        result = escalate_to_laptop(call, registry, "uno-q")
        self.assertEqual(result["device"], "latitude")
        self.assertEqual(calls, ["uno-q", "latitude"])

    def test_total_failure_raises_board_error(self):
        registry = [board(), laptop()]
        with self.assertRaises(EdgeDeviceError):
            escalate_to_laptop(lambda d: (_ for _ in ()).throw(EdgeDeviceError("x")),
                               registry, "uno-q")
        with self.assertRaises(EdgeDeviceError):
            escalate_to_laptop(lambda d: (_ for _ in ()).throw(EdgeDeviceError("x")),
                               [board()], "uno-q")

    def test_success_latency_includes_failed_board_attempt(self):
        registry = [board(), laptop()]
        calls = []

        def call(device_id):
            calls.append(device_id)
            if device_id == "uno-q":
                error = EdgeDeviceError("down")
                error.latency_ms = 123.4
                raise error
            return {"device": device_id, "latency_ms": 10.0}

        result = escalate_to_laptop(call, registry, "uno-q")
        self.assertEqual(result["device"], "latitude")
        self.assertEqual(result["latency_ms"], 133.4)

    def test_error_without_latency_still_preserves_result_latency(self):
        registry = [board(), laptop()]

        def call(device_id):
            if device_id == "uno-q":
                raise EdgeDeviceError("down")
            return {"device": device_id, "latency_ms": 7.5}

        self.assertEqual(escalate_to_laptop(call, registry, "uno-q")["latency_ms"], 7.5)


if __name__ == "__main__":
    unittest.main()
