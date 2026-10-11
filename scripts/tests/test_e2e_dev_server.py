"""Runs scripts/e2e_local.py over real HTTP sockets against the dependency-free dev server (in-memory repo, SYNTHETIC data).
This verifies the e2e script and the shared endpoint logic. It does NOT test the FastAPI wiring or PostgreSQL."""
import os, subprocess, sys, threading, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(ROOT, "scripts")); os.chdir(ROOT)
import dev_server
from floodcommon.config import Settings

TOKEN = "t" * 32


class E2EAgainstDevServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = dev_server.serve(0, settings=Settings(responder_token=TOKEN, demo_now="2024-09-28T20:00:00+00:00"))
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True); cls.t.start()

    @classmethod
    def tearDownClass(cls): cls.srv.shutdown(); cls.srv.server_close()

    def test_e2e_script_passes(self):
        env = {**os.environ, "API_URL": f"http://127.0.0.1:{self.srv.server_address[1]}", "RESPONDER_TOKEN": TOKEN, "DEMO_NOW": "2024-09-28T20:00:00+00:00"}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts/e2e_local.py")], env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"(\d+)/\1 checks passed")
        self.assertNotIn("FAIL", r.stdout)


if __name__ == "__main__":
    unittest.main()
