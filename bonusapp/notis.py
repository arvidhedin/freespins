"""macOS-notiser via osascript (inget extra att installera)."""

from __future__ import annotations

import subprocess


def _citera(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def skicka(titel: str, text: str, undertitel: str = "") -> bool:
    skript = f"display notification {_citera(text[:240])} with title {_citera(titel)}"
    if undertitel:
        skript += f" subtitle {_citera(undertitel[:120])}"
    try:
        subprocess.run(["osascript", "-e", skript], check=True, capture_output=True, timeout=10)
        return True
    except (OSError, subprocess.SubprocessError):
        return False
