# Device verification — September 15, 2026

These observations come from the team's actual Latitude 7455 and UNO Q. They are integration checks, not a general model-quality or hardware-performance benchmark.

## Laptop camera and local inference

- Native Windows ARM64 Python 3.14.6 runs the hub.
- Microsoft Edge delivers real integrated-camera frames at **1280×720**. The console posts fresh frames to the hub; no JavaScript errors were observed during this check.
- GenieX **0.6.1**, with QAIRT **2.45**, serves the imported X Elite Qwen3-VL-4B bundle at a loopback endpoint.
- Model source: Qualcomm's [Qwen3-VL-4B release assets](https://huggingface.co/qualcomm/Qwen3-VL-4B-Instruct/blob/main/release_assets.json), release 0.62.2, `geniex_qairt-w4a16-qualcomm_snapdragon_x_elite.zip`. The downloaded archive was **3,034,262,089 bytes** and passed ZIP CRC validation.
- Imported model name on this installation: **`local/qwen3-vl-4b-x-elite`**; `/v1/models` reports `local/qwen3-vl-4b-x-elite:w4a16`.

The first image request after model loading returned a valid UNKNOWN in **12,857 ms**, including model initialization. Three later requests used the same real camera still:

| Rule | Expected | Returned | Hub elapsed time |
|---|---|---|---|
| An upholstered chair must be visible. | OK | OK | 2,085 ms |
| The upholstered chair must be green. | CHECK | CHECK | 2,597 ms |
| The bottle label must be clearly readable; UNKNOWN if no label is visible. | UNKNOWN | UNKNOWN | 1,917 ms |

The frame visibly contained an upholstered, non-green chair and no readable bottle label. These are three integration cases on one image, selected and checked by the developer. They establish the image-to-structured-result path. They do not establish accuracy on packing, defect or safety inspections. Camera images and raw device logs remain outside Git.

## NPU evidence

Observed during the successful inference:

```text
Detected HTP arch: v73
HTP device reports 1 NSP core(s)
HTP graphs will execute on 1 core
LLMModel initialized: 4 shards, 4 CL variants [512,1024,2048,4096]
```

The running GenieX process also loaded `QnnHtp.dll`, `QnnSystem.dll` and `QnnHtpV73Stub.dll`. Successful image completions alongside these QAIRT/HTP observations support that the model graphs ran on the Hexagon NPU. CPU work for the server and preprocessing is still expected. No NPU utilization percentage, energy use, GPU comparison or cost saving was measured.

Qualcomm documents that its [QAIRT AI Hub models use the NPU backend](https://geniex.aihub.qualcomm.com/en/run/cli/reference). The console's backend-evidence field records the actual HTP observation; it does not display a fabricated utilization gauge.

## Hub and board software

- **17 automated tests passed on both the development Mac and Windows ARM64 Latitude.** They cover state expiry, stale/cancelled request handling, model-answer validation, HTTP boundaries and board-client failure handling. Model clients in these tests are test doubles.
- UNO Q is authenticated over USB ADB.
- Initial TCP forwarding was replaced by an ADB reverse filesystem socket. The running App Lab client reaches the Latitude hub through that socket without a board TCP listener.
- Arduino App CLI/daemon 0.12.1, Arduino CLI 1.5.1 and zephyr 0.56.0 were observed on the board.
- The sketch compiled and flashed successfully. `get_modules()` returns **29**: Buttons, Knob, Vibro and the onboard matrix; Pixels is absent. `set_status(4, 3000)` was acknowledged and `get_status()` returned UNKNOWN. The hub receives real board heartbeats.
- Eighteen tests pass on Mac after adding a Unix-socket integration test; that Unix-only test is skipped on Windows.
- A real VLM OK result reached the MCU (`get_status() == 2`). Pausing the App Lab Python container left the MCU independent: it reported 2 immediately, then **4 (UNKNOWN) after 3.5 seconds**. The container was resumed afterward.
- Physical button/LED confirmation and a full Wi-Fi-disconnected rehearsal remain in progress.

## Process-level offline check

Windows outbound-block firewall rules were temporarily enabled for both the actual GenieX executable and the ARM64 Python executable running the hub. While those rules were active, a fresh camera inspection returned **OK in 2,071 ms**, and the board remained connected. The rules were removed in a `finally` cleanup after the check.

This verifies the tested inference path under application outbound blocking. The Windows session, ADB/SSH development connection and unrelated applications remained online. It is not a claim that the whole kit was disconnected from Wi-Fi during this test.
