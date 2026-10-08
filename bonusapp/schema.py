"""Daglig sökning med launchd (macOS egen schemaläggare). Slås på och av från appens Data-sida.

Jobbet ligger i ~/Library/LaunchAgents/se.hedin.freespins.plist och kör verktyg/skanna.py --notis.
Om datorn sover vid den tiden körs sökningen när den vaknar.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from . import lagring

ETIKETT = "se.hedin.freespins"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{ETIKETT}.plist"
PYTHON = "/opt/anaconda3/bin/python3" if Path("/opt/anaconda3/bin/python3").exists() else sys.executable


def _domain() -> str:
    return f"gui/{os.getuid()}"


def aktivt() -> bool:
    return PLIST.exists()


def tid() -> str | None:
    if not PLIST.exists():
        return None
    k = plistlib.loads(PLIST.read_bytes()).get("StartCalendarInterval", {})
    return f"{k.get('Hour', 0):02d}:{k.get('Minute', 0):02d}"


def aktivera(klockslag: str) -> None:
    timme, minut = (int(d) for d in klockslag.split(":"))
    lagring.LOGGAR.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": ETIKETT,
        "ProgramArguments": [PYTHON, str(lagring.ROT / "verktyg" / "skanna.py"), "--notis"],
        "WorkingDirectory": str(lagring.ROT),
        "StartCalendarInterval": {"Hour": timme, "Minute": minut},
        "StandardOutPath": str(lagring.LOGGAR / "schema.log"),
        "StandardErrorPath": str(lagring.LOGGAR / "schema.log"),
        "EnvironmentVariables": {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/anaconda3/bin"},
        "ProcessType": "Background",
    }
    avaktivera()
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps(plist))
    subprocess.run(["launchctl", "bootstrap", _domain(), str(PLIST)], capture_output=True)


def avaktivera() -> None:
    if PLIST.exists():
        subprocess.run(["launchctl", "bootout", _domain(), str(PLIST)], capture_output=True)
        PLIST.unlink()
