import unittest

from fastapi.testclient import TestClient

from web.api.query_service import app


class FrontendRouteTests(unittest.TestCase):
    def test_welcome_page_and_browser_module_assets_are_served(self):
        with TestClient(app) as client:
            for path in ("/", "/chat.html"):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("行知", response.text)
            for name in ("chat.js", "chat-state.js"):
                response = client.get(f"/assets/{name}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("javascript", response.headers["content-type"])
            self.assertEqual(client.get("/assets/destinations.png").status_code, 200)

    def test_import_api_uses_same_origin_without_port_8000(self):
        with TestClient(app) as client:
            self.assertEqual(client.get("/import-api/health").json(), {"ok": True, "service": "import"})
            response = client.post("/import-api/upload", files={"files": ("invalid.exe", b"invalid")})
            self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
