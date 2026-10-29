# SPDX-License-Identifier: Apache-2.0
import unittest

from omaania import cli, player


class Units(unittest.TestCase):
    def test_parse_sums(self):
        text = ("b76e926ba795c02f4b4fac16c7bd516f24ebf4e247f0db9ffac777f120617785  AniaPlayerSetup.exe\n"
                "F6DC60882DB52CC7DBC5B661218D95CB0B741CA160E0BEB1F29886E94439A599 *AniaPlayerSetup.deb\n")
        self.assertEqual(player.parse_sums(text, "AniaPlayerSetup.deb"),
                         "f6dc60882db52cc7dbc5b661218d95cb0b741ca160e0beb1f29886e94439a599")
        self.assertIsNone(player.parse_sums(text, "other.deb"))

    def test_widget_state(self):
        ws = cli.widget_state
        self.assertEqual(ws({}, False), "setup")
        self.assertEqual(ws({"running": False}, True), "stopped")
        self.assertEqual(ws({"running": True, "status": "error"}, True), "stopped")
        self.assertEqual(ws({"running": True, "tts_active": True, "blocked": True}, True), "speaking")
        self.assertEqual(ws({"running": True, "va_session": True}, True), "listening")
        self.assertEqual(ws({"running": True, "blocked": True}, True), "locked")
        self.assertEqual(ws({"running": True, "visible": False}, True), "hidden")
        self.assertEqual(ws({"running": True, "visible": True}, True), "shown")

    def test_verbs_are_real_aniaplayer_verbs(self):
        # From Ania Player 1.2.47 cli_main.run(): the commands dict.
        real = {"show", "hide", "toggle", "block", "unblock", "lock", "unlock", "settings", "quit",
                "open", "status", "biometria"}
        for argv in cli.VERBS.values():
            self.assertIn(argv[0], real)

    def test_urls_are_https_on_known_hosts(self):
        for url in cli.URLS.values():
            self.assertTrue(url.startswith(("https://aniamodels.shop/", "https://github.com/rob-d3v/")), url)


if __name__ == "__main__":
    unittest.main()
