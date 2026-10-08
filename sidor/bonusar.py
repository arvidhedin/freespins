"""Huvudsidan: alla erbjudanden som klarar dina regler, sorterade på förväntat värde."""

import streamlit as st

from bonusapp import ui, urval

m = ui.mina()
ra = ui.bonusar_ra()
st.title("Bonusar")

if not ra.get("bonusar"):
    st.info("Ingen sökning har gjorts än. Starta en under **Sökning och inställningar**.", icon=":material/search:")
    if st.button("Starta sökningen nu", type="primary", icon=":material/play_arrow:"):
        ui.starta_skanning()
        st.switch_page("sidor/data.py")
    st.stop()

ui.forlopp()
alla = ui.effektiva(m)
senaste_sokning = ra.get("tid", "")
# "Ny" = först sedd under den senaste sökningen (inte vid allra första sökningen, då allt är nytt).
sedan = None if ra.get("forsta") else (ra.get("startad") or senaste_sokning)

with st.container(horizontal=True, vertical_alignment="bottom"):
    kategorier = ["omsättningsfri", "omsättning bonus", "granska"] + (["1x insättning"] if m["installningar"]["visa_1x"] else [])
    valda = st.pills("Kategori", kategorier, default=["omsättningsfri", "omsättning bonus"], selection_mode="multi")
    licens = st.segmented_control("Licens", ["Alla", "Svensk", "EU/EES"], default="Alla")
    utan_ins = st.toggle("Bara utan insättning")
    visa_anv = st.toggle("Visa använda kasinon")
    visa_okand = st.toggle("Även okänt om de tar emot Sverige", value=True,
                           help="EU-licensierade kasinon där appen inte kunde avgöra om svenska spelare tas emot.")
    sok = st.text_input("Sök", placeholder="kasino eller spel", label_visibility="collapsed", width=200)

urvalet = [b for b in alla if urval.visas(b, m, visa_anvanda=visa_anv) and b["kategori"] in (valda or [])]
if licens == "Svensk":
    urvalet = [b for b in urvalet if b.get("svensk_licens")]
elif licens == "EU/EES":
    urvalet = [b for b in urvalet if not b.get("svensk_licens")]
if utan_ins:
    urvalet = [b for b in urvalet if b.get("utan_insattning")]
if not visa_okand:
    urvalet = [b for b in urvalet if b.get("accepterar_se")]
if sok:
    s = sok.lower()
    urvalet = [b for b in urvalet if s in b["doman"].lower() or s in (b.get("spel") or "").lower()
               or s in b["titel"].lower()]
# Säkra (svensk licens eller bekräftat) först, sedan efter förväntat värde.
urvalet.sort(key=lambda b: (not b.get("accepterar_se"), -(b.get("ev_kr") or -1), b["doman"]))

synliga = [b for b in alla if urval.visas(b, m)]
c = st.columns(4)
c[0].metric("Omsättningsfria", sum(b["kategori"] == "omsättningsfri" for b in synliga))
c[1].metric("Omsättning bara på bonus", sum(b["kategori"] == "omsättning bonus" for b in synliga))
c[2].metric("Att granska", sum(b["kategori"] == "granska" for b in synliga))
c[3].metric("Nya vid senaste sökningen", sum(bool(sedan) and b.get("forst_sedd", "") >= sedan for b in synliga))
if ra.get("delvis"):
    st.info("En sökning pågår – listan visar delresultat och fylls på var 25:e kasino.", icon=":material/hourglass_top:")
st.caption(f"Senaste sökning: {senaste_sokning.replace('T', ' ')[:16]} · {len(urvalet)} erbjudanden visas · "
           "EV är en grov uppskattning (RTP och spinvärde ställs in under inställningar).")

if not urvalet:
    st.info("Inga erbjudanden matchar filtren.")
    st.stop()

df = ui.tabell(urvalet, sedan)
val = st.dataframe(df, hide_index=True, column_config=ui.KOLUMNER, on_select="rerun",
                   selection_mode="single-row", key="bonustabell", height=min(36 * len(df) + 40, 620))
rader = val.selection.rows if val and val.selection else []
if rader:
    vald = urvalet[rader[0]]
    ui.detaljkort(vald, m)
else:
    st.caption("Klicka på en rad för detaljer, villkorstext och knappar för att markera kasinot som använt.")
