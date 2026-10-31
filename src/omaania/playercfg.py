# SPDX-License-Identifier: Apache-2.0
"""Defaults for a fresh Ania Player, written into the player's own config.

Rule: omaania only fills keys that are MISSING. A value you (or the player's
settings window) already saved is never overwritten, so running setup again
is safe. Every key omaania adds is listed in the install record, and the
player ignores keys it does not know, so keys meant for a newer player do no
harm on an older one; see `features()` for what the installed build reads.

Key names come from Ania Player's voice_config.py (VoiceConfig dataclasses)
and the biometria plugin's store.py.
"""
from __future__ import annotations

import json
from pathlib import Path

from .paths import paths
from .util import atomic_write, read_json

VOICE_PROMPT = ("You are answering BY VOICE, through a talking avatar on the user's desktop. "
                "Answer in the user's language in two or three short sentences, with no markdown, "
                "lists, emoji or code blocks: the text goes straight to speech.")


def voice_defaults(brain: str, feats: dict, wake_ready: bool, wake_model: str,
                   own: dict | None = None) -> dict:
    """{section: {key: value}} for voice_config.json."""
    agent: dict = {}
    if brain == "own-key" and own:
        agent.update(provider="openai", base_url=own["base_url"], model=own["model"],
                     send_system_prompt=True, system_prompt=VOICE_PROMPT)
        if feats.get("api_key_file"):
            agent["api_key_file"] = str(paths.api_key_file)
        else:                       # older player: it moves the key to the OS keyring on load
            agent["api_key"] = own["key"]
    elif feats.get("omarchy_agent") and feats.get("agent_stdin"):
        agent["provider"] = "omarchy-agent"
    # Unknown to older players (ignored there); read by the feat/omarchy-ux build.
    agent["conversation_mode"] = "until_dismissed"

    wake: dict = {"keyboard_enabled": True}
    if wake_ready:
        wake.update(engine="wakeword_openwakeword", model_name=wake_model,
                    wake_word_enabled=True, mode="both", confirm_mode="local")
    return {
        "agent": agent,
        "wake_word": wake,
        # English first: the player ships pt-BR defaults.
        "tts": {"voice_locale": "en-US", "follow_central_language": False},
        "stt": {"language": "en"},
        "chat": {"theme": "auto"},
    }


def merge_missing(path: Path, sections: dict) -> tuple[list[str], bool]:
    """Fill missing keys of a sectioned JSON file. Returns (keys added, created)."""
    created = not path.exists()
    data = read_json(path)
    added = []
    for sec, vals in sections.items():
        cur = data.get(sec)
        if not isinstance(cur, dict):
            cur = {}
            data[sec] = cur
        for k, v in vals.items():
            if k not in cur:
                cur[k] = v
                added.append(f"{sec}.{k}")
    if added or created:
        atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", 0o600)
    return added, created


def set_keys(path: Path, sections: dict) -> list[str]:
    """Overwrite the given keys (used only when the user picks a brain in
    setup: that choice is theirs, so it replaces what is there)."""
    data = read_json(path)
    changed = []
    for sec, vals in sections.items():
        cur = data.setdefault(sec, {})
        for k, v in vals.items():
            if cur.get(k) != v:
                cur[k] = v
                changed.append(f"{sec}.{k}")
    if changed:
        atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", 0o600)
    return changed


def plugin_state_defaults() -> tuple[list[str], bool]:
    """Ask the player to start its voice assistant (installs its speech
    models on first run from the player's own settings)."""
    created = not paths.plugins_state.exists()
    data = read_json(paths.plugins_state)
    va = data.get("voice_assistant")
    if not isinstance(va, dict):
        va = {}
        data["voice_assistant"] = va
    added = []
    if "auto_start" not in va:
        va["auto_start"] = True
        added.append("voice_assistant.auto_start")
    if added or created:
        atomic_write(paths.plugins_state, json.dumps(data, indent=2) + "\n", 0o600)
    return added, created


def write_api_key(key: str) -> None:
    atomic_write(paths.api_key_file, key.strip() + "\n", 0o600)


def remove_keys(path: Path, dotted: list[str]) -> int:
    """Undo merge_missing: drop keys omaania added (if still present)."""
    data = read_json(path)
    if not data:
        return 0
    n = 0
    for d in dotted:
        sec, _, key = d.partition(".")
        if isinstance(data.get(sec), dict) and key in data[sec]:
            del data[sec][key]
            n += 1
            if not data[sec]:
                del data[sec]
    if n:
        atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", 0o600)
    return n


def biometria_flags() -> dict:
    """Read-only view of the biometric unlock / briefing switches."""
    cfg = read_json(paths.biometria_config)
    return {"unlock": bool(cfg.get("unlock_enabled")), "briefing": bool(cfg.get("briefing_enabled")),
            "consent": bool(cfg.get("consent"))}
