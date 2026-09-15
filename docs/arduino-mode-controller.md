# Arduino UNO Q mode controller and edge device

Status: code complete and offline-tested on 2026-09-15. Connectivity state is
whatever evidence the caller supplies; uno_q_board() itself defaults to
unverified. No inference, button press or pixel output has been measured on
the board yet. Every hardware behavior below is a design to confirm on the
bench. The parent service (turbo/service.py) serves GET /api/modes,
POST /api/apply and POST /api/run on 127.0.0.1:8080.

This is a real control plane, not a light show: each control changes the
actually applied Snapdragon policy. The parent /api/apply selects the
measured native config (device CPU/NPU/GPU placement, threads, context) for
the chosen mode from the tuned recommendation record and rejects modes with
no eligible measured profile. The adapter enforces the evidence loop in both
directions: apply_request() is the exact body, apply_response() refuses any
ack that lacks the applied config and its measured evidence source, and
handle_output() carries active_mode plus that config back to the board.

## Physical mode pad (turbo/arduino_adapter.py)

Three Modulino Buttons map one-to-one to inference modes; a press becomes
exactly one parent-service call:

| Control | Event line (board to host) | Resulting call |
|---|---|---|
| Button A | {"event":"button","source":"fast","mode":"fast"} | POST /api/apply {"mode":"fast"} |
| Button B | {"event":"button","source":"efficient","mode":"efficient"} | POST /api/apply {"mode":"efficient"} |
| Button C | {"event":"button","source":"balanced","mode":"balanced"} | POST /api/apply {"mode":"balanced"} |
| Knob turn | {"event":"knob","direction":1,"mode":"fast"} | apply to the next mode in fast -> efficient -> balanced -> fast |

Knob selection is discrete mode choice among the three measured modes and
nothing more. It never claims continuous tuning: no knob position maps to an
unknown config, thread count or context length, and the adapter produces no
such event. Preference weighting (fast/efficient as weights rather than
direct selection) is a server capability; until the parent API accepts one,
the knob stays a three-position selector.

The adapter is transport independent: it consumes newline-delimited JSON, so
stdin, a serial pipe or a socket drive the same ModeController. It validates
every line, debounces per source (default 250 ms, configurable 0-2000 ms) so
one physical press cannot fire twice, and raises EventError on malformed
input instead of guessing. It never opens a URL itself: the host receives
{"action":"apply","mode":...} and performs the HTTP call.

The compiled archive Bridge (commit 6edf840) already exposes get_action(),
get_status() and get_modules() on the MCU. bridge_action_to_event() maps its
packed int - low byte button number 1..3, high byte signed knob direction -
to the same events, so the existing firmware needs no reflash for mode-pad
duty. The button-to-mode index order is provisional; confirm on the bench.

Board output is one compact JSON line from handle_output():

    {"pixels":{"tiny-gguf":"cpu","whisper":"npu"},"progress":0.3,
     "active_mode":"balanced","config":{"device":"cpu","threads":4,"context":4096},
     "vibrate":true}

Pixels show per-model CPU/NPU/GPU placement from /api/status: the
models[].device field is the configured default placement, and when
status.applied names the model it acknowledged, that applied config's device
overrides the pixel because it was actually applied, not defaulted. progress
0.0 to 1.0 tracks a running tune, active_mode/config echo the actually
applied Snapdragon policy with its evidence, and vibrate marks a finished
secretary run for the Modulino Vibro. The real /api/status body has no
run_finished field: completion is a caller-derived event the host attaches
when its own run ends; the renderer never invents it. Device kinds are
extensible: a GPU entry in the registry or model list appears in pixels
automatically.

## Edge device registry and routing (turbo/edge_device.py)

uno_q_board() registers the board as a CPU Linux ARM64 inference device.
Registry facts and their evidence:

- compute: cpu is the intended runtime placement, not a claimed hardware
  limit. The Dragonwing QRB2210 SoC also contains a GPU that nobody has
  measured here, so this project makes no "CPU-only hardware" claim in either
  direction. No NPU claim either: register_device() rejects an npu entry
  that lacks measured_profiles.
- connectivity: unverified by default and never asserted from a past
  observation. A caller that has actually probed a board passes its evidence
  dict explicitly (uno_q_board(connectivity=...), requiring a boolean
  "verified" field); that evidence may record what was observed (arch,
  memory, swap, disk) as a clear observation of one unit at one time, not a
  hardware promise. Serial numbers and other per-unit identifiers stay out
  of this repo and this doc.
- status: unverified for inference. Connectivity does not imply capability;
  route() only selects devices whose status is verified and whose recorded
  context_tokens is a positive integer that fits the explicit prompt plus
  output budget. A device without a recorded context is never eligible:
  an unmeasured context is not unlimited, so routing fails closed with
  EdgeDeviceError instead of guessing, and prompts still go to the verified,
  bounded laptop until the board proves a serving endpoint.
- endpoint: always an operator-configured local LAN URL, never invented in
  code. BoardInferenceClient validates that shape and refuses everything
  else (device paths, empty strings).

BoardInferenceClient calls POST /v1/chat/completions (the same OpenAI shape
the parent service already serves) with a bounded timeout. This is the board
standalone-inference role, separate from the mode pad: once the operator
configures an endpoint and a measured run verifies it, the board serves
prompts directly. Its latency_ms covers the whole round trip: transfer plus
remote inference. Any transport or body failure surfaces as
EdgeDeviceError; escalate_to_laptop() retries once on the first registry
entry with kind laptop and re-raises if both paths fail, so callers see real
outages instead of silent degradation.

## Tiny GGUF on the board (research, unverified)

Can the UNO Q run a small GGUF on its Linux CPU? The verified numbers give a
real but narrow window: 1315 MB available RAM and 3.2 GB disk fit a
sub-1B 4-bit model (roughly 0.4-0.6 GB weights plus KV cache and runtime),
while anything around 1-2 GB of weights would hit swap and fail. aarch64
llama.cpp builds exist upstream, but decode speed on a QRB2210-class core is
unknown to us and we claim no speed or NPU advantage. The official GenieX
v0.6.1 Linux ARM64 CPU SDK (~10 MB zip) is the intended runtime; the parent
installs it after the current performance window, and turbo/native.py is the
candidate stdlib adapter to wrap it once validated on the board. Until then
this row stays unverified: no benchmark numbers exist for this device.

The parent owns the device exclusively (bench plus a 1.7B performance run in
flight); do not SSH to the board or start inference from this task. When a
measured run happens, record decode_tps and tokens_per_joule under
measured_profiles with runtime and model SHA-256 and RAM state, per
docs/benchmark-protocol.md.

## Untested reference sketch (explicitly unverified)

Prefer the compiled archive app: its Bridge RPCs are the verified path and
bridge_action_to_event() consumes them directly. If direct Serial is chosen
instead, the sketch below is a new, untested variant that must be verified
on hardware before any demo claim:

```cpp
// EXPLICITLY UNTESTED - verify on the bench before relying on it.
#include <Modulino.h>

ModulinoButtons buttons;
const unsigned long DEBOUNCE_MS = 250;
unsigned long lastFire[3] = {0, 0, 0};

void setup() {
  Serial.begin(115200);
  Modulino.begin();
  buttons.begin();
}

void loop() {
  if (buttons.update()) {
    unsigned long now = millis();
    const char* modes[3] = {"fast", "efficient", "balanced"};
    for (int i = 0; i < 3; i++) {
      if (buttons.isPressed(i) && now - lastFire[i] >= DEBOUNCE_MS) {
        lastFire[i] = now;
        Serial.print("{\"event\":\"button\",\"source\":\"");
        Serial.print(modes[i]);
        Serial.print("\",\"mode\":\"");
        Serial.print(modes[i]);
        Serial.println("\"}");
      }
    }
  }
}
```

The host reads those lines, feeds each to ModeController.handle_line(), and
on a non-None action performs POST /api/apply, then passes the JSON response
through apply_response() before updating any board display. Pixels and
vibration consume the handle_output line in the reverse direction.

## Tests

    python3 -m unittest tests.test_arduino_adapter tests.test_edge_device

26 tests pass offline: malformed and non-JSON event lines, duplicate presses
inside and outside the debounce window, knob cycling and spin coalescing,
Bridge packed-code mapping including invalid codes, the apply evidence
contract (request shape; acks without config or evidence rejected), active
config echo in board output, registry validation (including the NPU evidence
rule and connectivity-vs-capability separation), board-to-laptop escalation,
and board client transport/body failures.
