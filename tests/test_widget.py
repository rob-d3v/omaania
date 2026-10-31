import re
import unittest
from pathlib import Path


class WidgetTextTests(unittest.TestCase):
    """Labels come from `aniaplayer status --json` (avatar names, which can come
    from marketplace packs): Qt's default AutoText would render <img src=...> there."""

    def test_every_text_is_plain(self):
        qml = (Path(__file__).resolve().parents[1] / "Widget.qml").read_text()
        blocks = re.findall(r"\bText \{([^{}]*)", qml)
        self.assertTrue(blocks)
        for body in blocks:
            self.assertIn("textFormat: Text.PlainText", body)


if __name__ == "__main__":
    unittest.main()
