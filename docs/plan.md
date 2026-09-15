# Execution plan and acceptance checks

Status: September 15, 2026. No implementation milestones have passed. Work starts from an empty application repository and the hardware listed in [hardware.md](hardware.md).

## Current setup

- [x] Confirm the working GitHub repository and team write access.
- [x] Record the Latitude, UNO Q and available modules.
- [x] Confirm that Codex is installed on the Latitude, as reported by the team.
- [x] Prepare a dedicated SSH client key on the development Mac, kept outside this repository.
- [x] Confirm Windows OpenSSH Server setup, verify the host fingerprint and establish a connection.
- [ ] Confirm camera input, board connectivity and installed model/runtime versions.

SSH connection and remote checks succeeded on September 15; see [the verified status](ssh.md). Keep private keys, credentials and connection addresses in local setup notes. Follow [Microsoft's Windows OpenSSH instructions](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse) for remote access.

## Milestone 1: establish hardware feasibility

1. Inspect the Latitude's native Windows ARM64 environment, storage, drivers and installed tools.
2. Check GenieX and list compatible models. Ask the onsite mentor which VLM bundle is known to work on this laptop image.
3. Run one candidate model on a real image and inspect both its answer and runtime/backend evidence.
4. Connect UNO Q, run a simple LED or Pixels example, and read a button press.
5. Establish one working camera path.

**Acceptance:** a useful image answer on the Latitude and a real button-to-indicator interaction on UNO Q. Record what actually ran. Timebox the initial runtime/model investigation to roughly two hours; if blocked, use the mentor's demonstrated configuration before investing in UI work.

## Milestone 2: complete one inspection

Build the request service, board client and constrained response validation. Wire one button to inspection, with board feedback and a simple laptop result view. Give each request a frame identity and instruction version.

**Acceptance:** pressing the button produces a fresh answer and physical result. Changing the instruction changes the inspection. Invalid responses, timeout, disconnection and expired results yield UNKNOWN rather than an old OK. Do not advance on a simulated board response alone.

## Milestone 3: choose and evaluate the demo

Select a few ordinary objects and instructions that are visibly testable. Human-label a small repeatable set with compliant, noncompliant and ambiguous or obscured scenes. Record how many examples were tested and their outcomes; a hand-picked demo is not a general accuracy benchmark.

**Acceptance:** repeatable demonstrations of OK, CHECK and UNKNOWN, with measured elapsed time and an honest account of limitations. After required files are installed, disconnect internet while retaining local device connectivity and verify the intended offline visual loop.

## Milestone 4: optional gating and routing

Only after milestone 3, add a cheap gate or small board model. Keep a fixed-cadence or stable-inspection VLM baseline and compare both policies on the same human-labelled sequence.

| Measure | What to report |
|---|---|
| Inspection correctness | Correct, wrong and uncertain results against human labels |
| Missed changed events | Events missed during skipped windows as well as processed windows |
| Calls and traffic | VLM requests and actual transferred bytes |
| End-to-end latency | Elapsed time from trigger to board indication; report sample count and distribution |
| Runtime evidence | Active backend and software/model versions, separately from throughput |

Do not use a VLM on every raw video frame as an artificially expensive baseline. Do not use model answers as ground truth. A lower call count alone does not establish better latency, energy use or total cost.

**Acceptance:** show the accuracy/latency/resource tradeoff against the baseline, including regressions. If there is no second inference path, label the result as gating rather than generic placement optimization.

## Demo and submission

The [event page](https://lablab.ai/ai-hackathons/ai-infra-summit-hackathon), checked September 15, lists a September 16 deadline of 2:30 p.m. EDT / 11:30 a.m. PDT. Recheck onsite announcements before submission.

- [ ] Choose the final project name and exact scenario.
- [ ] Show the real camera input, instruction, model answer and physical feedback.
- [ ] Change the instruction, demonstrate a violation, and demonstrate a failure/unknown state.
- [ ] Show the actual backend evidence and measured figures available at submission time.
- [ ] Record a short demo video and prepare slides, cover image and project description.
- [ ] Add reproducible setup/run instructions and the final tested device/model versions to the repository.
- [ ] Supply the required repository and demo/application links, with offline access requirements explained.
- [ ] Submit the entry through the event platform.

Protect time for the video and submission before adding voice or a dashboard. Submission, hosted deployment and prize eligibility have not been completed or validated by this repository.

## Cut order if time is short

Keep one camera, one VLM, one button, one physical indication and explicit failure handling. Drop extra modules, richer dashboards, gating, multi-node routing and hosted voice before cutting the working device loop. A laptop-camera fallback is acceptable for feasibility, but must be described as laptop capture with board interaction.
