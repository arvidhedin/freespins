"""Tolkningen av bonustext. Exemplen efterliknar formuleringar som finns på riktiga kasinosidor (okt 2026)."""

import pytest

from bonusapp import tolka


def _hitta(text: str, allmant: str = "") -> dict[str, dict]:
    sidor = [("https://k.se/kampanj", text)] + ([("https://k.se/villkor", allmant)] if allmant else [])
    return {b["typ"]: b for b in tolka.hitta(sidor, "k.se")}


def test_omsattningsfria_spins_med_insattning():
    b = _hitta("Välkomstbonus\n100 omsättningsfria free spins på Book of Dead\n"
               "Gör din första insättning på minst 100 kr. Spinsen är värda 1 kr styck.")["freespins"]
    assert (b["antal_spins"], b["spinvarde_kr"], b["spel"], b["min_insattning_kr"]) == (100, 1.0, "Book of Dead", 100.0)
    assert (b["omsattning_pa"], b["sakerhet"], b["utan_insattning"]) == ("ingen", "hög", False)


def test_bonus_och_spins_tolkas_var_for_sig():
    r = _hitta("100% bonus upp till 2 000 kr + 50 freespins\nBonusen måste omsättas 35 gånger. "
               "Vinster från freespins har inget omsättningskrav. Minsta insättning 200 kr.")
    assert (r["bonuspengar"]["bonus_kr"], r["bonuspengar"]["omsattning_pa"], r["bonuspengar"]["omsattning_x"]) == (2000, "bonus", 35)
    assert r["freespins"]["omsattning_pa"] == "ingen"
    assert r["freespins"]["min_insattning_kr"] == 200


@pytest.mark.parametrize("text, x", [
    ("Få 100% upp till 1000 kr\nOmsättningskrav 30x (insättning + bonus) inom 30 dagar.", 30),
    ("100% bonus upp till 500 kr\nBonus + insättning måste omsättas 20 gånger.", 20),
    ("300% upp till 600 kr\nInsättning + bonus måste omsättas x20 i Casino & Live Casino.", 20),
    ("100% bonus upp till 500 kr\nBåde bonus- och insättningsbeloppen måste vardera omsättas 20 gånger före uttag.", 20),
    ("100% upp till 5 000 kr\nInsättning måste omsättas femton (15) gånger innan bonusen betalas ut.", 15),
    ("100% upp till 4 000 kr + 100 gratisspins\nNär första insättningen är gjord måste spelaren omsätta en summa "
     "motsvarande sin insättning 10x i casinot innan spelaren kan hämta bonusen.", 10),
    ("100% upp till 1 000 kr\nFör att motta bonusen behöver man omsätta sin första insättning sex gånger.", 6),
    ("100% upp till 1 000 kr\nInsättning behöver omsättas 25x", 25),
    ("Deposit bonus 100% up to €200\nThe deposit and bonus must be wagered 35 times.", 35),
])
def test_krav_pa_insattningen_utesluts(text, x):
    for b in _hitta(text).values():
        assert b["omsattning_pa"] == "insattning", b["skal"]
        assert b["omsattning_x"] == x


def test_spins_utan_omsattning_men_lasta_av_insattningskrav():
    r = _hitta("Bonus + insättning måste omsättas 20x i Casino + 100 omsättningsfria spins på Book of Dead värde 1kr/spin")
    assert r["freespins"]["omsattning_pa"] == "insattning"


def test_konflikt_med_annat_erbjudande_gar_till_granskning():
    # Spinsen är omsättningsfria, men ett annat erbjudande på sajten har krav på insättningen.
    r = _hitta("FÅ 25 FREESPINS\nGör en första insättning på minst 100 kr så får du 25 Freespins värda 4 kr styck, "
               "helt utan omsättningskrav.", allmant="Kod MRDUBBEL\nInsättning behöver omsättas 25x")
    b = r["freespins"]
    assert (b["omsattning_pa"], b["sakerhet"], b["spinvarde_kr"]) == ("ingen", "låg", 4.0)


def test_1x_penningtvatt_flaggas():
    r = _hitta("25 freespins helt utan omsättningskrav\nGör en insättning på minst 100 kr.",
               allmant="Varje insättning måste omsättas minst en gång.")
    b = r["freespins"]
    assert b["omsattning_pa"] == "ingen" and b["insattning_1x"]
    r = _hitta("50 freespins utan omsättningskrav vid insättning på 100 kr\nInsättning behöver omsättas x1")
    assert r["freespins"]["insattning_1x"] and r["freespins"]["omsattning_pa"] == "ingen"


def test_spela_for_egna_pengar_for_att_lasa_upp():
    r = _hitta("50 Freespins på Book Of Dead\nEfter första insättning måste du spela för 500 kr på slots för att få "
               "50 Freespins (värda 5 kr/st), utan omsättningskrav på vinsterna.")
    assert r["freespins"]["omsattning_pa"] == "insattning"


@pytest.mark.parametrize("text, pa, x", [
    ("40 free spins i Big Bass Bonanza värda 1 kr per snurr, omsättning 10 gånger.", "vinster", 10),
    ("Omsättningskrav för Free Spins i Big Bass Bonanza är 10 gånger.\n40 free spins vid registrering", "vinster", 10),
    ("50 free spins without deposit on Starburst\nWinnings must be wagered 40 times. Max win €100.", "vinster", 40),
    ("Registrera dig och få 20 gratissnurr\nVid registrering. Omsättningskrav 25x.", "vinster", 25),
    ("100 Free Spins on Big Bass Splash\nWinnings from Free Spins are paid as cash amounts without any wagering requirements.",
     "ingen", None),
    ("25 freespins\nPotentiella vinster från freespins behöver inte omsättas.", "ingen", None),
    ("50 kontantspinn på Starburst vid din första insättning", "ingen", None),
])
def test_freespins(text, pa, x):
    b = _hitta(text)["freespins"]
    assert (b["omsattning_pa"], b["omsattning_x"]) == (pa, x), b["skal"]


def test_no_deposit_maxvinst_i_euro():
    b = _hitta("50 free spins without deposit on Starburst\nWinnings must be wagered 40 times. Max win €100.")["freespins"]
    assert b["utan_insattning"] and b["maxvinst_kr"] == 1100 and b["spel"] == "Starburst"


def test_generiskt_krav_i_samma_mening_som_insattningen_blir_osakert():
    b = _hitta("Sätt in 100 kr och få 50 freespins på Pirots 5 (2kr/spinn) med 10x omsättningskrav.")["freespins"]
    assert b["sakerhet"] == "låg" and b["spinvarde_kr"] == 2.0 and b["min_insattning_kr"] == 100
    b = _hitta("Sätt in 100 kr – få 50 freespins på Pirots 5 (2kr/spinn) med endast 1x omsättningskrav.")["freespins"]
    assert (b["omsattning_pa"], b["omsattning_x"], b["sakerhet"]) == ("vinster", 1, "medel")


def test_maxvinst_utan_valuta_ar_inget_belopp():
    assert _hitta("100 omsättningsfria spins\nMaxvinsten på gratismarkerna är 10x.")["freespins"]["maxvinst_kr"] is None


def test_bonus_med_omsattning_pa_bonusen():
    b = _hitta("100% bonus upp till 1 000 kr\nFör att ta ut vinster måste du först omsätta din bonus 30 gånger.")["bonuspengar"]
    assert (b["omsattning_pa"], b["omsattning_x"], b["bonus_kr"], b["matchprocent"]) == ("bonus", 30, 1000, 100)


def test_generisk_bonus_och_spins_30x_wagering():
    r = _hitta("100% up to €100 + 100 Free Spins\nYour bonus and any winnings from Free Spins will be credited as "
               "generic bonus with 30x wagering requirements.")
    assert r["bonuspengar"]["bonus_kr"] == 1100
    assert (r["bonuspengar"]["omsattning_pa"], r["bonuspengar"]["omsattning_x"]) == ("bonus", 30)
    assert (r["freespins"]["omsattning_pa"], r["freespins"]["omsattning_x"]) == ("vinster", 30)


def test_maxinsats_ar_inte_spinvarde():
    b = _hitta("100 omsättningsfria spins på Book of Dead\nDu får maximalt satsa 50 kronor per spinn i Casinot.")["freespins"]
    assert b["spinvarde_kr"] is None


def test_ankare_med_adjektiv_och_sammansattningar():
    assert _hitta("plus 150 elektriska gratissnurr i spelet Deeper Money Bass")["freespins"]["antal_spins"] == 150
    assert _hitta("100% upp till 2000 kr + 40 Jackpottspins")["freespins"]["antal_spins"] == 40
    assert "freespins" not in _hitta("Du får maximalt satsa 50 kronor per spinn.")


def test_inget_om_omsattning_gar_till_granskning():
    b = _hitta("100 free spins på Book of Dead vid första insättningen")["freespins"]
    assert b["omsattning_pa"] is None and b["sakerhet"] == "låg"


def test_spelfunktioner_ar_inte_erbjudanden():
    assert _hitta("Slotten har 10 free spins som bonus feature när tre scatter landar.") == {}


def test_spelbeskrivning_med_gratissnurr_ar_inget_erbjudande():
    text = ("I detta spel expanderar Horus Wilds över hjulen, medan Temple Scatters utlöser 12 gratissnurr.\n"
            "Alla vinster betalas ut i riktiga pengar och det finns INGA omsättningskrav.")
    assert _hitta(text) == {}


def test_erbjudande_i_guide_ska_granskas():
    sidor = [("https://k.se/sv/casinoguiden/free-spins-vad-det-ar", "Alla nya användare får 99 free spins utan omsättningskrav")]
    b = tolka.hitta(sidor, "k.se")[0]
    assert b["omsattning_pa"] == "ingen" and b["sakerhet"] == "låg"


def test_wager_free_spins_galler_inte_bonusen():
    r = _hitta("Welcome Bonus 150% up to €100 + 10 Wager Free Spins")
    assert r["freespins"]["omsattning_pa"] == "ingen"
    assert r["bonuspengar"]["omsattning_pa"] != "ingen" and r["bonuspengar"]["bonus_kr"] == 1100


def test_spinvarde_med_valuta_fore_och_pund():
    b = _hitta("100 free spins on Gates of Olympus at €0.20 per spin\nNo wagering on winnings.")["freespins"]
    assert b["spinvarde_kr"] == 2.2
    assert _hitta("Welcome Bonus 25% up to £50 + 25 Free Spins")["bonuspengar"]["bonus_kr"] == 650


def test_sport_intervall_och_jackpott_ignoreras():
    assert _hitta("Sports Welcome Offer – 100% Up to €250!") == {}
    assert _hitta("Players can win randomly 5-500 Free Spins.") == {}
    assert "bonuspengar" not in _hitta("100% bonus up to €15 000 jackpot")


def test_nekad_no_deposit():
    b = _hitta("Our casino does not offer no-deposit bonuses.\n100% bonus up to €300 on your first deposit")
    assert all(not x["utan_insattning"] for x in b.values())


def test_generella_villkor_som_inte_galler_valkomst_blir_osakra():
    r = _hitta("100% match bonus up to €300 on your first deposit",
               allmant="Cashback winnings must be wagered 1 times.")
    assert r["bonuspengar"]["sakerhet"] == "låg"
    r = _hitta("100% match bonus up to €300 on your first deposit",
               allmant="The welcome bonus must be wagered 35 times.")
    assert (r["bonuspengar"]["omsattning_pa"], r["bonuspengar"]["omsattning_x"], r["bonuspengar"]["sakerhet"]) == ("bonus", 35, "medel")


def test_generiskt_kort_och_villkor_om_insattningen():
    r = _hitta("Casino: 100% upp till 500 kr\n20x omsättningskrav",
               allmant="Välkomstbonus: när första insättningen är gjord måste spelaren omsätta summan av sin insättning 20x innan bonusen kan hämtas.")
    assert r["bonuspengar"]["omsattning_pa"] == "insattning"


def test_uttryckligt_krav_vinner_over_omsattningsfritt_pa_annan_sida():
    sidor = [("https://k.se/", "100% upp till 1500 kr när du sätter in minst 200 kr. Spela utan omsättningskrav!"),
             ("https://k.se/bonus", "100% UPP TILL 1500 KR\nSätt in minst 200 kr och få dubbelt att spela för. Omsättningskrav: 35x")]
    b = next(x for x in tolka.hitta(sidor, "k.se") if x["typ"] == "bonuspengar")
    assert (b["omsattning_pa"], b["omsattning_x"], b["sakerhet"]) == ("bonus", 35, "låg")


def test_spela_for_insattningens_belopp_ar_1x():
    r = _hitta("FÅ 50 FREESPINS\nGör en första insättning på minst 500 kr och spela för 500 kr på slots för att få "
               "50 Freespins (värda 5 kr/st), utan omsättningskrav på vinsterna.")
    b = r["freespins"]
    assert (b["omsattning_pa"], b["insattning_1x"], b["min_insattning_kr"]) == ("ingen", True, 500)


def test_kronor_i_valkomsterbjudande():
    b = _hitta("Få 100 kronor i välkomsterbjudande när du sätter in 100 kr. Inga omsättningskrav.")["bonuspengar"]
    assert b["bonus_kr"] == 100 and b["omsattning_pa"] == "ingen"


def test_satt_in_och_spela_for_ar_1x():
    b = _hitta("150 freespins\nSätt in och spela för 300 kr på Book of Dead så får du 150 OMSÄTTNINGSFRIA freespins.")["freespins"]
    assert b["omsattning_pa"] == "ingen" and b["insattning_1x"]


def test_villkor_med_samma_antal_spins_kopplas():
    r = _hitta("99 free spins i Golden Joker vid din första insättning",
               allmant="Alla nya kunder får 99 freespins. Freespinsen är värda 1 kr styck, de är omsättningsfria och giltiga i 60 dagar.")
    assert r["freespins"]["omsattning_pa"] == "ingen" and r["freespins"]["sakerhet"] in ("hög", "medel")


def test_utlandsk_valuta_flaggas():
    assert _hitta("WELCOME PACKAGE 100% up to €100 + 50 Free Spins\n10x Bonus")["bonuspengar"]["utlandsk_valuta"]
    assert not _hitta("100% upp till 1000 kr + 50 freespins\n10x bonusen")["bonuspengar"]["utlandsk_valuta"]


def test_beskrivning_av_insattning_och_bonus_utan_multipel_ar_inget_krav():
    r = _hitta("100 freespins på Pirots 4 vid första insättningen\nVinsterna måste omsättas 20 gånger.",
               allmant="Omsättningskraven för insättning och bonus beskrivs i de bonusspecifika villkoren.")
    assert (r["freespins"]["omsattning_pa"], r["freespins"]["omsattning_x"]) == ("vinster", 20)


def test_krav_pa_insattning_och_bonus_utan_tal_i_villkoren():
    r = _hitta("100% bonus upp till 1000 kr\nOmsättningskrav 30x", allmant="Insättning + bonus måste omsättas.")
    assert r["bonuspengar"]["omsattning_pa"] == "insattning"


def test_standardtext_om_mojliga_krav_ar_inget_krav():
    r = _hitta("100 freespins på Pirots 4 vid första insättningen\nVinsterna måste omsättas 20 gånger.",
               allmant="Omsättningskraven för varje bonus beskrivs i de bonusspecifika reglerna, och kommer att anges som en "
                       "multiplikator av bonussumman, eller av summan av bonusen plus insättningsbeloppet, tillsammans med en "
                       "tidsbegränsning inom vilken denna summa måste spelas för.")
    assert r["freespins"]["omsattning_pa"] == "vinster"
