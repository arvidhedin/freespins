"""Själva sökningen: register -> kasinon -> sidor -> erbjudanden. Körs av verktyg/skanna.py.

Appen startar sökningen som en egen process (samma kommando som det schemalagda jobbet), så att den
fortsätter även om du laddar om sidan. Förloppet skrivs till data/status.json.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import gzip
import json
import os
import time
import traceback
from collections import defaultdict
from urllib.parse import urlsplit

from . import ev, geo, hamta, lagring, register_eu, register_se, sidhitta, text, tolka

GEO_OMKOLL_DAGAR = 7   # kasinon som blockerade Sverige kollas igen efter så här många dagar
TIDSBUDGET = 150       # sekunder per kasino för att läsa undersidor


# ---------------------------------------------------------------------------------------------
# Lås och status
# ---------------------------------------------------------------------------------------------


def _lever(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def pagaende() -> int | None:
    """PID för en pågående sökning, annars None."""
    try:
        pid = int(lagring.LAS.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None
    return pid if _lever(pid) else None


def _status(**falt) -> None:
    gammal = lagring.las_json(lagring.STATUS, {}) or {}
    gammal.update(falt, uppdaterad=lagring.nu())
    lagring.skriv_json(lagring.STATUS, gammal)


# ---------------------------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------------------------


def uppdatera_register(med_eu: bool = True) -> dict:
    """Hämtar registren och slår ihop dem till en post per domän i data/kasinon.json."""
    poster, hamtad, fel = [], {}, {}
    _status(fas="register", aktuell="Spelinspektionen", i=0, n=0)
    try:
        poster += register_se.hamta(lambda i, n: _status(i=i, n=n))
        hamtad["SE"] = lagring.nu()
    except Exception as e:  # noqa: BLE001
        fel["SE"] = f"{type(e).__name__}: {e}"
    if med_eu:
        for kalla, funktion in register_eu.KALLOR.items():
            _status(aktuell=kalla, i=0, n=0)
            try:
                poster += funktion(lambda i, n: _status(i=i, n=n))
                hamtad[kalla] = lagring.nu()
            except Exception as e:  # noqa: BLE001
                fel[kalla] = f"{type(e).__name__}: {e}"

    gammal = lagring.las_json(lagring.KASINON, {}) or {}
    kasinon: dict[str, dict] = {}
    for p in poster:
        k = kasinon.setdefault(p["doman"], {"doman": p["doman"], "start_url": p["start_url"], "licenser": []})
        # Svensk startadress (t.ex. betsson.com/sv) går före en MGA-adress för samma domän.
        if p["kalla"] == "SE" and not any(l["kalla"] == "SE" for l in k["licenser"]):
            k["start_url"] = p["start_url"]
        k["licenser"].append({f: p.get(f) for f in ("kalla", "bolag", "bolag_id", "licens_id", "typ", "giltig_till", "land")})
    # En källa som inte gick att hämta den här gången: behåll dess gamla poster.
    for doman, k in (gammal.get("kasinon") or {}).items():
        for l in k["licenser"]:
            if l["kalla"] in fel:
                kasinon.setdefault(doman, {**k, "licenser": []})["licenser"].append(l)
    for k in kasinon.values():
        k["svensk_licens"] = any(l["kalla"] == "SE" for l in k["licenser"])
        k["bolag"] = next((l["bolag"] for l in k["licenser"] if l["kalla"] == "SE"), k["licenser"][0]["bolag"])
        k["bolag_id"] = next((l["bolag_id"] for l in k["licenser"] if l["kalla"] == "SE"), k["licenser"][0]["bolag_id"])
    data = {"hamtad": {**(gammal.get("hamtad") or {}), **hamtad}, "fel": fel,
            "kasinon": dict(sorted(kasinon.items()))}
    lagring.skriv_json(lagring.KASINON, data)
    return data


# ---------------------------------------------------------------------------------------------
# Ett kasino
# ---------------------------------------------------------------------------------------------


async def _sitemap_kandidater(h: hamta.Hamtare, start: hamta.Sida, doman: str) -> list[tuple[str, str]]:
    bas = start.slutlig_url.split("/", 3)
    rot = "/".join(bas[:3])
    adresser = h.sitemaps(start.slutlig_url) or [f"{rot}/sitemap.xml"]
    ut: list[tuple[str, str]] = []
    for adress in adresser[:2]:
        s = await h.http(adress)
        if not s.ok:
            continue
        sidor, under = sidhitta.sitemap_lankar(s.html)
        # I ett sitemapindex: läs de undersitemaps som ser ut att gälla sidor/kampanjer på svenska.
        under.sort(key=lambda u: -sidhitta.poang(u.replace("sitemap", ""), "") - (3 if "/sv" in u else 0)
                   - (2 if "page" in u else 0))
        for u in under[:3]:
            s2 = await h.http(u)
            if s2.ok:
                sidor += sidhitta.sitemap_lankar(s2.html)[0]
        ut += [(u, "") for u in sidor[:5000]]
    return ut


def _vard(url: str) -> str:
    vard = (urlsplit(url).hostname or "").lower()
    return vard[4:] if vard.startswith("www.") else vard


def _omdirigering(k: dict, slutlig_url: str, kanda: set[str]) -> dict | None:
    """Om startsidan skickar vidare till en annan domän: till en känd (registrerad) domän är det en
    dubblett som söks igenom för sig, annars en sajt utanför registren som inte ska litas på."""
    vard = _vard(slutlig_url)
    if not vard or sidhitta.samma_sajt(slutlig_url, k["doman"]) or k["doman"].endswith("." + vard):
        return None
    if vard in kanda or any(vard.endswith("." + d) for d in kanda):
        return {"status": "omdirigerad", "omdirigerad_till": vard}
    return {"status": "utanfor_registret", "omdirigerad_till": vard}


async def skanna_kasino(h: hamta.Hamtare, k: dict, max_sidor: int, kanda: set[str] = frozenset()) -> dict:
    res = {"doman": k["doman"], "tid": lagring.nu(), "status": "ok", "accepterar_se": None,
           "geo_skal": "", "sidor": [], "fel": [], "bonusar": []}
    start = await h.hamta(k["start_url"])
    if not start.ok:
        res["status"] = start.fel or "fel"
        res["sidor"].append({"url": start.url, "via": start.via, "fel": start.fel})
        # En blockerad startsida kan ändå vara en geoblockering (t.ex. 403 med "not available in your country").
        if start.html:
            info = geo.startinfo(start.html, start.status, start.slutlig_url)
            acc, skal = geo.bedom([(start.url, info["synlig"])], info, k["svensk_licens"])
            if acc is False:
                res.update(status="geoblock", accepterar_se=False, geo_skal=skal)
        return res

    if om := _omdirigering(k, start.slutlig_url, kanda):
        res.update(om)
        res["sidor"].append({"url": start.slutlig_url, "via": start.via})
        return res

    starttext, lankar, _ = text.extrahera(start.html, start.slutlig_url)
    info = geo.startinfo(start.html, start.status, start.slutlig_url, lankar)
    lasta = [(start.slutlig_url, starttext)]
    res["sidor"].append({"url": start.slutlig_url, "via": start.via, "tecken": len(starttext)})

    acc, skal = geo.bedom(lasta, info, k["svensk_licens"])
    if acc is False and not skal.startswith("troligen"):
        res.update(status="geoblock", accepterar_se=False, geo_skal=skal)
        spara_sidor(k["doman"], info, lasta)
        return res

    doman_slut = (start.slutlig_url.split("/")[2] if "//" in start.slutlig_url else k["doman"])
    kandidater = list(lankar)
    if len(sidhitta.valj(lankar, doman_slut, start.slutlig_url, max_sidor)) < 3:
        kandidater += await _sitemap_kandidater(h, start, doman_slut)
    if len(sidhitta.valj(kandidater, doman_slut, start.slutlig_url, max_sidor)) < 2:
        kandidater += sidhitta.vanliga_adresser(start.slutlig_url)

    # Bästa först, två nivåer: länkar på lästa kampanjsidor (t.ex. /kampanjer/ -> /kampanjer/powerup/)
    # blir nya kandidater. Misslyckade försök (404 …) räknas inte mot sidbudgeten, men begränsas.
    provade = {start.url.rstrip("/"), start.slutlig_url.rstrip("/")}
    forsok = 0
    slut = time.monotonic() + TIDSBUDGET  # hellre tolka det som hunnit läsas än att förlora allt
    while len(lasta) < max_sidor and forsok < max_sidor + 8 and time.monotonic() < slut:
        nasta = next((u for u in sidhitta.valj(kandidater, doman_slut, start.slutlig_url, max_sidor + 10)
                      if u.rstrip("/") not in provade), None)
        if not nasta:
            break
        provade.add(nasta.rstrip("/"))
        forsok += 1
        s = await h.hamta(nasta)
        if not s.ok:
            res["fel"].append({"url": nasta, "fel": s.fel})
            continue
        if s.slutlig_url.rstrip("/") in {u.rstrip("/") for u, _ in lasta}:
            continue  # omdirigerad till en sida som redan lästs
        provade.add(s.slutlig_url.rstrip("/"))
        t, nya_lankar, _ = text.extrahera(s.html, s.slutlig_url)
        lasta.append((s.slutlig_url, t))
        res["sidor"].append({"url": s.slutlig_url, "via": s.via, "tecken": len(t)})
        kandidater += nya_lankar

    spara_sidor(k["doman"], info, lasta)
    res.update(tolka_sidor(k, info, lasta))
    return res


def tolka_sidor(k: dict, info: dict, lasta: list[tuple[str, str]]) -> dict:
    """Geobedömning och tolkning av redan lästa sidor (används både vid sökning och omtolkning)."""
    acc, skal = geo.bedom(lasta, info, k["svensk_licens"])
    ut = {"accepterar_se": acc, "geo_skal": skal, "bonusar": [], "status": "ok"}
    if acc is False:
        ut["status"] = "geoblock"
        return ut
    ut["bonusar"] = tolka.hitta(lasta, k["doman"])
    if not ut["bonusar"]:
        ut["status"] = "inga_bonusar"
    return ut


# ---------------------------------------------------------------------------------------------
# Sidcache: texten från lästa sidor sparas komprimerad, så att tolkningen kan göras om utan nätverk
# ---------------------------------------------------------------------------------------------

CACHE_MAX_TECKEN = 200_000  # per sida


def _cachefil(doman: str):
    return lagring.SIDCACHE / f"{doman}.json.gz"


def spara_sidor(doman: str, info: dict, lasta: list[tuple[str, str]]) -> None:
    lagring.SIDCACHE.mkdir(parents=True, exist_ok=True)
    data = {"tid": lagring.nu(), "start": info, "sidor": [(u, t[:CACHE_MAX_TECKEN]) for u, t in lasta]}
    with gzip.open(_cachefil(doman), "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def las_sidor(doman: str) -> dict | None:
    try:
        with gzip.open(_cachefil(doman), "rt", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, OSError, ValueError):
        return None


def omtolka() -> dict:
    """Tolkar om alla sparade sidor med nuvarande regler – utan att hämta något från nätet."""
    register = lagring.las_json(lagring.KASINON, {}) or {}
    skanning = lagring.las_json(lagring.SKANNING, {}) or {}
    inst = lagring.ladda_mina()["installningar"]
    antal = 0
    for doman, r in skanning.get("resultat", {}).items():
        k = register.get("kasinon", {}).get(doman)
        if not k or r.get("status") not in ("ok", "inga_bonusar", "geoblock") or not (c := las_sidor(doman)):
            continue
        r.update(tolka_sidor(k, c["start"], [tuple(x) for x in c["sidor"]]))
        antal += 1
    lagring.skriv_json(lagring.SKANNING, skanning)
    nya = bygg_bonuslista(register, skanning, inst)
    return {"omtolkade": antal, "nya": nya}


# ---------------------------------------------------------------------------------------------
# Hela sökningen
# ---------------------------------------------------------------------------------------------


def _ska_hoppas_over(k: dict, tidigare: dict | None) -> bool:
    if not tidigare or k["svensk_licens"] or tidigare.get("accepterar_se") is not False:
        return False
    senast = dt.datetime.fromisoformat(tidigare["tid"])
    return (dt.datetime.now() - senast).days < GEO_OMKOLL_DAGAR


async def _kor(kasinon: list[dict], inst: dict, tidigare: dict, kanda: set[str], delspara=None) -> dict:
    resultat: dict[str, dict] = {}
    klara = 0
    sem = asyncio.Semaphore(int(inst["parallella"]))
    async with hamta.Hamtare(chrome=inst["chrome"], robots=inst["respektera_robots"],
                             max_flikar=int(inst.get("chrome_flikar", 6))) as h:

        async def en(k: dict) -> None:
            nonlocal klara
            async with sem:
                _status(aktuell=k["doman"])
                try:
                    resultat[k["doman"]] = await asyncio.wait_for(
                        skanna_kasino(h, k, int(inst["max_sidor"]), kanda), timeout=300)
                except asyncio.TimeoutError:
                    resultat[k["doman"]] = {"doman": k["doman"], "tid": lagring.nu(), "status": "timeout",
                                            "accepterar_se": None, "sidor": [], "fel": [], "bonusar": []}
                except Exception as e:  # noqa: BLE001 – ett trasigt kasino ska inte stoppa resten
                    resultat[k["doman"]] = {"doman": k["doman"], "tid": lagring.nu(), "status": "fel",
                                            "accepterar_se": None, "sidor": [], "bonusar": [],
                                            "fel": [{"fel": f"{type(e).__name__}: {e}"[:300],
                                                     "spar": traceback.format_exc()[-800:]}]}
                klara += 1
                _status(i=klara)
                if klara % 25 == 0 and delspara:
                    delspara({**tidigare, **resultat})

        await asyncio.gather(*(en(k) for k in kasinon))
        chrome_fel = h.chrome_fel
    for d, gammal in tidigare.items():
        resultat.setdefault(d, gammal)  # överhoppade (geoblockade) behåller sitt gamla resultat
    return {"resultat": resultat, "chrome_fel": chrome_fel}


def kor_skanning(bara: list[str] | None = None, bara_svenska: bool = False) -> dict:
    """Söker igenom alla kasinon i data/kasinon.json (eller bara de angivna domänerna)."""
    mina = lagring.ladda_mina()
    inst = mina["installningar"]
    register = lagring.las_json(lagring.KASINON, {}) or {}
    if not register.get("kasinon"):
        register = uppdatera_register()
    gammal_skanning = (lagring.las_json(lagring.SKANNING, {}) or {}).get("resultat", {})
    alla = list(register["kasinon"].values())
    if bara_svenska:
        bara = [k["doman"] for k in alla if k["svensk_licens"]]
    if bara:
        alla = [k for k in alla if k["doman"] in bara]
        tidigare = {d: r for d, r in gammal_skanning.items() if d not in bara}
        aktuella = alla
    else:
        tidigare = {d: r for d, r in gammal_skanning.items()
                    if _ska_hoppas_over(register["kasinon"].get(d, {"svensk_licens": True}), r)}
        aktuella = [k for k in alla if k["doman"] not in tidigare]

    startad = lagring.nu()
    _status(fas="kasinon", startad=startad, klar=None, i=0, n=len(aktuella), aktuell="")
    # Gamla resultat för domäner som inte hunnit sökas ännu behålls i delresultaten.
    gamla = {d: r for d, r in gammal_skanning.items() if d not in tidigare}

    def delspara(resultat: dict) -> None:
        delvis = {"tid": lagring.nu(), "startad": startad, "delvis": True, "resultat": {**gamla, **resultat}}
        lagring.skriv_json(lagring.SKANNING, delvis)
        bygg_bonuslista(register, delvis, inst, uppdatera_sedda=False)

    ut = asyncio.run(_kor(aktuella, inst, tidigare, set(register["kasinon"]), delspara))
    skanning = {"tid": lagring.nu(), "startad": startad, "chrome_fel": ut["chrome_fel"], "resultat": ut["resultat"]}
    lagring.skriv_json(lagring.SKANNING, skanning)
    nya = bygg_bonuslista(register, skanning, inst)
    _status(fas="klar", klar=lagring.nu(), aktuell="", nya=len(nya))
    return {"skanning": skanning, "nya": nya}


def bygg_bonuslista(register: dict, skanning: dict, inst: dict, uppdatera_sedda: bool = True) -> list[dict]:
    """Skriver data/bonusar.json och returnerar de erbjudanden som aldrig setts förut."""
    sedda = lagring.las_json(lagring.SEDDA, {}) or {}
    forsta = not sedda  # vid allra första sökningen är allt "nytt" – då markeras inget som nytt
    idag = lagring.nu()
    bonusar, nya = [], []
    per_bolag = defaultdict(list)
    for k in register.get("kasinon", {}).values():
        per_bolag[k["bolag_id"]].append(k["doman"])
    for doman, r in skanning["resultat"].items():
        k = register.get("kasinon", {}).get(doman)
        if not k:
            continue
        for b in r.get("bonusar", []):
            b = {**b, "bolag": k["bolag"], "bolag_id": k["bolag_id"], "svensk_licens": k["svensk_licens"],
                 "licenser": sorted({l["kalla"] for l in k["licenser"]}),
                 "systersajter": [d for d in per_bolag[k["bolag_id"]] if d != doman],
                 "accepterar_se": True if k["svensk_licens"] else r.get("accepterar_se")}
            if b["svensk_licens"] and b.get("utlandsk_valuta") and b["sakerhet"] != "låg":
                # Svensk sajt men beloppen i euro/pund: troligen den internationella versionens erbjudande.
                b["sakerhet"] = "låg"
                b["skal"] = b["skal"] + ["beloppen står i euro/pund – troligen erbjudandet för en annan marknad"]
            b["ev_kr"], b["ev_text"] = ev.berakna(b, inst["rtp"], inst["spinvarde"])
            if b["nyckel"] not in sedda:
                sedda[b["nyckel"]] = idag
                nya.append(b)
            b["forst_sedd"] = sedda[b["nyckel"]]
            bonusar.append(b)
    if uppdatera_sedda:
        lagring.skriv_json(lagring.SEDDA, sedda)
    lagring.skriv_json(lagring.BONUSAR, {"tid": skanning["tid"], "startad": skanning.get("startad"),
                                         "forsta": forsta, "delvis": bool(skanning.get("delvis")),
                                         "bonusar": bonusar})
    return nya
