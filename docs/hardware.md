# Hackathon hardware

Recorded September 15, 2026. Hardware identifiers and laptop RAM below were supplied by the team. Vendor specifications are linked separately; no device execution has been tested yet.

| Component | Team hardware | Intended role |
|---|---|---|
| AI PC | Dell Latitude 7455; Snapdragon X Elite X1E-80-100; 32 GB RAM; Qualcomm Adreno X1-85 GPU as reported | Run one vision-language model through GenieX on the Hexagon NPU |
| Edge board | Arduino UNO Q, SKU ABX00162 | Camera capture, lightweight filtering, communication and MCU-driven LED feedback |

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

## Initial device checks

1. Confirm the Latitude's Windows ARM64 version, driver versions, free storage and whether GenieX is already installed. [Official Windows CLI setup](https://geniex.aihub.qualcomm.com/en/run/cli/install).
2. Run `geniex --help` and `geniex model list` in a terminal on the Latitude. The latter lists compatible QAIRT models for the detected chipset. [CLI reference](https://geniex.aihub.qualcomm.com/en/run/cli/reference).
3. Test one actual image with a compatible VLM. `ai-hub-models/Qwen3-VL-4B-Instruct` is a documented candidate with X Elite support; availability and speed on this unit remain unverified. [Model page](https://aihub.qualcomm.com/models/qwen3_vl_4b_instruct).
4. Confirm a USB webcam and a suitable powered USB-C hub are available, then test camera capture and LED-matrix control on UNO Q. [Arduino user manual](https://docs.arduino.cc/tutorials/uno-q/user-manual/).
5. Establish device-to-device connectivity and complete one image-to-result-to-LED round trip before adding routing policies or voice.

## Still unknown

- Windows OS build, installed software and drivers; SSH access verification.
- Laptop storage capacity and free space.
- Webcam and powered-hub availability.
- Board software version and reachable device addresses.
- Actual model quality, memory use and inference latency.

Passwords and other credentials are not stored in this repository.
