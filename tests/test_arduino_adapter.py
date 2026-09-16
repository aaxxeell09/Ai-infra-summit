"""Tests for the UNO Q mode-pad event adapter (offline, no hardware)."""
import json
import unittest

from turbo.arduino_adapter import (EventError, ModeController,
                                   apply_request, apply_response,
                                   bridge_action_to_event, handle_output)


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class ButtonTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.ctl = ModeController(debounce_ms=250, now=self.clock)

    def press(self, mode):
        return self.ctl.handle_line(json.dumps({"event": "button", "source": mode, "mode": mode}))

    def test_three_buttons_map_to_apply_events(self):
        for mode in ("fast", "efficient", "balanced"):
            self.assertEqual(self.press(mode), {"action": "apply", "mode": mode})

    def test_debounce_drops_bounce_then_accepts_next_press(self):
        self.assertEqual(self.press("fast")["mode"], "fast")
        self.clock.advance(0.1)
        self.assertIsNone(self.press("fast"))
        self.clock.advance(0.2)
        self.assertIsNone(self.press("fast"))
        self.clock.advance(0.3)
        self.assertEqual(self.press("fast")["mode"], "fast")

    def test_debounce_is_per_source(self):
        self.assertEqual(self.press("fast")["mode"], "fast")
        self.clock.advance(0.05)
        self.assertEqual(self.press("efficient")["mode"], "efficient")


class KnobTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.ctl = ModeController(debounce_ms=250, now=self.clock)

    def turn(self, direction, mode="fast"):
        return self.ctl.handle_line(json.dumps({"event": "knob", "direction": direction, "mode": mode}))

    def test_knob_cycles_through_modes(self):
        self.assertEqual(self.turn(1), {"action": "apply", "mode": "efficient", "via": "knob"})
        self.clock.advance(1)
        self.assertEqual(self.turn(1, "efficient")["mode"], "balanced")
        self.clock.advance(1)
        self.assertEqual(self.turn(1, "balanced")["mode"], "fast")
        self.clock.advance(1)
        self.assertEqual(self.turn(-1, "fast")["mode"], "balanced")

    def test_knob_debounce_coalesces_spins(self):
        self.assertEqual(self.turn(1)["mode"], "efficient")
        self.clock.advance(0.05)
        for _ in range(4):
            self.assertIsNone(self.turn(1))


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.ctl = ModeController(debounce_ms=0, now=FakeClock())

    def test_malformed_lines_raise_event_error(self):
        for line in ("not json", "", "[]", '"str"', '{"event": "sliders"}',
                     '{"event": "button", "source": "fast", "mode": "slow"}',
                     '{"event": "button", "source": "fast"}',
                     '{"event": "knob", "direction": 5}',
                     '{"event": "knob", "direction": "left"}'):
            with self.assertRaises(EventError, msg=line):
                self.ctl.handle_line(line)

    def test_extreme_debounce_rejected(self):
        with self.assertRaises(ValueError):
            ModeController(debounce_ms=-1)
        with self.assertRaises(ValueError):
            ModeController(debounce_ms=5000)


class OutputTests(unittest.TestCase):
    def test_status_renders_pixels_progress_and_vibration(self):
        status = {
            "models": [
                {"id": "tiny-llama", "device": "cpu"},
                {"id": "whisper", "device": "npu"},
                {"id": "bad", "device": "quantum"},
            ],
            "tuning": {"running": True, "completed": 3, "total": 10},
            "run_finished": True,
        }
        out = json.loads(handle_output(status))
        self.assertEqual(out["pixels"], {"tiny-llama": "cpu", "whisper": "npu"})
        self.assertEqual(out["progress"], 0.3)
        self.assertTrue(out["vibrate"])

    def test_applied_config_overrides_default_pixel_for_acknowledged_model(self):
        status = {
            "models": [{"id": "tiny-gguf", "device": "cpu"},
                       {"id": "whisper", "device": "npu"}],
            "applied": {"model": "tiny-gguf", "mode": "balanced",
                        "config": {"device": "npu", "threads": 2, "context": 2048}},
        }
        out = json.loads(handle_output(status))
        # The acknowledged applied placement wins for that model only.
        self.assertEqual(out["pixels"], {"tiny-gguf": "npu", "whisper": "npu"})

    def test_default_pixels_stay_configured_when_applied_names_no_model(self):
        status = {
            "models": [{"id": "tiny-gguf", "device": "cpu"}],
            "applied": {"mode": "balanced",
                        "config": {"device": "npu", "threads": 2, "context": 2048}},
        }
        out = json.loads(handle_output(status))
        self.assertEqual(out["pixels"], {"tiny-gguf": "cpu"})

    def test_unverifiable_applied_device_cannot_override_configured_pixel(self):
        # An applied block with a bogus device value does not describe an
        # actually applied placement, so the pixel stays at the configured
        # default instead of echoing an unverifiable ack.
        for bad_device in ("quantum", None, 3, ""):
            status = {
                "models": [{"id": "tiny-gguf", "device": "cpu"}],
                "applied": {"model": "tiny-gguf", "mode": "balanced",
                            "config": {"device": bad_device, "threads": 2,
                                       "context": 2048}},
            }
            out = json.loads(handle_output(status))
            self.assertEqual(out["pixels"], {"tiny-gguf": "cpu"},
                             msg=repr(bad_device))

    def test_ack_config_echoes_only_actually_applied_values(self):
        status = {
            "models": [{"id": "tiny-gguf", "device": "cpu"}],
            "applied": {"model": "tiny-gguf", "mode": "fast",
                        "config": {"device": "gpu", "threads": 6, "context": 8192,
                                   "speculative": True}},
        }
        out = json.loads(handle_output(status))
        # Pixel and config both come from the applied block, and only the
        # three applied config fields cross to the board; the unapplied
        # default (cpu) is not presented as state.
        self.assertEqual(out["pixels"], {"tiny-gguf": "gpu"})
        self.assertEqual(out["config"],
                         {"device": "gpu", "threads": 6, "context": 8192})
        self.assertEqual(out["active_mode"], "fast")

    def test_run_finished_is_caller_derived_not_service_state(self):
        out = json.loads(handle_output({"models": [], "tuning": {"running": False}}))
        self.assertFalse(out["vibrate"])

    def test_idle_status_and_non_dict_rejected(self):
        out = json.loads(handle_output({}))
        self.assertEqual(out, {"pixels": {}, "progress": None, "vibrate": False})
        with self.assertRaises(ValueError):
            handle_output("nope")


if __name__ == "__main__":
    unittest.main()


class BridgeMappingTests(unittest.TestCase):
    def test_packed_bridge_codes_map_to_events(self):
        self.assertEqual(bridge_action_to_event(0x0100),
                         {"event": "knob", "direction": 1, "mode": "fast"})
        self.assertEqual(bridge_action_to_event(0xFF00, "balanced"),
                         {"event": "knob", "direction": -1, "mode": "balanced"})
        self.assertEqual(bridge_action_to_event(0x02),
                         {"event": "button", "source": "efficient", "mode": "efficient"})
        self.assertIsNone(bridge_action_to_event(0))

    def test_invalid_bridge_codes_raise(self):
        for bad in (-1, 0x10000, "3", None, True):
            with self.assertRaises(EventError, msg=repr(bad)):
                bridge_action_to_event(bad)
        with self.assertRaises(EventError):
            bridge_action_to_event(0x04)


class ApplyContractTests(unittest.TestCase):
    def test_request_is_exact_body(self):
        self.assertEqual(apply_request("fast"), {"mode": "fast"})
        for bad in ("baseline", "turbo", "", None):
            with self.assertRaises(EventError):
                apply_request(bad)

    def test_response_requires_config_and_evidence(self):
        good = {"mode": "balanced",
                "config": {"device": "cpu", "threads": 4, "context": 4096},
                "evidence": {"source": "tuned sweep", "metrics": {"decode_tps": 31.2}}}
        out = apply_response(good)
        self.assertEqual(out["mode"], "balanced")
        self.assertEqual(out["config"]["device"], "cpu")
        self.assertEqual(out["evidence_source"], "tuned sweep")
        missing_cfg = {k: v for k, v in good.items() if k != "config"}
        missing_ev = {k: v for k, v in good.items() if k != "evidence"}
        partial = dict(good, config={"device": "cpu"})
        for bad in (missing_cfg, missing_ev, partial, [], None,
                    dict(good, mode="turbo")):
            with self.assertRaises(EventError, msg=repr(bad)[:60]):
                apply_response(bad)

    def test_handle_output_carries_active_config(self):
        status = {"applied": {"mode": "efficient",
                              "config": {"device": "npu", "threads": 3, "context": 2048,
                                         "extra": True}},
                  "run_finished": True}
        out = json.loads(handle_output(status))
        self.assertEqual(out["active_mode"], "efficient")
        self.assertEqual(out["config"], {"device": "npu", "threads": 3, "context": 2048})
        self.assertTrue(out["vibrate"])
