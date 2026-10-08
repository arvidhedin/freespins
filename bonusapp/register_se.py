"""Spelinspektionens licensregister: alla bolag med svensk licens för onlinespel och deras spelsidor.

Registret på spelinspektionen.se byggs av ett öppet JSON-API (samma som sidans Vue-komponent):
  GET /api/licenseregistryapi/?licenseTypes=20&licenseTypes=21   -> {holders:[{id,name}], urls:[...]}
  GET /api/licenseregistryapi/GetLicensesForHolder?holderId=<id> -> licenser med licenseUrls
Typ 20 = "Kommersiellt online" (kasino, poker, bingo), 21 = "Kommersiellt vadhållning" (många
spelbolag med vadhållningslicens har kasinot på samma sajt, t.ex. betsson.com/sv).
"""

from __future__ import annotations

import re
import time

import requests

BAS = "https://www.spelinspektionen.se/api/licenseregistryapi"
TYPER = (20, 21)
PAUS = 0.4  # sekunder mellan anrop
HUVUDEN = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/154.0 Safari/537.36",
    "Accept": "application/json",
}
_DOMAN = re.compile(r"^[a-z0-9À-ɏ.-]+\.[a-z]{2,}$")


def normalisera(adress: str) -> tuple[str, str] | None:
    """'www.Betsson.com/sv' -> ('betsson.com', 'https://www.betsson.com/sv'). None för t.ex. 'App: GGPoker'."""
    rad = adress.strip()
    utan = re.sub(r"^https?://", "", rad, flags=re.I)
    vard = utan.split("/")[0].split("?")[0].lower()
    doman = vard[4:] if vard.startswith("www.") else vard
    if not _DOMAN.match(doman):
        return None
    sokvag = utan[len(vard):].rstrip("/") if utan.lower().startswith(vard) else ""
    return doman, f"https://{vard}{sokvag}"


def _get(s: requests.Session, url: str, params=None, forsok: int = 3):
    for i in range(forsok):
        r = s.get(url, params=params, timeout=30)
        if r.status_code in (429, 500, 502, 503, 504) and i < forsok - 1:
            time.sleep(2 * (i + 1))
            continue
        r.raise_for_status()
        return r.json()


def hamta(framsteg=None) -> list[dict]:
    """En post per (domän, licens). framsteg(i, n) anropas efter varje bolag."""
    s = requests.Session()
    s.headers.update(HUVUDEN)
    sok = _get(s, f"{BAS}/", params=[("licenseTypes", t) for t in TYPER])
    bolag = sok["holders"]
    poster = []
    for i, b in enumerate(bolag, 1):
        time.sleep(PAUS)
        for lic in _get(s, f"{BAS}/GetLicensesForHolder", params={"holderId": b["id"]}):
            typ = lic["licenseType"]["licenseTypeId"]
            if typ not in TYPER or lic["licenseStatus"]["licenseStatusName"] != "Aktiv":
                continue
            innehavare = lic["licenseHolder"]
            namn = " ".join(innehavare["licenseHolderName"].split())  # namn kan innehålla \xa0
            for u in lic.get("licenseUrls") or []:
                norm = normalisera(u["licenseUrl"])
                if not norm:
                    continue
                poster.append({
                    "doman": norm[0],
                    "start_url": norm[1],
                    "kalla": "SE",
                    "bolag": namn,
                    "bolag_id": f"se:{b['id']}",
                    "licens_id": str(lic["licenseId"]),
                    "typ": lic["licenseType"]["licenseTypeName"],
                    "giltig_till": (lic.get("licenseTo") or "")[:10] or None,
                    "land": (innehavare.get("Country") or {}).get("countryName"),
                })
        if framsteg:
            framsteg(i, len(bolag))
    return poster
