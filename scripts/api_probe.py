"""Independent remote API readiness checks. No local inference or hardware lock."""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import json
import logging
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo.optimizer.api_status import classify_exception
from turbo.optimizer.proposer import AnthropicClient
from turbo.optimizer.critic import OpenAIClient


class _Discard:
    def write(self, text):
        return len(text)
    def flush(self):
        pass


def _safe_model(value, env):
    if not isinstance(value, str):
        return None
    secrets = [env.get(name) for name in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY')]
    if any(isinstance(secret, str) and secret and secret in value for secret in secrets):
        return '[REDACTED]'
    return value[:200]


def probe(provider, *, timeout_s=30, env=None, factories=None, clock=time.perf_counter):
    """One SDK request, no retries. Payload and provider exception text are discarded."""
    if provider not in ('anthropic', 'openai'):
        raise ValueError('Unsupported provider')
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 120:
        raise ValueError('timeout must be finite and in (0, 120] seconds')
    env = os.environ if env is None else env
    factories = factories or {'anthropic': AnthropicClient, 'openai': OpenAIClient}
    record = {'provider': provider, 'model': _safe_model(env.get(provider.upper()+'_MODEL'), env),
              'timestamp': datetime.now(timezone.utc).isoformat(), 'status': 'error',
              'error_category': None, 'latency_ms': None,
              'latency_scope': 'wall clock around SDK construction and one remote request',
              'workspace_header_configured': bool(env.get('ANTHROPIC_WORKSPACE_ID', '').strip()) if provider == 'anthropic' else False}
    try:
        record['sdk_version'] = version(provider)
    except PackageNotFoundError:
        record['sdk_version'] = None
    started = clock()
    try:
        client = factories[provider](env=env, max_output_tokens=128)
        client.complete('You are an API connectivity check. Reply only OK.', 'Reply OK.', timeout_s=timeout_s)
        record['status'] = 'ok'
    except Exception as exc:
        record['error_category'] = classify_exception(exc)
    finally:
        record['latency_ms'] = round(max(0, clock()-started)*1000, 3)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=('anthropic', 'openai', 'all'), default='all')
    parser.add_argument('--timeout', type=float, default=30, help='Per SDK request timeout seconds, (0,120]; no retries')
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 120:
        parser.error('--timeout must be finite and in (0,120]')
    providers = ('anthropic', 'openai') if args.provider == 'all' else (args.provider,)
    # CLI-only suppression: external SDK debug logging/stdout must not contaminate
    # the safe JSON stream. Restore logging state for callers embedding main().
    prior = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with redirect_stdout(_Discard()), redirect_stderr(_Discard()):
            results = [probe(provider, timeout_s=args.timeout) for provider in providers]
    finally:
        logging.disable(prior)
    print(json.dumps({'schema_version': 'turbolab.api-probe.v1', 'results': results},
                     ensure_ascii=False, allow_nan=False, indent=2))
    return 0 if all(row['status'] == 'ok' for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
