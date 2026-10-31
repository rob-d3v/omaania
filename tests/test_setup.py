# SPDX-License-Identifier: Apache-2.0
"""End-to-end: setup, setup again, CLI verbs, uninstall, all in a scratch
HOME with a fake .deb (OMAANIA_SANDBOX=1: no systemctl, no hyprctl)."""
import json
import unittest

from helpers import Sandbox, fake_deb


class SetupUninstall(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.deb = self.sb.home.parent / (self.sb.home.name + ".deb")
        self.sha = fake_deb(self.deb)
        self.before = self.sb.files()

    def tearDown(self):
        self.deb.unlink(missing_ok=True)
        self.sb.close()

    def setup_(self, *extra):
        r = self.sb.run("setup", "--yes", "--deb", str(self.deb), "--sha256", self.sha, "--tag", "vTEST", *extra)
        self.assertIn("Ania Player", r.stdout, r.stdout + r.stderr)
        return r

    def test_full_cycle(self):
        r = self.setup_()
        h = self.sb.home
        self.assertIn("sha256 verified", r.stdout)
        launcher = (h / ".local/bin/aniaplayer").read_text()
        self.assertIn("omaania: launcher generated", launcher)
        self.assertNotIn(" /usr/share/aniaplayer", launcher.replace(str(h), "~"))
        self.assertIn(str(h / ".local/opt/ania-player/usr/share/aniaplayer"), launcher)
        hl = (h / ".config/hypr/hyprland.lua").read_text()
        self.assertEqual(hl.count('pcall(require, "hypr.omaania")'), 1)
        self.assertTrue((h / ".config/hypr/omaania.lua").is_file())
        unit = (h / ".config/systemd/user/aniaplayer.service").read_text()
        self.assertIn("managed-by: omaania", unit)
        self.assertTrue((h / ".config/systemd/user/graphical-session.target.wants/aniaplayer.service").is_symlink())
        vc = json.loads((h / ".config/aniaplayer/plugins/voice_assistant/voice_config.json").read_text())
        self.assertEqual(vc["agent"]["conversation_mode"], "until_dismissed")
        self.assertEqual(vc["chat"]["theme"], "auto")
        self.assertNotIn("provider", vc["agent"])          # fake build has no omarchy-agent
        self.assertNotIn("wake_word_enabled", vc["wake_word"])  # model not published

        # idempotent: same record, still one include line
        rec1 = json.loads((h / ".local/state/omaania/installed.json").read_text())
        self.setup_()
        rec2 = json.loads((h / ".local/state/omaania/installed.json").read_text())
        rec1.pop("setup_at"), rec2.pop("setup_at")
        self.assertEqual(rec1, rec2)
        self.assertEqual((h / ".config/hypr/hyprland.lua").read_text().count("hypr.omaania"), 1)

        # CLI verbs go to the (fake) player
        st = json.loads(self.sb.run("status", "--json").stdout)
        self.assertTrue(st["setup_ok"])
        self.assertEqual(st["state"], "locked")
        for args, expect in ((("lock", "--all"), "block --all"), (("unlock",), "unblock"),
                             (("hide",), "hide"), (("settings", "avatar"), "settings avatar")):
            self.assertEqual(self.sb.run(*args).returncode, 0)
            self.assertEqual(self.sb.calls()[-1], expect)

        # uninstall: back to exactly what was there, hyprland.lua byte-identical
        r = self.sb.run("uninstall", "--yes", "--purge")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((h / ".config/hypr/hyprland.lua").read_text(), Sandbox.HYPR)
        self.assertEqual(self.sb.files(), self.before)

    def test_hypr_line_needs_consent(self):
        h = self.sb.home
        include = 'pcall(require, "hypr.omaania")'
        # --yes: the question and its answer are printed, then the line is added
        r = self.setup_()
        self.assertIn("Add the avatar's Hyprland window rules?", r.stdout)
        self.assertIn(include + ") yes (--yes)", r.stdout)
        self.assertEqual((h / ".config/hypr/hyprland.lua").read_text().count(include), 1)
        # once it is there, setup does not ask again
        r = self.setup_()
        self.assertNotIn("Add the avatar's Hyprland window rules?", r.stdout)
        self.sb.run("uninstall", "--yes", "--purge")
        self.assertEqual((h / ".config/hypr/hyprland.lua").read_text(), Sandbox.HYPR)

    def test_hypr_interactive_no_leaves_hyprland_lua_alone(self):
        h = self.sb.home
        out = self.sb.run_tty("setup", "--deb", str(self.deb), "--sha256", self.sha, "--tag", "vTEST",
                              "--no-mcp", answers={"Hyprland window rules?": "n"})
        self.assertIn("Add the avatar's Hyprland window rules?", out)
        self.assertIn("[Y/n]", out)
        self.assertIn("left your Hyprland config alone", out)
        self.assertEqual((h / ".config/hypr/hyprland.lua").read_text(), Sandbox.HYPR)
        self.assertFalse((h / ".config/hypr/omaania.lua").exists())

    def test_hypr_interactive_default_is_yes(self):
        h = self.sb.home
        out = self.sb.run_tty("setup", "--deb", str(self.deb), "--sha256", self.sha, "--tag", "vTEST", "--no-mcp")
        self.assertIn("Add the avatar's Hyprland window rules?", out)
        self.assertEqual((h / ".config/hypr/hyprland.lua").read_text().count('pcall(require, "hypr.omaania")'), 1)

    def test_hypr_without_terminal_or_yes_changes_nothing(self):
        r = self.sb.run("setup", "--deb", str(self.deb), "--sha256", self.sha, "--tag", "vTEST", "--no-mcp")
        self.assertIn("skipped (no terminal; re-run with --yes)", r.stdout)
        self.assertEqual((self.sb.home / ".config/hypr/hyprland.lua").read_text(), Sandbox.HYPR)

    def test_codex_agent_gets_the_mcp_server(self):
        agent = self.sb.home / ".config/omarchy/defaults/agent"
        agent.parent.mkdir(parents=True)
        agent.write_text("codex\n")
        r = self.setup_("--mcp")
        self.assertIn("would run: npx -y ania-mcp@0.1.3 install codex", r.stdout, r.stdout)
        self.assertNotIn("not handled by", r.stdout)

    def test_wake_word_is_honest_until_published(self):
        r = self.setup_()
        self.assertIn("Wake word “Hey Omarchy” (free model coming soon, not published yet)", r.stdout)
        self.assertIn("Press ctrl+shift+space to talk.", r.stdout)

    def test_omahey_installed_gets_asked_who_owns_the_wake_word(self):
        r = self.setup_()
        self.assertNotIn("omahey skips it", r.stdout)
        (self.sb.home / ".config/omahey").mkdir(parents=True)
        r = self.setup_()
        self.assertIn("the avatar gets the wake word; omahey skips it", r.stdout)
        r = self.setup_("--no-wake")
        self.assertNotIn("omahey skips it", r.stdout)

    def test_omawake_from_before_the_rename_counts_as_omahey(self):
        (self.sb.home / ".config/omawake").mkdir(parents=True)
        r = self.setup_()
        self.assertIn("the avatar gets the wake word; omahey skips it", r.stdout)

    def test_existing_user_values_win(self):
        vc = self.sb.home / ".config/aniaplayer/plugins/voice_assistant/voice_config.json"
        vc.parent.mkdir(parents=True)
        vc.write_text(json.dumps({"agent": {"provider": "ollama", "conversation_mode": "followup"},
                                  "tts": {"voice_locale": "pt-BR"}}))
        self.setup_()
        data = json.loads(vc.read_text())
        self.assertEqual(data["agent"]["provider"], "ollama")
        self.assertEqual(data["agent"]["conversation_mode"], "followup")
        self.assertEqual(data["tts"]["voice_locale"], "pt-BR")
        self.assertEqual(data["chat"]["theme"], "auto")
        self.sb.run("uninstall", "--yes")
        data = json.loads(vc.read_text())             # the user's file stays, minus our keys
        self.assertEqual(data, {"agent": {"provider": "ollama", "conversation_mode": "followup"},
                                "tts": {"voice_locale": "pt-BR"}})

    def test_bad_checksum_installs_nothing(self):
        r = self.sb.run("setup", "--yes", "--deb", str(self.deb), "--sha256", "0" * 64)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("checksum mismatch", r.stdout)
        self.assertFalse((self.sb.home / ".local/opt/ania-player").exists())
        self.assertFalse((self.sb.home / ".local/bin/aniaplayer").exists())

    def test_external_player_is_left_alone(self):
        own = self.sb.home / ".local/bin/aniaplayer"
        own.parent.mkdir(parents=True)
        own.write_text("#!/bin/bash\necho mine\n")
        self.setup_()
        self.assertEqual(own.read_text(), "#!/bin/bash\necho mine\n")
        self.assertFalse((self.sb.home / ".local/opt/ania-player").exists())
        self.sb.run("uninstall", "--yes", "--purge")
        self.assertEqual(own.read_text(), "#!/bin/bash\necho mine\n")

    def test_external_player_config_and_rules_are_left_alone(self):
        h = self.sb.home
        own = h / ".local/bin/aniaplayer"
        own.parent.mkdir(parents=True)
        own.write_text("#!/bin/bash\necho mine\n")
        vc = h / ".config/aniaplayer/plugins/voice_assistant/voice_config.json"
        vc.parent.mkdir(parents=True)
        vc.write_text('{"agent": {"provider": "openai"}, "stt": {"language": "pt"}}\n')
        rules = h / ".config/hypr/aniaplayer.lua"
        rules.parent.mkdir(parents=True, exist_ok=True)
        rules.write_text('-- my rules: class "^Ania Player$"\n')
        main = h / ".config/hypr/hyprland.lua"
        main_before = main.read_text() if main.exists() else None
        if main_before is None:
            main.write_text("-- stub\n")
            main_before = "-- stub\n"
        r = self.setup_()
        self.assertIn("leaves its settings alone", r.stdout)
        self.assertIn("adds no second set", r.stdout)
        self.assertEqual(json.loads(vc.read_text()), {"agent": {"provider": "openai"}, "stt": {"language": "pt"}})
        self.assertFalse((h / ".config/hypr/omaania.lua").exists())
        self.assertEqual(main.read_text(), main_before)
        self.sb.run("uninstall", "--yes", "--purge")
        self.assertEqual(json.loads(vc.read_text()), {"agent": {"provider": "openai"}, "stt": {"language": "pt"}})

    def test_uninstall_leaves_no_empty_folders(self):
        self.setup_()
        self.sb.run("uninstall", "--yes", "--purge")
        h = self.sb.home
        for d in (".local/share/icons", ".local/share/applications", ".local/opt",
                  ".config/systemd/user/graphical-session.target.wants"):
            self.assertFalse((h / d).exists(), d)

    def test_foreign_unit_is_left_alone(self):
        unit = self.sb.home / ".config/systemd/user/aniaplayer.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Service]\nExecStart=/bin/true\n")
        self.setup_()
        self.sb.run("uninstall", "--yes", "--purge")
        self.assertEqual(unit.read_text(), "[Service]\nExecStart=/bin/true\n")

    def test_feature_build_gets_agent_brain(self):
        self.sha = fake_deb(self.deb, features=True)
        self.setup_()
        vc = json.loads((self.sb.home / ".config/aniaplayer/plugins/voice_assistant/voice_config.json").read_text())
        self.assertEqual(vc["agent"]["provider"], "omarchy-agent")

    def test_argv_agent_build_does_not_get_agent_brain(self):
        self.sha = fake_deb(self.deb, features=True, agent_argv=True)
        r = self.setup_()
        self.assertIn("on its command line", r.stdout)
        vc = json.loads((self.sb.home / ".config/aniaplayer/plugins/voice_assistant/voice_config.json").read_text())
        self.assertNotIn("provider", vc["agent"])

    def test_own_key_never_in_argv_and_0600(self):
        r = self.sb.run("setup", "--yes", "--deb", str(self.deb), "--sha256", self.sha, "--brain", "own-key",
                        "--api-base", "https://api.example.com/v1", "--api-model", "m1",
                        OMAANIA_API_KEY="sk-test-123")
        self.assertIn("your own key", r.stdout)
        key = self.sb.home / ".config/aniaplayer/omaania-api.key"
        self.assertEqual(key.read_text().strip(), "sk-test-123")
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        vc = json.loads((self.sb.home / ".config/aniaplayer/plugins/voice_assistant/voice_config.json").read_text())
        self.assertEqual(vc["agent"]["provider"], "openai")
        self.assertEqual(vc["agent"]["api_key_file"], str(key))
        self.assertNotIn("sk-test-123", json.dumps(vc))


if __name__ == "__main__":
    unittest.main()
