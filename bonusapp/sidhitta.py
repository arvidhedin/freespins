"""Hittar de undersidor på ett kasino som troligen innehåller bonuserbjudanden och bonusvillkor.

Kandidater kommer från länkarna på startsidan och från sitemap.xml. Varje URL får poäng efter
nyckelord i adress och länktext; svenska sidor föredras framför andra språkversioner.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

NYCKELORD = [
    (re.compile(r"bonus-?villkor|bonusvillkor|bonus-?terms|bonus-?regler|bonus-?rules|"
                r"kampanj-?villkor|promotion-?terms|promo-?terms|bonus-?policy|erbjudande-?villkor", re.I), 12),
    (re.compile(r"v[aä]lkomst|welcome|nykund|new-?customer|f[oö]rsta-?ins[aä]ttning|first-?deposit", re.I), 9),
    (re.compile(r"free-?spins?|freespins|gratis-?snurr|fria-?snurr|omsattningsfri|omsättningsfri|"
                r"wager-?free|no-?wager", re.I), 8),
    (re.compile(r"kampanj|promotion|promos?\b|erbjudand|offers?\b|bonus", re.I), 6),
    (re.compile(r"allm[aä]nna-?villkor|terms-?(and|&)-?conditions|terms-?of-?(use|service)|"
                r"anv[aä]ndarvillkor|villkor|\bterms\b|\bt-?c\b|regler", re.I), 3),
]
UTESLUT = re.compile(
    r"log-?in|logga-?in|sign-?(in|up)|registrer|register|signup|kassa|cashier|deposit$|ins[aä]ttning$|"
    r"apps?\.apple|play\.google|facebook|instagram|twitter|x\.com|youtube|linkedin|tiktok|"
    r"spelpaus|stodlinjen|stödlinjen|gamcare|begambleaware|cookie|integritet|privacy|"
    r"\.(pdf|jpg|png|svg|zip)$|/(game|games|play|spela|spel|slots?|live-?casino|sport|odds|poker|bingo)/[^/]+/[^/]+|"
    r"/(play|game|games|spela)/[^/]+/?$",
    re.I)
GUIDE = re.compile(r"guide|guiden|blogg?|nyheter|news|artik|faq|fragor|frågor|/go/|ordlista|glossary|how-to|sa-fungerar", re.I)
SPRAKSEGMENT = re.compile(r"^/([a-z]{2})(?:[-_]([a-z]{2}))?(?=/|$)", re.I)
SVENSKA = {"sv", "se"}


def _bas(doman: str) -> str:
    return doman[4:] if doman.startswith("www.") else doman


def samma_sajt(url: str, doman: str) -> bool:
    vard = (urlsplit(url).hostname or "").lower()
    bas = _bas(doman)
    return vard == bas or vard.endswith("." + bas)


def sprak_i_sokvag(url: str) -> str | None:
    m = SPRAKSEGMENT.match(urlsplit(url).path)
    return m.group(1).lower() if m else None


def poang(url: str, lanktext: str = "", foredraget_sprak: str | None = None) -> int:
    delar = urlsplit(url)
    if UTESLUT.search(delar.path) or UTESLUT.search(delar.query) or UTESLUT.search(lanktext):
        return 0
    falt = f"{delar.path} {delar.query} {lanktext}"
    p = max((v for monster, v in NYCKELORD if monster.search(falt)), default=0)
    if re.match(r"(?:offers?|kampanj(?:er)?|promo(?:tions?)?|bonus(?:ar)?)\.", delar.hostname or "", re.I):
        p = max(p, 8)  # offers.betsson.com, kampanjer.hajper.com …
    if not p:
        return 0
    if (sprak := sprak_i_sokvag(url)) and sprak not in SVENSKA and sprak != foredraget_sprak:
        p -= 6  # annan språkversion (t.ex. /en/, /fi/, /de-de/)
    if delar.path.count("/") > 5:
        p -= 2
    if re.search(r"/(?:slots?|spel|games?|spelautomater|online-spelautomater|slot-machines|online-slots|"
                 r"casino/games?|casino/[^/]+)/[^/]+", delar.path, re.I):
        p -= 5  # enskilda spelsidor ("/casino/online-spelautomater/welcome-fortune")
    if re.search(r"sportsbook|betting|/sport|odds|poker|bingo", delar.path, re.I):
        p -= 4  # sport-, poker- och bingoerbjudanden
    if GUIDE.search(delar.path):
        p -= 4  # guider, bloggar och FAQ beskriver bonusar generellt (t.ex. "Vad är no deposit bonus?")
    return p


def valj(kandidater: list[tuple[str, str]], doman: str, start_url: str, antal: int) -> list[str]:
    """Väljer de `antal` bästa undersidorna. kandidater = [(url, länktext)]."""
    foredraget = sprak_i_sokvag(start_url)
    basta: dict[str, int] = {}
    start = start_url.rstrip("/")
    for url, lanktext in kandidater:
        url = url.split("#")[0]
        if not url.startswith("http") or not samma_sajt(url, doman) or url.rstrip("/") == start:
            continue
        p = poang(url, lanktext, foredraget)
        if p > 0:
            basta[url] = max(p, basta.get(url, 0))
    ordnade = sorted(basta.items(), key=lambda kv: (-kv[1], len(kv[0])))
    # Ta högst två allmänna villkorssidor; de är långa och innehåller sällan själva erbjudandet.
    valda, allmanna = [], 0
    for url, p in ordnade:
        if p <= 3:
            if allmanna >= 2:
                continue
            allmanna += 1
        valda.append(url)
        if len(valda) >= antal:
            break
    return valda


def sitemap_lankar(xml: str) -> tuple[list[str], list[str]]:
    """Returnerar (sid-URL:er, under-sitemaps) ur en sitemap eller sitemapindex."""
    soup = BeautifulSoup(xml, "xml")
    if soup.find("sitemapindex"):
        return [], [loc.get_text(strip=True) for loc in soup.select("sitemap > loc")]
    return [loc.get_text(strip=True) for loc in soup.select("url > loc")], []


# Vanliga adresser för kampanjer och bonusvillkor; provas när sidan inte länkar till tillräckligt många.
VANLIGA = ["kampanjer/", "promotions/", "bonus/", "bonusar/", "valkomstbonus/", "erbjudanden/", "bonusvillkor/",
           "bonus-terms/", "promotions/casino/", "kampanjer/casino/"]


def vanliga_adresser(start_url: str) -> list[tuple[str, str]]:
    """Gissade kampanjadresser, med samma språksegment som startsidan (t.ex. /sv/)."""
    delar = urlsplit(start_url)
    rot = f"{delar.scheme}://{delar.netloc}"
    sprak = SPRAKSEGMENT.match(delar.path)
    prefix = sprak.group(0) if sprak else ""
    # Länktexten "kampanjer" ger samma poäng som en riktig kampanjlänk.
    return [(f"{rot}{prefix}/{v}", v.strip("/").replace("/", " ")) for v in VANLIGA]
