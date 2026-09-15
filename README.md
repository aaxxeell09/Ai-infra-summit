# AI Infra Summit — Qualcomm track

**Project idea: a local inspection station that checks instructions written in plain language, runs visual reasoning on a Snapdragon AI PC, and returns a physical result through an Arduino UNO Q.**

This is the working repository for our entry in the [AI Infra Summit Hackathon's Qualcomm Model-to-Device Innovation track](https://lablab.ai/ai-hackathons/ai-infra-summit-hackathon).

## Current status

**Prototype in development, September 15, 2026.** The Python hub and browser console run on the Latitude. The connected UNO Q can reach the hub over USB. GenieX 0.6.1 is installed; the compatible Qwen3-VL model is downloading. Model inference, NPU execution and the complete physical inspection loop are still unverified.

| Implemented or verified | Remaining |
|---|---|
| Windows ARM64 Python hub; offline browser assets; image upload and camera capture code | Useful model answers and tested inspection scenarios |
| Versioned instructions, one in-flight request, strict answer validation and expiring results | Actual NPU/backend evidence and measured inference latency |
| Dedicated SSH access; USB ADB reverse tunnel from UNO Q to the hub | Board firmware compilation, physical controls and feedback |
| 17 automated hub/API and board-client tests | Repeatable OK/CHECK/UNKNOWN demonstrations and offline hardware test |

## Run the hub

Python 3.11 or later; no pip dependencies:

```bash
python -m inspection
```

Open **http://127.0.0.1:8080** on the computer running the hub. Upload an image, or start its camera and allow camera access. Choose an instruction and select **Inspect**. Without GenieX, an inspection returns UNKNOWN. No simulated model answers are enabled in the app.

On our Windows installation, the launcher finds the native ARM64 Python under the user's local `QualcommTools` folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-hub.ps1
```

In another terminal, after installing [GenieX](https://geniex.aihub.qualcomm.com/en/run/cli/install) and downloading the compatible model:

```powershell
geniex model list
geniex pull qualcomm/Qwen3-VL-4B-Instruct
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-geniex.ps1
```

The server listens on loopback port 18181. The hub uses its OpenAI-compatible `/v1/chat/completions` endpoint. `--compute npu` requests the NPU; the console keeps backend evidence **unverified** until actual execution is checked. If importing a local bundle under another model name, pass that name to `start-hub.ps1 -Model NAME` or `python -m inspection --model NAME`.

```bash
python -m unittest discover -s tests -v
```

See [API and state rules](docs/api.md), [UNO Q setup](docs/arduino.md) and [device verification](docs/hardware.md). Test doubles are confined to tests and the explicitly labelled board simulation option.

## The demo we want to build

1. Choose an inspection instruction, such as “the bottle must be capped and upright.”
2. Put the objects in view and press a physical button.
3. The UNO Q requests an inspection from the Latitude over USB or the local network.
4. One vision-language model running through GenieX checks the image against the instruction.
5. The board shows **OK**, **CHECK**, or **UNKNOWN**, with a short explanation on the laptop.
6. Change the instruction and repeat without changing code or retraining a model.

The objects and instructions are candidates, pending tests on the real model. The kit has no USB webcam, so the first version captures on the Latitude or accepts an uploaded image. The UNO Q handles physical controls and feedback. Independent board capture remains an extension.

## The infrastructure idea

The longer-term idea is a **tiered edge brain**: a small node handles capture and cheap decisions, while the AI PC handles contextual visual reasoning. A policy could decide whether to inspect locally, escalate to the laptop, or reuse a still-valid result. We would measure accuracy, missed events, calls, traffic and latency before claiming an improvement.

The first prototype will use explicit button-triggered inspection. A fixed trigger is an event-driven pipeline; a general inference router remains an extension to earn through implementation and evaluation.

## Project documentation

- [Project brief](docs/project.md): problem, use cases, intended value and scope.
- [Architecture](docs/architecture.md): device responsibilities, data flow, result handling and routing extensions.
- [Hardware](docs/hardware.md): actual kit, available modules and vendor references.
- [SSH setup](docs/ssh.md): setup procedure and verified remote access status.
- [Execution plan](docs/plan.md): setup, milestones, evaluation and demo checklist.

Passwords, private keys, device addresses and raw camera captures belong outside the public repository.
