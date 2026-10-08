"""Tester för EV, urval, sidval, textutdrag och registernormalisering."""

from bonusapp import ev, register_se, sidhitta, text, urval


def test_ev_omsattningsfria_spins():
    v, _ = ev.berakna({"antal_spins": 100, "spinvarde_kr": 1.0, "omsattning_pa": "ingen"}, rtp=0.96)
    assert v == 96.0


def test_ev_antaget_spinvarde_och_tak():
    v, forkl = ev.berakna({"antal_spins": 200, "omsattning_pa": "ingen", "maxvinst_kr": 100}, rtp=0.96, spinvarde=2)
    assert v == 100.0 and "antaget" in forkl and "tak" in forkl


def test_ev_bonus_med_omsattning_golvas():
    v, _ = ev.berakna({"bonus_kr": 1000, "omsattning_pa": "bonus", "omsattning_x": 35}, rtp=0.96)
    assert v == 0.0
    v, _ = ev.berakna({"bonus_kr": 1000, "omsattning_pa": "bonus", "omsattning_x": 10}, rtp=0.96)
    assert v == 600.0


def test_ev_1x_insattning_kostar():
    v, _ = ev.berakna({"antal_spins": 50, "spinvarde_kr": 1, "omsattning_pa": "ingen",
                       "insattning_1x": True, "min_insattning_kr": 100}, rtp=0.96)
    assert v == 44.0


def test_ev_insattningskrav_varderas_inte():
    assert ev.berakna({"bonus_kr": 100, "omsattning_pa": "insattning"})[0] is None


def _b(**kw):
    bas = {"nyckel": "k", "doman": "x.se", "titel": "t", "bolag_id": "se:1", "svensk_licens": True,
           "omsattning_pa": "ingen", "sakerhet": "hög", "accepterar_se": True}
    return {**bas, **kw}


def test_kategorier():
    assert urval.kategori(_b()) == "omsättningsfri"
    assert urval.kategori(_b(omsattning_pa="bonus")) == "omsättning bonus"
    assert urval.kategori(_b(omsattning_pa="insattning")) == "insättning"
    assert urval.kategori(_b(insattning_1x=True)) == "1x insättning"
    assert urval.kategori(_b(omsattning_pa=None)) == "granska"
    assert urval.kategori(_b(sakerhet="låg")) == "granska"
    assert urval.kategori(_b(sakerhet="låg", granskad=True)) == "omsättningsfri"


def test_anvant_galler_hela_svenska_bolaget():
    mina = {"anvanda": {"bolag:se:1": {}}, "installningar": {}, "dolda": {}, "granskningar": {}}
    syster = urval.effektiv(_b(doman="syster.se"), mina)
    assert urval.ar_anvand(syster, mina) and not urval.visas(syster, mina)
    eu = urval.effektiv(_b(doman="eu.com", svensk_licens=False, bolag_id="mga:1"), mina)
    assert not urval.ar_anvand(eu, mina)


def test_1x_visas_bara_med_reglage():
    mina = {"anvanda": {}, "installningar": {"visa_1x": False}, "dolda": {}, "granskningar": {}}
    b = urval.effektiv(_b(insattning_1x=True), mina)
    assert not urval.visas(b, mina)
    mina["installningar"]["visa_1x"] = True
    assert urval.visas(b, mina)


def test_granskning_overstyr():
    mina = {"anvanda": {}, "installningar": {}, "dolda": {},
            "granskningar": {"k": {"omsattning_pa": "insattning", "godkand": True}}}
    assert urval.effektiv(_b(), mina)["kategori"] == "insättning"


def test_normalisera_registeradress():
    assert register_se.normalisera("www.Betsson.com/sv") == ("betsson.com", "https://www.betsson.com/sv")
    assert register_se.normalisera("se.megacasino.com") == ("se.megacasino.com", "https://se.megacasino.com")
    assert register_se.normalisera("App: GGPoker") is None


def test_sidval_foredrar_bonusvillkor_och_svenska():
    lankar = [
        ("https://kasino.se/sv/bonusvillkor", "Bonusvillkor"),
        ("https://kasino.se/en/bonus-terms", "Bonus terms"),
        ("https://kasino.se/sv/kampanjer", "Kampanjer"),
        ("https://kasino.se/sv/logga-in", "Logga in"),
        ("https://annan.se/bonus", "Bonus"),
        ("https://kasino.se/sv/allmanna-villkor", "Allmänna villkor"),
    ]
    valda = sidhitta.valj(lankar, "kasino.se", "https://kasino.se/sv", 4)
    assert valda[0] == "https://kasino.se/sv/bonusvillkor"
    assert "https://kasino.se/sv/logga-in" not in valda and "https://annan.se/bonus" not in valda
    assert valda.index("https://kasino.se/sv/kampanjer") < valda.index("https://kasino.se/en/bonus-terms")


def test_text_tar_med_inbaddad_json():
    html = """<html lang="sv"><body><div id="root"></div>
    <script id="__NEXT_DATA__" type="application/json">{"props":{"t":"<p>100 freespins utan omsättningskrav</p>"}}</script>
    <a href="/kampanjer">Kampanjer</a></body></html>"""
    t, lankar, sprak = text.extrahera(html, "https://kasino.se/")
    assert "100 freespins utan omsättningskrav" in t
    assert ("https://kasino.se/kampanjer", "Kampanjer") in lankar and sprak == "sv"


def test_alt_text_och_kampanjsubdoman():
    t, _, _ = text.extrahera('<html><body><img alt="100% up to €44 + 44 FREE SPINS"></body></html>', "https://k.se/")
    assert "44 FREE SPINS" in t
    assert sidhitta.poang("https://offers.k.com/sv", "") >= 8


def test_spelkatalog_prioriteras_ner_och_vanliga_adresser():
    assert sidhitta.poang("https://k.com/sv/casino/online-spelautomater/welcome-fortune", "Welcome Fortune") <= 4
    assert ("https://k.com/sv/kampanjer/", "kampanjer") in sidhitta.vanliga_adresser("https://k.com/sv/index")
