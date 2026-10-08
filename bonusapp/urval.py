"""Dina regler: vilken kategori ett erbjudande hamnar i och om det ska visas.

Kategorier (i den ordning de prövas):
  avvisad          – du har avvisat det i granskningen
  insättning       – omsättningskrav på insättningen (eller insättning + bonus): visas aldrig
  1x insättning    – insättningen måste spelas 1 gång innan uttag: visas bara med reglaget på
  granska          – appen är osäker på var omsättningskravet ligger: du avgör
  omsättningsfri   – inget omsättningskrav alls
  omsättning bonus – krav bara på bonusen eller freespinvinsterna: OK enligt dina regler
"""

from __future__ import annotations

from . import ev

OK_KATEGORIER = ("omsättningsfri", "omsättning bonus")


def anvand_nyckel(b: dict) -> str:
    """Svensk licens: bonus ges bara första gången du spelar hos *bolaget*, oavsett varumärke."""
    return f"bolag:{b['bolag_id']}" if b.get("svensk_licens") else b["doman"]


def ar_anvand(b: dict, mina: dict) -> bool:
    anv = mina.get("anvanda", {})
    return b["doman"] in anv or anvand_nyckel(b) in anv


def effektiv(b: dict, mina: dict) -> dict:
    """Erbjudandet med dina granskningar inlagda och EV räknat med dina inställningar."""
    g = mina.get("granskningar", {}).get(b["nyckel"]) or {}
    ut = dict(b)
    for falt in ("omsattning_pa", "omsattning_x", "insattning_1x", "antal_spins", "spinvarde_kr",
                 "bonus_kr", "min_insattning_kr", "maxvinst_kr"):
        if falt in g and g[falt] is not None:
            ut[falt] = g[falt]
    ut["granskad"] = bool(g)
    ut["godkand"] = g.get("godkand")
    inst = mina.get("installningar", {})
    ut["ev_kr"], ut["ev_text"] = ev.berakna(ut, inst.get("rtp", 0.96), inst.get("spinvarde", 1.0))
    ut["kategori"] = kategori(ut)
    return ut


def kategori(b: dict) -> str:
    if b.get("godkand") is False:
        return "avvisad"
    if b.get("omsattning_pa") == "insattning":
        return "insättning"
    if b.get("insattning_1x"):
        return "1x insättning"
    if b.get("omsattning_pa") is None or (b.get("sakerhet") == "låg" and not b.get("granskad")):
        return "granska"
    if b.get("omsattning_pa") == "ingen":
        return "omsättningsfri"
    return "omsättning bonus"


def visas(b: dict, mina: dict, visa_anvanda: bool = False) -> bool:
    inst = mina.get("installningar", {})
    if b["kategori"] in ("avvisad", "insättning"):
        return False
    if b["kategori"] == "1x insättning" and not inst.get("visa_1x"):
        return False
    if b.get("accepterar_se") is False or b["nyckel"] in mina.get("dolda", {}):
        return False
    return visa_anvanda or not ar_anvand(b, mina)


def for_notis(nya: list[dict], mina: dict) -> list[dict]:
    min_ev = mina.get("installningar", {}).get("notis_min_ev", 0.0) or 0.0
    ut = [e for e in (effektiv(b, mina) for b in nya)
          if visas(e, mina) and e["kategori"] in OK_KATEGORIER and (e["ev_kr"] or 0) >= min_ev]
    return sorted(ut, key=lambda e: -(e["ev_kr"] or 0))
