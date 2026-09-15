# Local hub API

Run `python -m inspection` from the repository root. The default listener is `127.0.0.1:8080`. Only Python's standard library is required. The browser assets are served locally; no CDN or hosted inference is used by the hub.

## Requests

All POST requests use `Content-Type: application/json`. Errors return an HTTP error status and `{"error":"..."}`. Image bytes remain in memory; the app does not write raw captures to disk.

| Endpoint | Body | Behavior |
|---|---|---|
| `GET /api/state` | — | Current state, instruction/version, request identity, expiry, runtime and board connectivity, counters and recent events |
| `POST /api/instruction` | `{"instruction":"...","preset_id":"optional"}` | Set a 1–1200 character instruction and invalidate the old result or pending answer |
| `POST /api/preset` | `{"direction":1}` or `{"direction":-1}` | Cycle saved instructions |
| `POST /api/frame` | `{"image":"data:image/jpeg;base64,..."}` | Cache an inline JPEG, PNG or WebP, at most 4 MB decoded |
| `POST /api/frame` | `{"image":null}` | Clear camera input and invalidate a pending/current result |
| `POST /api/inspect` | `{}` or `{"image":"data:image/jpeg;base64,..."}` | Inspect the cached frame, or a supplied image; 202 accepted, 409 busy, 400 missing/stale image |
| `POST /api/clear` | `{}` | Clear the result to IDLE; any outstanding model answer is discarded |
| `POST /api/board/heartbeat` | `{"device_id":"uno-q"}` | Mark the board seen and return the current state |

## Freshness and concurrency

The cached frame is usable for 15 seconds. Each accepted inspection captures the image and instruction at that moment. A result describes that snapshot, not every subsequent frame of a live video. The server allows one outstanding model call. Cancelling an inspection invalidates its answer but does not start a second overlapping model call.

The default request timeout is 90 seconds. Valid OK/CHECK results expire 20 seconds after completion; the state then becomes UNKNOWN. An instruction change, invalid model answer, missing input, timeout or camera disconnect invalidates the previous result. A late answer cannot replace a newer instruction or a cleared result. Only OK/CHECK/UNKNOWN plus a bounded explanation are accepted from the model.

The browser and MCU additionally expire displayed results locally. Board connectivity is based on a heartbeat less than five seconds old. The hub retains the most recent 30 result records in memory; counters reset when the process restarts. Automated tests use a test client, so their elapsed times are not model benchmarks.

## Local connections

GenieX must be a loopback HTTP endpoint, by default `http://127.0.0.1:18181/v1`. `runtime.connected` reports server reachability; it does not prove model loading or NPU execution. `runtime.backend_evidence` defaults to `unverified`. Set `INSPECTION_BACKEND_EVIDENCE` only to a description backed by actual runtime observations.

For USB transport, run `scripts/connect-board.ps1` on the Latitude. ADB reverse maps a board filesystem socket to Latitude loopback port 8080. The board client uses that socket inside App Lab's shared app directory; no venue-facing TCP port or container host networking is needed. A plain TCP reverse mapping was useful during initial transport checks, but has been replaced because ADB listens on all board interfaces in that mode.

For a deliberate LAN setup, bind with `--host 0.0.0.0`, set `INSPECTION_DEVICE_TOKEN`, and add the actual laptop address to `INSPECTION_ALLOWED_HOSTS`. Non-loopback requests must include the matching `X-Device-Token` header. Keep these values outside Git. The current browser console is intended for localhost; use a tunnel rather than putting a device token into browser source. Cross-origin writes and unexpected Host headers are rejected.
