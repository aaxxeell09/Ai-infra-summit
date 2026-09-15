"""Tests for turbo.bench against a local scripted SSE fixture server."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from turbo.bench import _SSEParser, _compute_tps, run_completion


def sse(objs: list[dict | str]) -> bytes:
    """Encode JSON objects (or raw strings like [DONE]) as an SSE body."""
    out = []
    for item in objs:
        if isinstance(item, str):
            out.append("data: " + item)
        else:
            out.append("data: " + json.dumps(item))
        out.append("")
        out.append("")
    return "\n".join(out).encode("utf-8")


def chunk(delta: dict, finish: str | None = None) -> dict:
    return {"choices": [{"delta": delta, "finish_reason": finish}]}


GOOD_STREAM = sse([
    chunk({"role": "assistant"}),          # role-only: must not start TTFT
    chunk({"content": "héllo "}),
    chunk({"content": "wörld 🚀"}),
    chunk({}, finish="stop"),
    {"usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11}},
    "[DONE]",
])

MISSING_USAGE_STREAM = sse([
    chunk({"role": "assistant"}),
    chunk({"content": "abc"}),
    chunk({}, finish="stop"),
    "[DONE]",
])

MALFORMED_STREAM = sse([
    "{not json",
    chunk({"content": "survivor"}),
    chunk({}, finish="length"),
    "[DONE]",
])

TRUNCATED_STREAM = sse([
    chunk({"role": "assistant"}),
    chunk({"content": "half"}),
])  # connection drops: no finish_reason, no [DONE]


class _Handler(BaseHTTPRequestHandler):
    script: bytes = b""
    status: int = 200
    hang: bool = False

    last_body: dict | None = None

    def do_POST(self):  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", 0))
        type(self).last_body = json.loads(self.rfile.read(length))
        self.send_response(self.status)
        if self.status == 200:
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(self.script)
            self.wfile.flush()
            self.close_connection = True
        else:
            body = b'{"error": "boom"}'
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *args):  # silence test output
        pass


class SSEParserTest(unittest.TestCase):
    def test_multiline_data_comments_and_boundaries(self):
        parser = _SSEParser()
        events = []
        for line in [
            ": keepalive comment",
            "data: {",            # JSON value split across two data: lines
            "data: \"a\": 1}",
            "",
            "data: second",
            "",
        ]:
            payload = parser.feed_line(line)
            if payload is not None:
                events.append(payload)
        self.assertEqual(events, ['{\n"a": 1}', "second"])

    def test_empty_events_do_not_emit(self):
        parser = _SSEParser()
        for line in ["data-x: not data", "event: ping", ""]:
            self.assertIsNone(parser.feed_line(line))


class RunCompletionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d/v1" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def run_script(self, script: bytes, status: int = 200) -> dict:
        _Handler.script = script
        _Handler.status = status
        return run_completion(self.base, "local/model", [{"role": "user",
                                                          "content": "hi"}],
                              max_tokens=64, timeout=10)

    def test_good_stream_utf8_usage_and_timings(self):
        res = self.run_script(GOOD_STREAM)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["text"], "héllo wörld 🚀")
        self.assertEqual(res["finish_reason"], "stop")
        self.assertEqual(res["usage"]["completion_tokens"], 6)
        self.assertEqual(res["completion_tokens"], 6)
        self.assertTrue(res["done_seen"])
        self.assertEqual(res["http_status"], 200)
        # role-only event did not start the content window
        self.assertGreater(res["content_elapsed_s"], 0)
        self.assertLessEqual(res["first_content_s"], res["last_content_s"])
        self.assertGreater(res["decode_tps"], 0)
        self.assertGreater(res["total_output_tps"], 0)
        self.assertTrue(json.dumps(res, ensure_ascii=False))  # serializable

    def test_request_body_shape(self):
        self.run_script(GOOD_STREAM)
        body = _Handler.last_body
        self.assertEqual(body["stream"], True)
        self.assertEqual(body["stream_options"], {"include_usage": True})
        self.assertEqual(body["enable_think"], False)
        self.assertEqual(body["model"], "local/model")
        self.assertEqual(body["max_tokens"], 64)

    def test_missing_usage_gives_null_tps_with_reason(self):
        res = self.run_script(MISSING_USAGE_STREAM)
        self.assertTrue(res["ok"])
        self.assertIsNone(res["decode_tps"])
        self.assertIsNone(res["total_output_tps"])
        self.assertIn("completion_tokens", res["decode_tps_reason"])
        self.assertEqual(res["decode_tps_label"], "client_observed")

    def test_malformed_event_recorded_and_flags_not_ok(self):
        res = self.run_script(MALFORMED_STREAM)
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "parse_error")
        self.assertEqual(len(res["parse_errors"]), 1)
        self.assertEqual(res["text"], "survivor")
        self.assertEqual(res["finish_reason"], "length")
        self.assertTrue(res["done_seen"])

    def test_truncated_stream_is_not_ok(self):
        res = self.run_script(TRUNCATED_STREAM)
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "truncated_stream")
        self.assertFalse(res["done_seen"])
        self.assertIsNone(res["finish_reason"])

    def test_non_200_is_http_error(self):
        res = self.run_script(b"ignored", status=500)
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "http_error")
        self.assertEqual(res["http_status"], 500)
        self.assertIn("boom", res["errors"][0]["detail"])

    def test_non_200_does_not_leak_resource_warning(self):
        import gc
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            res = self.run_script(b"ignored", status=500)
            gc.collect()
        self.assertEqual(res["status"], "http_error")

    def test_connection_refused_is_structured(self):
        res = run_completion("http://127.0.0.1:1/v1", "m",
                             [{"role": "user", "content": "hi"}], timeout=5)
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "connection_error")


class ComputeTPSTest(unittest.TestCase):
    def test_decode_tps_excludes_first_token(self):
        res = {"completion_tokens": 11, "content_elapsed_s": 1.0,
               "total_time_s": 2.0, "decode_tps": None,
               "decode_tps_reason": None, "total_output_tps": None,
               "total_output_tps_reason": None}
        _compute_tps(res)
        self.assertAlmostEqual(res["decode_tps"], 10.0)
        self.assertAlmostEqual(res["total_output_tps"], 5.5)

    def test_single_token_returns_null_with_reason(self):
        res = {"completion_tokens": 1, "content_elapsed_s": 1.0,
               "total_time_s": 2.0, "decode_tps": None,
               "decode_tps_reason": None, "total_output_tps": None,
               "total_output_tps_reason": None}
        _compute_tps(res)
        self.assertIsNone(res["decode_tps"])
        self.assertIn("1 completion token", res["decode_tps_reason"])
        self.assertAlmostEqual(res["total_output_tps"], 0.5)

    def test_zero_width_window_returns_null_with_reason(self):
        res = {"completion_tokens": 8, "content_elapsed_s": 0.0,
               "total_time_s": 0.01, "decode_tps": None,
               "decode_tps_reason": None, "total_output_tps": None,
               "total_output_tps_reason": None}
        _compute_tps(res)
        self.assertIsNone(res["decode_tps"])
        self.assertIn("one flush", res["decode_tps_reason"])
        self.assertAlmostEqual(res["total_output_tps"], 800.0)


if __name__ == "__main__":
    unittest.main()
