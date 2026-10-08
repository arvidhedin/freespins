"""Filer i data/: register, sökresultat och dina egna markeringar.

Allt sparas lokalt som JSON. data/mina.json (använda kasinon, granskningar, inställningar) får en
kopia i data/backups/ före varje ändring (de 60 senaste behålls), precis som i kurs- och utbytesappen.
Övriga filer skrivs om helt vid varje sökning och kan alltid hämtas på nytt.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
import shutil
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
# FREESPINS_DATA låter testerna (eller du) köra mot en annan datamapp.
DATA = Path(os.environ.get("FREESPINS_DATA", ROT / "data"))

KASINON = DATA / "kasinon.json"      # sammanslaget licensregister: en post per domän
SKANNING = DATA / "skanning.json"    # senaste sökningen per domän (status, lästa sidor, fel)
BONUSAR = DATA / "bonusar.json"      # alla hittade erbjudanden från senaste sökningen
SEDDA = DATA / "sedda.json"          # bonusnyckel -> datum då den först sågs (för "ny"-märkning/notiser)
STATUS = DATA / "status.json"        # pågående sökning: framsteg, för appens förloppsindikator
LAS = DATA / "skanning.las"          # finns medan en sökning pågår
LOGGAR = DATA / "loggar"
SIDCACHE = DATA / "sidcache"         # texten från lästa sidor, för omtolkning utan nätverk
MINA = DATA / "mina.json"
BACKUPS = DATA / "backups"
MAX_BACKUPS = 60

STANDARD = {
    "format": 1,
    "installningar": {
        "rtp": 0.96,                 # antagen återbetalning på slots (för EV)
        "spinvarde": 1.0,            # antaget värde per freespin i kr när villkoren inte säger något
        "visa_1x": False,            # visa erbjudanden där insättningen måste omsättas 1 gång (penningtvätt)
        "max_sidor": 6,              # högst så här många undersidor läses per kasino
        "parallella": 8,             # så många kasinon läses samtidigt
        "chrome_flikar": 6,          # så många Chrome-flikar samtidigt (för sidor som kräver JavaScript)
        "chrome": True,              # rendera JS-tunga sidor med din installerade Chrome (headless)
        "respektera_robots": True,   # hoppa över sidor som robots.txt förbjuder
        "notis_min_ev": 0.0,         # notis bara för nya erbjudanden med minst så här högt EV (kr)
        "schema_tid": "08:00",
    },
    # domän eller "bolag:<id>" -> {"datum", "anteckning"}; ett svenskt bolag ger bonus bara en gång
    "anvanda": {},
    # bonusnyckel -> {"omsattning_pa", "omsattning_x", "godkand", "anteckning", "datum"}
    "granskningar": {},
    "dolda": {},  # bonusnyckel -> datum, för erbjudanden du inte vill se igen
}


def nu() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def las_json(fil: Path, standard=None):
    try:
        return json.loads(fil.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return copy.deepcopy(standard)


def skriv_json(fil: Path, data) -> None:
    fil.parent.mkdir(parents=True, exist_ok=True)
    tmp = fil.with_suffix(fil.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, fil)  # atomiskt, så att appen aldrig läser en halvskriven fil


# ---------------------------------------------------------------------------------------------
# Dina egna uppgifter
# ---------------------------------------------------------------------------------------------


def ladda_mina() -> dict:
    data = las_json(MINA, STANDARD)
    for nyckel, varde in STANDARD.items():
        data.setdefault(nyckel, copy.deepcopy(varde))
    for nyckel, varde in STANDARD["installningar"].items():
        data["installningar"].setdefault(nyckel, varde)
    return data


def spara_mina(data: dict) -> None:
    if MINA.exists():
        if las_json(MINA) == data:
            return
        BACKUPS.mkdir(parents=True, exist_ok=True)
        stampel = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(MINA, BACKUPS / f"mina-{stampel}.json")
        for fil in sorted(BACKUPS.glob("mina-*.json"))[:-MAX_BACKUPS]:
            fil.unlink()
    skriv_json(MINA, data)


def lista_backups() -> list[Path]:
    return sorted(BACKUPS.glob("mina-*.json"), reverse=True)


def aterstall(fil: Path) -> None:
    spara_mina(json.loads(fil.read_text(encoding="utf-8")))
