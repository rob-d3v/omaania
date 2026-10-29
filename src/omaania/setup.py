# SPDX-License-Identifier: Apache-2.0
"""`omaania setup` / `omaania uninstall`. Idempotent; stdlib only.

What setup may add (all of it recorded in ~/.local/state/omaania/installed.json):
  ~/.local/opt/ania-player/            the unpacked release .deb
  ~/.local/bin/aniaplayer              launcher pointing at it
  ~/.local/bin/omaania                 symlink to this plugin's bin/omaania
  ~/.local/share/applications/ania-player.desktop, the app icon
  ~/.config/hypr/omaania.lua           window rules + ONE line in hyprland.lua
  ~/.config/systemd/user/aniaplayer.service (+ its wants link when autostart is on)
  ~/.config/aniaplayer/...             only MISSING keys of the player's config,
                                       the wake word bundle, the API key file
                                       (if you choose your own key)
No sudo, no package manager, nothing outside your home folder.
"""
from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from . import assets, hypr, player, playercfg
from .paths import CLI, MCP_PACKAGE, PLUGIN_ID, UNIT_MARKER, UNIT_NAME, cache_home, paths, state_home
from .util import UI, Record, atomic_write, default_agent, head, ok, read_json, systemctl, warn

STEPS = 8

# omarchy default agent -> `ania-mcp install <client>` (clients ania-mcp 0.1.0 knows).
MCP_CLIENTS = {"claude": "claude-code", "gemini": "gemini", "cursor-agent": "cursor"}
MCP_URL = "https://mcp.aniamodels.shop/mcp/ania"

UNIT = """[Unit]
{marker} (https://github.com/rob-d3v/omaania). `omaania uninstall` removes it.
Description=Ania Player: talking desktop avatar and voice assistant
PartOf=graphical-session.target
After=graphical-session.target pipewire.service

[Service]
Type=simple
ExecStart="{bin}" --service
ExecStop="{bin}" quit
Environment=ANIAPLAYER_AUDIO_FIX=0
Restart=on-failure
RestartSec=5
TimeoutStopSec=15

[Install]
WantedBy=graphical-session.target
"""


def sandboxed() -> bool:
    return os.environ.get("OMAANIA_SANDBOX", "") == "1"


def unit_is_ours() -> bool:
    try:
        return UNIT_MARKER in paths.unit_file.read_text(encoding="utf-8")
    except OSError:
        return False


def load_settings() -> dict:
    return read_json(paths.config_file)


def save_settings(changes: dict) -> dict:
    cur = load_settings()
    cur.update(changes)
    atomic_write(paths.config_file, json.dumps(cur, indent=2) + "\n", 0o600)
    return cur


# ---------------------------------------------------------------- steps

def _step(n: int, title: str) -> None:
    head(f"{n}/{STEPS} {title}")


def step_player(ui: UI, rec: Record, o) -> bool:
    _step(1, "Ania Player")
    ext = player.external_player()
    if ext and not o.force:
        ok(f"using the Ania Player already installed at {ext} (omaania leaves it alone)")
        rec.set("player", "external")
        rec.set("external_launcher", ext)
        return True
    info = player.release_info()
    if player.installed() and info and not o.update and not o.deb:
        ok(f"Ania Player {info.get('tag', '?')} in {paths.opt} (omaania update: setup --update)")
        rec.set("player", "omaania")
        rec.data.pop("external_launcher", None)
        return True
    try:
        if o.deb:
            deb = Path(o.deb).expanduser().resolve()
            want, source = (o.sha256, "--sha256") if o.sha256 else (None, "none given")
            if not want and o.sums:
                want = player.parse_sums(Path(o.sums).read_text(errors="replace"), player.DEB_ASSET)
                source = Path(o.sums).name
            tag, url = o.tag or "local", str(deb)
        else:
            print("  Looking up the latest release of rob-d3v/ania-player…")
            rel = player.latest_release()
            tag, url = rel["tag"], rel["deb_url"]
            want, source = player.expected_sha(rel)
            deb = player.download(url, paths.cache_dir / f"AniaPlayerSetup-{tag}.deb")
        got = player.verify(deb, want, source)
        print(f"  Unpacking into {paths.opt}…")
        player.unpack(deb, paths.opt)
        player.write_release_info({"tag": tag, "url": url, "sha256": got, "checksum_source": source,
                                   "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        if not o.deb and deb.parent == paths.cache_dir:
            deb.unlink(missing_ok=True)
        rec.add(paths.opt, "player")
        rec.set("player", "omaania")
        rec.data.pop("external_launcher", None)
        ok(f"Ania Player {tag} installed in {paths.opt}")
        return True
    except Exception as e:  # noqa: BLE001 - every failure becomes one clear line
        warn(f"could not install Ania Player: {e}")
        return False


def step_launcher(rec: Record) -> bool:
    _step(2, "Launcher, app menu entry and command line")
    if rec.data.get("player") == "external":
        ok("skipped: your own Ania Player keeps its launcher")
    else:
        try:
            existed = paths.launcher.exists()
            player.write_launcher()
            rec.add(paths.launcher, "launcher", created=not existed or rec.owns(paths.launcher))
            ok(f"{paths.launcher}")
            existed = paths.desktop_file.exists()
            if not existed or "X-Omaania=1" in paths.desktop_file.read_text(errors="replace"):
                atomic_write(paths.desktop_file, player.desktop_text())
                rec.add(paths.desktop_file, "desktop", created=not existed or rec.owns(paths.desktop_file))
                ok(f"app menu entry {paths.desktop_file.name}")
            else:
                warn(f"{paths.desktop_file} exists and is not ours; left alone")
            icon = player.icon_source()
            if icon:
                existed = paths.icon_file.exists()
                paths.icon_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(icon, paths.icon_file)
                rec.add(paths.icon_file, "icon", created=not existed or rec.owns(paths.icon_file))
        except Exception as e:  # noqa: BLE001
            warn(f"launcher: {e}")
            return False
    link = paths.cli_link
    if link.is_symlink() and Path(os.readlink(link)) == CLI:
        ok(f"{link} -> {CLI}")
    elif link.exists() or link.is_symlink():
        warn(f"{link} exists and is not ours; leaving it alone")
    else:
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(CLI)
        rec.add(link, "cli-link")
        ok(f"linked {link}")
    return True


def step_hypr(rec: Record, o) -> bool:
    _step(3, "Hyprland window rules")
    if o.no_hypr:
        ok("skipped (--no-hypr)")
        return True
    existed = paths.hypr_rules.exists()
    wrote, added, note = hypr.install()
    if note:
        warn(note)
        return False
    if wrote:
        rec.add(paths.hypr_rules, "hypr-rules", created=not existed or rec.owns(paths.hypr_rules))
    elif rec.get(paths.hypr_rules) is None:
        rec.add(paths.hypr_rules, "hypr-rules", created=True)
    if added:
        rec.set("hypr_include", True)
    ok(f"{paths.hypr_rules} ({'updated' if wrote else 'current'})")
    ok(f"hyprland.lua loads it with: {hypr.INCLUDE}" + (" (added)" if added else ""))
    for other in hypr.other_rules():
        warn(f"another Ania Player rule file exists: {other} (both apply; remove one if windows misbehave)")
    errs = hypr.reload()
    if errs:
        warn(f"hyprctl configerrors: {errs}")
    return True


def step_wake(rec: Record, o) -> tuple[bool, str]:
    _step(4, "Wake word “Hey Omarchy”")
    model = assets.wake_id()
    if o.no_wake:
        ok("skipped (--no-wake): the keyboard shortcut ctrl+shift+space still talks to the avatar")
        return False, model
    src, label = assets.find_wake_bundle(model)
    if src is None:
        try:
            src = assets.download_wake_bundle()
            rec.add(src, "wake-bundle-shared")
            label = "downloaded"
        except Exception as e:  # noqa: BLE001
            warn(f"{e}")
            warn("until then the assistant answers the keyboard shortcut (ctrl+shift+space)")
            return False, model
    try:
        before = {p: p.exists() for p in (paths.player_wake_dir / model,
                                          paths.player_wake_dir / (model + ".verifier"))}
        for p in assets.install_wake_bundle(src, model):
            rec.add(p, "wake-bundle", created=not before.get(p, False) or rec.owns(p))
        ok(f"{model} ({label}) -> {paths.player_wake_dir / model}")
        return True, model
    except Exception as e:  # noqa: BLE001
        warn(f"could not install the wake word: {e}")
        return False, model


def _own_key(ui: UI, o) -> dict | None:
    base = o.api_base or "https://api.openai.com/v1"
    model = o.api_model or "gpt-4o-mini"
    key = os.environ.get("OMAANIA_API_KEY", "")
    if ui.tty and not ui.yes:
        try:
            base = input(f"  API base URL [{base}]: ").strip() or base
            model = input(f"  Model [{model}]: ").strip() or model
            if not key:
                key = getpass.getpass("  API key (not shown, stored 0600 in ~/.config/aniaplayer): ").strip()
        except EOFError:
            pass
    if not key:
        warn("no API key given (type it in setup, or set OMAANIA_API_KEY for a non-interactive run)")
        return None
    if not base.startswith(("https://", "http://127.", "http://localhost")):
        warn(f"refusing {base}: use https (or a local http://127.0.0.1 / localhost server)")
        return None
    return {"base_url": base, "model": model, "key": key}


def step_assistant(ui: UI, rec: Record, o, wake_ready: bool, wake_model: str) -> bool:
    _step(5, "Voice assistant defaults")
    feats = player.features() if paths.share.is_dir() else {}
    agent = default_agent()
    brain = o.brain or ui.choose(
        "Who answers when you talk to the avatar?",
        [("omarchy-agent", f"My Omarchy default agent ({agent or 'none set yet'})"),
         ("own-key", "Use my own API key (any OpenAI-compatible endpoint)")],
        load_settings().get("brain", "omarchy-agent"))
    own = _own_key(ui, o) if brain == "own-key" else None
    if brain == "own-key" and own is None:
        brain = "omarchy-agent"
    sections = playercfg.voice_defaults(brain, feats, wake_ready, wake_model, own)
    created = not paths.voice_config.exists()
    if own:
        if feats.get("api_key_file"):
            playercfg.write_api_key(own["key"])
            rec.add(paths.api_key_file, "api-key")
        agent_keys = sections.pop("agent")
        changed = playercfg.set_keys(paths.voice_config, {"agent": agent_keys})
        added, _ = playercfg.merge_missing(paths.voice_config, sections)
        added += changed
        ok(f"brain: your own key, {own['model']} at {own['base_url']}")
    else:
        added, _ = playercfg.merge_missing(paths.voice_config, sections)
        if not feats.get("omarchy_agent"):
            warn("this Ania Player build has no “omarchy-agent” brain yet (needs a newer release);"
                 " the player keeps its own brain setting until then")
        else:
            ok(f"brain: your Omarchy default agent ({agent or 'pick one: omarchy default agent <name>'})")
    keys = sorted(set(rec.data["player_keys"].get(str(paths.voice_config), [])) | set(added))
    rec.data["player_keys"][str(paths.voice_config)] = keys
    rec.add(paths.voice_config, "player-config", created=created or rec.owns(paths.voice_config))
    added_ps, created_ps = playercfg.plugin_state_defaults()
    if added_ps:
        rec.data["player_keys"][str(paths.plugins_state)] = sorted(
            set(rec.data["player_keys"].get(str(paths.plugins_state), [])) | set(added_ps))
    rec.add(paths.plugins_state, "player-config", created=created_ps or rec.owns(paths.plugins_state))
    ok(f"{len(added)} missing key(s) filled in {paths.voice_config.name}" if added
       else "player config already set (nothing overwritten)")
    print("    wake word " + (f"on ({wake_model})" if wake_ready else "off until the model is published")
          + " · conversation until you say “that's all” · chat colours follow your Omarchy theme"
          + " · English voice")
    for feat, what in (("conversation_mode", "conversation until dismissed"), ("chat_theme", "chat in Omarchy colours")):
        if feats and not feats.get(feat):
            warn(f"{what}: needs a newer Ania Player release (setting saved for when it arrives)")
    ok("biometric unlock: off · briefing: off (both opt-in from the bar menu)")
    save_settings({"brain": brain})
    return True


def step_avatar(rec: Record) -> bool:
    _step(6, "Default avatar")
    e = assets.default_avatar()
    if e.get("status") == "available" and e.get("url") and e.get("sha256"):
        dest = paths.avatars_dir / e.get("file", "Glyph.ania")
        if not dest.exists():
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                assets._fetch(e["url"], e["sha256"], dest)
                rec.add(dest, "avatar")
            except Exception as ex:  # noqa: BLE001
                warn(f"{e.get('name')}: {ex}")
                return False
        cfg = read_json(paths.player_config)
        if not cfg.get("startup_file"):
            created = not paths.player_config.exists()
            cfg["startup_file"] = str(dest)
            atomic_write(paths.player_config, json.dumps(cfg, indent=4, ensure_ascii=False) + "\n")
            rec.data["player_keys"][str(paths.player_config)] = ["startup_file"]
            rec.add(paths.player_config, "player-config", created=created or rec.owns(paths.player_config))
        ok(f"{e.get('name')} is the startup avatar")
    else:
        ok(f"{e.get('name', 'Glyph')} (free default avatar) is coming soon;"
           " until then Ania Player opens with its own default")
    return True


def step_service(rec: Record, o) -> bool:
    _step(7, "Background service")
    if o.no_service:
        ok("skipped (--no-service); start the player with: aniaplayer")
        return True
    if paths.unit_file.exists() and not unit_is_ours():
        warn(f"{paths.unit_file} exists and is not ours; leaving it alone")
        return True
    existed = paths.unit_file.exists()
    text = UNIT.format(marker=UNIT_MARKER, bin=rec.data.get("external_launcher") or paths.launcher)
    if not existed or paths.unit_file.read_text() != text:
        atomic_write(paths.unit_file, text)
        ok(f"wrote {paths.unit_file}")
    rec.add(paths.unit_file, "unit", created=not existed or rec.owns(paths.unit_file))
    systemctl("daemon-reload")
    autostart = not o.no_autostart
    wants = paths.unit_wants
    if autostart:
        if not (wants.is_symlink() or wants.exists()):
            wants.parent.mkdir(parents=True, exist_ok=True)
            wants.symlink_to(paths.unit_file)
        rec.add(wants, "unit-wants")
        ok("starts with your session (omaania setup --no-autostart to change)")
    else:
        if wants.is_symlink():
            wants.unlink()
        ok("autostart off: start it from the bar icon")
    save_settings({"autostart": autostart})
    legacy = Path.home() / ".config/autostart/aniaplayer.desktop"
    if legacy.exists():
        warn(f"{legacy} also starts the player at login: remove it to avoid two avatars")
    if not o.no_start and not sandboxed():
        r = systemctl("restart", UNIT_NAME)
        if r is not None and r.returncode == 0:
            ok("aniaplayer.service running")
        elif r is not None:
            warn(f"aniaplayer.service did not start: journalctl --user -u {UNIT_NAME}")
    return True


def step_mcp(ui: UI, rec: Record, o) -> bool:
    _step(8, "Ania tools for your AI agent (optional)")
    agent = default_agent()
    client = MCP_CLIENTS.get(agent)
    if o.mcp is False:
        ok("skipped (--no-mcp)")
        return True
    if not client:
        ok(f"{agent or 'your agent'}: not handled by {MCP_PACKAGE} yet; add the MCP server by hand: {MCP_URL}")
        return True
    if not shutil.which("npx"):
        ok(f"needs Node.js (npx) for: npx -y {MCP_PACKAGE} install {client}")
        return True
    want = o.mcp if o.mcp is not None else ui.ask(
        f"Let {agent} create and switch avatars (runs: npx -y {MCP_PACKAGE} install {client})?", False)
    if not want:
        ok(f"not now; later: npx -y {MCP_PACKAGE} install {client}")
        return True
    if sandboxed():
        ok(f"(sandbox) would run: npx -y {MCP_PACKAGE} install {client}")
        rec.set("mcp_client", client)
        return True
    r = subprocess.run(["npx", "-y", MCP_PACKAGE, "install", client])
    if r.returncode == 0:
        rec.set("mcp_client", client)
        ok(f"{agent} has the Ania tools (sign-in opens in your browser the first time)")
        return True
    warn(f"npx -y {MCP_PACKAGE} install {client} failed (exit {r.returncode})")
    return False


def run_setup(o) -> int:
    ui = UI(o.yes)
    rec = Record()
    print("omaania setup (safe to run again)")
    problems = 0
    if not step_player(ui, rec, o):
        rec.save()
        print("\nStopped: Ania Player is needed for the rest. Fix the line above and run setup again.")
        return 1
    for fn in (lambda: step_launcher(rec), lambda: step_hypr(rec, o)):
        problems += 0 if fn() else 1
    wake_ready, model = step_wake(rec, o)
    for fn in (lambda: step_assistant(ui, rec, o, wake_ready, model), lambda: step_avatar(rec),
               lambda: step_service(rec, o), lambda: step_mcp(ui, rec, o)):
        problems += 0 if fn() else 1
    rec.set("setup_version", 1)
    rec.set("setup_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    rec.save()
    print("\nDone." if not problems else f"\nFinished with {problems} item(s) to look at (see ! above).")
    print("Click the avatar icon in the bar to show or hide it."
          + (f" Say “Hey Omarchy” to talk." if wake_ready else " Press ctrl+shift+space to talk."))
    return 0 if not problems else 1


# ---------------------------------------------------------------- uninstall

def _rm(p: Path) -> bool:
    try:
        if p.is_symlink() or p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
        else:
            return False
        return True
    except OSError as e:
        warn(f"could not remove {p}: {e}")
        return False


def run_uninstall(o) -> int:
    ui = UI(o.yes)
    rec = Record()
    files = rec.data.get("files", {})
    print("omaania uninstall")

    if unit_is_ours():
        systemctl("disable", "--now", UNIT_NAME)
        _rm(paths.unit_wants)
        _rm(paths.unit_file)
        systemctl("daemon-reload")
        ok("aniaplayer.service stopped and removed")

    if hypr.remove_include():
        ok("removed the omaania line from hyprland.lua")
    if paths.hypr_rules.exists() and (rec.owns(paths.hypr_rules) or "omaania" in paths.hypr_rules.read_text()):
        _rm(paths.hypr_rules)
        ok(f"removed {paths.hypr_rules}")
    hypr.reload()

    # Player config: drop only the keys omaania added; delete files it created
    # when nothing else is left in them.
    for f, keys in (rec.data.get("player_keys") or {}).items():
        n = playercfg.remove_keys(Path(f), keys)
        if n:
            ok(f"removed {n} key(s) omaania set in {Path(f).name}")
        if rec.owns(Path(f)) and Path(f).exists() and not read_json(Path(f)):
            _rm(Path(f))

    own_player = rec.data.get("player") == "omaania" or player.launcher_is_ours()
    for f, meta in sorted(files.items(), key=lambda kv: -len(kv[0])):
        p = Path(f)
        kind = meta.get("kind")
        if kind in ("unit", "unit-wants", "hypr-rules", "player-config"):
            continue
        if kind in ("player", "launcher") and not own_player:
            continue
        if kind == "wake-bundle-shared" and paths.omawake_models.parent.exists():
            print(f"  · kept {p}: omawake uses it too")
            continue
        if kind == "launcher" and not player.launcher_is_ours(p):
            continue
        if meta.get("created") and _rm(p):
            ok(f"removed {p}")
    if own_player:
        for p in (paths.opt, paths.launcher if player.launcher_is_ours() else None):
            if p and p.exists() and _rm(p):
                ok(f"removed {p}")
    if paths.cli_link.is_symlink() and Path(os.readlink(paths.cli_link)) == CLI:
        _rm(paths.cli_link)

    if rec.data.get("mcp_client"):
        print(f"  · your agent keeps the Ania MCP entry; remove the “ania” server from its"
              f" config to drop it (added by: npx {MCP_PACKAGE} install {rec.data['mcp_client']})")

    leftovers = [p for p in (paths.player_cfg, paths.player_data, cache_home() / "aniaplayer",
                             state_home() / "aniaplayer") if p.exists()]
    if leftovers and own_player:
        purge = o.purge or ui.ask("Also delete Ania Player's own settings and downloads (avatars, voices, logs)?", False)
        if purge:
            for p in leftovers:
                if _rm(p):
                    ok(f"removed {p}")
        else:
            print("  · kept the player's settings and data: " + ", ".join(str(p) for p in leftovers))
    for d in (paths.cache_dir, paths.config_dir, paths.state_dir):
        if d.exists():
            _rm(d)
    print(f"\nTo remove the bar widget too: omarchy plugin remove {PLUGIN_ID}")
    return 0
