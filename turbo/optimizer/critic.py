"""An adversarial second opinion from a different vendor, on purpose.

A proposer that reviews its own ideas agrees with itself. This module asks a
model from another family to attack a batch of candidates: is the comparison
confounded, has this idea already been measured, is a claim asserted rather than
evidenced, is the candidate gaming the benchmark, does it move a measurement
boundary. The answer is advisory input to the scheduler and to the human record.

It is deliberately asynchronous. Hardware minutes are the scarce resource in a
bounded session, so a pending critique must never be waited on by the loop that
owns the device: submit it, keep running treatments, collect it when it is done.
"""
from __future__ import annotations

import concurrent.futures
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer.llm import (LLMClient, LLMProtocolError, LLMUnavailable, STATUS_AVAILABLE,
                                 call_json, credential_status, require, require_keys, require_text,
                                 response_meta)

SCHEMA = 'local-turbo.autotune-critique.v1'

OPENAI_KEY_VAR = 'OPENAI_API_KEY'
OPENAI_MODEL_VAR = 'OPENAI_MODEL'

KINDS = ('confounding', 'duplicate_idea', 'unsupported_claim', 'benchmark_gaming',
         'boundary_shift', 'other')
SEVERITIES = ('block', 'warn')
BLOCK = 'block'
WARN = 'warn'

FINDING_KEYS = ('kind', 'candidate_id', 'detail', 'severity')

SYSTEM_PROMPT = (
    'You are reviewing proposed configuration experiments for an edge inference autotune '
    'session. Attack them. Look for: a comparison that is confounded, an idea already measured '
    'in this session, a claim asserted without evidence in the payload, a candidate that would '
    'improve the benchmark without improving the product, and anything that moves a measurement '
    'boundary so results stop being comparable.\n'
    'You may only reason from the payload given. Do not invent measurements.\n'
    'Answer with a single JSON object and nothing else, no prose and no code fence:\n'
    '{"findings":[{"kind":"confounding"|"duplicate_idea"|"unsupported_claim"|"benchmark_gaming"'
    '|"boundary_shift"|"other","candidate_id":str|null,"detail":str,"severity":"block"|"warn"}]}\n'
    'Return an empty findings array when you have no objection.'
)

_EXECUTOR = None


class OpenAIClient(LLMClient):
    """OpenAI adapter. The SDK reads the key from the environment itself.

    As with the proposer, the credential value never passes through TurboLab and
    the model version is never hardcoded: an unset model variable is a failure,
    not a silent default.
    """

    name = 'openai'

    def __init__(self, *, model=None, env=os.environ, max_output_tokens=4096):
        self.status = credential_status(OPENAI_KEY_VAR, env)
        declared = model if model is not None else env.get(OPENAI_MODEL_VAR)
        self.model = declared if isinstance(declared, str) and declared.strip() else None
        self.max_output_tokens = max_output_tokens
        self._sdk_client = None

    def complete(self, system, user, *, timeout_s):
        if self.status != STATUS_AVAILABLE:
            raise LLMUnavailable(OPENAI_KEY_VAR + ' is not set, so no OpenAI call is possible')
        if not self.model:
            raise LLMUnavailable(OPENAI_MODEL_VAR + ' is not set; TurboLab never assumes a model version')
        try:
            import openai
        except ImportError as exc:
            raise LLMUnavailable('The openai SDK is not installed in this environment') from exc
        if self._sdk_client is None:
            self._sdk_client = openai.OpenAI()
        completion = self._sdk_client.chat.completions.create(
            model=self.model, max_completion_tokens=self.max_output_tokens, timeout=timeout_s,
            messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}])
        choices = getattr(completion, 'choices', None) or []
        if not choices:
            raise LLMProtocolError('OpenAI response carried no choice')
        text = getattr(choices[0].message, 'content', None)
        if not isinstance(text, str) or not text.strip():
            raise LLMProtocolError('OpenAI response carried no text content')
        return text


def validate(response):
    """Strict schema check. Nothing is coerced and no finding is invented."""
    require(response, dict, 'critique response')
    if 'findings' not in response:
        raise LLMProtocolError('critique response is missing findings')
    raw = response['findings']
    require(raw, list, 'findings')
    findings = []
    for index, item in enumerate(raw):
        where = 'findings[' + str(index) + ']'
        require_keys(item, FINDING_KEYS, where)
        kind = item['kind']
        if kind not in KINDS:
            raise LLMProtocolError(where + '.kind is not a declared kind: ' + repr(kind))
        severity = item['severity']
        if severity not in SEVERITIES:
            raise LLMProtocolError(where + '.severity is not block or warn: ' + repr(severity))
        candidate_id = item['candidate_id']
        if candidate_id is not None:
            require_text(candidate_id, where + '.candidate_id')
        require_text(item['detail'], where + '.detail')
        findings.append(dict(item))
    return findings


def render_user_prompt(payload):
    import json
    return ('Review payload:\n'
            + json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            + '\n\nReturn the declared JSON object.')


def critique(client, payload, *, cache=None, timeout_s=60, retries=1):
    """Review a batch of candidates and return the validated findings.

    A finding with severity 'block' is ADVISORY. It is a reason for the
    scheduler to deprioritise, rewrite or drop a candidate and it belongs in the
    session record, but it is never a substitute for turbo.optimizer.guard.check
    and it never grants permission either: guard.check is the only thing that
    decides what may run, and it runs regardless of what the critic said.
    """
    response = call_json(client, SYSTEM_PROMPT, render_user_prompt(payload), cache=cache,
                         timeout_s=timeout_s, retries=retries)
    findings = validate(response)
    return {'schema_version': SCHEMA, 'findings': findings,
            'blocking': [f for f in findings if f['severity'] == BLOCK],
            'advisory_only': True,
            'source': {'client': getattr(client, 'name', None), 'model': getattr(client, 'model', None),
                       **response_meta(response)}}


def executor():
    """The shared single-worker pool. One critique at a time is enough."""
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1,
                                                          thread_name_prefix='turbo-critic')
    return _EXECUTOR


def submit(client, payload, *, cache=None, timeout_s=60, retries=1, pool=None):
    """Start a critique off the hardware path and return a handle.

    The caller must keep scheduling treatments after this returns. Blocking the
    device loop on a critique converts an API latency into idle hardware, which
    is the one cost a bounded session cannot recover.
    """
    return (pool or executor()).submit(critique, client, payload, cache=cache,
                                       timeout_s=timeout_s, retries=retries)


def result(handle, *, wait_s=None):
    """The critique if it is ready, else None. Never idle the worker on this.

    ``wait_s`` defaults to no waiting at all: poll between treatments. Pass a
    small value only at the end of a session, when there is no hardware work
    left to lose. Failures inside the critique surface here, so a caller that
    treats the critique as optional should catch LLMUnavailable and
    LLMProtocolError and carry on.
    """
    if wait_s is None:
        if not handle.done():
            return None
        return handle.result()
    try:
        return handle.result(timeout=wait_s)
    except concurrent.futures.TimeoutError:
        return None


def shutdown(wait=False):
    """Drop the shared pool. Tests and session teardown use this."""
    global _EXECUTOR
    pool, _EXECUTOR = _EXECUTOR, None
    if pool is not None:
        pool.shutdown(wait=wait)
