"""Starta sökningar, schemalägg dem och ändra inställningar."""

import datetime as dt

import streamlit as st

from bonusapp import lagring, notis, schema, skanna, ui

m = ui.mina()
inst = m["installningar"]
reg = ui.register()
sk = ui.skanning()
st.title("Sökning och inställningar")

# --- Sökning ---------------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("Sökning")
    pagar = skanna.pagaende()
    c = st.columns(3)
    c[0].metric("Domäner i registren", len(reg.get("kasinon", {})))
    c[1].metric("Senaste sökning", (sk.get("tid") or "–")[:16].replace("T", " "))
    c[2].metric("Erbjudanden", len(ui.bonusar_ra().get("bonusar", [])))
    with st.container(horizontal=True):
        if st.button("Sök igenom alla kasinon", type="primary", icon=":material/play_arrow:", disabled=bool(pagar)):
            ui.starta_skanning()
            st.rerun()
        if st.button("Hämta licensregistren på nytt", icon=":material/gavel:", disabled=bool(pagar)):
            ui.starta_skanning("--bara-register")
            st.rerun()
        if st.button("Tolka om sparade sidor", icon=":material/manage_search:", disabled=bool(pagar),
                     help="Kör tolkningen igen på texten från senaste sökningen – tar några sekunder och "
                          "hämtar inget från nätet. Användbart efter att tolkningsreglerna ändrats."):
            ui.starta_skanning("--omtolka")
            st.rerun()
    ui.forlopp()
    st.caption("En hel sökning tar ungefär 15–40 minuter beroende på hur många sidor som behöver Chrome. "
               "Den körs i bakgrunden, så du kan stänga fliken under tiden. Kasinon som inte tar emot svenska "
               f"spelare kollas bara om var {skanna.GEO_OMKOLL_DAGAR}:e dag. Registren hämtas om automatiskt "
               "när de är äldre än en vecka.")
    if reg.get("hamtad"):
        st.caption("Register hämtade: " + ", ".join(f"{k} {v[:10]}" for k, v in reg["hamtad"].items())
                   + (f" · fel: {reg['fel']}" if reg.get("fel") else ""))
    if sk.get("chrome_fel"):
        st.warning(f"Chrome kunde inte startas vid senaste sökningen, så JS-sidor lästes inte: {sk['chrome_fel']}")
    if sk.get("resultat"):
        from collections import Counter
        antal = Counter(r.get("status") for r in sk["resultat"].values())
        st.caption("Utfall: " + " · ".join(f"{ui.STATUSTEXT.get(s, s)}: {n}" for s, n in antal.most_common()))
    logg = lagring.LOGGAR / "senaste.log"
    if logg.exists() and logg.stat().st_size:
        with st.expander("Logg från senaste körningen"):
            st.code(logg.read_text(encoding="utf-8", errors="replace")[-6000:], language=None)

# --- Schema och notiser ----------------------------------------------------------------------
with st.container(border=True):
    st.subheader("Daglig sökning och notiser")
    aktivt = schema.aktivt()
    st.caption("Kör sökningen automatiskt en gång per dag med macOS egen schemaläggare (launchd) och skicka en "
               "notis när nya erbjudanden som klarar dina regler dyker upp. Om datorn sover vid den tiden körs "
               "sökningen när den vaknar.")
    c1, c2, c3 = st.columns([1, 1, 2], vertical_alignment="bottom")
    tid = c1.time_input("Klockslag", value=dt.time.fromisoformat(schema.tid() or inst["schema_tid"]), step=900)
    min_ev = c2.number_input("Notis bara om EV minst (kr)", min_value=0.0, step=10.0, value=float(inst["notis_min_ev"]))
    with c3.container(horizontal=True):
        if st.button("Uppdatera schemat" if aktivt else "Slå på daglig sökning", type="primary",
                     icon=":material/schedule:"):
            inst["schema_tid"], inst["notis_min_ev"] = tid.strftime("%H:%M"), min_ev
            ui.spara(m)
            schema.aktivera(inst["schema_tid"])
            st.toast(f"Daglig sökning kl. {inst['schema_tid']}.")
            st.rerun()
        if aktivt and st.button("Stäng av", icon=":material/schedule_send:"):
            schema.avaktivera()
            st.rerun()
        if st.button("Testa notis", icon=":material/notifications:"):
            notis.skicka("Bonussökaren", "Så här ser en notis ut.", "Test")
    st.markdown(f"Status: **{'på, kl. ' + schema.tid() if aktivt else 'av'}**")

# --- Inställningar ---------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("Inställningar")
    with st.form("inst"):
        c1, c2 = st.columns(2)
        rtp = c1.slider("Antagen RTP på slots (för EV)", 0.85, 0.99, float(inst["rtp"]), 0.005, format="%.3f")
        spinv = c2.number_input("Antaget värde per freespin när villkoren inte säger något (kr)", 0.1, 50.0,
                                float(inst["spinvarde"]), 0.1)
        visa_1x = st.toggle("Visa erbjudanden där insättningen måste spelas 1 gång före uttag (penningtvättsregel)",
                            value=inst["visa_1x"], help="De är strikt sett omsättningskrav på insättningen, men "
                            "bara 1×. Avstängt = de döljs.")
        c3, c4 = st.columns(2)
        max_sidor = c3.number_input("Max undersidor per kasino", 2, 15, int(inst["max_sidor"]))
        parallella = c4.number_input("Kasinon samtidigt", 1, 12, int(inst["parallella"]))
        chrome = st.toggle("Läs JS-sidor med Chrome (headless)", value=inst["chrome"])
        robots = st.toggle("Respektera robots.txt", value=inst["respektera_robots"])
        if st.form_submit_button("Spara", type="primary"):
            inst.update(rtp=rtp, spinvarde=spinv, visa_1x=visa_1x, max_sidor=int(max_sidor),
                        parallella=int(parallella), chrome=chrome, respektera_robots=robots)
            ui.spara(m, "Inställningarna sparade.")
            st.rerun()

# --- Backuper --------------------------------------------------------------------------------
with st.expander("Backuper av dina markeringar"):
    st.caption("Före varje ändring sparas en kopia av data/mina.json (använda kasinon, granskningar, inställningar).")
    backups = lagring.lista_backups()
    if backups:
        fil = st.selectbox("Backup", backups, format_func=lambda p: p.stem.removeprefix("mina-"))
        if st.button("Återställ den här"):
            lagring.aterstall(fil)
            st.toast("Återställd.")
            st.rerun()
    else:
        st.caption("Inga backuper än.")
