# SPDX-License-Identifier: Apache-2.0
"""Every path omaania reads or writes, in one place. Stdlib only.

Paths follow the XDG variables, so tests (and careful users) can point them
at a scratch folder. Two exceptions mirror Ania Player itself:
  * the player keeps its plugin configs under ~/.config/aniaplayer/plugins
    (it does not read XDG_CONFIG_HOME there), and
  * Omarchy's Hyprland bootstrap loads Lua modules from ~/.config (HOME, not
    XDG_CONFIG_HOME).
"""
from __future__ import annotations

import os
from pathlib import Path

APP = "omaania"
PLUGIN_ID = "io.github.rob-d3v.omaania"
PLAYER_REPO = "rob-d3v/ania-player"
DEB_ASSET = "AniaPlayerSetup.deb"
SUMS_ASSET = "SHA256SUMS.txt"
MCP_PACKAGE = "ania-mcp@0.1.2"
UNIT_NAME = "aniaplayer.service"
UNIT_MARKER = "# managed-by: omaania"


def _xdg(var: str, default: str) -> Path:
    raw = (os.environ.get(var) or "").strip()
    return Path(raw) if raw and os.path.isabs(raw) else Path.home() / default


def home() -> Path:
    return Path.home()


def config_home() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def data_home() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share")


def state_home() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state")


def cache_home() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache")


def runtime_dir() -> Path:
    raw = (os.environ.get("XDG_RUNTIME_DIR") or "").strip()
    return Path(raw) if raw else Path(f"/run/user/{os.getuid()}")


REPO_DIR = Path(__file__).resolve().parents[2]          # plugin checkout root
CLI = REPO_DIR / "bin" / APP


class P:
    """Resolved lazily so a test can change HOME/XDG_* before using them."""

    # ---- omaania's own files
    @property
    def config_dir(self) -> Path: return config_home() / APP
    @property
    def config_file(self) -> Path: return self.config_dir / "config.json"
    @property
    def state_dir(self) -> Path: return state_home() / APP
    @property
    def install_record(self) -> Path: return self.state_dir / "installed.json"
    @property
    def log_file(self) -> Path: return self.state_dir / "omaania.log"
    @property
    def cache_dir(self) -> Path: return cache_home() / APP

    # ---- the player install (generalised from the .deb layout)
    @property
    def opt(self) -> Path: return home() / ".local/opt/ania-player"
    @property
    def share(self) -> Path: return self.opt / "usr/share/aniaplayer"
    @property
    def bin_dir(self) -> Path: return home() / ".local/bin"
    @property
    def launcher(self) -> Path: return self.bin_dir / "aniaplayer"
    @property
    def cli_link(self) -> Path: return self.bin_dir / APP
    @property
    def desktop_file(self) -> Path: return data_home() / "applications/ania-player.desktop"
    @property
    def icon_file(self) -> Path: return data_home() / "icons/hicolor/256x256/apps/aniaplayer.png"

    # ---- systemd --user
    @property
    def unit_dir(self) -> Path: return config_home() / "systemd/user"
    @property
    def unit_file(self) -> Path: return self.unit_dir / UNIT_NAME
    @property
    def unit_wants(self) -> Path:
        return self.unit_dir / "graphical-session.target.wants" / UNIT_NAME

    # ---- Hyprland (Omarchy 4: Lua config, modules resolved from ~/.config)
    @property
    def hypr_dir(self) -> Path: return home() / ".config/hypr"
    @property
    def hypr_main(self) -> Path: return self.hypr_dir / "hyprland.lua"
    @property
    def hypr_rules(self) -> Path: return self.hypr_dir / "omaania.lua"

    # ---- the player's own config (written only where documented below)
    @property
    def player_cfg(self) -> Path: return home() / ".config/aniaplayer"
    @property
    def player_config(self) -> Path: return self.player_cfg / "player_config.json"
    @property
    def plugins_state(self) -> Path: return self.player_cfg / "plugins_state.json"
    @property
    def voice_config(self) -> Path:
        return self.player_cfg / "plugins/voice_assistant/voice_config.json"
    @property
    def player_wake_dir(self) -> Path:
        return self.player_cfg / "plugins/wakeword_openwakeword/models/wake_word"
    @property
    def api_key_file(self) -> Path: return self.player_cfg / "omaania-api.key"
    @property
    def player_data(self) -> Path: return data_home() / "aniaplayer"
    @property
    def avatars_dir(self) -> Path: return self.player_data / "avatars"
    @property
    def biometria_config(self) -> Path: return self.player_data / "biometria/config.json"

    # ---- wake word bundles shared with omawake
    @property
    def shared_wake_dir(self) -> Path:
        # omawake scans ~/.local/share/aniaplayer/wakeword on its own, so a
        # bundle placed here serves both plugins.
        return self.player_data / "wakeword"
    @property
    def omawake_models(self) -> Path: return data_home() / "omawake/models"

    # ---- Omarchy
    @property
    def omarchy_agent_file(self) -> Path: return home() / ".config/omarchy/defaults/agent"


paths = P()
