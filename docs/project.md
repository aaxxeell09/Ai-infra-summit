# Project brief

Status: prototype development, September 15, 2026. This document records the team's design and broader direction; it does not describe a completed product. A final project name and exact demo scenario have not been selected.

## Problem and intended users

Small packing stations, repair benches and workshops sometimes need to check changing visual instructions. A fixed object detector can answer which known objects are present, but changing instructions may also refer to their visible state, orientation or relationship to one another.

Our hypothesis is that an operator could write a short inspection rule and use a local vision-language model to evaluate it without training a new model for every rule. An inexpensive physical station would provide the camera input and operator controls, while a nearby AI PC supplies the heavier inference.

Potential value includes keeping images on the local network, continuing the core inspection when internet access is unavailable, and avoiding a hosted inference dependency for each inspection. Reliability, latency, power consumption, hardware cost and commercial demand remain to be evaluated. We have not validated customer demand or an ROI claim.

## Original idea and current direction

The original proposal was an edge inference router for workshop safety or quality checks. An always-on detector on UNO Q would escalate interesting frames to a Snapdragon X Elite laptop, where GenieX would run visual reasoning. The laptop would send an action back to the board. A dashboard would explain placement decisions and show measured execution data.

That is the broader research direction. Because the project started without code and uses a 2 GB UNO Q, the recommended first milestone is one image-to-answer-to-physical-result loop. The available modules support manual controls and feedback; no distance, temperature or motion sensor has been confirmed.

The earlier idea review, including independent agent feedback and Fable 5.1 through Claude Code, supported keeping one VLM and proving this loop before adding routing. The resulting design decisions are captured here; runtime feasibility still requires tests on our devices.

## Candidate demonstrations

| Candidate | Why it is useful to test | Main limitation |
|---|---|---|
| Packing or bench inspection with changeable instructions | Easy to stage with ordinary objects; demonstrates changing requirements | Model must reliably understand the selected states and relationships |
| Local visual assistant with physical controls | An operator selects a question and receives a visible or tactile answer | Needs a specific task to demonstrate value beyond image chat |
| Workshop PPE or part-defect inspection | Potential application of the same architecture | Needs representative data and much stronger error evaluation; outside the initial demo commitment |

Example instructions include “the bottle is capped and upright” or “the mug is inside the box and the tool is outside.” These are proposed test cases, not demonstrated capabilities. Avoid tiny defects, obscured conditions and unsupported claims about machine safety.

A fixed checklist of object presence may be better served by a detector and a set comparison. The proposed reason to use a VLM is flexible language and visual context; it is not the only technology that could address those tasks.

## Minimum useful scope

- One Latitude, one UNO Q, one camera source and one VLM.
- One physical button starts an inspection; the knob may select a saved instruction.
- A validated result produces OK, CHECK or UNKNOWN on the board.
- A laptop view shows the instruction, result, brief explanation and measured elapsed time.
- One clear success, one visible violation and one failure or uncertain case can be demonstrated repeatedly.
- Once software and model files are installed, the intended visual inference path stays on the local network.

## Extensions, in priority order

1. Add a measured change or stability gate on UNO Q to reduce unnecessary model calls.
2. Add a policy that selects between genuinely available local and laptop inference paths, with logged reasons and a fair comparison.
3. Add a dashboard for event history, actual backend evidence and measured performance.
4. Add optional Speechmatics voice questions about recent results if the core and submission assets are complete.
5. Explore multiple edge nodes, richer sensors and additional applications after the first station works.

The initial build excludes custom model training, robot arms, industrial actuation, multiple boards and a second LLM. Hosted Speechmatics integration would require network access for voice; it must be presented separately from the intended offline visual core. See [Speechmatics documentation](https://docs.speechmatics.com/).

## Track fit

The [published Qualcomm track](https://lablab.ai/ai-hackathons/ai-infra-summit-hackathon) emphasizes GenieX, on-device AI and collaboration between the X Elite platform and UNO Q. Our proposed station makes both devices visible in one workflow. Offline operation and verified NPU use are project goals; we have not treated rules from other Qualcomm events as this event's requirements. Prize odds and unverified competitor counts are not part of the project rationale.
