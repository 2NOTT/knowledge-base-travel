import tempfile
import unittest
from pathlib import Path

from scripts.build_demo import ASSETS, ROOT, build_demo


class DemoBuildTests(unittest.TestCase):
    def test_pages_build_is_relative_and_only_publishes_frontend_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_demo(output)
            html = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn('data-demo="true"', html)
            self.assertNotIn('"/assets/', html)
            self.assertNotIn('href="/chat.html"', html)
            self.assertNotIn("url('/assets/", (output / "assets/travel.css").read_text(encoding="utf-8"))
            self.assertEqual({file.name for file in output.iterdir()}, {"assets", "index.html", ".nojekyll"})
            self.assertEqual({file.name for file in (output / "assets").iterdir()}, set(ASSETS))
            for name in ASSETS:
                self.assertEqual((output / "assets" / name).read_bytes(), (ROOT / "web/assets" / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
