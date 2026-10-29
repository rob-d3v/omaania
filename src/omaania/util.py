# SPDX-License-Identifier: Apache-2.0
"""Small helpers shared by setup, uninstall and the CLI. Stdlib only."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .paths import paths


class UI:
    """Questions in the setup terminal. --yes answers the default "yes";
    without a terminal every question is skipped (the safe answer)."""

    def __init__(self, assume_yes: bool = False):
        self.yes = assume_yes
        self.tty = sys.stdin.isatty()

    def ask(self, question: str, default: bool = True) -> bool:
        if self.yes:
            print(f"  {question} {'yes' if default else 'no'} (--yes)")
            return default
        if not self.tty:
            print(f"  {question} skipped (no terminal; re-run with --yes)")
            return False
        hint = "[Y/n]" if default else "[y/N]"
        try:
            ans = input(f"  {question} {hint} ").strip().lower()
        except EOFError:
            return default
        return default if not ans else ans in ("y", "yes")

    def choose(self, question: str, options: list[tuple[str, str]], default: str) -> str:
        if self.yes or not self.tty:
            return default
        print(f"  {question}")
        for i, (key, label) in enumerate(options, 1):
            mark = " (default)" if key == default else ""
            print(f"    {i}) {label}{mark}")
        try:
            ans = input("  Choose a number: ").strip()
        except EOFError:
            return default
        if ans.isdigit() and 1 <= int(ans) <= len(options):
            return options[int(ans) - 1][0]
        return default


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def warn(msg: str) -> None:
    print(f"  ! {msg}")


def head(msg: str) -> None:
    print(f"\n{msg}")


def atomic_write(path: Path, text: str, mode: int | None = None) -> None:
    """Write next to the target and rename into place (Hyprland and the
    shell watch some of these files and must never see half of one)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".omaania-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if mode is not None:
            os.chmod(tmp, mode)
        elif path.exists():
            shutil.copymode(path, tmp)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def systemctl(*args: str) -> subprocess.CompletedProcess | None:
    """`systemctl --user ...`. OMAANIA_SANDBOX=1 turns every call into a
    no-op (tests run with a scratch HOME and must never reach the real
    user manager)."""
    if os.environ.get("OMAANIA_SANDBOX", "") == "1" or not shutil.which("systemctl"):
        return None
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def default_agent() -> str:
    """`omarchy default agent` (codex, claude, opencode, ...), or ""."""
    try:
        r = subprocess.run(["omarchy-default-agent"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().split()[0]
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        return paths.omarchy_agent_file.read_text().split()[0]
    except (OSError, IndexError):
        return ""


# ---------------------------------------------------------------- install record
# Everything setup adds is written down in ~/.local/state/omaania/installed.json,
# so `omaania uninstall` removes exactly that and nothing else.

class Record:
    def __init__(self):
        self.data = read_json(paths.install_record)
        self.data.setdefault("schema", 1)
        self.data.setdefault("files", {})        # path -> {"created": bool, "kind": ...}
        self.data.setdefault("player_keys", {})  # config file -> [dotted keys we set]

    def add(self, path: Path, kind: str, created: bool = True, **extra) -> None:
        key = str(path)
        prev = self.data["files"].get(key)
        if prev is not None:
            # A second setup must not forget that the first one created it.
            created = prev.get("created", created)
        self.data["files"][key] = {"kind": kind, "created": created, **extra}

    def get(self, path: Path) -> dict | None:
        return self.data["files"].get(str(path))

    def owns(self, path: Path) -> bool:
        e = self.get(path)
        return bool(e and e.get("created"))

    def drop(self, path: Path) -> None:
        self.data["files"].pop(str(path), None)

    def set(self, key: str, value) -> None:
        self.data[key] = value

    def save(self) -> None:
        atomic_write(paths.install_record, json.dumps(self.data, indent=2, sort_keys=True) + "\n", 0o600)
