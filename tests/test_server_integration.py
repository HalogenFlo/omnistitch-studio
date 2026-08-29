import http.client
import os
import tempfile
import threading
import unittest
import urllib.parse

from http.server import ThreadingHTTPServer

import server


class TestServerIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(server.DATA_DIR, exist_ok=True)
        cls.temp_dir = tempfile.TemporaryDirectory(dir=server.DATA_DIR)
        cls.image_path = os.path.join(cls.temp_dir.name, "stream.bmp")
        cls.payload = b"BM" + (b"x" * (2 * server.FILE_STREAM_CHUNK_BYTES + 17))
        with open(cls.image_path, "wb") as stream:
            stream.write(cls.payload)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.AlignmentToolRequestHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(5)
        cls.temp_dir.cleanup()

    def _connection(self):
        return http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=10)

    def test_image_response_streams_allowed_file_without_cross_origin_cors(self):
        path = "/api/image?" + urllib.parse.urlencode({"path": self.image_path})
        connection = self._connection()
        connection.request("GET", path, headers={"Origin": "https://attacker.example"})
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))
        self.assertEqual(int(response.getheader("Content-Length")), len(self.payload))
        self.assertEqual(response.read(), self.payload)
        connection.close()

    def test_same_origin_cors_and_workspace_source_denial(self):
        port = self.httpd.server_address[1]
        connection = self._connection()
        connection.request("GET", "/api/health", headers={"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"})
        response = connection.getresponse()
        response.read()
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), f"http://127.0.0.1:{port}")
        connection.close()

        denied = "/api/image?" + urllib.parse.urlencode({"path": os.path.join(server.WORKSPACE_DIR, "README.md")})
        connection = self._connection()
        connection.request("GET", denied)
        response = connection.getresponse()
        response.read()
        self.assertEqual(response.status, 403)
        connection.close()

    def test_oversized_json_request_is_rejected_before_body_read(self):
        connection = self._connection()
        connection.request(
            "POST",
            "/api/scan_folder",
            body=b"x",
            headers={"Content-Length": str(server.MAX_JSON_REQUEST_BYTES + 1)},
        )
        response = connection.getresponse()
        response.read()
        self.assertEqual(response.status, 413)
        connection.close()


if __name__ == "__main__":
    unittest.main()
