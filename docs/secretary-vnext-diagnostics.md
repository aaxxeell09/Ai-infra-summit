# Secretary vNext diagnostics and versioning plan

Status: **diagnostic only; no evaluator, parser, scoring, dataset, golden action,
fixture, or historical result changed.** No hardware inference was performed.
The examples below are synthetic and do not copy development or heldout prompts.

The tests in `tests/test_secretary_vnext_diagnostics.py` characterize current
`secretary-eval-v2` behavior. Passing these tests means the documented behavior
was reproduced; it does **not** mean the unsafe or permissive behavior is desired.
They must not become acceptance criteria for a stricter future evaluator.

## Observed behavior

| Synthetic diagnostic | Current frozen behavior | Why it matters |
|---|---|---|
| One valid tagged action followed by an unfinished second action | Successful, not marked invalid | The decoder counts surviving complete calls, not every attempted action envelope. |
| One valid tagged action followed by a tagged object whose `name` is numeric | Successful, not marked invalid | The production parser silently discards the malformed action object. |
| One valid tagged action followed by a tagged JSON array | Successful, not marked invalid | Valid JSON does not necessarily represent an action; the parser discards it. |
| Two well-formed action objects in separate envelopes | Invalid | The frozen adapter still enforces exactly one surviving call; the diagnostics do not weaken that check. |
| A literal `</tool_call>` inside a JSON string | Plain JSON accepted; tagged JSON rejected | The envelope regex treats the marker inside the quoted string as the end of the outer envelope. This parser limitation is distinct from streaming stop detection. |
| Introductory/trailing prose outside one valid envelope | Successful, not marked invalid | The parser does not require complete consumption of the response. Whether prose is allowed needs an explicit future contract. |
| Duplicate JSON keys inside a complete envelope | Invalid | Existing duplicate-key rejection is useful and must be preserved. |
| Absolute path resolving inside a disposable root | General executor permits it; frozen fixture adapter refuses it | Production and evaluation path contracts differ even when containment holds. No path outside the temporary test root is read. |
| Another writer creates a move destination after the existence check, before rename | POSIX rename replaces that destination | Static overwrite protection is not atomic protection against concurrent writers. The deterministic test injects this interleaving inside its temporary directory. |

Relevant implementation boundaries:

- `turbo/service.py::parse_calls`: regex extraction, JSON decoding, and silent
  filtering of non-action objects.
- `eval/scoring.py::score`: duplicate-key checking of extracted JSON fragments,
  followed by adapter decoding.
- `eval/secretary_adapter.py::SecretaryAdapter.decode`: exactly-one-call and
  argument-schema validation after production parsing.
- `eval/secretary_adapter.py::PreparedFixture.run_actual`: stricter fixture path
  restrictions and isolated execution.
- `turbo/secretary.py::_safe_resolve` and `execute_tool`: containment checks and
  check-then-rename move behavior.

These probes establish possible failure modes. They do not establish that any
stored hardware result was affected, and they do not authorize rescoring or
rewriting any historical artifact.

## Proposed vNext changes, requiring explicit versioned approval

1. **Define one unambiguous output contract.** Decide which envelopes are supported
   (tagged action, raw JSON, fenced JSON), whether surrounding prose is allowed,
   and whether this interface represents one action or a multi-action plan.
   Preserve the current v2 implementation and its hashes. The current prompt's
   “at most four” instruction and the evaluator's exactly-one-action contract
   should be reconciled only in a separately approved version.
2. **Validate the entire response.** A JSON-aware envelope scanner should track
   quoted strings and escapes, require all envelopes to close, and reject extra
   malformed or non-action objects instead of discarding them. Preserve
   duplicate-key rejection, exact schemas, and exactly-one-action enforcement.
   Do not repair malformed output or return the first usable action as success.
3. **Separate parsing from generation control.** An optional native generation
   stop can reduce unwanted continuation, but cannot prove action correctness.
   Literal markers inside strings must not prematurely end generation or parsing.
   Benchmark baseline and candidate configurations independently, preserving raw
   output and native termination evidence. Do not disable thinking; it is already
   disabled in the current path.
4. **Bind all semantic dependencies.** Include the actual parser and tool executor
   in the future evaluator identity, not only the four eval-module source hashes.
   Report canonical Git identity and actual executable-file identity explicitly
   across LF/CRLF checkouts. Runtime tuning differences remain declared treatments.
5. **Preserve path constraints and strengthen atomicity.** Define an explicit
   workspace-relative path contract across adapters. Design atomic no-replace
   moves and safe file opening for each supported OS. Add Windows junction,
   reparse-point, alternate-stream, reserved-name, Unicode/case, and concurrent
   writer tests using disposable synthetic roots. Do not assume POSIX rename
   behavior describes Windows behavior.
6. **Version and re-establish evidence.** Add a new evaluator/protocol version and
   an approved new baseline for the new contract. Keep v2 datasets, expectations,
   manifests, fixtures, and collected results unchanged. Publish comparability
   limits between versions. Tests can validate software behavior in CI; fresh
   Snapdragon trials are needed for performance and backend conclusions.

Suggested future small changes, after approval: contract specification; isolated
new parser and adversarial acceptance tests; semantic-provenance schema; atomic
file operations; new-version runner integration; device baseline/candidate runs.
None are implemented by this diagnostic document.

## Portable workflow inspection

`.github/workflows/portable-validation.yml` targets Ubuntu, Windows, and macOS,
Python 3.12 and Node 22. It keeps source/archive LF bytes for hash verification,
while the separate fixture checkout test explicitly exercises `core.autocrlf=true`.
It runs frozen validation, the narrowly pinned historical-exposure audit, Python
unit tests, frontend checks, and a final tracked-file diff guard.

The MCP compiled-library integration explicitly skips Windows because that test
currently builds only POSIX shared-library stubs; a missing C compiler is a
separate explicit skip. It uses synthetic model bytes and performs no inference.
The new rename-race diagnostic skips non-POSIX platforms because its assertion is
specific to POSIX replacement semantics. Neither skip validates Windows native
SDK behavior.

Windows CI still needs actual execution evidence. The following existing tests
create symlinks without capability checks and therefore require the runner's
symlink privilege/developer-mode support:

- `tests/test_backend_identity.py::test_qairt_requires_all_declared_shards_and_rejects_escape`
- `tests/test_secretary.py::SandboxEscapeTest` symlink cases
- `tests/test_service.py::test_search_does_not_follow_outside_symlink`

The directory-link test must also exercise an actual Windows directory link,
not assume Unix symlink behavior. Do not blanket-skip these safety tests merely
to obtain a green job. Prefer a verified capable runner; if a capability is truly
unavailable, report that exact gap and retain separate supported-platform coverage.

No Windows run was performed while preparing these diagnostics. GitHub-hosted
loopback HTTP tests should remain enabled; a local sandbox socket denial is not
a reason to disable those integration tests in CI. Windows/Snapdragon dispatch,
compiled QAIRT behavior, energy-counter operation, and stop-callback behavior
remain **REQUIRES_HARDWARE_VALIDATION**.

## Reproduce software diagnostics

```sh
python -m pytest tests/test_secretary_vnext_diagnostics.py -q -p no:cacheprovider
```

All inputs and filesystem roots are synthetic. No model, dataset mutation,
network connection, or native SDK is required.
