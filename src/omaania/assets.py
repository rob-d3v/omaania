# SPDX-License-Identifier: Apache-2.0
"""Data files omaania places for the player: the "Hey Omarchy" wake word
bundle (shared with omawake) and the default avatar slot. Data only: ONNX,
JSON and .ania files, never code. Stdlib only."""
from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from .paths import REPO_DIR, paths
from .util import sha256

CATALOG = REPO_DIR / "models.json"


def catalog() -> dict:
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _is_bundle(d: Path) -> bool:
    return (d / "manifest.json").is_file()


def wake_id() -> str:
    return str(catalog().get("wake_word", {}).get("id", "hey_omarchy"))


def wake_phrase() -> str:
    return str(catalog().get("wake_word", {}).get("phrase", "Hey Omarchy"))


def wake_published() -> bool:
    return catalog().get("wake_word", {}).get("status") == "available"


def find_wake_bundle(model: str | None = None) -> tuple[Path | None, str]:
    """Where a usable bundle already is: (path, label)."""
    model = model or wake_id()
    for d, label in ((paths.player_wake_dir / model, "already in Ania Player"),
                     (paths.shared_wake_dir / model, "shared folder"),
                     (paths.omawake_models / model, "from omawake")):
        if _is_bundle(d):
            return d, label
    return None, ""


def _fetch(url: str, sha: str, dest: Path) -> None:
    if not str(url).startswith("https://") or not sha:
        raise RuntimeError(f"refusing {url}: needs an https url and a pinned sha256")
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "omaania"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    got = sha256(tmp)
    if got != sha:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"checksum mismatch for {url}: {got} != {sha}")
    tmp.replace(dest)


def download_wake_bundle(log=print) -> Path:
    """Fetch the catalog bundle into the shared folder (omawake reads it too)."""
    e = catalog().get("wake_word") or {}
    if e.get("status") != "available":
        raise RuntimeError(f"“{e.get('phrase', 'Hey Omarchy')}” is not published yet ({e.get('status')})")
    model = e["id"]
    paths.shared_wake_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(paths.shared_wake_dir)) as t:
        arc = Path(t) / "bundle.tar.gz"
        log(f"  Downloading {e['url']}")
        _fetch(e["url"], e.get("sha256"), arc)
        out = Path(t) / "x"
        with tarfile.open(arc, "r:gz") as tf:
            tf.extractall(out, filter="data")
        cands = [p.parent for p in out.rglob("manifest.json")]
        if not cands:
            raise RuntimeError("archive has no manifest.json")
        src = min(cands, key=lambda p: len(p.parts))
        dest = paths.shared_wake_dir / model
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(src), dest)
        ver = src.parent / (src.name + ".verifier")
        if ver.is_dir():
            vdest = paths.shared_wake_dir / (model + ".verifier")
            if vdest.exists():
                shutil.rmtree(vdest)
            shutil.move(str(ver), vdest)
    return dest


def install_wake_bundle(src: Path, model: str) -> list[Path]:
    """Copy a bundle (and its .verifier sidecar) into the player's wake word
    folder. Replaced whole, never merged; the player re-checks the bundle's
    checksums and self-test when it loads it. Returns the paths written."""
    written = []
    for s, name in ((src, model), (src.parent / (src.name + ".verifier"), model + ".verifier")):
        if not s.is_dir():
            continue
        dest = paths.player_wake_dir / name
        if dest.resolve() == s.resolve():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(s, dest, ignore=shutil.ignore_patterns("__pycache__"))
        written.append(dest)
    return written


# ---------------------------------------------------------------- avatars

def default_avatar() -> dict:
    return catalog().get("default_avatar") or {}


def avatar_files() -> list[str]:
    """.ania files the player knows about: its recents, then the avatars folder."""
    out: list[str] = []
    try:
        cfg = json.loads(paths.player_config.read_text(encoding="utf-8"))
        out += [str(x) for x in (cfg.get("recent_files") or []) if isinstance(x, str)]
    except (OSError, ValueError):
        pass
    if paths.avatars_dir.is_dir():
        out += [str(p) for p in sorted(paths.avatars_dir.glob("*.ania"))]
    seen, keep = set(), []
    for f in out:
        if f not in seen and Path(f).is_file():
            seen.add(f)
            keep.append(f)
    return keep
