# UNO Q inspection controls

The `arduino/` folder is an Arduino App Lab app for UNO Q ABX00162. The Linux client uses Arduino Bridge to talk to the MCU and HTTP to reach the Latitude hub. The sketch has compiled and flashed, and the real Linux client reaches the hub. The board reports Buttons, Knob, Vibro and the onboard matrix; Pixels is not detected. Physical button/indicator checks are in progress.

## Controls and feedback

| Control | Action |
|---|---|
| Buttons A | Inspect the hub's latest fresh camera frame |
| Buttons B | Clear the current result |
| Buttons C | Select the next saved instruction |
| Knob clockwise / counterclockwise | Select the next / previous instruction |

Pixels show neutral, blue progress, green OK, red CHECK or amber UNKNOWN. The onboard 8×13 matrix also shows a state glyph and works without Modulinos. Vibro pulses on a state transition. Buzzer support is not implemented. Connect one Buttons and one Pixels first; Knob and Vibro are optional. Missing modules are skipped after probing at startup. Reboot or restart the app after changing module wiring.

## Run on the connected kit

On the Latitude, start the hub and connect the authorized UNO Q:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/connect-board.ps1
```

This creates an ADB reverse mapping from the board's filesystem socket at `/home/arduino/ArduinoApps/inspection-station/data/hub.sock` to the Latitude's loopback port 8080. App Lab shares that app folder into its container, so the client reaches the socket as `/app/data/hub.sock`. No TCP listener is opened on the board. The socket is restricted to the app's user.

`adb` is installed under `%LOCALAPPDATA%\QualcommTools\platform-tools` on our kit. A user-level `Qualcomm-ADB` task keeps its server alive between SSH sessions. Re-run the connection script after reconnecting USB or restarting the ADB server.

Copy the contents of `arduino/` into `/home/arduino/ArduinoApps/inspection-station` on the board. Run these commands on UNO Q via ADB shell or SSH:

```bash
arduino-app-cli app start /home/arduino/ArduinoApps/inspection-station -v
arduino-app-cli app logs /home/arduino/ArduinoApps/inspection-station --tail 50
arduino-app-cli app stop /home/arduino/ArduinoApps/inspection-station
```

App CLI 0.12.1 has no separate `app build` command. `app start` installs dependencies, compiles/uploads the sketch and launches Python. The profile pins zephyr 0.56.0 and its libraries. The first run needs internet for any missing dependencies.

The real Python client defaults to the shared Unix socket. `INSPECTION_HUB_SOCKET` overrides its path. `--simulate` uses loopback HTTP on the development machine. For a deliberate LAN setup, configure `INSPECTION_HUB_URL` and `INSPECTION_DEVICE_TOKEN` outside Git and follow the [hub authentication rules](api.md). The tested app uses App Lab's normal bridge network; host networking is unnecessary.

## Result expiry

The Linux client requests a fresh hub snapshot once per second, and polls controls approximately every 100 ms between HTTP requests. Network calls have a 1.5-second timeout. A malformed reply, expired result or failed connection sends UNKNOWN. An RPC failure is retried using the next fresh hub snapshot; the client never renews an old OK from a stored retry value.

For OK/CHECK, the MCU receives the smaller of three seconds and the remaining hub validity, conservatively reduced by the HTTP round trip and a short transport margin. The MCU expires the result independently if Python stops responding. Exact physical timing still needs hardware measurement. This is demonstration feedback, not an industrial machine interlock.

All display operations happen in the MCU loop. RPC handlers exchange packed state atomically; they do not write the I2C bus. `set_status` uses signed `int` arguments to match the installed RPClite decoder; the initial unsigned signature was rejected and has been corrected. The single-slot operator queue may coalesce very rapid presses.

| Bridge RPC | Result |
|---|---|
| `set_status(status, ttl_ms)` | Accept a state and remaining validity; codes 0 IDLE, 1 INSPECTING, 2 OK, 3 CHECK, 4 UNKNOWN |
| `get_action()` | Consume the queued control action; low byte is action, high byte is signed knob direction |
| `get_status()` | Read the state applied by the MCU loop, for integration checks |
| `get_modules()` | Bitmask: Buttons 1, Pixels 2, Knob 4, Vibro 8, onboard matrix 16 |

A successful diagnostic RPC proves the firmware's reported state; it does not replace visually checking the LEDs or physically pressing a button.

## Tests and simulation

```bash
python -m unittest discover -s tests -v
python arduino/python/main.py --simulate
```

Simulation uses fake control events and a fake Bridge with real HTTP. It injects Inspect, preset-cycle and Clear after 3, 8 and 10 seconds. It is explicitly labelled in logs, is not enabled by the real app, and proves no hardware behavior. The board-client tests cover malformed/expired state, connection failure and retry freshness.

## Primary API references

- [Arduino Bridge examples](https://github.com/arduino/app-bricks-examples/tree/main/core-and-foundational/03-bridge-basics).
- [UNO Q matrix example](https://github.com/arduino/app-bricks-examples/blob/main/core-and-foundational/02-led-matrix/01-led-matrix-frame-mcu/sketch/sketch.ino). The installed zephyr 0.56.0 header provides `begin()`, `setGrayscaleBits()` and `draw()`.
- [Arduino_Modulino source](https://github.com/arduino-libraries/Arduino_Modulino), version 0.9.0.
- [Arduino_RouterBridge source](https://github.com/bcmi-labs/Arduino_RouterBridge), version 0.4.3.
- [App CLI 0.12.1 app specification](https://github.com/arduino/arduino-app-cli/blob/v0.12.1/docs/app-specification.md).
- [Arduino Python app utilities](https://github.com/arduino/app-bricks-py/tree/main/src/arduino/app_utils).
