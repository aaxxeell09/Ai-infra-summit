# Hackathon hardware

Recorded September 15, 2026. Hardware identifiers and laptop RAM below were supplied by the team. Vendor specifications are linked separately; executed setup checks are recorded below.

| Component | Team hardware | Intended role |
|---|---|---|
| AI PC | Dell Latitude 7455; Snapdragon X Elite X1E-80-100; 32 GB RAM; Qualcomm Adreno X1-85 GPU as reported | Run one vision-language model through GenieX on the Hexagon NPU |
| Edge board | Arduino UNO Q, SKU ABX00162 | Physical controls, USB communication and MCU-driven feedback; later capture/filtering |

The [Arduino datasheet](https://docs.arduino.cc/resources/datasheets/ABX00162-datasheet.pdf) maps ABX00162 to **2 GB RAM and 16 GB eMMC**. The board combines the Dragonwing QRB2210 Linux processor, Adreno 702 GPU and STM32U585 microcontroller. Keep this board's software and model footprint small.

[Dell's specifications](https://www.dell.com/en-us/shop/dell-laptops/latitude-7455-laptop/spd/latitude-14-7455-laptop/s003l7455usvp) list an NPU rated up to **45 TOPS** for the X1E-80-100. Adreno is the GPU; the planned inference target is the separate Hexagon NPU. TOPS is a vendor specification, not a measured model benchmark.

## Available modules and development tools

The team reports access to Modulino Vibro, Knob, Buzzer, Buttons (three buttons), and Pixels, with multiple units available. Exact quantities and module labels have not been inspected.

| Module | Function | Possible demo role |
|---|---|---|
| [Vibro](https://docs.arduino.cc/hardware/modulino-vibro) | Vibration motor for haptic output | Tactile notification of a result |
| [Knob](https://docs.arduino.cc/hardware/modulino-knob) | Rotary encoder with a push switch | Select an inspection instruction or mode |
| [Buzzer](https://docs.arduino.cc/hardware/modulino-buzzer) | Audible output | Short completion or attention signal |
| [Buttons](https://docs.arduino.cc/hardware/modulino-buttons) | Three push buttons | Start, retry, acknowledge |
| [Pixels](https://docs.arduino.cc/hardware/modulino-pixels) | Eight RGB LEDs | Show pass, check, and unknown states |

Vibro produces vibration; it does not measure vibration. No distance, temperature, or movement sensor is confirmed. The team confirms UNO Q is connected to the Latitude and there is no USB webcam. Initial development will use uploaded images and evaluate the laptop's built-in camera. Start with one of each needed module; duplicate modules require checking address configuration and power before connecting them together.

Codex is installed on the Latitude, as reported by the team. SSH from the development Mac is now verified with a pinned host key and a dedicated client key. The Windows service is running and the inspected SSH firewall rules are restricted to the development Mac. See [SSH verification](ssh.md); keep connection details outside this public repository.

## Executed setup checks — September 15

| Device | Observed |
|---|---|
| Latitude | Windows 11 Pro 10.0.26200, ARM64; NPU and integrated camera enumerate without device errors |
| Storage | Approximately 398 GB free before tool and model downloads |
| Python | Native Windows ARM64 Python 3.14.6 installed and version checked |
| GenieX | 0.6.1, QAIRT 2.45; `geniex model list` includes `qualcomm/Qwen3-VL-4B-Instruct` for this device |
| Git | Native ARM64 Git 2.55.0.windows.5; repository cloned |
| UNO Q | Linux aarch64; Arduino App CLI and daemon 0.12.1; Arduino CLI 1.5.1; zephyr platform 0.56.0 |
| Connection | Authenticated USB ADB; a shared filesystem socket forwards HTTP from the App Lab container to the real Latitude hub |
| Hub | Python service running on Latitude loopback port 8080; status API responds |

The real Latitude camera was subsequently verified in Edge at 1280×720, delivering fresh frames to the hub with no JavaScript errors. The model bundle is installed and real inference has been verified with QAIRT/HTP logs. See [the results](verification.md); NPU utilization and broad model quality remain unmeasured.

The current development processes run as user-level Windows Scheduled Tasks: `Qualcomm-Hub`, `Qualcomm-ADB` and `Qualcomm-GenieX`. They have no recurring trigger. Logging out of Codex does not stop SSH; signing out of Windows can stop these interactive tasks. Startup wrappers and download logs live under `%LOCALAPPDATA%\QualcommTools`, outside Git.

## Still to verify

- Broader tests of physical inspection scenes.
- Model quality, end-to-end physical latency and resource measurements beyond the initial runtime checks.
- Physical controls and visual feedback (firmware reports Buttons, Knob, Vibro and matrix present; Pixels absent).
- Full inspection loop with internet disconnected after setup.

Passwords, private keys, local addresses and raw captures are not stored in this repository.
