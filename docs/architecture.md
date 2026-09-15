# Architecture and routing extensions

The hub and browser console are implemented; the Latitude-to-UNO-Q USB transport is verified. Firmware integration and real model inference are in progress. This document separates that first prototype from later routing work.

## First prototype

```mermaid
flowchart LR
    Camera[Latitude camera or image upload] --> PC[Python hub on Latitude]
    Buttons[Modulino controls] --> MCU[UNO Q microcontroller]
    MCU --> Bridge[Arduino Bridge]
    Bridge --> Board[UNO Q Linux client]
    Board -->|Inspect and preset requests over USB| PC
    PC --> GenieX[GenieX and Qwen3-VL]
    GenieX --> Validate[Response validation and freshness]
    Validate -->|Result state over USB| Board
    Board --> Bridge
    MCU --> Output[Physical feedback]
    Validate --> View[Local browser console]
```

There is no USB webcam in the kit. The first capture path runs in the Latitude browser, with image upload as a fallback. The board requests an inspection of the latest fresh frame and handles controls and results. This does not yet demonstrate independent edge camera capture or an edge vision model.

The verified transport is USB ADB reverse forwarding: board port 8080 reaches the Latitude's loopback hub port 8080. There is no need to open the hub to the venue network. An independent board camera or [phone-to-UNO-Q camera stream](https://blog.arduino.cc/2026/03/06/turn-your-smartphone-into-a-real-time-vision-input-for-arduino-uno-q/) remains an extension.

## Device responsibilities

| Component | First milestone | Possible extension |
|---|---|---|
| UNO Q Linux processor | Send operator requests to the laptop and relay results over Bridge | Independent capture, change/stability filtering or a small validated detector |
| UNO Q microcontroller | Read controls and drive feedback through Bridge | More deterministic peripheral behavior |
| Latitude | Host a request service, run one VLM through GenieX, validate its answer and display the result | Policy evaluation and measured comparisons |
| Knob / Buttons | Choose a saved instruction and request or retry an inspection | Operator acknowledgement or labelled evaluation input |
| LED matrix / Pixels / Vibro / Buzzer | Indicate progress and result | Distinct tactile and audible patterns |

[Arduino Bridge](https://docs.arduino.cc/hardware/uno-q) provides communication between Linux applications and microcontroller sketches. Module library compatibility must be checked against the installed board software. Vibro is an output motor; none of the listed modules provides scene imagery or vibration measurements.

## Model and runtime

[Qwen3-VL-4B-Instruct](https://aihub.qualcomm.com/models/qwen3_vl_4b_instruct) is a candidate: Qualcomm documents a GenieX deployment and X Elite support. GenieX 0.6.1 lists `qualcomm/Qwen3-VL-4B-Instruct` as compatible on our Latitude. The X Elite QAIRT bundle is downloading. Real image inference and its quality have not yet been tested.

The intended target is the Latitude's Hexagon NPU. A model name, `--compute npu` request or vendor TOPS figure is not proof of active NPU execution. Record runtime/backend logs and corroborating device evidence. A fallback backend must be labelled accurately. Do not assume UNO Q has the same NPU or model support as X Elite.

GenieX offers an [OpenAI-compatible local serving interface](https://geniex.aihub.qualcomm.com/en/run/cli/reference), used by our Python service through loopback port 18181. The browser and board use hub port 8080; see the [implemented API](api.md). Compatibility of the selected model's actual image answers remains a runtime acceptance check.

For QAIRT bundles, the context limit is fixed when the bundle is compiled; increasing `--nctx` does not enlarge it. Keep inspection requests short and independent, and check the selected bundle's limit before adding conversational history. See the [runtime constraints in the CLI reference](https://geniex.aihub.qualcomm.com/en/run/cli/reference#increasing-the-context-length).

## Result handling

The application owns the result state. The model proposes a constrained answer; deterministic code checks it before any physical indication.

| State | Meaning | Planned indication |
|---|---|---|
| IDLE | No current inspection | Neutral display |
| INSPECTING | A fresh request is in progress | Progress pattern |
| OK | The current image satisfies the current instruction | Green Pixels or an OK matrix pattern |
| CHECK | The current image visibly violates the instruction | Red Pixels or a CHECK pattern |
| UNKNOWN | The result cannot be established or the request failed | Amber Pixels or a distinct UNKNOWN pattern |

The hub binds each request to a unique ID, captured image, instruction version and deadline. Responses contain a bounded status and short explanation. Current limits are a 15-second cached-frame age, 90-second inference timeout and 20-second result lifetime. A result applies to the captured image; it does not certify subsequent live video frames.

Reject malformed answers and mismatched or expired responses. Clear the previous OK when a new inspection starts, the instruction changes, the camera disconnects or the result expires. Use a local timer on the board so a broken laptop connection cannot leave an OK displayed indefinitely. Expiry values must be selected during testing.

Keep responses out of executable code paths. The MCU should receive only an allowlisted indication command. This prototype controls feedback devices; it is not a machine interlock.

## From trigger to inference policy

The first version always sends a requested inspection to the laptop. A later event gate could skip unchanged frames, but skipped time windows must still count in evaluation. Periodic sampling does not guarantee that short events will be observed.

A routing extension would need actual alternatives: a board model that can answer a validated subset of questions, a laptop model for contextual judgments, and explicit conditions for requesting human review. Policy inputs could include supported task type, freshness, queue depth, measured runtime and the local-only privacy constraint.

A cheap detector must not declare a scene OK for a language instruction it cannot evaluate. Cache entries must be bound to instruction version and scene validity. With only one working inference destination, describe the system as an event-triggered pipeline or cascade.

## Data and measurements

The current visual core keeps images on the Latitude and sends only control/result metadata over USB. An independent board-camera extension would send selected images between the two devices. Model downloads and development tools can require internet access during setup. Optional hosted voice would send audio to its provider; it is a separate mode.

Initially keep only the metadata needed to debug requests and measure results. Raw image retention should be explicit. Record end-to-end elapsed time, VLM calls, transferred bytes, backend evidence, correctness and missed events. Tokens per second and call counts are not NPU utilization or energy measurements. No savings or performance numbers have been measured yet.
