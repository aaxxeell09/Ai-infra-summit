# TurboLab remote API readiness

Branch based on `c866c48f0d12219d8cf38187c71769623143c0c8`. No local model inference or historical archive mutation is required to validate these API adapters.

## Credentials and workspace

Set `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` in the target process environment. TurboLab observes key availability; the SDK reads its credential directly. Models remain explicitly configured, with no guessed default.

`ANTHROPIC_WORKSPACE_ID` is optional. When nonempty, the Anthropic SDK is constructed with `default_headers={"anthropic-workspace-id": workspace_id}`. Unset/blank leaves this header absent, including for existing workspace-scoped keys. The probe reports only whether the header is configured, not the workspace identifier itself.

SDK automatic retries are disabled for both adapters. This avoids silently multiplying an advisory/probe request timeout. The existing JSON-protocol retry policy remains separate. A timeout is an SDK transport timeout, **not** a guaranteed hard whole-process deadline for every transport/DNS phase.

## Probe

```powershell
# Run from the isolated checkout using the Windows ARM64 Python that has the SDKs.
$env:PYTHONUTF8 = '1'
# Needed only for the key that requires this header; use its actual workspace ID.
$env:ANTHROPIC_WORKSPACE_ID = 'YOUR_ACTUAL_WORKSPACE_ID'
python -X utf8 scripts/api_probe.py --provider anthropic --timeout 30
python -X utf8 scripts/api_probe.py --provider openai --timeout 30
python -X utf8 scripts/api_probe.py --provider all --timeout 30
```

Each provider makes one small remote text request independently. The script never imports a local inference backend or acquires a hardware mutex. An Anthropic failure does not suppress the OpenAI attempt. Exit0 means all selected probes succeeded, exit1 means at least one failed, exit2 means invalid CLI arguments.

Output schema: `turbolab.api-probe.v1`, with `results[]` entries containing provider, configured model, SDK version, timestamp, status, `error_category`, `latency_ms`, latency scope and workspace-header presence. Latency includes SDK construction and the request; it is not pure server processing time. Response text, HTTP bodies, exception messages, headers and credentials are not printed. CLI SDK debug/stdout/stderr output is discarded; only the safe JSON is printed.

Categories: `key_unavailable`, `sdk_unavailable`, `auth_error`, `quota_error`, `rate_limit`, `model_error`, `timeout`, `connection_error`, `protocol_error`, `api_error`. A generic404 with no model evidence remains `api_error`;429 is only classified quota when quota/billing evidence exists. Ambiguous provider errors are not guessed. OpenAI distinguishes exhausted quota from transient request rate limits in its [official error guide](https://developers.openai.com/api/docs/guides/error-codes).

## Search isolation

Advisor errors, malformed responses, cancelled critique futures and cache failures become sanitized failure records; deterministic candidates remain eligible through the normal guards. API requests occur outside hardware ownership. Critiques remain asynchronous. Scheduler claim/release cleanup is exception-safe and a scheduler instance refuses concurrent hardware entry. The tracker remains the shared cross-process hardware mutex authority.

A proposer is still a bounded synchronous advisory call before candidate generation, so its API latency can delay that round; it never owns the hardware lock. This does not make remote APIs mandatory for deterministic search.

## Portable validation

```powershell
python -X utf8 -m pytest tests -q -p no:cacheprovider
python -X utf8 eval/validate_dataset.py
python -X utf8 eval/leakage_audit.py
npm --prefix frontend run check
npm --prefix frontend test
```

Tests inject SDKs/providers/runners and perform no paid calls or local model inference. Header propagation, absence, credentials missing, error categories, redaction and provider-failure search fallback are covered. Live key/workspace authorization, model entitlement, replenished OpenAI credits and actual Windows ARM64 network latency require running the probe on the target. Successful portable tests cannot assert those live facts.

### Installed SDK transport check

`tests/test_api_sdk_transport.py` also exercises the actual installed provider SDK
request builders through a synthetic `httpx2.MockTransport`. It is optional in
the default dependency-light suite. An isolated environment with Anthropic
1.6.0, OpenAI 3.14.1 and httpx2 2.13.0 passed this test together with all readiness
checks (35 tests), with no network requests. This verifies header propagation
and SDK transport compatibility for those versions; it does not verify real
credentials, workspace authorization, available credits or model access.
