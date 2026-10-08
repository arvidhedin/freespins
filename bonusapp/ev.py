"""Förväntat värde (EV) i kronor för ett erbjudande. Grov uppskattning – se förklaringen per rad.

Antaganden:
- En slot betalar i snitt tillbaka `rtp` (standard 96 %) av insatsen, så husets fördel är h = 1 − rtp.
- Freespins utan omsättning är värda antal × spinvärde × rtp.
- Pengar med omsättningskrav W× tappar i snitt W × belopp × h innan de blir uttagbara. Du kan inte
  förlora mer än bonusen (insättningen omsätts inte), så värdet golvas till 0. Det underskattar lite,
  eftersom man ibland vinner stort tidigt – men räcker för att sortera.
- Måste insättningen spelas igenom 1 gång (penningtvättsregel) kostar det i snitt insättning × h.
- Maxvinst/maxuttag sätter ett tak.
"""

from __future__ import annotations


def berakna(b: dict, rtp: float = 0.96, spinvarde: float = 1.0) -> tuple[float | None, str]:
    """Returnerar (ev_kr, förklaring). ev_kr är None om erbjudandet inte går att värdera."""
    h = 1.0 - rtp
    delar, ev = [], 0.0
    pa, x = b.get("omsattning_pa"), b.get("omsattning_x") or 0

    if pa == "insattning":
        return None, "Omsättningskrav på insättningen – värderas inte."

    if spins := b.get("antal_spins"):
        varde = b.get("spinvarde_kr")
        antaget = varde is None
        varde = spinvarde if antaget else varde
        brutto = spins * varde * rtp
        text = f"{spins} spins × {varde:g} kr{' (antaget)' if antaget else ''} × RTP {rtp:.0%} = {brutto:.0f} kr"
        if pa in ("vinster", "bonus") and x:
            netto = max(0.0, brutto * (1 - x * h))
            text += f", minus omsättning {x:g}× på vinsterna → {netto:.0f} kr"
            brutto = netto
        ev += brutto
        delar.append(text)

    if belopp := b.get("bonus_kr"):
        if pa in ("bonus", "vinster") and x:
            netto = max(0.0, belopp * (1 - x * h))
            delar.append(f"bonus {belopp:g} kr med {x:g}× omsättning → {netto:.0f} kr")
        elif pa == "ingen":
            netto = float(belopp)
            delar.append(f"bonus {belopp:g} kr utan omsättning")
        else:
            netto = None
            delar.append(f"bonus {belopp:g} kr med okänt omsättningskrav – inte värderad")
        if netto is not None:
            ev += netto

    if b.get("insattning_1x") and (ins := b.get("min_insattning_kr")):
        kostnad = ins * h
        ev -= kostnad
        delar.append(f"insättningen {ins:g} kr omsätts 1× → −{kostnad:.0f} kr")

    if (tak := b.get("maxvinst_kr")) and ev > tak:
        ev = float(tak)
        delar.append(f"tak (maxvinst) {tak:g} kr")

    if not delar:
        return None, "Ingen beloppsuppgift hittades."
    return round(ev, 1), "; ".join(delar)
