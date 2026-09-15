"""Bounded streaming benchmark client for the GenieX OpenAI-compatible server.

Stdlib only (Python 3.11+). Measures client-observed decode throughput from a
single streaming /chat/completions call. Token counts are taken only from the
server-provided usage object; SSE chunk counts are never treated as tokens.
"""

from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import socket
import statistics
import sys
import time
import urllib.error
import urllib.request
from typing import Any

SCHEMA_VERSION = "bench.v1"

# Keys we interpret ourselves; everything else seen on the wire is preserved
# verbatim under provider_fields without assuming a schema.
_KNOWN_TOP_KEYS = {"choices", "id", "object", "created", "model",
                   "system_fingerprint", "usage", "service_tier"}
_KNOWN_CHOICE_KEYS = {"delta", "message", "finish_reason", "index", "logprobs"}


def _endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


class _SSEParser:
    """Incremental text-mode SSE parser.

    Handles blank-line event boundaries, multi-line data fields (joined with
    a newline), and colon comment lines. Feed arbitrary decoded text chunks;
    complete data payloads come back from feed_line.
    """

    def __init__(self) -> None:
        self._data_lines: list[str] = []
        self._has_event = False

    def feed_line(self, line: str) -> str | None:
        """Consume one line (no trailing newline). Returns a payload or None."""
        if line == "":
            if self._has_event and self._data_lines:
                payload = "\n".join(self._data_lines)
                self._data_lines = []
                self._has_event = False
                return payload
            self._data_lines = []
            self._has_event = False
            return None
        if line.startswith(":"):
            return None  # comment
        if line.startswith("data:"):
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            self._data_lines.append(value)
            self._has_event = True
        # Other SSE fields (event:, id:, retry:) do not matter here.
        return None


class _LineBuffer:
    """Byte chunks to complete SSE lines with incremental UTF-8 decoding.

    Socket boundaries are arbitrary: a trailing partial line is retained
    until a newline arrives. CR is stripped from CRLF endings. At EOF the
    remaining text is flushed once as a final line (SSE permits a final
    event without a trailing newline).
    """

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buf = ""

    def feed(self, chunk: bytes) -> list[str]:
        self._buf += self._decoder.decode(chunk)
        *lines, self._buf = self._buf.split("\n")
        return [line.removesuffix("\r") for line in lines]

    def flush(self) -> str | None:
        tail = self._buf + self._decoder.decode(b"", final=True)
        self._buf = ""
        tail = tail.removesuffix("\r")
        return tail or None


def run_completion(
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 256,
    temperature: float = 0,
    extra_body: dict[str, Any] | None = None,
    timeout: float = 120,
) -> dict[str, Any]:
    """Run one streaming chat completion and return a serializable result.

    Never raises for HTTP/network issues: failures come back as structured
    results with ok=False and a machine-readable status.
    """
    started = time.perf_counter()
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
        "enable_think": False,
    }
    if extra_body:
        body.update(extra_body)

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "status": "ok",
        "http_status": None,
        "text": "",
        "finish_reason": None,
        "ttft_s": None,
        "first_content_s": None,
        "last_content_s": None,
        "content_elapsed_s": None,
        "total_time_s": None,
        "usage": None,
        "completion_tokens": None,
        "decode_tps": None,
        "decode_tps_label": "client_observed",
        "decode_tps_method":
            "(completion_tokens - 1) / (last_content - first_content)",
        "decode_tps_caveat":
            "streamed SSE chunks may group multiple tokens; timings are "
            "client-observed wall clock, not device-side kernel timings",
        "decode_tps_reason": None,
        "total_output_tps": None,
        "total_output_tps_method": "completion_tokens / total_time",
        "total_output_tps_reason": None,
        "provider_fields": {},
        "sse_event_count": 0,
        "parse_errors": [],
        "errors": [],
        "done_seen": False,
    }

    req = urllib.request.Request(
        _endpoint(base_url),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Accept": "text/event-stream"},
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        try:
            snippet = exc.read(4096).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - best-effort body read
            snippet = ""
        finally:
            exc.close()
        result["status"] = "http_error"
        result["http_status"] = exc.code
        result["errors"].append({"type": "http_error", "detail": snippet})
        result["total_time_s"] = time.perf_counter() - started
        return result
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
        result["status"] = "connection_error"
        result["errors"].append({"type": "connection_error", "detail": str(exc)})
        result["total_time_s"] = time.perf_counter() - started
        return result

    text_parts: list[str] = []
    first_content: float | None = None
    last_content: float | None = None
    parser = _SSEParser()
    linebuf = _LineBuffer()

    def handle_line(line: str) -> None:
        nonlocal first_content, last_content
        if result["done_seen"]:
            return
        payload = parser.feed_line(line)
        if payload is None:
            return
        result["sse_event_count"] += 1
        if payload.strip() == "[DONE]":
            result["done_seen"] = True
            return
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError as exc:
            result["parse_errors"].append(
                {"detail": "invalid JSON data payload: " + str(exc)})
            return
        _absorb(obj, result, text_parts)
        if result.pop("_pending_content", ""):
            now = time.perf_counter() - started
            if first_content is None:
                first_content = now
                result["ttft_s"] = now
            last_content = now

    try:
        with resp:
            result["http_status"] = resp.status
            # read1 returns as soon as any bytes arrive; plain read would
            # buffer until EOF on responses without Content-Length.
            read_now = getattr(resp, "read1", resp.read)
            while not result["done_seen"]:
                chunk = read_now(65536)
                if not chunk:
                    break
                for line in linebuf.feed(chunk):
                    handle_line(line)
            if not result["done_seen"]:
                tail = linebuf.flush()
                if tail is not None:
                    handle_line(tail)
    except (socket.timeout, TimeoutError):
        result["status"] = "timeout"
        result["errors"].append({"type": "timeout", "detail": "read timed out"})
    except OSError as exc:
        result["status"] = "connection_error"
        result["errors"].append({"type": "connection_error", "detail": str(exc)})

    if first_content is not None and last_content is not None:
        result["first_content_s"] = first_content
        result["last_content_s"] = last_content
        result["content_elapsed_s"] = last_content - first_content
    result["text"] = "".join(text_parts)
    result["total_time_s"] = time.perf_counter() - started

    usage = result.get("usage")
    if isinstance(usage, dict):
        tokens = usage.get("completion_tokens")
        if isinstance(tokens, int) and not isinstance(tokens, bool):
            result["completion_tokens"] = tokens

    if result["status"] == "ok" and result["parse_errors"]:
        result["status"] = "parse_error"
    if (result["status"] == "ok" and not result["done_seen"]
            and result["finish_reason"] is None):
        result["status"] = "truncated_stream"

    _compute_tps(result)
    result["ok"] = result["status"] == "ok"
    return result


def _absorb(obj: dict[str, Any], result: dict[str, Any],
            text_parts: list[str]) -> None:
    """Merge one parsed JSON stream object into the result."""
    for key, value in obj.items():
        if key in _KNOWN_TOP_KEYS:
            continue
        result["provider_fields"][key] = value  # last write wins
    usage = obj.get("usage")
    if isinstance(usage, dict):
        result["usage"] = usage
    for choice in obj.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        for key, value in choice.items():
            if key in _KNOWN_CHOICE_KEYS:
                continue
            result["provider_fields"]["choice." + key] = value
        finish = choice.get("finish_reason")
        if finish is not None:
            result["finish_reason"] = finish
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            delta = choice.get("message")
        if isinstance(delta, dict) and delta.get("content"):
            text_parts.append(delta["content"])
            result["_pending_content"] = delta["content"]


def _compute_tps(result: dict[str, Any]) -> None:
    tokens = result.get("completion_tokens")
    if not isinstance(tokens, int) or isinstance(tokens, bool):
        reason = "completion_tokens missing from server usage"
        result["decode_tps_reason"] = reason
        result["total_output_tps_reason"] = reason
        return
    elapsed = result.get("content_elapsed_s")
    if tokens > 1 and elapsed is not None and elapsed > 0:
        result["decode_tps"] = (tokens - 1) / elapsed
    elif tokens <= 1:
        result["decode_tps_reason"] = (
            "needs more than 1 completion token to exclude prefill from decode")
    elif elapsed is not None and elapsed <= 0:
        result["decode_tps_reason"] = (
            "all content arrived in one flush; no positive decode window")
    else:
        result["decode_tps_reason"] = "no content-timing window"
    total = result.get("total_time_s")
    if total is not None and total > 0:
        result["total_output_tps"] = tokens / total


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _aggregate(samples: list[dict[str, Any]]) -> dict[str, Any]:
    good = [s for s in samples if s.get("ok")]
    tps = [s["decode_tps"] for s in good
           if isinstance(s.get("decode_tps"), (int, float))]
    ttft = [s["ttft_s"] for s in good
            if isinstance(s.get("ttft_s"), (int, float))]
    totals = [s["total_time_s"] for s in good
              if isinstance(s.get("total_time_s"), (int, float))]
    total_tps = [s["total_output_tps"] for s in good
                 if isinstance(s.get("total_output_tps"), (int, float))]
    return {
        "valid_samples": len(good),
        "median_decode_tps_client_observed": _median(tps),
        "median_ttft_s": _median(ttft),
        "median_total_time_s": _median(totals),
        "median_total_output_tps": _median(total_tps),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m turbo.bench",
        description="Benchmark local LLM decode tokens/s on a GenieX "
                    "OpenAI-compatible server (streaming, client-observed).")
    ap.add_argument("--base-url", required=True,
                    help="e.g. http://127.0.0.1:18181/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt-file", required=True,
                    help="UTF-8 text file; sent as a single user message")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--temperature", type=float, default=0)
    ap.add_argument("--warmup", type=int, default=1,
                    help="warmup runs, excluded from the aggregate")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--output", help="write the JSON report here (default stdout)")
    args = ap.parse_args(argv)

    with open(args.prompt_file, "rb") as fh:
        prompt_bytes = fh.read()
    prompt = prompt_bytes.decode("utf-8")
    messages = [{"role": "user", "content": prompt}]

    def one() -> dict[str, Any]:
        return run_completion(args.base_url, args.model, messages,
                              args.max_tokens, args.temperature,
                              timeout=args.timeout)

    warmup = [one() for _ in range(max(0, args.warmup))]
    samples = [one() for _ in range(max(0, args.repeats))]

    report = {
        "schema_version": SCHEMA_VERSION,
        "config": {
            "base_url": args.base_url,
            "model": args.model,
            "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
            "prompt_chars": len(prompt),
            "max_tokens": args.max_tokens,
            "temperature": args.temperature,
            "warmup_runs": args.warmup,
            "repeats": args.repeats,
            "timeout_s": args.timeout,
            "remote_model_downloads": "none; the client never pulls models",
        },
        "warmup": warmup,
        "samples": samples,
        "aggregate": _aggregate(samples),
        "validation": {
            "sample_count_matches_repeats": len(samples) == args.repeats,
            "all_samples_ok": all(s.get("ok") for s in samples) if samples
                              else False,
            "counts_from_server_usage_only": True,
        },
    }
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    else:
        sys.stdout.write(payload + "\n")
    agg = report["aggregate"]
    print("samples=%d ok=%s median_decode_tps=%s"
          % (len(samples), report["validation"]["all_samples_ok"],
             agg["median_decode_tps_client_observed"]),
          file=sys.stderr)
    return 0 if report["validation"]["all_samples_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
