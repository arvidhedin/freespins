"""Avgör om ett kasino tar emot spelare från Sverige.

Kasinon med svensk licens gör det per definition. För EU/EES-licensierade (MGA, EMTA) är det vanligt
att Sverige blockeras sedan 2019. Sökningen körs från din dator med svensk IP-adress, så en
geoblockeringssida syns direkt.

Signaler, i ordning:
  Nej   – HTTP 451, blockeringstext på startsidan, omdirigering till /blocked m.m., Sverige i en lista
          över "restricted countries", nationell sajt för ett annat land (.co.uk, .de, .ee …) eller
          brittisk sajt (pund + GamStop/UK Gambling Commission). De två sista är "troligen inte".
  Ja    – svensk språkversion (lang/hreflang sv, länkar till /sv/ eller /se/) eller svenska villkor
          med kronor.
  Okänt – inget av ovanstående.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from . import sidhitta, text

BLOCKERAD = re.compile(
    r"inte\s+tillgänglig\w*\s+i\s+(ditt\s+land|din\s+region|sverige)|"
    r"kan\s+(tyvärr\s+)?inte\s+(ta\s+emot|acceptera)\s+(spelare|kunder)\s+från\s+(sverige|ditt\s+land)|"
    r"(not|isn'?t|is\s+not|are\s+not)\s+(currently\s+)?(available|accessible|permitted|offered)\s+"
    r"(in|from|to\s+(players|customers|users)\s+(in|from))\s+(your\s+(country|region|jurisdiction|location|area|territory)|sweden)|"
    r"(players|customers|users|residents)\s+(from|in|of)\s+(your\s+(country|jurisdiction|region)|sweden)\s+"
    r"(are\s+not|cannot|can'?t|may\s+not)\s+(be\s+)?(accepted|allowed|permitted|play|register|access)|"
    r"(unable|not\s+able)\s+to\s+(accept|offer\s+our\s+services\s+to)\s+(players|customers)\s+from\s+(your|sweden)|"
    r"access\s+from\s+your\s+(country|location|region)\s+(is|has\s+been)\s+(restricted|blocked|denied)|"
    r"(country|region|jurisdiction|location)\s+(is\s+)?(restricted|blocked|not\s+supported)|"
    r"(not|isn'?t)\s+(currently\s+)?(available|accessible)\s+in\s+the\s+(country|region|jurisdiction)\s+(you\s+are|where\s+you)|"
    r"geo-?(block|restrict)",
    re.I)
LISTA = re.compile(
    r"(restricted|prohibited|excluded|forbidden|blocked|non-accepted|unaccepted)\s+"
    r"(countries|jurisdictions|territories|regions)|"
    r"(not|cannot)\s+(accept|be\s+accepted\s+from|open\s+accounts?\s+(to|for))\s+(players|customers|residents|persons)"
    r"\s+(from|residing\s+in|in)\s+the\s+following|"
    r"(players|customers|residents)\s+from\s+the\s+following\s+(countries|jurisdictions)|"
    r"följande\s+länder|ej\s+tillåtna\s+länder",
    re.I)
SVERIGE = re.compile(r"\bsweden\b|\bsverige\b|\bswedish\s+residents\b", re.I)
SVENSKA_ORD = re.compile(r"\b(?:insättning|omsättning|uttag|välkomstbonus|spelpaus|snurr)\w*", re.I)
KRONOR = re.compile(r"\d\s?(?:kr\b|kronor|sek\b)|\bsek\s?\d|spelpaus|spelinspektionen", re.I)
BRITTISK = re.compile(r"gamstop|uk\s+gambling\s+commission|gamblingcommission\.gov\.uk|begambleaware", re.I)
# Nationella domäner för andra länders reglerade marknader.
ANDRA_LAND = (".co.uk", ".uk", ".ie", ".gr", ".de", ".dk", ".it", ".es", ".pt", ".nl", ".be", ".fr", ".hu",
              ".lv", ".lt", ".pl", ".ro", ".bg", ".cz", ".at", ".ch", ".ca", ".ee", ".fi", ".no", ".mt")


def startinfo(html: str, status: int | None, slutlig_url: str, lankar: list[tuple[str, str]] | None = None) -> dict:
    """Det som behövs från startsidan för bedömningen (sparas i sidcachen så att den kan göras om)."""
    lang, hreflang = "", []
    if html:
        soup = BeautifulSoup(html, "lxml")
        lang = ((soup.html.get("lang") if soup.html else "") or "").lower()
        hreflang = sorted({(l.get("hreflang") or "").lower() for l in soup.find_all("link", hreflang=True)})
    svenska_lankar = any(sidhitta.sprak_i_sokvag(u) in ("sv", "se") for u, _ in (lankar or []))
    return {"status": status, "slutlig_url": slutlig_url, "synlig": text.synlig(html)[:8000] if html else "",
            "lang": lang, "hreflang": hreflang, "svenska_lankar": svenska_lankar}


def bedom(sidor: list[tuple[str, str]], start: dict, svensk_licens: bool) -> tuple[bool | None, str]:
    """Returnerar (True/False/None, skäl). None = okänt."""
    if svensk_licens:
        return True, "svensk licens"
    if start.get("status") == 451:
        return False, "HTTP 451 (blockerat av juridiska skäl)"
    synlig = start.get("synlig") or ""
    # Bara synlig text: inbäddade översättningar innehåller ofta blockeringsmeddelandet även när sidan
    # inte blockerar. En geoblockeringssida är dessutom kort.
    if (m := BLOCKERAD.search(synlig[:4000])) and len(synlig) < 6000:
        return False, f"startsidan: \"{m.group(0)}\""
    url = (start.get("slutlig_url") or "").lower()
    if any(o in url for o in ("/blocked", "/restricted", "geo-block", "not-available", "forbidden-country")):
        return False, f"omdirigerad till {start.get('slutlig_url')}"
    for kalla, t in sidor:
        for m in LISTA.finditer(t):
            fonster = t[m.start(): m.end() + 1500]
            if s := SVERIGE.search(fonster):
                return False, (f"{kalla}: Sverige finns i listan efter \"{m.group(0)}\" "
                               f"(… {fonster[max(0, s.start() - 60): s.end() + 20]} …)")

    starttext = sidor[0][1] if sidor else synlig
    allt = "\n".join(t for _, t in sidor)
    if start.get("lang", "").startswith("sv") or any(h.startswith("sv") for h in start.get("hreflang", [])) \
            or start.get("svenska_lankar"):
        return True, "sajten har en svensk språkversion"
    if KRONOR.search(allt) and SVENSKA_ORD.search(starttext):
        return True, "sidan är på svenska och visar belopp i kronor"

    vard = (urlsplit(start.get("slutlig_url") or "").hostname or "").lower()
    if land := next((t for t in ANDRA_LAND if vard.endswith(t)), None):
        return False, f"troligen inte: nationell sajt ({land}) för spelare i ett annat land"
    if "£" in starttext and BRITTISK.search(allt):
        return False, "troligen inte: brittisk sajt (pund, GamStop/UK Gambling Commission)"
    return None, "inga tydliga tecken åt något håll"
