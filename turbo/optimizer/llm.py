"""Vendor neutral plumbing for the language-model side of an autotune session.

A tuning session must keep running when no API key exists, when a vendor SDK is
absent and when a model answers with prose instead of the JSON it was asked for.
So every vendor detail lives behind one narrow interface, credentials are only
ever observed as present or absent, and a malformed answer is a hard protocol
error rather than something to repair: a repaired hypothesis is an unattributable
hypothesis, and this loop spends hardware minutes on what it is told.

Responses are cached by the digest of the exact request, which makes a replayed
session free, deterministic and offline. That is also what ``--mock-llm`` and the
whole test suite use, so no test in this repository can reach a network.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.experiments import atomic, digest
from turbo.json_io import parse_json

SCHEMA = 'local-turbo.autotune-llm.v1'

STATUS_AVAILABLE = 'AVAILABLE'
STATUS_UNAVAILABLE = 'UNAVAILABLE'

#: Where a cached response lives. state.ensure_home creates this directory.
DEFAULT_CACHE_DIR = ROOT / 'local/autotune/analyses'

#: Keys call_json stamps onto a parsed response. A model that emits one of them
#: would be shadowing session bookkeeping, so seeing one is a protocol error.
RESERVED_KEYS = ('_elapsed_s', '_api_calls', 'cached')


class LLMUnavailable(RuntimeError):
    """No usable client: credentials, SDK, transport or time ran out."""

    def __init__(self, message, *, category='api_error'):
        super().__init__(message)
        self.category = category


class LLMProtocolError(ValueError):
    """The answer was not the strict JSON object the caller declared."""


def credential_status(env_var, env=os.environ):
    """Whether a credential is present. The value never leaves this function.

    Nothing downstream needs the secret itself: the vendor SDKs read it from the
    environment on their own, so TurboLab only ever handles its presence, and a
    status object can be logged or archived without redaction.
    """
    value = env.get(env_var)
    return STATUS_AVAILABLE if isinstance(value, str) and value.strip() else STATUS_UNAVAILABLE


def prompt_digest(payload):
    """Stable sha256 of a canonical request. Same request, same cache entry."""
    return digest(payload)


def request_payload(client, system, user):
    """The canonical request whose digest keys the cache.

    The model identity is part of the key: the same prompt answered by a
    different model is a different answer, and silently reusing one for the
    other would misattribute every hypothesis that came out of it.
    """
    return {'schema_version': SCHEMA, 'client': getattr(client, 'name', None),
            'model': getattr(client, 'model', None), 'system': system, 'user': user}


class ResponseCache:
    """Content addressed responses on disk. A damaged entry is simply a miss."""

    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else DEFAULT_CACHE_DIR

    def path_for(self, request_digest):
        return self.directory / (str(request_digest) + '.json')

    def get(self, request_digest):
        """The cached response object, or None.

        Reads the bytes once and never writes during a read: a cache is an
        accelerator, so a corrupt entry must degrade into an API call rather
        than end a session that is holding hardware.
        """
        try:
            entry = parse_json(self.path_for(request_digest).read_bytes(), require_object=True)
        except (OSError, ValueError, UnicodeDecodeError):
            return None
        response = entry.get('response')
        return response if isinstance(response, dict) else None

    def put(self, request_digest, response):
        if not isinstance(response, dict):
            raise ValueError('Only a JSON object response is cacheable')
        payload = {'schema_version': SCHEMA, 'digest': str(request_digest),
                   'stored_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                   'response': {k: v for k, v in response.items() if k not in RESERVED_KEYS}}
        path = self.path_for(request_digest)
        atomic(path, json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n')
        return path


class LLMClient:
    """One completion call, one string back. Vendors subclass this.

    A subclass must import its SDK inside ``complete`` and not at module import
    time, so this module and everything above it load on a machine with no
    vendor package installed at all.
    """

    name = 'abstract'
    model = None
    status = STATUS_UNAVAILABLE

    def complete(self, system, user, *, timeout_s):
        raise NotImplementedError('LLMClient subclasses implement complete()')

    def describe(self):
        return {'client': self.name, 'model': self.model, 'status': self.status}


class MockClient(LLMClient):
    """Deterministic canned answers, keyed by request digest or by callable.

    Backing ``--mock-llm`` and every test. A canned value that is an exception
    instance is raised instead of returned, which is how a test reaches the
    timeout and transport paths without a network.
    """

    name = 'mock'
    status = STATUS_AVAILABLE

    def __init__(self, responses, *, model='mock', default=None):
        self.responses = responses
        self.model = model
        self.default = default
        self.calls = []

    def complete(self, system, user, *, timeout_s):
        key = prompt_digest(request_payload(self, system, user))
        self.calls.append({'digest': key, 'system': system, 'user': user, 'timeout_s': timeout_s})
        if callable(self.responses):
            answer = self.responses(system, user)
        else:
            answer = self.responses.get(key, self.default)
        if isinstance(answer, BaseException):
            raise answer
        if answer is None:
            raise LLMUnavailable('MockClient has no canned response for digest ' + key)
        return answer


def call_json(client, system, user, *, cache=None, timeout_s=60, retries=1):
    """Call the model and return the strict JSON object it was asked for.

    ``retries`` counts extra attempts after the first, so the default makes at
    most two calls. Malformed output is never repaired or partially parsed: when
    the last attempt still fails to decode, this raises LLMProtocolError.

    The returned object carries ``_elapsed_s`` (wall clock the scheduler charges
    to API wait), ``_api_calls`` and ``cached``. A cache hit reports zero of
    both and ``cached`` True, so a replayed session cannot inflate its own API
    call counter.
    """
    key = prompt_digest(request_payload(client, system, user))
    if cache is not None:
        hit = cache.get(key)
        if hit is not None:
            return {**hit, '_elapsed_s': 0.0, '_api_calls': 0, 'cached': True}

    if getattr(client, 'status', STATUS_UNAVAILABLE) != STATUS_AVAILABLE:
        raise LLMUnavailable(getattr(client, 'name', 'client') + ' is unavailable: ' + STATUS_UNAVAILABLE)
    if not isinstance(retries, int) or retries < 0:
        raise ValueError('retries must be a non-negative integer')

    started = time.monotonic()
    attempts = 0
    last_error = None
    for _ in range(retries + 1):
        attempts += 1
        try:
            text = client.complete(system, user, timeout_s=timeout_s)
        except LLMUnavailable as exc:
            exc.elapsed_s = time.monotonic() - started
            exc.api_calls = attempts
            raise
        except TimeoutError as exc:
            elapsed = time.monotonic() - started
            failure = LLMUnavailable(getattr(client, 'name', 'client') + ' timed out after '
                                     + format(elapsed, '.3f') + ' s (limit ' + str(timeout_s) + ' s)')
            failure.elapsed_s = elapsed
            failure.api_calls = attempts
            raise failure from exc
        except Exception as exc:
            # Transport, auth and rate-limit failures are all "no answer right
            # now". They are unavailability, not a protocol violation, because
            # the model never got to say anything.
            elapsed = time.monotonic() - started
            failure = LLMUnavailable(getattr(client, 'name', 'client') + ' call failed: ' + type(exc).__name__)
            failure.elapsed_s = elapsed
            failure.api_calls = attempts
            raise failure from exc

        if not isinstance(text, str):
            last_error = 'client returned ' + type(text).__name__ + ', not text'
            continue
        try:
            parsed = parse_json(text.encode('utf-8'), require_object=True)
        except (ValueError, UnicodeDecodeError) as exc:
            last_error = str(exc)
            continue
        present = [k for k in RESERVED_KEYS if k in parsed]
        if present:
            elapsed = time.monotonic() - started
            failure = LLMProtocolError('Response claims session bookkeeping keys: ' + ', '.join(present))
            failure.elapsed_s = elapsed
            failure.api_calls = attempts
            raise failure

        elapsed = time.monotonic() - started
        if cache is not None:
            cache.put(key, parsed)
        return {**parsed, '_elapsed_s': elapsed, '_api_calls': attempts, 'cached': False}

    elapsed = time.monotonic() - started
    failure = LLMProtocolError('Response was not a JSON object after ' + str(attempts)
                               + ' attempt(s): ' + str(last_error))
    failure.elapsed_s = elapsed
    failure.api_calls = attempts
    raise failure


def require(value, kind, where):
    """Strict type assertion used by every schema validator in this package."""
    if type(value) is not kind:
        raise LLMProtocolError(where + ' must be ' + kind.__name__ + ', got ' + type(value).__name__)
    return value


def require_text(value, where):
    require(value, str, where)
    if not value.strip():
        raise LLMProtocolError(where + ' must not be empty')
    return value


def require_keys(obj, expected, where):
    """Exactly these keys. An extra key means the schema drifted, not that the
    model was helpful, and a missing key must never be filled with a default."""
    require(obj, dict, where)
    missing = sorted(set(expected) - set(obj))
    extra = sorted(set(obj) - set(expected))
    if missing:
        raise LLMProtocolError(where + ' is missing ' + ', '.join(missing))
    if extra:
        raise LLMProtocolError(where + ' carries undeclared keys ' + ', '.join(extra))
    return obj


def response_meta(response):
    """Timing and cache facts the scheduler needs, without the payload."""
    return {'elapsed_s': response.get('_elapsed_s'), 'api_calls': response.get('_api_calls'),
            'cached': bool(response.get('cached'))}
