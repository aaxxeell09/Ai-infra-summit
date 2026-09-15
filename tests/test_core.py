import threading
import time
import unittest

from inspection.core import Hub, InspectionError, parse_answer, validate_image

PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jr1kAAAAASUVORK5CYII="


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now


class Client:
    base_url, model = "http://127.0.0.1:18181/v1", "test-only"
    def __init__(self): self.entered, self.release = threading.Event(), threading.Event()
    def infer(self, image, instruction):
        self.entered.set()
        if not self.release.wait(2): raise TimeoutError()
        return "OK", "Visible test condition met."


class StateTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.client = Clock(), Client()
        self.hub = Hub(self.client, clock=self.clock)

    def finish(self):
        self.client.release.set()
        for _ in range(100):
            if not self.hub.busy: return
            time.sleep(.005)
        self.fail("Worker did not finish")

    def test_old_answer_cannot_override_changed_instruction(self):
        self.hub.inspect(PNG)
        self.assertTrue(self.client.entered.wait(1))
        self.hub.instruction_set("Different inspection")
        self.finish()
        self.assertEqual(self.hub.snapshot()["status"], "UNKNOWN")
        self.assertEqual(self.hub.snapshot()["counters"]["completed"], 1)

    def test_clear_cancels_result_but_does_not_spawn_parallel_model(self):
        self.hub.inspect(PNG)
        self.hub.clear()
        with self.assertRaises(InspectionError) as error: self.hub.inspect(PNG)
        self.assertEqual(error.exception.status, 409)
        self.finish()
        self.assertEqual(self.hub.snapshot()["status"], "IDLE")

    def test_result_expiry_removes_ok(self):
        self.hub.inspect(PNG)
        self.finish()
        self.assertEqual(self.hub.snapshot()["status"], "OK")
        self.clock.now += 21
        self.assertEqual(self.hub.snapshot()["status"], "UNKNOWN")

    def test_stale_uploaded_frame_cannot_be_inspected(self):
        self.hub.frame(PNG)
        self.clock.now += 16
        with self.assertRaises(InspectionError): self.hub.inspect()
        self.assertFalse(self.hub.busy)

    def test_camera_disconnect_invalidates_running_answer(self):
        self.hub.inspect(PNG)
        self.hub.frame_clear()
        self.finish()
        self.assertEqual(self.hub.snapshot()["status"], "UNKNOWN")
        self.assertFalse(self.hub.snapshot()["frame_ready"])

    def test_late_answer_cannot_restore_ok_after_timeout(self):
        self.hub.inspect(PNG)
        self.clock.now += 91
        self.assertEqual(self.hub.snapshot()["status"], "UNKNOWN")
        self.finish()
        self.assertEqual(self.hub.snapshot()["status"], "UNKNOWN")

    def test_dead_board_is_marked_disconnected(self):
        self.hub.heartbeat("uno-q")
        self.assertTrue(self.hub.snapshot()["board"]["connected"])
        self.clock.now += 6
        self.assertFalse(self.hub.snapshot()["board"]["connected"])

    def test_malformed_model_output_is_not_an_ok(self):
        for text in ['OK', '{"status":"OK"}', '{"status":"GREEN","explanation":"yes"}',
                     '{"status":"OK","explanation":"yes","command":"run"}']:
            with self.assertRaises(ValueError): parse_answer(text)

    def test_remote_image_urls_and_spoofed_types_are_rejected(self):
        for value in ['https://example.com/image.png', 'file:///etc/passwd', 'data:image/png;base64,aGVsbG8=']:
            with self.assertRaises(InspectionError): validate_image(value)


if __name__ == "__main__": unittest.main()
