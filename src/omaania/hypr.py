# SPDX-License-Identifier: Apache-2.0
"""Hyprland rules for the avatar and chat windows.

Omarchy 4 configures Hyprland in Lua. Its only auto-loaded folder
(~/.local/state/omarchy/toggles/hypr) is Omarchy's own state for its toggle
commands, so omaania does not put files there. Instead the rules live in
their own file, ~/.config/hypr/omaania.lua, and hyprland.lua gets exactly one
line, `pcall(require, "hypr.omaania")` (the Lua form of `source =`). pcall
keeps Hyprland happy if you delete the file and forget the line.
"""
from __future__ import annotations

import shutil
import subprocess

from .paths import REPO_DIR, paths
from .util import atomic_write

TEMPLATE = REPO_DIR / "hypr" / "omaania.lua"
INCLUDE = 'pcall(require, "hypr.omaania")'
INCLUDE_LINE = INCLUDE + "  -- omaania: Ania Player window rules (hypr/omaania.lua)"


def rules_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def rules_current() -> bool:
    try:
        return paths.hypr_rules.read_text(encoding="utf-8") == rules_text()
    except OSError:
        return False


def has_include() -> bool:
    try:
        return any(l.strip().startswith(INCLUDE) for l in paths.hypr_main.read_text().splitlines())
    except OSError:
        return False


def install() -> tuple[bool, bool, str]:
    """Write the rules file and the include line.
    Returns (rules_written, include_added, note)."""
    if not paths.hypr_main.is_file():
        legacy = paths.hypr_dir / "hyprland.conf"
        note = ("found hyprland.conf but no hyprland.lua: omaania supports Omarchy 4 (Lua config) only"
                if legacy.is_file() else "no ~/.config/hypr/hyprland.lua (is this Omarchy 4?)")
        return False, False, note
    wrote = False
    if not rules_current():
        atomic_write(paths.hypr_rules, rules_text())
        wrote = True
    added = False
    if not has_include():
        text = paths.hypr_main.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            text += "\n"
        atomic_write(paths.hypr_main, text + INCLUDE_LINE + "\n")
        added = True
    return wrote, added, ""


def remove_include() -> bool:
    try:
        text = paths.hypr_main.read_text(encoding="utf-8")
    except OSError:
        return False
    lines = text.split("\n")
    keep = [l for l in lines if not l.strip().startswith(INCLUDE)]
    if keep == lines:
        return False
    atomic_write(paths.hypr_main, "\n".join(keep))
    return True


def reload() -> str:
    """hyprctl reload + configerrors, only inside a live Hyprland session."""
    import os
    if os.environ.get("OMAANIA_SANDBOX", "") == "1":
        return ""
    if not shutil.which("hyprctl") or not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return ""
    subprocess.run(["hyprctl", "reload"], capture_output=True)
    r = subprocess.run(["hyprctl", "configerrors"], capture_output=True, text=True)
    errs = [l for l in (r.stdout or "").splitlines() if l.strip() and "no errors" not in l.lower()]
    return "; ".join(errs)


def other_rules() -> list[str]:
    """Other Ania Player rule files (e.g. from an earlier manual install)."""
    out = []
    for p in sorted(paths.hypr_dir.glob("*.lua")):
        if p in (paths.hypr_rules, paths.hypr_main):
            continue
        try:
            if "Ania Player Chat" in p.read_text(errors="replace") or "^Ania Player$" in p.read_text(errors="replace"):
                out.append(str(p))
        except OSError:
            pass
    return out
