"""Delade delar för Streamlit-sidorna: data med cache, tabeller, detaljkort och sökstart."""

from __future__ import annotations

import html
import re
import subprocess
import sys

import pandas as pd
import streamlit as st

from . import lagring, skanna, urval

ETIKETT_PA = {
    "ingen": "Ingen omsättning",
    "bonus": "På bonusen",
    "vinster": "På freespinvinsterna",
    "insattning": "På insättningen",
    None: "Okänt",
}
KATEGORIFARG = {
    "omsättningsfri": "green",
    "omsättning bonus": "blue",
    "1x insättning": "orange",
    "granska": "violet",
    "insättning": "red",
    "avvisad": "gray",
}
STATUSTEXT = {
    "ok": "Erbjudande hittat",
    "inga_bonusar": "Inget erbjudande hittat",
    "geoblock": "Tar inte emot Sverige",
    "botskydd": "Botskydd (hoppas över)",
    "robots": "robots.txt förbjuder",
    "timeout": "Svarade inte",
    "chrome saknas": "Behöver Chrome",
    "omdirigerad": "Skickar vidare till annan registrerad sajt",
    "utanfor_registret": "Skickar vidare till sajt UTANFÖR registren",
    "fel": "Fel vid läsning",
}


_MARKERA = re.compile(
    r"(omsättning\w*|omsätt\w*|wager\w*|playthrough|\d+\s?(?:x|ggr|gånger|times)\b|\bx\s?\d+|"
    r"insättning\w*|deposit\w*|bonusbelopp\w*|vinster\w*|winnings|free\s?spins?|freespins?|"
    r"utan omsättning\w*|no wagering|wager[- ]free|maxvinst|max(?:imal)? (?:win|withdrawal|uttag))", re.I)


def markera(utdrag: str) -> str:
    """Text från en kasinosida -> säker HTML med nyckelorden markerade."""
    return _MARKERA.sub(lambda m: f"<mark>{m.group(0)}</mark>", html.escape(utdrag).replace("$", "&#36;"))


def injicera_css() -> None:
    st.markdown("""<style>
      .block-container {padding-top: 2.2rem; max-width: 1400px;}
      .utdrag {font-size: 0.86rem; border-left: 3px solid rgba(128,128,128,.35); padding: .2rem .7rem;
               margin: .3rem 0; white-space: pre-wrap;}
      .utdrag mark {background: rgba(255, 196, 0, .35); color: inherit; padding: 0 .1rem;}
    </style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------------------------


def _mtime(fil) -> float:
    return fil.stat().st_mtime if fil.exists() else 0.0


@st.cache_data(show_spinner=False)
def _las(fil: str, _m: float):
    from pathlib import Path
    return lagring.las_json(Path(fil), {}) or {}


def bonusar_ra() -> dict:
    return _las(str(lagring.BONUSAR), _mtime(lagring.BONUSAR))


def register() -> dict:
    return _las(str(lagring.KASINON), _mtime(lagring.KASINON))


def skanning() -> dict:
    return _las(str(lagring.SKANNING), _mtime(lagring.SKANNING))


def mina() -> dict:
    return lagring.ladda_mina()


def spara(d: dict, meddelande: str | None = None) -> None:
    lagring.spara_mina(d)
    if meddelande:
        st.toast(meddelande)


def effektiva(m: dict) -> list[dict]:
    return [urval.effektiv(b, m) for b in bonusar_ra().get("bonusar", [])]


def fmt_kr(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    return f"{v:,.0f} kr".replace(",", " ")


def omsattningstext(b: dict) -> str:
    pa = b.get("omsattning_pa")
    if pa in ("bonus", "vinster", "insattning") and b.get("omsattning_x"):
        return f"{b['omsattning_x']:g}× {ETIKETT_PA[pa].lower()}"
    return ETIKETT_PA.get(pa, "Okänt")


def tabell(bonusar: list[dict], sedan: str | None = None) -> pd.DataFrame:
    rader = []
    for b in bonusar:
        rader.append({
            "nyckel": b["nyckel"],
            "Ny": bool(sedan and b.get("forst_sedd", "") >= sedan),
            "Kasino": b["doman"],
            "Erbjudande": b["titel"],
            "Kategori": b["kategori"],
            "Spins": b.get("antal_spins"),
            "Bonus (kr)": b.get("bonus_kr"),
            "Kräver insättning": "Nej" if b.get("utan_insattning") else (
                fmt_kr(b["min_insattning_kr"]) if b.get("min_insattning_kr") else "Ja"),
            "Omsättning": omsattningstext(b),
            "EV (kr)": b.get("ev_kr"),
            "Licens": " + ".join(b.get("licenser", [])),
            "Sverige": "Ja" if b.get("accepterar_se") else "Okänt",
            "Säkerhet": b.get("sakerhet"),
            "Länk": b.get("kalla_url"),
            "Först sedd": (b.get("forst_sedd") or "")[:10],
        })
    df = pd.DataFrame(rader)
    for kolumn in ("Spins", "Bonus (kr)", "EV (kr)"):
        df[kolumn] = pd.to_numeric(df[kolumn], errors="coerce")  # None -> tom cell, inte texten "None"
    return df


KOLUMNER = {
    "nyckel": None,
    "Sverige": st.column_config.TextColumn(width="small", help="Tar kasinot emot spelare från Sverige? Svensk licens = "
                                           "ja. 'Okänt' = EU-licens utan tydliga tecken åt något håll."),
    "Ny": st.column_config.CheckboxColumn("Ny", width="small"),
    "Spins": st.column_config.NumberColumn(format="%d", width="small"),
    "Bonus (kr)": st.column_config.NumberColumn(format="%d", width="small"),
    "EV (kr)": st.column_config.NumberColumn(format="%.0f", width="small",
                                             help="Förväntat värde i kronor – se förklaringen i detaljvyn."),
    "Länk": st.column_config.LinkColumn(display_text="öppna", width="small"),
    "Erbjudande": st.column_config.TextColumn(width="large"),
}


# ---------------------------------------------------------------------------------------------
# Detaljkort
# ---------------------------------------------------------------------------------------------


def detaljkort(b: dict, m: dict, nyckelprefix: str = "") -> None:
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"#### {b['doman']}")
        c1.markdown(f"**{b['titel']}**")
        c2.badge(b["kategori"], color=KATEGORIFARG.get(b["kategori"], "gray"))
        if b.get("granskad"):
            c2.caption("Granskad av dig")
        st.markdown(
            f"- **Omsättning:** {omsattningstext(b)}"
            + (" – och insättningen måste spelas 1 gång före uttag" if b.get("insattning_1x") else "")
            + f"\n- **Insättning:** {'krävs inte' if b.get('utan_insattning') else fmt_kr(b.get('min_insattning_kr')) + ' minst' if b.get('min_insattning_kr') else 'krävs'}"
            + (f"\n- **Spins:** {b['antal_spins']} st" + (f" à {b['spinvarde_kr']:g} kr" if b.get("spinvarde_kr") else "")
               + (f" på {b['spel']}" if b.get("spel") else "") if b.get("antal_spins") else "")
            + (f"\n- **Bonus:** {fmt_kr(b['bonus_kr'])}" + (f" ({b['matchprocent']} %)" if b.get("matchprocent") else "")
               if b.get("bonus_kr") else "")
            + (f"\n- **Maxvinst/maxuttag:** {fmt_kr(b['maxvinst_kr'])}" if b.get("maxvinst_kr") else "")
            + (f"\n- **Giltighet:** {b['giltighet']}" if b.get("giltighet") else "")
            + f"\n- **EV:** {fmt_kr(b.get('ev_kr'))} – {b.get('ev_text', '')}"
            + f"\n- **Bolag:** {b.get('bolag', '–')} ({' + '.join(b.get('licenser', []))})"
        )
        if b.get("svensk_licens") and b.get("systersajter"):
            st.caption("Samma bolag (bonus bara en gång per bolag med svensk licens): "
                       + ", ".join(b["systersajter"][:12]) + (" …" if len(b["systersajter"]) > 12 else ""))
        if b.get("skal"):
            st.caption("Tolkning: " + "; ".join(b["skal"]))
        if b.get("utdrag"):
            with st.expander("Text från kasinots sida", expanded=b["kategori"] == "granska"):
                for u in b["utdrag"]:
                    st.markdown(f"<div class='utdrag'>{markera(u)}</div>", unsafe_allow_html=True)
                st.caption(f"Källa: {b.get('kalla_url')}")

        k1, k2, k3 = st.columns(3)
        anv = urval.ar_anvand(b, m)
        if k1.button("Ångra använt" if anv else "Jag har använt det här kasinot", key=f"{nyckelprefix}anv{b['nyckel']}",
                     icon=":material/undo:" if anv else ":material/check_circle:", width="stretch"):
            satt_anvand(m, b, not anv)
            st.rerun()
        if k2.button("Dölj erbjudandet", key=f"{nyckelprefix}dolj{b['nyckel']}", icon=":material/visibility_off:",
                     width="stretch"):
            m["dolda"][b["nyckel"]] = lagring.nu()
            spara(m, "Dolt.")
            st.rerun()
        if b.get("kalla_url"):
            k3.link_button("Öppna kasinots sida", b["kalla_url"], icon=":material/open_in_new:", width="stretch")


def satt_anvand(m: dict, b: dict, anvand: bool) -> None:
    nyckel = urval.anvand_nyckel(b)
    if anvand:
        m["anvanda"][nyckel] = {"datum": lagring.nu()[:10], "doman": b["doman"], "bolag": b.get("bolag")}
        spara(m, f"Markerat som använt: {b.get('bolag') if b.get('svensk_licens') else b['doman']}")
    else:
        m["anvanda"].pop(nyckel, None)
        m["anvanda"].pop(b["doman"], None)
        spara(m, "Ångrat.")


# ---------------------------------------------------------------------------------------------
# Sökning
# ---------------------------------------------------------------------------------------------


def starta_skanning(*argument: str) -> None:
    lagring.LOGGAR.mkdir(parents=True, exist_ok=True)
    logg = open(lagring.LOGGAR / "senaste.log", "w", encoding="utf-8")  # noqa: SIM115 – ärvs av processen
    if skanna.pagaende():
        return
    # Barnprocessens pid är skriptets os.getpid(), så låset kan skrivas direkt och knapparna låses
    # redan vid nästa omritning (skriptet godtar ett lås med sitt eget pid).
    proc = subprocess.Popen([sys.executable, str(lagring.ROT / "verktyg" / "skanna.py"), *argument],
                            cwd=lagring.ROT, stdout=logg, stderr=subprocess.STDOUT, start_new_session=True)
    lagring.LAS.write_text(str(proc.pid))
    lagring.skriv_json(lagring.STATUS, {"fas": "startar", "i": 0, "n": 0, "aktuell": "", "uppdaterad": lagring.nu()})


@st.fragment(run_every=2)
def forlopp() -> None:
    """Visar hur långt en pågående sökning har kommit; laddar om sidan när den är klar."""
    s = lagring.las_json(lagring.STATUS, {}) or {}
    if skanna.pagaende():
        n, i = s.get("n") or 0, s.get("i") or 0
        fas = {"register": "Hämtar licensregister", "kasinon": "Söker igenom kasinon"}.get(s.get("fas"), "Arbetar")
        st.progress(i / n if n else 0.0, text=f"{fas}: {i}/{n} {s.get('aktuell') or ''}")
        st.session_state["_sokning_pagar"] = True
    elif st.session_state.pop("_sokning_pagar", False):
        st.cache_data.clear()
        st.rerun(scope="app")
