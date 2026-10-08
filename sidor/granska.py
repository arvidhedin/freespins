"""Granskning: erbjudanden där appen inte säkert kunde avgöra var omsättningskravet ligger."""

import streamlit as st

from bonusapp import lagring, ui, urval

m = ui.mina()
st.title("Granska")
st.caption("Här hamnar erbjudanden där villkorstexten var oklar. Läs utdraget, rätta det som behövs och "
           "godkänn eller avvisa. Ditt beslut sparas och gäller tills erbjudandet ändras.")

alla = ui.effektiva(m)
vis = st.segmented_control("Visa", ["Att granska", "Granskade", "Alla"], default="Att granska")
if vis == "Att granska":
    lista = [b for b in alla if b["kategori"] == "granska" and urval.visas(b, m)]
elif vis == "Granskade":
    lista = [b for b in alla if b.get("granskad")]
else:
    lista = [b for b in alla if b.get("accepterar_se") is not False]
lista.sort(key=lambda b: (b["doman"], b["titel"]))

if not lista:
    st.success("Inget att granska just nu.", icon=":material/task_alt:")
    st.stop()

val = st.selectbox("Erbjudande", range(len(lista)),
                   format_func=lambda i: f"{lista[i]['doman']} – {lista[i]['titel'][:90]}  [{lista[i]['kategori']}]")
b = lista[val]
ui.detaljkort(b, m, nyckelprefix="g")

ALT = ["ingen", "bonus", "vinster", "insattning", None]
with st.form(f"granska_{b['nyckel']}"):
    st.markdown("**Din bedömning**")
    c1, c2, c3 = st.columns(3)
    pa = c1.selectbox("Omsättningskrav på", ALT, index=ALT.index(b.get("omsattning_pa")),
                      format_func=lambda v: ui.ETIKETT_PA[v])
    x = c2.number_input("Gånger (x)", min_value=0.0, max_value=200.0, step=1.0,
                        value=float(b.get("omsattning_x") or 0))
    ettx = c3.checkbox("Insättningen måste spelas 1 gång före uttag", value=bool(b.get("insattning_1x")))
    c4, c5, c6, c7 = st.columns(4)
    spins = c4.number_input("Antal spins", min_value=0, step=10, value=int(b.get("antal_spins") or 0))
    spinv = c5.number_input("Värde per spin (kr)", min_value=0.0, step=0.5, value=float(b.get("spinvarde_kr") or 0))
    bonus = c6.number_input("Bonusbelopp (kr)", min_value=0.0, step=100.0, value=float(b.get("bonus_kr") or 0))
    ins = c7.number_input("Minsta insättning (kr)", min_value=0.0, step=50.0,
                          value=float(b.get("min_insattning_kr") or 0))
    anteckning = st.text_input("Anteckning", value=(m["granskningar"].get(b["nyckel"]) or {}).get("anteckning", ""))
    g1, g2, g3 = st.columns(3)
    godkann = g1.form_submit_button("Spara och godkänn", type="primary", icon=":material/check:", width="stretch")
    avvisa = g2.form_submit_button("Avvisa", icon=":material/block:", width="stretch")
    nollstall = g3.form_submit_button("Ta bort min granskning", icon=":material/restart_alt:", width="stretch")

if godkann or avvisa:
    m["granskningar"][b["nyckel"]] = {
        "omsattning_pa": pa, "omsattning_x": x or None, "insattning_1x": ettx,
        "antal_spins": spins or None, "spinvarde_kr": spinv or None, "bonus_kr": bonus or None,
        "min_insattning_kr": ins or None, "godkand": bool(godkann), "anteckning": anteckning,
        "datum": lagring.nu()[:10],
    }
    ui.spara(m, "Godkänt." if godkann else "Avvisat.")
    st.rerun()
if nollstall:
    m["granskningar"].pop(b["nyckel"], None)
    ui.spara(m, "Granskningen borttagen.")
    st.rerun()
