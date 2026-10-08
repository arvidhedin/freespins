"""Alla kasinon från licensregistren: status vid senaste sökningen och vilka du redan har använt."""

import pandas as pd
import streamlit as st

from bonusapp import lagring, ui, urval

m = ui.mina()
reg = ui.register()
sk = ui.skanning().get("resultat", {})
st.title("Kasinon")

if not reg.get("kasinon"):
    st.info("Licensregistren är inte hämtade än – gör det under **Sökning och inställningar**.")
    st.stop()

ui.forlopp()
st.caption("Kasinon vars sajt skickar vidare till en domän som inte finns i något av registren söks inte "
           "igenom – det kan vara ett bolag med annan licens (t.ex. Curaçao/Anjouan) bakom samma namn.")
st.caption("Bocka i **Använt** för kasinon där du redan har registrerat dig eller fått bonus. Med svensk "
           "licens får ett bolag bara ge bonus första gången du spelar hos bolaget, så då döljs alla "
           "bolagets sajter. För EU-licensierade kasinon gäller markeringen bara den sajten.")

rader = []
for d, k in reg["kasinon"].items():
    r = sk.get(d, {})
    nyckel = f"bolag:{k['bolag_id']}" if k["svensk_licens"] else d
    rader.append({
        "Använt": nyckel in m["anvanda"] or d in m["anvanda"],
        "Kasino": d,
        "Bolag": k["bolag"],
        "Licens": " + ".join(sorted({l["kalla"] for l in k["licenser"]})),
        "Status": ui.STATUSTEXT.get(r.get("status"), r.get("status") or "Inte sökt"),
        "Tar emot Sverige": "Ja" if k["svensk_licens"] else {True: "Ja", False: "Nej", None: "Okänt"}[r.get("accepterar_se")],
        "Erbjudanden": len(r.get("bonusar", [])),
        "Vidare till": r.get("omdirigerad_till") or "",
        "Lästa sidor": len(r.get("sidor", [])),
        "Senast sökt": (r.get("tid") or "")[:16].replace("T", " "),
        "Länk": k["start_url"],
        "_nyckel": nyckel,
    })
df = pd.DataFrame(rader)

with st.container(horizontal=True, vertical_alignment="bottom"):
    sok = st.text_input("Sök kasino eller bolag", width=260)
    statusval = st.multiselect("Status", sorted(df["Status"].unique()), width=420)
    licens = st.segmented_control("Licens", ["Alla", "Svensk", "Bara EU/EES"], default="Alla")
    bara_anv = st.toggle("Bara använda")

vis = df
if sok:
    vis = vis[vis["Kasino"].str.contains(sok, case=False) | vis["Bolag"].str.contains(sok, case=False)]
if statusval:
    vis = vis[vis["Status"].isin(statusval)]
if licens == "Svensk":
    vis = vis[vis["Licens"].str.contains("SE")]
elif licens == "Bara EU/EES":
    vis = vis[~vis["Licens"].str.contains("SE")]
if bara_anv:
    vis = vis[vis["Använt"]]

st.caption(f"{len(vis)} av {len(df)} domäner · {df['Använt'].sum()} markerade som använda")
redigerad = st.data_editor(
    vis.drop(columns=["_nyckel"]), hide_index=True, disabled=[c for c in vis.columns if c != "Använt"],
    column_config={"Länk": st.column_config.LinkColumn(display_text="öppna", width="small"),
                   "Använt": st.column_config.CheckboxColumn(width="small")},
    key=f"kasinoeditor_{len(m['anvanda'])}", height=600)

andrade = vis.loc[redigerad["Använt"].values != vis["Använt"].values]
if len(andrade):
    for _, rad in andrade.iterrows():
        k = reg["kasinon"][rad["Kasino"]]
        if not rad["Använt"]:
            m["anvanda"][rad["_nyckel"]] = {"datum": lagring.nu()[:10], "doman": rad["Kasino"], "bolag": k["bolag"]}
        else:
            m["anvanda"].pop(rad["_nyckel"], None)
            m["anvanda"].pop(rad["Kasino"], None)
    ui.spara(m, "Sparat.")
    st.rerun()

with st.expander("Sök igenom ett enskilt kasino igen"):
    doman = st.selectbox("Kasino", list(reg["kasinon"]), index=None, placeholder="Välj domän")
    if doman:
        r = sk.get(doman)
        if r:
            st.write({"status": r.get("status"), "geo": r.get("geo_skal"), "sidor": r.get("sidor"), "fel": r.get("fel")})
        if st.button("Sök igen", icon=":material/refresh:", disabled=bool(ui.skanna.pagaende())):
            ui.starta_skanning("--doman", doman)
            st.toast(f"Söker igenom {doman} …")
            st.rerun()

anvanda = [b for b in ui.effektiva(m) if urval.ar_anvand(b, m)]
if anvanda:
    st.caption(f"{len(anvanda)} erbjudanden döljs för att kasinot (eller bolaget) är markerat som använt.")
