import json
import threading
import unittest
import urllib.error
import urllib.request

from inspection.__main__ import make_server
from inspection.core import Hub
from test_core import Client, PNG


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.hub = Hub(Client())
        self.server = make_server("127.0.0.1", 0, self.hub)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_browser_frame_reaches_hardware_inspection(self):
        request = urllib.request.Request(self.url + "/api/frame", data=json.dumps({"image":PNG}).encode(), headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(request) as response: self.assertEqual(response.status, 200)
        request = urllib.request.Request(self.url + "/api/inspect", data=b'{}', headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(request) as response: self.assertEqual(response.status, 202)
        self.hub.client.release.set()

    def test_cross_origin_write_is_rejected(self):
        request = urllib.request.Request(self.url + "/api/clear", data=b'{}', headers={"Content-Type":"application/json","Origin":"https://untrusted.example"})
        with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_dns_rebinding_host_is_rejected(self):
        request = urllib.request.Request(self.url + "/api/state", headers={"Host":"untrusted.example"})
        with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_network_binding_requires_token(self):
        with self.assertRaises(ValueError): make_server("0.0.0.0", 0, self.hub)


if __name__ == "__main__": unittest.main()
