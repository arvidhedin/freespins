"""HTML -> läsbar text och länkar.

Många kasinon är byggda som JavaScript-appar (Next.js, Nuxt m.fl.) men skickar ändå med sitt
CMS-innehåll som JSON i sidan. Strängarna i den JSON:en tas med som text, så att bonusvillkoren ofta
kan läsas utan att starta en webbläsare.
"""

from __future__ import annotations

import html as htmlmod
import json
import re
from urllib.parse import urljoin, urldefrag

from bs4 import BeautifulSoup

MAX_TEXT = 400_000  # tecken per sida
_TAGG = re.compile(r"<[^>]+>")
_BLANK = re.compile(r"[ \t   ]+")
_JSON_SKRIPT = re.compile(r"application/(ld\+)?json", re.I)
_TILLSTAND = re.compile(r"window\.(__[A-Z_]+__|__NUXT__)\s*=\s*", re.I)


def _strangar(obj, ut: list[str], djup: int = 0) -> None:
    if djup > 40:
        return
    if isinstance(obj, str):
        s = obj.strip()
        if len(s) >= 12 and " " in s and not s.startswith(("http", "/", "{", "data:")):
            if "<" in s and ">" in s:
                s = _TAGG.sub(" ", s)
            ut.append(htmlmod.unescape(s))
    elif isinstance(obj, dict):
        for v in obj.values():
            _strangar(v, ut, djup + 1)
    elif isinstance(obj, list):
        for v in obj:
            _strangar(v, ut, djup + 1)


_STRANG = re.compile(r'"((?:[^"\\\n]|\\.){20,})"')
_BONUSORD = re.compile(r"omsätt|wager|free\s?spin|freespin|snurr|spins|bonus|insättning|deposit", re.I)


def _js_strangar(skript: str, ut: list[str], djup: int = 0) -> None:
    """Textsträngar ur ett skript som inte är ren JSON, t.ex. Next.js `self.__next_f.push([1,"…"])`.

    Strängliteraler avkodas som JSON-strängar; det avkodade kan i sin tur innehålla strängar (RSC-data),
    så det görs i två nivåer. Bara strängar som nämner bonusrelaterade ord behålls.
    """
    for m in _STRANG.finditer(skript):
        try:
            s = json.loads(f'"{m.group(1)}"')
        except ValueError:
            continue
        if djup == 0 and ('":' in s or '\\"' in s or s.count('"') > 6):
            _js_strangar(s, ut, djup + 1)
        if not _BONUSORD.search(s) or " " not in s:
            continue
        if "<" in s and ">" in s:
            s = _TAGG.sub("\n", s)
        for rad in htmlmod.unescape(s).split("\n"):
            if len(rad.strip()) >= 12 and not rad.lstrip().startswith(("{", "[", "$", "http")):
                ut.append(rad)


def _rensa(rader: list[str]) -> list[str]:
    ut, sedda = [], set()
    for r in rader:
        r = _BLANK.sub(" ", r).strip()
        if len(r) < 2 or r in sedda:
            continue
        sedda.add(r)
        ut.append(r)
    return ut


def extrahera(html: str, bas_url: str) -> tuple[str, list[tuple[str, str]], str]:
    """Returnerar (text, länkar, språk). Länkar = [(absolut url, länktext)]."""
    soup = BeautifulSoup(html, "lxml")
    sprak = (soup.html.get("lang") if soup.html else "") or ""

    inbaddad: list[str] = []
    for s in soup.find_all("script"):
        innehall = s.string or s.get_text() or ""
        if not innehall:
            continue
        data = None
        if _JSON_SKRIPT.search(s.get("type") or "") or s.get("id") in ("__NEXT_DATA__", "__NUXT_DATA__"):
            if '"FAQPage"' in innehall:
                continue  # generiska frågor och svar ("Vad är omsättningskrav?") är inga villkor
            try:
                data = json.loads(innehall)
            except ValueError:
                pass
        elif m := _TILLSTAND.search(innehall):
            try:
                data = json.loads(innehall[m.end():].rstrip().rstrip(";"))
            except ValueError:
                pass
        if data is not None:
            _strangar(data, inbaddad)
        elif _BONUSORD.search(innehall):
            _js_strangar(innehall, inbaddad)

    lankar = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = urldefrag(urljoin(bas_url, href))[0]
        lankar.append((url, " ".join(a.get_text(" ", strip=True).split())[:120]))

    # Erbjudanden i bannerbilder står ofta i alt-texten ("100% up to €44 + 44 Free Spins").
    bildtext = [b.get("alt") or b.get("title") or "" for b in soup.find_all("img")]
    bildtext = [t for t in bildtext if len(t) >= 12 and _BONUSORD.search(t)]

    for t in soup(["script", "style", "noscript", "svg", "iframe", "head"]):
        t.decompose()
    synlig = soup.get_text("\n").split("\n") + bildtext
    text = "\n".join(_rensa(synlig + inbaddad))[:MAX_TEXT]
    return text, lankar, sprak.lower()




def synlig(html: str) -> str:
    """Bara den text som syns på sidan (utan inbäddad JSON) – för t.ex. geoblockeringskontroll."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "svg", "iframe", "head", "template"]):
        t.decompose()
    return "\n".join(_rensa(soup.get_text("\n").split("\n")))
