# SPDX-License-Identifier: Apache-2.0
"""Test helpers: a scratch HOME and a tiny fake Ania Player .deb whose
`aniaplayer` only logs its arguments (it never reaches a real player)."""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "bin" / "omaania"

FAKE_LAUNCHER = """#!/bin/bash
# Ania Player - Wrapper script (test double)
for _envfile in "$HOME/.config/aniaplayer/aniaplayer.env" "/usr/share/aniaplayer/aniaplayer.env"; do :; done
cd /usr/share/aniaplayer 2>/dev/null || true
echo "$*" >> "$HOME/aniaplayer-calls.log"
case "$1" in
  status) echo '{"status": "success", "running": true, "visible": false, "blocked": true, "tts_active": false, "va_session": false, "name": "Test"}' ;;
  --version) echo "Ania Player 0.0.0-test" ;;
esac
exit 0
"""


def _ar(members: list[tuple[str, bytes]]) -> bytes:
    out = io.BytesIO()
    out.write(b"!<arch>\n")
    for name, data in members:
        hdr = f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n"
        out.write(hdr.encode())
        out.write(data)
        if len(data) % 2:
            out.write(b"\n")
    return out.getvalue()


def _tgz(files: dict[str, tuple[bytes, int]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, (data, mode) in files.items():
            ti = tarfile.TarInfo("./" + name)
            ti.size, ti.mode = len(data), mode
            t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def fake_deb(dest: Path, *, features: bool = False) -> str:
    """Write a fake AniaPlayerSetup.deb; returns its sha256."""
    vc = b"class AgentConfig:\n    api_key_file: str = ''\n"
    if features:
        vc += b'    conversation_mode: str = "followup"\n    theme: str = "auto"\n'
    files = {
        "usr/bin/aniaplayer": (FAKE_LAUNCHER.encode(), 0o755),
        "usr/share/aniaplayer/AniaPlayer": (b"\x7fELF-not-really", 0o755),
        "usr/share/aniaplayer/aniaplayer.env": (b"ANIA_API_URL=https://example.invalid/api\n", 0o644),
        "usr/share/icons/hicolor/256x256/apps/aniaplayer.png": (b"\x89PNG fake", 0o644),
        "usr/share/aniaplayer/plugins-runtime/ania_player/plugins/voice_assistant/voice_config.py": (vc, 0o644),
        "usr/share/aniaplayer/plugins-runtime/ania_player/plugins/biometria/cli.py": (b"# briefing editar\n", 0o644),
    }
    if features:
        files["usr/share/aniaplayer/plugins-runtime/ania_player/plugins/voice_assistant/components/omarchy_agent.py"] = (b"#\n", 0o644)
    data = _ar([("debian-binary", b"2.0\n"), ("control.tar.gz", _tgz({"control": (b"Package: aniaplayer\n", 0o644)})),
                ("data.tar.gz", _tgz(files))])
    dest.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


class Sandbox:
    """A throwaway HOME with an Omarchy-like hyprland.lua."""

    HYPR = '-- user config\nrequire("default.hypr.omarchy")\nrequire("hypr.bindings")\n'

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="omaania-test-")
        self.home = Path(self._tmp.name)
        (self.home / ".config/hypr").mkdir(parents=True)
        (self.home / ".config/hypr/hyprland.lua").write_text(self.HYPR)
        (self.home / "run").mkdir(mode=0o700)

    def env(self, **extra) -> dict:
        env = {"HOME": str(self.home), "XDG_RUNTIME_DIR": str(self.home / "run"),
               "OMAANIA_SANDBOX": "1", "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}
        env.update(extra)
        return env

    def run(self, *args: str, **extra) -> subprocess.CompletedProcess:
        return subprocess.run([str(CLI), *args], env=self.env(**extra), capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=120)

    def calls(self) -> list[str]:
        p = self.home / "aniaplayer-calls.log"
        return p.read_text().splitlines() if p.exists() else []

    def files(self) -> set[str]:
        out = set()
        for root, _dirs, names in os.walk(self.home):
            for n in names:
                rel = os.path.relpath(os.path.join(root, n), self.home)
                if not rel.startswith(".cache/omaania/pycache") and rel != "aniaplayer-calls.log":
                    out.add(rel)
        return out

    def close(self):
        self._tmp.cleanup()
