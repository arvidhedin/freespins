"""Söker igenom alla kasinon efter bonusar. Körs från appen, av det schemalagda jobbet eller för hand:

    python verktyg/skanna.py                    # hela sökningen (hämtar registren först om de saknas)
    python verktyg/skanna.py --register         # hämta registren på nytt först
    python verktyg/skanna.py --bara-register    # bara registren
    python verktyg/skanna.py --doman leovegas.com --doman snabbare.com
    python verktyg/skanna.py --notis            # macOS-notis om nya erbjudanden (används av schemat)
    python verktyg/skanna.py --omtolka          # tolka om sparade sidor med nya regler (ingen nätverkstrafik)
    python verktyg/skanna.py --svenska          # bara kasinon med svensk licens (några minuter)
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bonusapp import lagring, notis, skanna, urval  # noqa: E402

REGISTER_MAX_DAGAR = 7


def _register_gammalt() -> bool:
    data = lagring.las_json(lagring.KASINON, {}) or {}
    tider = list((data.get("hamtad") or {}).values())
    if not tider:
        return True
    return (dt.datetime.now() - dt.datetime.fromisoformat(min(tider))).days >= REGISTER_MAX_DAGAR


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--register", action="store_true", help="hämta licensregistren på nytt först")
    ap.add_argument("--bara-register", action="store_true", help="hämta bara registren")
    ap.add_argument("--doman", action="append", help="sök bara den här domänen (kan upprepas)")
    ap.add_argument("--notis", action="store_true", help="skicka macOS-notis om nya erbjudanden")
    ap.add_argument("--omtolka", action="store_true", help="tolka om sparade sidor, utan nätverk")
    ap.add_argument("--svenska", action="store_true", help="sök bara kasinon med svensk licens (snabbt)")
    a = ap.parse_args()

    if a.omtolka:
        ut = skanna.omtolka()
        print(f"Omtolkade {ut['omtolkade']} kasinon; {len(ut['nya'])} nya erbjudanden.")
        return 0

    if (pid := skanna.pagaende()) and pid != os.getpid():
        print(f"En sökning pågår redan (pid {pid}).")
        return 1
    lagring.DATA.mkdir(parents=True, exist_ok=True)
    lagring.LAS.write_text(str(os.getpid()))
    try:
        if a.register or a.bara_register or _register_gammalt():
            data = skanna.uppdatera_register()
            print(f"Register: {len(data['kasinon'])} domäner", f"(fel: {data['fel']})" if data["fel"] else "")
            if a.bara_register:
                skanna._status(fas="klar", klar=lagring.nu(), aktuell="")
                return 0
        ut = skanna.kor_skanning(a.doman, bara_svenska=a.svenska)
        res = ut["skanning"]["resultat"]
        antal = sum(len(r.get("bonusar", [])) for r in res.values())
        print(f"Klar: {len(res)} kasinon, {antal} erbjudanden, {len(ut['nya'])} nya.")
        if ut["skanning"].get("chrome_fel"):
            print("Chrome kunde inte startas:", ut["skanning"]["chrome_fel"])
        if a.notis:
            mina = lagring.ladda_mina()
            nya = urval.for_notis(ut["nya"], mina)
            if nya:
                basta = nya[0]
                notis.skicka(
                    "Nya kasinobonusar",
                    f"{basta['doman']}: {basta['titel']}" + (f" (+{len(nya) - 1} till)" if len(nya) > 1 else ""),
                    f"{len(nya)} nya erbjudanden utan omsättning på insättningen")
        return 0
    except Exception as e:
        skanna._status(fas="fel", klar=lagring.nu(), fel=f"{type(e).__name__}: {e}")
        raise
    finally:
        lagring.LAS.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
