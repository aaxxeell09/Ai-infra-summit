# AI Infra Summit — Qualcomm track

**Project idea: a local inspection station that checks instructions written in plain language, runs visual reasoning on a Snapdragon AI PC, and returns a physical result through an Arduino UNO Q.**

This is the working repository for our entry in the [AI Infra Summit Hackathon's Qualcomm Model-to-Device Innovation track](https://lablab.ai/ai-hackathons/ai-infra-summit-hackathon).

## Current status

**Planning and device setup, September 15, 2026.** The hardware is in hand. This repository currently contains documentation only: there is no application, trained model, working router, or measured benchmark yet. SSH setup between the development Mac and the Latitude is in progress; a successful connection has not been verified.

| Confirmed by the team | Still to verify |
|---|---|
| Dell Latitude 7455, Snapdragon X Elite X1E-80-100, 32 GB RAM | GenieX installation, compatible model, actual NPU execution and latency |
| Arduino UNO Q ABX00162 | Board setup, software version, camera input and device communication |
| Access to Modulino Vibro, Knob, Buzzer, Buttons and Pixels; multiple units available | Exact module quantities, wiring and functioning firmware |
| Codex installed on the Latitude | Remote SSH access |

## The demo we want to build

1. Choose an inspection instruction, such as “the bottle must be capped and upright.”
2. Put the objects in view and press a physical button.
3. The UNO Q requests an inspection from the Latitude over the local network.
4. One vision-language model running through GenieX checks the image against the instruction.
5. The board shows **OK**, **CHECK**, or **UNKNOWN**, with a short explanation on the laptop.
6. Change the instruction and repeat without changing code or retraining a model.

The objects and instructions are candidates, pending tests on the real model. Start with large, visible conditions. Camera hardware has not been confirmed; a USB webcam is preferred, with phone or laptop camera paths as alternatives to evaluate.

## The infrastructure idea

The longer-term idea is a **tiered edge brain**: a small node handles capture and cheap decisions, while the AI PC handles contextual visual reasoning. A policy could decide whether to inspect locally, escalate to the laptop, or reuse a still-valid result. We would measure accuracy, missed events, calls, traffic and latency before claiming an improvement.

The first prototype will use explicit button-triggered inspection. A fixed trigger is an event-driven pipeline; a general inference router remains an extension to earn through implementation and evaluation.

## Project documentation

- [Project brief](docs/project.md): problem, use cases, intended value and scope.
- [Architecture](docs/architecture.md): device responsibilities, data flow, result handling and routing extensions.
- [Hardware](docs/hardware.md): actual kit, available modules and vendor references.
- [Execution plan](docs/plan.md): setup, milestones, evaluation and demo checklist.

There are no installation or launch commands for this project yet. They will be added after the first working implementation. Passwords, private keys, device addresses and raw camera captures belong outside the public repository.
