"""Hämtar sidor: först vanlig HTTP, och med din installerade Chrome (headless) när sidan kräver JavaScript.

Appen läser bara publika sidor. Den loggar aldrig in, fyller aldrig i formulär och försöker inte ta
sig förbi botskydd: en sida som svarar med en Cloudflare-kontroll eller CAPTCHA märks "botskydd" och
hoppas över. robots.txt respekteras (kan stängas av i inställningarna).
"""

from __future__ import annotations

import asyncio
import html as htmlmod
import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from . import text

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")
HUVUDEN = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.6",
}
PAUS_PER_VARD = 0.7      # sekunder mellan två anrop till samma webbplats
MIN_TEXT = 800           # mindre synlig text än så -> sidan byggs troligen med JavaScript
# Starka tecken på en kontroll/blockering räknas alltid; svaga (skript som laddas även på vanliga sidor)
# räknas bara när servern samtidigt svarar 403/429/503.
_BOTSKYDD_STARK = re.compile(
    r"cf-chl|chl_page|Just a moment\.\.\.|Attention Required!|Checking your browser|verify you are human|"
    r"Pardon Our Interruption|Incapsula incident ID|Request unsuccessful|ddos-guard|px-captcha|"
    r"Sorry, you have been blocked", re.I)
_BOTSKYDD_SVAG = re.compile(r"captcha|challenge-platform|_Incapsula_Resource|Access denied", re.I)


_SKUGGTEXT = """() => {
  const ut = [];
  const gå = (rot) => rot.querySelectorAll('*').forEach(el => {
    if (el.shadowRoot) {
      ut.push(Array.from(el.shadowRoot.children)
        .filter(c => !['STYLE', 'SCRIPT', 'TEMPLATE', 'LINK'].includes(c.tagName))
        .map(c => (c.textContent || '').replace(/[ \\t]+/g, ' ')).join('\\n'));
      gå(el.shadowRoot);
    }
  });
  gå(document);
  return ut.join('\\n').slice(0, 300000);
}"""


@dataclass
class Sida:
    url: str
    slutlig_url: str = ""
    status: int | None = None
    html: str = ""
    via: str = "http"          # "http" eller "chrome"
    fel: str | None = None     # "robots", "botskydd", "timeout", "nätverk: …", "http 404" …

    @property
    def ok(self) -> bool:
        return self.fel is None and bool(self.html)


def ar_botskydd(status: int | None, html: str) -> bool:
    if len(html) < 60000 and _BOTSKYDD_STARK.search(html):
        return True
    return status in (403, 429, 503) and bool(_BOTSKYDD_SVAG.search(html[:20000]))


class Hamtare:
    def __init__(self, chrome: bool = True, robots: bool = True, max_flikar: int = 3):
        self.anvand_chrome = chrome
        self.robots = robots
        self._klient = httpx.AsyncClient(headers=HUVUDEN, follow_redirects=True, timeout=25.0,
                                         max_redirects=8)
        self._robotar: dict[str, RobotFileParser | None] = {}
        self._vardlas: dict[str, asyncio.Lock] = {}
        self._senast: dict[str, float] = {}
        self._flikar = asyncio.Semaphore(max_flikar)
        self._pw = self._webblasare = self._kontext = None
        self._startlas = asyncio.Lock()
        self.chrome_fel: str | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self._klient.aclose()
        if self._webblasare:
            await self._webblasare.close()
        if self._pw:
            await self._pw.stop()

    # --- artighet ----------------------------------------------------------------------------

    async def _vanta_pa_tur(self, vard: str) -> None:
        las = self._vardlas.setdefault(vard, asyncio.Lock())
        async with las:
            vantan = self._senast.get(vard, 0) + PAUS_PER_VARD - time.monotonic()
            if vantan > 0:
                await asyncio.sleep(vantan)
            self._senast[vard] = time.monotonic()

    async def tillats(self, url: str) -> bool:
        if not self.robots:
            return True
        delar = urlsplit(url)
        vard = f"{delar.scheme}://{delar.netloc}"
        if vard not in self._robotar:
            rp = None
            try:
                r = await self._klient.get(f"{vard}/robots.txt", timeout=10.0)
                if r.status_code == 200 and "html" not in r.headers.get("content-type", ""):
                    rp = RobotFileParser()
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                pass
            self._robotar[vard] = rp
        rp = self._robotar[vard]
        return rp is None or rp.can_fetch("*", url)

    def sitemaps(self, url: str) -> list[str]:
        delar = urlsplit(url)
        rp = self._robotar.get(f"{delar.scheme}://{delar.netloc}")
        return list(rp.site_maps() or []) if rp else []

    # --- hämtning ----------------------------------------------------------------------------

    async def http(self, url: str) -> Sida:
        if not await self.tillats(url):
            return Sida(url, url, fel="robots")
        await self._vanta_pa_tur(urlsplit(url).netloc)
        try:
            r = await self._klient.get(url)
        except httpx.TimeoutException:
            return Sida(url, url, fel="timeout")
        except (httpx.HTTPError, ValueError) as e:
            return Sida(url, url, fel=f"nätverk: {type(e).__name__}")
        sida = Sida(url, str(r.url), r.status_code, r.text if "html" in r.headers.get("content-type", "html")
                    or "xml" in r.headers.get("content-type", "") else "")
        if ar_botskydd(r.status_code, sida.html):
            sida.fel = "botskydd"
        elif r.status_code >= 400:
            sida.fel = f"http {r.status_code}"
        return sida

    async def _starta_chrome(self) -> bool:
        async with self._startlas:
            if self._kontext or self.chrome_fel:
                return self._kontext is not None
            try:
                from playwright.async_api import async_playwright
                self._pw = await async_playwright().start()
                self._webblasare = await self._pw.chromium.launch(channel="chrome", headless=True)
                self._kontext = await self._webblasare.new_context(
                    locale="sv-SE", timezone_id="Europe/Stockholm", viewport={"width": 1366, "height": 900})
                # Bilder, video och typsnitt behövs inte för att läsa villkor.
                await self._kontext.route(
                    "**/*", lambda route: route.abort()
                    if route.request.resource_type in ("image", "media", "font") else route.continue_())
            except Exception as e:  # noqa: BLE001 – Chrome saknas, Playwright saknas m.m.
                self.chrome_fel = f"{type(e).__name__}: {e}"[:300]
            return self._kontext is not None

    async def chrome(self, url: str) -> Sida:
        if not await self.tillats(url):
            return Sida(url, url, fel="robots")
        if not await self._starta_chrome():
            return Sida(url, url, via="chrome", fel="chrome saknas")
        await self._vanta_pa_tur(urlsplit(url).netloc)
        async with self._flikar:
            flik = await self._kontext.new_page()
            try:
                svar = await flik.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    await flik.wait_for_load_state("networkidle", timeout=8000)
                except Exception:  # noqa: BLE001 – sidor med ständig trafik blir aldrig "idle"
                    pass
                # Scrolla ner: FAQ- och villkorssektioner laddas ofta först när de kommer i bild.
                for _ in range(5):
                    await asyncio.wait_for(flik.mouse.wheel(0, 2500), 5)
                    await flik.wait_for_timeout(350)
                await flik.wait_for_timeout(800)
                html = await asyncio.wait_for(flik.content(), 15)
                # Webbkomponenter (shadow DOM) syns inte i sidkällan – lägg till deras text.
                try:
                    skugga = await asyncio.wait_for(flik.evaluate(_SKUGGTEXT), 10)
                except Exception:  # noqa: BLE001 – sidan svarar inte på skript; ta det som finns
                    skugga = ""
                if skugga:
                    # Före </body> – lxml kastar allt som står efter </html>.
                    div = f"<div data-skugg-dom>{htmlmod.escape(skugga)}</div>"
                    fore, slut, efter = html.rpartition("</body>")
                    html = f"{fore}{div}{slut}{efter}" if slut else html + div
                sida = Sida(url, flik.url, svar.status if svar else None, html, via="chrome")
            except Exception as e:  # noqa: BLE001
                namn = type(e).__name__
                return Sida(url, url, via="chrome", fel="timeout" if "Timeout" in namn else f"chrome: {namn}")
            finally:
                try:
                    await asyncio.wait_for(flik.close(), 5)
                except Exception:  # noqa: BLE001 – en flik som inte går att stänga får inte låsa sökningen
                    pass
        if ar_botskydd(sida.status, sida.html):
            sida.fel = "botskydd"
        elif sida.status and sida.status >= 400:
            sida.fel = f"http {sida.status}"
        return sida

    async def hamta(self, url: str) -> Sida:
        """HTTP först; Chrome om sidan uppenbart behöver JavaScript för att visa sitt innehåll."""
        sida = await self.http(url)
        if not self.anvand_chrome or sida.fel in ("robots", "botskydd") or (
                sida.fel and sida.fel.startswith("http 4") and sida.status != 403):
            return sida
        if sida.fel or len(text.extrahera(sida.html, sida.slutlig_url)[0]) < MIN_TEXT:
            renderad = await self.chrome(url)
            if renderad.ok or not sida.ok:
                return renderad
        return sida
