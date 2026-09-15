# Demonstrating Local Inspection

**Pitch:** A local visual inspection station with rules you can rewrite. The Snapdragon laptop interprets the image; the UNO Q handles physical controls and feedback. The demonstrated model runs through GenieX on the Hexagon HTP backend.

This first prototype uses the laptop camera. It is an event-triggered pipeline with one inference destination. Board-side vision, model-placement routing and measured call savings remain extensions.

## Prepare the kit

1. Start GenieX and the hub on the Latitude. Use model `local/qwen3-vl-4b-x-elite`, which is the imported name on this kit.
2. Connect UNO Q by USB and run `scripts/connect-board.ps1` on the Latitude. Start the `inspection-station` App Lab app on the board.
3. Open `http://127.0.0.1:8080` in Edge **on the Latitude**, select **Start camera**, and frame a large, visible object. Check that Board is Online.
4. Confirm the physical A button requests an inspection and the onboard matrix changes state. Pixels is optional and was not detected during setup.

The current development session already runs the hub, GenieX and ADB as user-level Windows tasks. Signing out of Codex is fine; keep the Windows session signed in and the laptop awake.

## First repeatable walkthrough

The initial camera tests used a clearly visible upholstered, non-green chair. With that scene visible:

1. Set “An upholstered chair must be visible.” Press A and observe the result. The recorded still-image check returned OK.
2. Change the rule to “The upholstered chair must be green.” Press A. The recorded still-image check returned CHECK.
3. Ask for a readable bottle label when none is visible, explicitly allowing UNKNOWN. The recorded check returned UNKNOWN.
4. Show the runtime details, the explanation and measured elapsed time. Explain that results describe a captured image and expire after 20 seconds.
5. Demonstrate lost-connection handling only after checking a valid result: disconnect USB and wait for the MCU to change to UNKNOWN. Reconnect and re-run `connect-board.ps1` before continuing.

These prompts are a setup demonstration, not the final product scenario. Next, stage a packing or bench task with a few ordinary objects and label compliant, noncompliant and obscured examples before running them. Keep the examples that the actual model handles reliably; report failures too.

## What the evidence supports

The [verification record](verification.md) includes real camera capture, successful local VLM answers, QAIRT/HTP runtime evidence, firmware communication and an independent MCU timeout check. Three warm requests on one image took 1.9–2.6 seconds. That range is a small integration observation, not a benchmark or accuracy claim.

The visual core has completed inference while outbound access was blocked for the GenieX and hub executables. Development tools and the Windows session remained online during that check. A full Wi-Fi-disconnected rehearsal and a recorded physical button walkthrough still need to be done onsite.
