# Native feedback diagnostic: failed invoice task

Clean source `cd06b4215fbecdce7922afdc031148ece89c0908`, Qwen3-4B-Instruct-2507 Q4_0, CPU10 on the Latitude. The opt-in diagnostic ran two real model turns. First it searched `hexagon invoice`, receiving zero matches. The second turn explicitly acknowledged that empty result, proving native tool-history feedback arrived, but returned a natural-language clarification instead of a tool call. The strict diagnostic decoder rejected it.

No move occurred; unchanged demo call and final-state checks both failed. This is not a v2 candidate result or a quality PASS. The complete transcript, native profiles and file hashes are preserved. Private user-path prefixes were redacted.

Loop duration was 8.057 seconds, excluding fixture creation and model loading. The `total_process_elapsed_s` field is a broader diagnostic interval beginning at artifact hashing and ending after model destruction/verification; despite its legacy name, it excludes argument parsing, initial Git reads, final serialization and SDK shutdown. No power or cold-E2E claim is made.

The service restart was requested after the process finished. Next separate diagnostic: constrained tool-output syntax with a real restrictive canary. Do not repair this output into a successful clarification or change frozen v2 semantics.
