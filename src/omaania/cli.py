# SPDX-License-Identifier: Apache-2.0
"""omaania command line. Every avatar action is a real `aniaplayer` verb
(see VERBS); omaania adds setup, status for the widget, and doctor."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

from . import __version__, assets, hypr, player, playercfg
from .paths import CLI, MCP_PACKAGE, UNIT_NAME, paths
from .util import default_agent, read_json, systemctl

SITE = "https://aniamodels.shop"
URLS = {
    "marketplace": f"{SITE}/marketplace?category=free",   # free avatars
    "credits": f"{SITE}/reports?tab=wallet",              # wallet: balance + add funds
    "create-avatar": f"{SITE}/connect-ai",                # MCP how-to: create with your AI
    "create-wakeword": f"{SITE}/create-wakeword",
    "docs": "https://github.com/rob-d3v/omaania#readme",
}

# omaania verb -> aniaplayer argv (all exist in Ania Player 1.2.47's cli_main.py).
VERBS = {
    "show": ["show"],
    "hide": ["hide"],
    "toggle": ["toggle"],
    "lock": ["block"],          # position lock: no drag, clicks ignored (aniaplayer travar)
    "unlock": ["unblock"],
    "settings": ["settings"],   # + avatar|voice|plugins|hotkeys|startup
    "quit": ["quit"],
}

# Things the widget menu needs that Ania Player has no CLI verb for yet.
MISSING_VERBS = {
    "briefing on|off": "aniaplayer biometria briefing on|off (briefing_enabled in biometria/config.json)",
    "avatar picker": "aniaplayer avatars --json / a file picker verb (omaania lists .ania files itself)",
    "marketplace/credits in-app": "aniaplayer marketplace|wallet (omaania opens the website instead)",
}


def running(st: dict) -> bool:
    return bool(st.get("running")) and st.get("status") != "error"


def widget_state(st: dict, setup_ok: bool) -> str:
    if not setup_ok:
        return "setup"
    if not running(st):
        return "stopped"
    if st.get("tts_active"):
        return "speaking"
    if st.get("va_session"):
        return "listening"
    if st.get("blocked"):
        return "locked"
    return "shown" if st.get("visible", True) else "hidden"


def collect_status() -> dict:
    rec = read_json(paths.install_record)
    have_player = player.installed() or bool(player.external_player())
    setup_ok = have_player and bool(rec.get("setup_at"))
    st = player.status_json() if have_player else {"running": False}
    feats = player.features() if paths.share.is_dir() else {}
    unit = paths.unit_file.exists()
    out = {
        "plugin_version": __version__,
        "setup_ok": setup_ok,
        "player_installed": have_player,
        "player": "external" if rec.get("player") == "external" else ("omaania" if have_player else None),
        "player_version": player.release_info().get("tag", ""),
        "running": running(st),
        "state": widget_state(st, setup_ok),
        "visible": bool(st.get("visible")) if running(st) else False,
        "blocked": bool(st.get("blocked")),
        "speaking": bool(st.get("tts_active")),
        "listening": bool(st.get("va_session")),
        "assistant_running": bool(st.get("assistant_running")),
        "avatar": st.get("name") or "",
        "service": unit,
        "autostart": paths.unit_wants.exists(),
        "features": feats,
        "biometric": playercfg.biometria_flags(),
        "default_agent": default_agent(),
        "urls": URLS,
    }
    return out


def cmd_status(a) -> int:
    s = collect_status()
    if a.json:
        print(json.dumps(s))
        return 0
    print(f"omaania {s['plugin_version']}: {s['state']}")
    print(f"  player     {s['player'] or 'not installed'} {s['player_version']}")
    print(f"  running    {s['running']}  visible {s['visible']}  locked {s['blocked']}  avatar {s['avatar'] or '-'}")
    print(f"  service    {'installed' if s['service'] else 'no'}  autostart {s['autostart']}")
    print(f"  brain      {read_json(paths.voice_config).get('agent', {}).get('provider', '(player default)')}"
          f"  (omarchy default agent: {s['default_agent'] or 'none'})")
    if not s["setup_ok"]:
        print("  -> run: omaania setup")
    return 0


def _ensure_running() -> bool:
    if running(player.status_json()):
        return True
    if paths.unit_file.exists():
        r = systemctl("start", UNIT_NAME)
        if r is not None and r.returncode == 0:
            return True
    try:
        subprocess.Popen([player.player_cmd()], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        return True
    except OSError as e:
        print(f"omaania: cannot start Ania Player: {e}", file=sys.stderr)
        return False


def passthrough(args: list[str], start: bool = False) -> int:
    if start and not running(player.status_json()):
        return 0 if _ensure_running() else 1      # a fresh start shows the avatar
    r = player.call(*args, timeout=10)
    if r is None:
        print("omaania: Ania Player is not installed (run: omaania setup)", file=sys.stderr)
        return 1
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    return r.returncode


def cmd_verb(name: str):
    def run(a) -> int:
        argv = list(VERBS[name])
        if name == "settings":
            argv.append(a.page)
        if getattr(a, "all", False):
            argv.append("--all")
        return passthrough(argv, start=name in ("show", "toggle"))
    return run


def cmd_start(a) -> int:
    return 0 if _ensure_running() else 1


def cmd_avatars(a) -> int:
    items = [{"file": f, "name": os.path.splitext(os.path.basename(f))[0]} for f in assets.avatar_files()]
    if a.json:
        print(json.dumps({"avatars": items, "default": assets.default_avatar()}))
    else:
        for i in items:
            print(f"{i['name']:24} {i['file']}")
        if not items:
            print("(no .ania avatars yet: get free ones with `omaania open marketplace`)")
    return 0


def cmd_avatar(a) -> int:
    f = os.path.realpath(os.path.expanduser(a.file))
    if not f.endswith(".ania") or not os.path.isfile(f):
        print(f"omaania: not an .ania file: {a.file}", file=sys.stderr)
        return 1
    if not running(player.status_json()):
        _ensure_running()
    return passthrough(["open", f])


def cmd_open(a) -> int:
    url = URLS[a.what]
    if a.print:
        print(url)
        return 0
    subprocess.Popen(["xdg-open", url], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 0


def cmd_biometric(a) -> int:
    feats = player.features() if paths.share.is_dir() else {}
    if feats and not feats.get("biometria"):
        print("This Ania Player build has no biometric plugin.", file=sys.stderr)
        return 2
    verb = {"on": "ligar", "off": "desligar", "setup": "tela", "status": "status"}[a.action]
    if a.action == "on" and not playercfg.biometria_flags()["consent"]:
        verb = "tela"          # enrol first: the player's own screen asks for consent
        print("Biometric unlock is opt-in: enrol your face first (the window explains what is stored).")
    if a.action in ("setup",) or verb == "tela":
        subprocess.Popen([player.player_cmd(), "biometria", "tela"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    return passthrough(["biometria", verb])


def cmd_briefing(a) -> int:
    feats = player.features() if paths.share.is_dir() else {}
    if a.action == "edit":
        if not feats.get("briefing_edit"):
            print("Edit briefing needs a newer Ania Player release (aniaplayer biometria briefing editar).",
                  file=sys.stderr)
            return 2
        subprocess.Popen(["omarchy-launch-floating-terminal-with-presentation",
                          f"'{player.player_cmd()}' biometria briefing editar"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    if a.action == "preview":
        return passthrough(["biometria", "briefing"])
    # TODO(ania-player): no CLI verb toggles briefing_enabled yet.
    print("Briefing on/off has no Ania Player command yet (TODO: aniaplayer biometria briefing on|off).\n"
          "Until then: aniaplayer biometria  → Briefing switch in that window.", file=sys.stderr)
    return 2


def cmd_logs(a) -> int:
    cmd = ["journalctl", "--user", "-u", UNIT_NAME, "-n", "200", "-f"]
    if a.open:
        subprocess.Popen(["uwsm-app", "--", "xdg-terminal-exec", "--app-id=org.omarchy.omaania-logs",
                          "--title=Ania Player logs", "-e", *cmd], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    return subprocess.call(cmd if a.follow else cmd[:-1])


def cmd_open_setup(a) -> int:
    """The widget's "Finish setup": run setup in a floating terminal."""
    subprocess.Popen(["omarchy-launch-floating-terminal-with-presentation", f"'{CLI}' setup"],
                     start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 0


def cmd_doctor(a) -> int:
    bad = 0

    def line(good: bool, text: str, fix: str = "") -> None:
        nonlocal bad
        bad += 0 if good else 1
        print(f"  {'✓' if good else '!'} {text}" + (f"  -> {fix}" if fix and not good else ""))

    rec = read_json(paths.install_record)
    ext = player.external_player()
    print("omaania doctor")
    line(player.installed() or bool(ext), f"Ania Player: {ext or paths.opt}", "omaania setup")
    if player.installed() and not ext:
        info = player.release_info()
        line(bool(info.get("sha256")), f"release {info.get('tag', '?')} sha256 {info.get('sha256', '?')[:16]}…"
             f" ({info.get('checksum_source', 'unknown')})")
        line(player.launcher_is_ours() or bool(ext), f"launcher {paths.launcher}", "omaania setup")
        feats = player.features()
        need = [k for k in ("omarchy_agent", "conversation_mode", "chat_theme", "briefing_edit") if not feats.get(k)]
        line(not need, "player features: " + ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in feats.items()),
             "needs a newer Ania Player release for: " + ", ".join(need))
    others = hypr.other_rules()
    if others and not paths.hypr_rules.exists() and not hypr.has_include():
        line(True, f"Hyprland rules: your own ({', '.join(others)})")
    else:
        line(hypr.rules_current(), f"Hyprland rules {paths.hypr_rules}", "omaania setup")
        line(hypr.has_include(), f"hyprland.lua loads them ({hypr.INCLUDE})", "omaania setup")
        for other in others:
            line(False, f"second rule file for the player: {other}", "keep one of them")
    unit = paths.unit_file.exists()
    line(unit, f"systemd unit {paths.unit_file}", "omaania setup")
    if unit:
        r = systemctl("is-active", UNIT_NAME)
        state = (r.stdout.strip() if r else "unknown (sandbox)")
        line(state in ("active", "unknown (sandbox)"), f"aniaplayer.service {state}",
             f"journalctl --user -u {UNIT_NAME}")
    model = assets.wake_id()
    line((paths.player_wake_dir / model / "manifest.json").is_file(), f"wake word {model}",
         "not published yet, or run: omaania setup")
    vc = read_json(paths.voice_config)
    ag, ww = vc.get("agent", {}), vc.get("wake_word", {})
    line(bool(vc), f"voice config: brain={ag.get('provider', '?')} wake={ww.get('wake_word_enabled')}"
         f" conversation={ag.get('conversation_mode', '?')} chat={vc.get('chat', {}).get('theme', '?')}")
    agent = default_agent()
    line(bool(agent), f"omarchy default agent: {agent or 'none'}", "omarchy default agent <name>")
    line(bool(shutil.which("bsdtar")), "bsdtar (unpacks the .deb)", "omarchy-pkg-add libarchive")
    line(True, f"npx for {MCP_PACKAGE}: {'yes' if shutil.which('npx') else 'no (optional)'}")
    legacy = os.path.expanduser("~/.config/autostart/aniaplayer.desktop")
    if os.path.exists(legacy) and unit:
        line(False, f"{legacy} starts a second player at login", "remove it")
    print("  missing aniaplayer verbs (TODO upstream): " + "; ".join(MISSING_VERBS))
    print("All good." if not bad else f"{bad} item(s) to look at.")
    if rec.get("setup_at"):
        print(f"Setup last ran {rec['setup_at']}.")
    return 0 if not bad else 1


def main(argv=None) -> int:
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser(prog="omaania",
                                description="Ania Player for Omarchy (unofficial community plugin)")
    p.add_argument("--version", action="version", version=f"omaania {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="player state (for the bar widget: --json)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("setup", help="install and configure Ania Player (idempotent)")
    s.add_argument("--yes", action="store_true", help="accept the defaults without asking")
    s.add_argument("--update", action="store_true", help="re-download the latest release")
    s.add_argument("--force", action="store_true", help="install even if another Ania Player is present")
    s.add_argument("--deb", help="install this local AniaPlayerSetup.deb instead of downloading")
    s.add_argument("--sha256", help="expected sha256 of --deb")
    s.add_argument("--sums", help="SHA256SUMS.txt to check --deb against")
    s.add_argument("--tag", help="release tag to record for --deb")
    s.add_argument("--brain", choices=("omarchy-agent", "own-key"))
    s.add_argument("--api-base", help="own key: OpenAI-compatible base URL (key from the prompt or OMAANIA_API_KEY)")
    s.add_argument("--api-model", help="own key: model name")
    s.add_argument("--no-hypr", action="store_true")
    s.add_argument("--no-wake", action="store_true")
    s.add_argument("--no-service", action="store_true")
    s.add_argument("--no-autostart", action="store_true")
    s.add_argument("--no-start", action="store_true")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--mcp", dest="mcp", action="store_const", const=True, default=None,
                   help=f"give your agent the Ania tools ({MCP_PACKAGE})")
    g.add_argument("--no-mcp", dest="mcp", action="store_const", const=False)

    s = sub.add_parser("open-setup", help="run setup in a floating terminal")
    s.set_defaults(fn=cmd_open_setup)

    s = sub.add_parser("uninstall", help="remove everything setup added")
    s.add_argument("--yes", action="store_true")
    s.add_argument("--purge", action="store_true", help="also delete the player's own settings and downloads")

    for name, hlp in (("show", "show the avatar (starts the player if needed)"),
                      ("hide", "hide the avatar"), ("toggle", "show/hide"),
                      ("lock", "lock the avatar's position (aniaplayer block)"),
                      ("unlock", "unlock the position (aniaplayer unblock)"),
                      ("quit", "close the player")):
        s = sub.add_parser(name, help=hlp)
        if name in ("lock", "unlock", "show", "hide"):
            s.add_argument("--all", action="store_true", help="every open avatar window")
        s.set_defaults(fn=cmd_verb(name))
    s = sub.add_parser("settings", help="open a player settings window")
    s.add_argument("page", nargs="?", default="voice", choices=("voice", "avatar", "plugins", "hotkeys", "startup"))
    s.set_defaults(fn=cmd_verb("settings"))
    s = sub.add_parser("start", help="start the player")
    s.set_defaults(fn=cmd_start)
    s = sub.add_parser("avatars", help="list .ania avatars on this computer")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_avatars)
    s = sub.add_parser("avatar", help="switch to this .ania avatar")
    s.add_argument("file")
    s.set_defaults(fn=cmd_avatar)
    s = sub.add_parser("open", help="open an aniamodels.shop page")
    s.add_argument("what", choices=sorted(URLS))
    s.add_argument("--print", action="store_true", help="print the URL instead of opening it")
    s.set_defaults(fn=cmd_open)
    s = sub.add_parser("biometric", help="face unlock (opt-in, local): on | off | setup | status")
    s.add_argument("action", choices=("on", "off", "setup", "status"))
    s.set_defaults(fn=cmd_biometric)
    s = sub.add_parser("briefing", help="spoken briefing after login: edit | preview | on | off")
    s.add_argument("action", choices=("edit", "preview", "on", "off"))
    s.set_defaults(fn=cmd_briefing)
    s = sub.add_parser("logs", help="player logs (journalctl)")
    s.add_argument("-f", "--follow", action="store_true")
    s.add_argument("--open", action="store_true", help="open in a terminal window")
    s.set_defaults(fn=cmd_logs)
    s = sub.add_parser("doctor", help="check the installation")
    s.set_defaults(fn=cmd_doctor)

    a = p.parse_args(argv)
    if a.cmd == "setup":
        from .setup import run_setup
        return run_setup(a)
    if a.cmd == "uninstall":
        from .setup import run_uninstall
        return run_uninstall(a)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
