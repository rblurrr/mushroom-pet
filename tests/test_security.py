import http.client
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from mushroompet.api import ApiServer, Bridge
from mushroompet import launchers
from mushroompet.platforms.macos import MacBackend


class SecurityTests(unittest.TestCase):
    def test_api_auth_and_query_token_rejected(self):
        server = ApiServer(Bridge(), 0, "secret")
        self.assertTrue(server.start())
        port = server.httpd.server_port
        try:
            def get(path, headers=None):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                c.request("GET", path, headers=headers or {})
                r = c.getresponse(); body = r.read(); c.close()
                return r.status, body
            self.assertEqual(get("/health?token=secret")[0], 200)
            self.assertEqual(get("/state?token=secret")[0], 401)
            self.assertEqual(get("/state", {"Authorization": "bEaReR secret"})[0], 200)
            self.assertEqual(get("/state", {"Authorization": "Basic secret"})[0], 401)
        finally:
            server.stop()

    def test_url_scheme_rejected(self):
        ok, msg = launchers.launch_custom({"kind": "url", "target": "file:///etc/passwd"})
        self.assertFalse(ok)
        self.assertIn("http", msg)

    def test_token_file_permissions_posix(self):
        if os.name != "posix":
            self.skipTest("POSIX mode bits unavailable")
        import mushroompet.config as config
        with tempfile.TemporaryDirectory() as d, patch.object(config, "APP_DIR", d), \
             patch.object(config, "INBOX_DIR", os.path.join(d, "inbox")), \
             patch.object(config, "TOKEN_PATH", os.path.join(d, "token")):
            c = object.__new__(config.Config)
            c.data = {"api_token": "secret"}
            c._write_token()
            self.assertEqual(os.stat(config.TOKEN_PATH).st_mode & 0o777, 0o600)

    def test_plist_is_structured(self):
        import plistlib
        with tempfile.TemporaryDirectory() as d, patch.object(MacBackend, "_plist_path", lambda self: os.path.join(d, "x.plist")), \
             patch("mushroompet.platforms.macos.subprocess.run"):
            b = MacBackend(); ok, path = b.install_autostart("/tmp/run.py")
            self.assertTrue(ok)
            with open(path, "rb") as f:
                p = plistlib.load(f)
            self.assertEqual(p["Label"], "com.mushroompet")
            self.assertEqual(p["ProgramArguments"][1], "/tmp/run.py")

    def test_windows_no_policy_bypass_in_source(self):
        path = os.path.join(os.path.dirname(__file__), "..", "mushroompet", "platforms", "windows.py")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("ExecutionPolicy", text)
        self.assertNotIn("Bypass", text)


if __name__ == "__main__":
    unittest.main()
