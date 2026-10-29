# SPDX-License-Identifier: Apache-2.0
"""Ania Player itself: fetch the release .deb, verify it, unpack it into
~/.local/opt/ania-player and make ~/.local/bin/aniaplayer point there.

Nothing from the download is run here. The .deb is checked against the
release's SHA256SUMS.txt (or the sha256 digest GitHub publishes for the
asset) before it is unpacked, and it is unpacked with bsdtar, which refuses
absolute paths and `..`. No root, no dpkg, no postinst scripts.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from .paths import DEB_ASSET, PLAYER_REPO, SUMS_ASSET, paths
from .util import atomic_write, ok, read_json, sha256, warn

API = "https://api.github.com/repos/{repo}/releases/latest"
UA = {"User-Agent": "omaania (+https://github.com/rob-d3v/omaania)",
      "Accept": "application/vnd.github+json"}
LAUNCHER_MARKER = "# omaania: launcher generated from the Ania Player .deb"
RELEASE_FILE = ".omaania-release.json"


class VerifyError(RuntimeError):
    pass


# ---------------------------------------------------------------- release lookup

def latest_release(repo: str = PLAYER_REPO) -> dict:
    """{tag, deb_url, deb_digest, sums_url} of the latest (non pre-)release."""
    req = urllib.request.Request(API.format(repo=repo), headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        rel = json.load(r)
    out = {"tag": rel.get("tag_name", "?"), "deb_url": None, "deb_digest": None, "sums_url": None}
    for a in rel.get("assets") or []:
        if a.get("name") == DEB_ASSET:
            out["deb_url"] = a.get("browser_download_url")
            out["deb_digest"] = a.get("digest")          # "sha256:<hex>" on new releases
        elif a.get("name") == SUMS_ASSET:
            out["sums_url"] = a.get("browser_download_url")
    if not out["deb_url"]:
        raise RuntimeError(f"{repo} {out['tag']} has no {DEB_ASSET} asset")
    return out


def _https(url: str) -> None:
    if not str(url).startswith("https://"):
        raise VerifyError(f"refusing non-https url: {url}")


def download(url: str, dest: Path, log=print) -> Path:
    _https(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    log(f"  Downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    tmp.replace(dest)
    return dest


def parse_sums(text: str, name: str) -> str | None:
    """sha256 for `name` in a `sha256sum`-style file (`<hex>  <name>`)."""
    for line in text.splitlines():
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(\S+)\s*$", line.strip())
        if m and Path(m.group(2)).name == name:
            return m.group(1).lower()
    return None


def expected_sha(rel: dict, log=print) -> tuple[str | None, str]:
    """(sha256, where it came from). SHA256SUMS.txt wins; GitHub's own asset
    digest is the fallback; (None, ...) when the release publishes neither."""
    if rel.get("sums_url"):
        with tempfile.TemporaryDirectory() as t:
            f = download(rel["sums_url"], Path(t) / SUMS_ASSET, log=lambda *_: None)
            sha = parse_sums(f.read_text(errors="replace"), DEB_ASSET)
        if sha:
            return sha, SUMS_ASSET
    dig = rel.get("deb_digest") or ""
    if dig.startswith("sha256:") and len(dig) == 71:
        return dig[7:].lower(), "GitHub asset digest"
    return None, "none published"


def verify(deb: Path, want: str | None, source: str) -> str:
    got = sha256(deb)
    if want is None:
        warn(f"the release publishes no checksum; sha256 of what was downloaded: {got}")
        warn("compare it with the release page before you trust it")
        return got
    if got != want.lower():
        raise VerifyError(f"checksum mismatch for {deb.name}: got {got}, {source} says {want}")
    ok(f"sha256 verified against {source}: {got[:16]}…")
    return got


# ---------------------------------------------------------------- unpack

def unpack(deb: Path, dest: Path) -> None:
    """ar -> data.tar.* -> dest, with bsdtar (libarchive). The new tree is
    built next to `dest` and swapped in, so a failed unpack leaves the old
    install untouched."""
    if not shutil.which("bsdtar"):
        raise RuntimeError("bsdtar not found (it ships with libarchive on Omarchy)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(dest.parent), prefix=".omaania-deb-") as t:
        t = Path(t)
        r = subprocess.run(["bsdtar", "-xf", str(deb), "-C", str(t)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{deb.name} is not a valid .deb (bsdtar: {r.stderr.strip()[:200]})")
        data = sorted(t.glob("data.tar*"))
        if not data:
            raise RuntimeError(f"{deb.name} is not a .deb (no data.tar.*)")
        root = t / "root"
        root.mkdir()
        subprocess.run(["bsdtar", "-xf", str(data[0]), "-C", str(root)], check=True)
        if not (root / "usr/bin/aniaplayer").is_file() or not (root / "usr/share/aniaplayer").is_dir():
            raise RuntimeError(f"{deb.name} has no usr/bin/aniaplayer: not an Ania Player package")
        new = dest.with_name(dest.name + ".new")
        old = dest.with_name(dest.name + ".old")
        for p in (new, old):
            if p.exists():
                shutil.rmtree(p)
        root.rename(new)
        if dest.exists():
            dest.rename(old)
        new.rename(dest)
        if old.exists():
            shutil.rmtree(old, ignore_errors=True)


def write_release_info(info: dict) -> None:
    atomic_write(paths.opt / RELEASE_FILE, json.dumps(info, indent=2) + "\n")


def release_info() -> dict:
    return read_json(paths.opt / RELEASE_FILE)


# ---------------------------------------------------------------- launcher

def launcher_text() -> str:
    """The .deb's /usr/bin/aniaplayer with /usr/share/aniaplayer pointed at
    ~/.local/opt/ania-player/usr/share/aniaplayer, plus a desktop default:
    ANIAPLAYER_AUDIO_FIX=0 (the packaged launcher otherwise moves the
    default audio sink to HDMI on every start, which is right for a kiosk
    and wrong for a laptop)."""
    src = (paths.opt / "usr/bin/aniaplayer").read_text(encoding="utf-8")
    body = src.replace("/usr/share/aniaplayer", str(paths.share))
    lines = body.split("\n")
    shebang = lines[0] if lines and lines[0].startswith("#!") else "#!/bin/bash"
    rest = lines[1:] if lines and lines[0].startswith("#!") else lines
    header = [shebang, LAUNCHER_MARKER,
              "# Re-generated by `omaania setup`; edits here are overwritten.",
              'export ANIAPLAYER_AUDIO_FIX="${ANIAPLAYER_AUDIO_FIX:-0}"']
    return "\n".join(header + rest)


def launcher_is_ours(p: Path | None = None) -> bool:
    p = p or paths.launcher
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return LAUNCHER_MARKER in f.read(4096)
    except OSError:
        return False


def write_launcher() -> None:
    text = launcher_text()
    atomic_write(paths.launcher, text, 0o755)
    r = subprocess.run(["bash", "-n", str(paths.launcher)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"generated launcher does not parse: {r.stderr.strip()}")


def desktop_text() -> str:
    return ("[Desktop Entry]\nType=Application\nName=Ania Player\n"
            "Comment=Talking desktop avatar and voice assistant\n"
            f"Exec={paths.launcher} %u\nIcon=aniaplayer\nTerminal=false\n"
            "Categories=AudioVideo;Utility;\nMimeType=x-scheme-handler/ania;\n"
            "X-Omaania=1\n")


def icon_source() -> Path | None:
    for size in ("256x256", "512x512", "128x128"):
        p = paths.opt / f"usr/share/icons/hicolor/{size}/apps/aniaplayer.png"
        if p.is_file():
            return p
    return None


# ---------------------------------------------------------------- what this build can do

def runtime_plugins() -> Path:
    return paths.share / "plugins-runtime/ania_player/plugins"


def features(share: Path | None = None) -> dict:
    """Capabilities of the installed player, read from the plugin sources
    the .deb ships (plugins-runtime). Used to decide which config keys mean
    something to this build; keys a build does not know are ignored by it."""
    base = (share / "plugins-runtime/ania_player/plugins") if share else runtime_plugins()
    va = base / "voice_assistant"

    def has(path: Path, needle: str) -> bool:
        try:
            return needle in path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False

    vc = va / "voice_config.py"
    bio = base / "biometria/cli.py"
    return {
        "omarchy_agent": (va / "components/omarchy_agent.py").is_file() or has(vc, '"omarchy-agent"'),
        "conversation_mode": has(vc, "conversation_mode"),
        "chat_theme": has(vc, "theme: str"),
        "api_key_file": has(vc, "api_key_file"),
        "biometria": bio.is_file(),
        "briefing_edit": has(bio, "editar"),
        "briefing_toggle": has(bio, "briefing ligar") or has(bio, "'briefing_on'"),
    }


def installed() -> bool:
    return (paths.share / "AniaPlayer").exists() or (paths.opt / "usr/bin/aniaplayer").is_file()


def external_player() -> str | None:
    """An Ania Player that omaania did not install (system .deb, another
    installer, a source checkout): its launcher path, else None."""
    if paths.launcher.exists() and not launcher_is_ours():
        return str(paths.launcher)
    w = None if os.environ.get("OMAANIA_SANDBOX", "") == "1" else shutil.which("aniaplayer")
    if w and Path(w).resolve() != paths.launcher.resolve() and not launcher_is_ours(Path(w)):
        return w
    return None


def player_cmd() -> str:
    """The `aniaplayer` the widget and CLI should call."""
    if paths.launcher.exists() or os.environ.get("OMAANIA_SANDBOX", "") == "1":
        return str(paths.launcher)
    return shutil.which("aniaplayer") or str(paths.launcher)


def call(*args: str, timeout: float = 5) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run([player_cmd(), *args], capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None


def status_json() -> dict:
    r = call("status", "--json", timeout=4)
    if r is None:
        return {"running": False}
    try:
        data = json.loads((r.stdout or "").strip().splitlines()[-1])
        return data if isinstance(data, dict) else {"running": False}
    except (ValueError, IndexError):
        return {"running": False}


def version() -> str:
    info = release_info()
    if info.get("tag"):
        return str(info["tag"])
    r = call("--version", timeout=8)
    return (r.stdout.strip().splitlines() or ["?"])[-1] if r and r.returncode == 0 else ""


