"""EU/EES-licensregister: Malta (MGA) och Estland (EMTA).

MGA: licensregistret (mgalicenseeregister.mga.org.mt) är en Angular-app vars API-svar är krypterat och
dekrypteras i webbläsaren. Appen låter därför din Chrome (headless, via Playwright) visa sidan och läser
tabellen – den försöker inte knäcka något. Domänerna står inte i registret utan på bolagets "Dynamic
Seal"-sida (authorisation.mga.org.mt), som är vanlig HTML. MGA svarar med 429 redan vid ~1 anrop/s,
så seal-sidorna hämtas med 5 s mellanrum och sparas i data/mga_seal_cache.json i 30 dagar. Första
hämtningen tar därför ~13 minuter, senare bara någon minut.

EMTA: listan över lagliga spelbolag är en statisk sida med varumärken och domäner.

Varje källa returnerar poster med samma fält som register_se.hamta().
"""

from __future__ import annotations

import datetime as dt
import time
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from . import lagring
from .register_se import normalisera

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/154.0 Safari/537.36")

# ---------------------------------------------------------------------------------------------
# Malta
# ---------------------------------------------------------------------------------------------

MGA_REGISTER = "https://mgalicenseeregister.mga.org.mt/"
MGA_SEAL = "https://authorisation.mga.org.mt/verification.aspx?lang=EN&company={guid}&details=1"
SEAL_CACHE = lagring.DATA / "mga_seal_cache.json"
SEAL_MAX_DAGAR = 30
SEAL_PAUS = 5.0

# Körs i registersidan: klicka "View All", bläddra igenom alla sidor och returnera raderna.
_LAS_TABELL = r"""
async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const btn = [...document.querySelectorAll('button')].find(b => /View All/i.test(b.innerText));
  if (!btn) return {error: 'ingen View All-knapp'};
  btn.click();
  for (let i = 0; i < 100 && !document.querySelector('mat-expansion-panel'); i++) await sleep(200);
  const rader = [], sedda = new Set();
  for (let sida = 0; sida < 200; sida++) {
    for (const p of document.querySelectorAll('mat-expansion-panel')) {
      const r = {name: p.querySelector('.company_name')?.textContent.trim()};
      for (const tr of p.querySelectorAll('table tr')) {
        const k = tr.querySelector('th')?.textContent.trim();
        const td = tr.querySelector('td');
        if (!k || !td) continue;
        const a = td.querySelector('a');
        r[k] = a ? a.getAttribute('href') : td.textContent.trim();
      }
      const nyckel = r.name + '|' + r['Authorisation Number'];
      if (!sedda.has(nyckel)) { sedda.add(nyckel); rader.push(r); }
    }
    const nasta = document.querySelector('.mat-mdc-paginator-navigation-next');
    if (!nasta || nasta.disabled || nasta.getAttribute('aria-disabled') === 'true') break;
    nasta.click();
    await sleep(300);
  }
  return {rader};
}
"""


def _mga_tabell() -> list[dict]:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        webblasare = p.chromium.launch(channel="chrome", headless=True)
        try:
            flik = webblasare.new_page()
            flik.goto(MGA_REGISTER, wait_until="domcontentloaded", timeout=60000)
            flik.get_by_role("button", name="View All").wait_for(timeout=60000)
            flik.wait_for_timeout(1500)  # låt API-svaret hinna dekrypteras
            data = flik.evaluate(_LAS_TABELL)
        finally:
            webblasare.close()
    if not data or data.get("error") or not data.get("rader"):
        raise RuntimeError(f"Kunde inte läsa MGA-registret: {data and data.get('error')}")
    return data["rader"]


def _guid(href: str | None) -> str | None:
    return (parse_qs(urlparse(href).query).get("company") or [None])[0] if href else None


def tolka_seal(html: str) -> dict:
    s = BeautifulSoup(html, "lxml")
    ut = {"licenser": [], "vertikaler": [], "adresser": []}
    tabell = s.find("table", id=lambda x: x and x.endswith("tblLicenses"))
    for tr in (tabell.find_all("tr") if tabell else []):
        if nummer := tr.find("td", class_="cell-license-number"):
            cell = lambda c: (tr.find("td", class_=c).get_text(" ", strip=True) if tr.find("td", class_=c) else None)  # noqa: E731
            ut["licenser"].append({"nummer": nummer.get_text(strip=True), "typ": cell("cell-license-type"),
                                   "status": cell("cell-license-status")})
    spel = s.find("table", id=lambda x: x and x.endswith("tblGameTypesTable"))
    for td in (spel.find_all("td", class_="cell-game-type-vertical") if spel else []):
        for v in td.get_text("\n", strip=True).split("\n"):
            v = v.strip(" •• ").strip()
            if v and v not in ut["vertikaler"]:
                ut["vertikaler"].append(v)
    th = next((t for t in s.find_all("th") if "Website Urls" in t.get_text()), None)
    if td := (th.find_next_sibling("td") if th else None):
        adresser = [a.get("href") or a.get_text(strip=True) for a in td.find_all("a")] or \
                   [li.get_text(strip=True) for li in td.find_all("li")]
        ut["adresser"] = [a for a in dict.fromkeys(x.strip() for x in adresser) if a]
    return ut


def _hamta_seal(s: requests.Session, url: str, forsok: int = 5) -> str:
    vanta = 30.0
    for _ in range(forsok):
        r = s.get(url, timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            ra = r.headers.get("Retry-After")
            time.sleep(float(ra) if ra and ra.isdigit() else vanta)
            vanta = min(vanta * 2, 300)
            continue
        r.raise_for_status()
        return r.text
    r.raise_for_status()
    return r.text


def hamta_mga(framsteg=None) -> list[dict]:
    rader = _mga_tabell()
    kandidater = {}
    for r in rader:
        delar = (r.get("Authorisation Number") or "").split("/")
        if (len(delar) > 1 and delar[1] in ("B2C", "CRP") and "Type 1" in (r.get("Authorisation type") or "")
                and (r.get("Status") or "").lower() == "licensed" and (g := _guid(r.get("Company Seal")))):
            kandidater.setdefault(g, r)

    cache = lagring.las_json(SEAL_CACHE, {}) or {}
    s = requests.Session()
    s.headers["User-Agent"] = UA
    grans = (dt.datetime.now() - dt.timedelta(days=SEAL_MAX_DAGAR)).isoformat()
    poster = []
    for i, (guid, r) in enumerate(kandidater.items(), 1):
        post = cache.get(guid)
        if not post or post.get("tid", "") < grans:
            try:
                post = {**tolka_seal(_hamta_seal(s, MGA_SEAL.format(guid=guid))), "tid": lagring.nu()}
                cache[guid] = post
                if i % 10 == 0:
                    lagring.skriv_json(SEAL_CACHE, cache)
            except requests.RequestException:
                post = cache.get(guid)  # behåll gammal uppgift hellre än ingen
            time.sleep(SEAL_PAUS)
        if framsteg:
            framsteg(i, len(kandidater))
        if not post:
            continue
        b2c = [l for l in post["licenser"] if "B2C" in (l.get("typ") or "") and (l.get("status") or "") == "Licensed"]
        if not b2c:
            continue
        for adress in post["adresser"]:
            if norm := normalisera(adress):
                poster.append({
                    "doman": norm[0], "start_url": norm[1], "kalla": "MGA",
                    "bolag": " ".join((r.get("name") or "").split()), "bolag_id": f"mga:{guid}",
                    "licens_id": b2c[0]["nummer"], "typ": ", ".join(post["vertikaler"]) or r.get("Authorisation type"),
                    "giltig_till": None, "land": "Malta",
                })
    lagring.skriv_json(SEAL_CACHE, cache)
    return poster


# ---------------------------------------------------------------------------------------------
# Estland
# ---------------------------------------------------------------------------------------------

EMTA = "https://emta.ee/en/business-client/registration-business/gambling-operators/list-legal-gambling-operators"


def _rubrik(tabell) -> str:
    p = tabell
    for _ in range(8):
        p = p.parent
        if p is None:
            break
        fore = p.find_previous_sibling()
        if fore and fore.get_text(strip=True):
            return fore.get_text(" ", strip=True)
    return ""


def tolka_emta(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    poster = []
    for tabell in (soup.find("main") or soup.body).find_all("table"):
        if "games of chance online" not in _rubrik(tabell).lower():
            continue
        bolag = None
        for tr in tabell.find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            mtr = next((a["href"] for a in tr.find_all("a", href=True) if "mtr.ttja.ee" in a["href"]), None)
            if mtr or bolag is None:
                bolag = {"namn": tds[0].get_text(" ", strip=True), "id": (mtr or tds[0].get_text()).rstrip("/").split("/")[-1]}
            for a in tr.find_all("a", href=True):
                if "mtr.ttja.ee" in a["href"]:
                    continue
                if norm := normalisera(a["href"]):
                    poster.append({
                        "doman": norm[0], "start_url": norm[1], "kalla": "EE", "bolag": bolag["namn"],
                        "bolag_id": f"ee:{bolag['id']}", "licens_id": bolag["id"], "typ": "Games of chance online",
                        "giltig_till": None, "land": "Estland",
                    })
    return poster


def hamta_ee(framsteg=None) -> list[dict]:
    r = requests.get(EMTA, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    poster = tolka_emta(r.text)
    if framsteg:
        framsteg(1, 1)
    if not poster:
        raise RuntimeError("Hittade inga bolag i EMTA-listan – har sidan ändrat utseende?")
    return poster


KALLOR = {"MGA": hamta_mga, "EE": hamta_ee}
