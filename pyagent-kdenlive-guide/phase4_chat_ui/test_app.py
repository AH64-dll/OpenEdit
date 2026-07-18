"""REST + route tests for the FastAPI app (TestClient, no pi subprocess)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

FIXTURE = _REPO_ROOT / "phase4_chat_ui" / "tests" / "fixtures" / "demo.kdenlive"
CATALOG = _REPO_ROOT / "phase4_chat_ui" / "tests" / "fixtures" / "catalog.json"


class TestAppREST(unittest.TestCase):
    def setUp(self):
        # Use a temp copy of the fixture so state changes don't dirty it.
        self.tmp = tempfile.mkdtemp()
        self.project = os.path.join(self.tmp, "work.kdenlive")
        with open(FIXTURE, "rb") as src:
            with open(self.project, "wb") as dst:
                dst.write(src.read())
        from phase4_chat_ui.app import create_app
        self.app = create_app(
            project=self.project,
            provider="x", model="y", pi_binary="false",
            catalog=str(CATALOG),
        )
        self.client = TestClient(self.app)

    def test_index_returns_html(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("PyAgent", r.text)

    def test_static_served(self):
        r = self.client.get("/static/app.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("WebSocket", r.text)

    def test_project_endpoint_returns_info(self):
        r = self.client.get("/api/project")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("info", body)
        self.assertIsNotNone(body["info"])
        self.assertEqual(body["info"]["width"], 1920)

    def test_plan_approve_without_pending_is_error(self):
        r = self.client.post("/api/plan/approved")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["ok"])

    def test_plan_bad_decision_is_error(self):
        r = self.client.post("/api/plan/maybe")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["ok"])

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_base64_image_valid(self):
        from phase4_chat_ui.app import save_base64_image
        import os
        base64_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        path = save_base64_image(base64_png)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".png"))
        os.remove(path)

    def test_save_base64_image_invalid_ext(self):
        from phase4_chat_ui.app import save_base64_image
        bad_url = "data:image/exe;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        with self.assertRaises(ValueError):
            save_base64_image(bad_url)

    def test_save_base64_image_too_large(self):
        from phase4_chat_ui.app import save_base64_image
        huge_data = "data:image/png;base64," + ("A" * (15 * 1024 * 1024))
        with self.assertRaises(ValueError):
            save_base64_image(huge_data)


if __name__ == "__main__":
    unittest.main()
