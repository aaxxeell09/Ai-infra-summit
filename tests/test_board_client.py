import importlib.util
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest

spec = importlib.util.spec_from_file_location("board_client", Path(__file__).resolve().parents[1] / "arduino/python/main.py")
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)


class Bridge:
    def __init__(self):
        self.calls = []
        self.fail = False

    def call(self, name, *args, **kwargs):
        if name == "get_action":
            return 0
        if self.fail:
            raise OSError("disconnected")
        self.calls.append(args)
        return True


class Hub:
    last_elapsed_ms = 40

    def heartbeat(self):
        return None, None


class BoardClientTests(unittest.TestCase):
    def setUp(self):
        self.bridge = Bridge()
        self.client = board.Client(Hub(), self.bridge)

    def test_expiry_never_refreshes_an_old_ok(self):
        self.client.apply_hub_state({"status": "OK", "expires_in_ms": 500})
        self.assertEqual(self.bridge.calls[-1], (board.STATUS_OK, 410))
        self.client.apply_hub_state({"status": "OK", "expires_in_ms": 80})
        self.assertEqual(self.bridge.calls[-1][0], board.STATUS_UNKNOWN)

    def test_malformed_states_clear_previous_result(self):
        for body in (None, [], {"status": "OK"}, {"status": "OK", "expires_in_ms": "20000"}, {"status": "unexpected"}):
            self.client.apply_hub_state({"status": "OK", "expires_in_ms": 20000})
            self.client.apply_hub_state(body)
            self.assertEqual(self.bridge.calls[-1][0], board.STATUS_UNKNOWN)

    def test_failed_heartbeat_does_not_resend_old_ok(self):
        self.client.apply_hub_state({"status": "OK", "expires_in_ms": 20000})
        self.client.poll()
        self.assertEqual(self.bridge.calls[-1][0], board.STATUS_UNKNOWN)

    def test_rpc_failure_retries_only_with_new_state(self):
        self.bridge.fail = True
        self.client.apply_hub_state({"status": "OK", "expires_in_ms": 20000})
        self.assertIsNone(self.client.last_status)
        self.bridge.fail = False
        self.client.apply_hub_state({"status": "CHECK", "expires_in_ms": 1000})
        self.assertEqual(self.bridge.calls, [(board.STATUS_CHECK, 910)])

    @unittest.skipIf(os.name == "nt", "Board Unix socket transport is tested on Unix")
    def test_usb_unix_socket_http_transport(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "hub.sock")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(path)
                listener.listen(1)
                def respond():
                    conn, _ = listener.accept()
                    with conn:
                        conn.recv(8192)
                        body = b'{"status":"UNKNOWN"}'
                        conn.sendall(b'HTTP/1.0 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
                thread = threading.Thread(target=respond, daemon=True)
                thread.start()
                hub = board.HubClient("http://localhost:8080", socket_path=path)
                self.assertEqual(hub.state(), (200, {"status":"UNKNOWN"}))
                thread.join(2)


if __name__ == "__main__":
    unittest.main()
