# Repeated constrained feedback diagnostics

Clean source `31bb6a178638eda96c33fe3b9f0bbd4ec97c3ebe`, CPU10/context4096,
GenieX0.6.1, same public invoice fixture and opt-in CLI as the initial trial.
The frozen50-case evaluator is unchanged and is not used by these diagnostics.

| Run | Native canary | Turns | Final state matches | Existing grade | Loop time |
|---|---|---:|---|---|---:|
| 4B repeat1 | Pass | 5 | Yes | Fail: extra calls |21.150 s|
| 4B repeat2 | Pass | 6 | Yes | Fail: extra calls |61.174 s|
| 20B | Pass | 3 | No | Fail: invalid output |19.551 s|

Together with `invoice-grammar-1000`, the4B made the intended filesystem move in
three of three trials. **All three fail the existing exact-call verifier.**
This is repetition of one public fixture, not diverse-task quality qualification.
Loop timing excludes model load and fixture creation. Broader diagnostic intervals
were32.220,95.489 and90.288 seconds respectively; those include hashing/loading,
canary, fixture, loop and verification, but exclude final serialization/SDKshutdown.
The latency variation prevents a dependable latency or speedup claim. No energy
was captured. No best-run selection is used.

The20B passed the simple grammar canary and produced initial valid tool output,
but the subsequent loop ended `invalid_output`; nothing was repaired or re-scored.
Passing a canary does not establish every tool-grammar branch or task success.

Each JSON contains the original native output, action/results, file snapshots,
identities and timing scope. Only private tools-path roots were replaced; private
original SHA-256 values are included. The initial native configs remain in the
campaign folder; exact argv appears in the supervisor source and prior diagnostic
README. These results do not change default MCP/service behavior or the quality gate.
