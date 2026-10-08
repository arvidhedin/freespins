"""Bonussökaren – freespins och kasinobonusar utan omsättningskrav på insättningen.

Starta med:  streamlit run app.py   (eller dubbelklicka på start.command)
Allt körs lokalt på http://localhost:8503.
"""

import importlib
import sys
from pathlib import Path

import streamlit as st

# Ladda om bonusapp-modulerna när någon av dem ändrats, så att appen aldrig kör blandade versioner.
_MODULER = ["lagring", "text", "ev", "notis", "schema", "register_se", "register_eu", "hamta", "sidhitta",
            "geo", "tolka", "urval", "skanna", "ui"]
_tider = {m: Path(__file__).parent.joinpath("bonusapp", f"{m}.py").stat().st_mtime for m in _MODULER}
if any(f"bonusapp.{m}" in sys.modules for m in _MODULER) and st.session_state.get("_modultider") != _tider:
    for m in _MODULER:
        if f"bonusapp.{m}" in sys.modules:
            importlib.reload(sys.modules[f"bonusapp.{m}"])
    st.cache_data.clear()
st.session_state["_modultider"] = _tider

from bonusapp import ui  # noqa: E402

st.set_page_config(page_title="Bonussökaren", page_icon=":material/casino:", layout="wide")
ui.injicera_css()

sida = st.navigation({
    "": [
        st.Page("sidor/bonusar.py", title="Bonusar", icon=":material/redeem:", default=True),
        st.Page("sidor/granska.py", title="Granska", icon=":material/rule:"),
        st.Page("sidor/kasinon.py", title="Kasinon", icon=":material/storefront:"),
        st.Page("sidor/data.py", title="Sökning och inställningar", icon=":material/sync:"),
    ],
}, position="top")
sida.run()
