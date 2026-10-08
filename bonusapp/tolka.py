"""Regelbaserad tolkning av bonustext: hittar erbjudanden och var omsättningskravet ligger.

Varje sida delas i rader. Rader som nämner ett antal freespins, en procentbonus eller ett bonusbelopp
blir "ankare". Från ankaret tas ett textfönster (fram till nästa erbjudande) som delas i meningar.
Varje mening tolkas för sig, så att "Bonusen ska omsättas 35x" inte smittar freespinsen i samma
erbjudande. Utöver fönstret används kasinots generella villkor ("allmänt": alla meningar på de lästa
sidorna som handlar om omsättning).

Omsättningskrav på:
  ingen       – "utan omsättningskrav", "omsättningsfria", "behöver inte omsättas", "wager-free" …
  insattning  – krav på insättning + bonus, på insättningen fler än 1 gång, eller "spela för 500 kr
                för att få spinsen" (egna pengar måste omsättas)
  1x          – insättningen måste spelas igenom 1 gång före uttag (penningtvätt) – egen flagga
  bonus       – "35x bonusbeloppet", "bonusen måste omsättas 35 gånger" …
  vinster     – "vinsterna från freespins ska omsättas 20 gånger", "omsättningskrav för free spins 10x" …

Ett erbjudande med både bonuspengar och freespins delas upp i två poster. Osäkra fall och konflikter
(t.ex. "omsättningsfria spins" på en sida där villkoren kräver omsättning av insättningen) får
säkerhet "låg" och hamnar under Granska i appen.
"""

from __future__ import annotations

import hashlib
import re

# Ungefärliga kurser för att kunna jämföra erbjudanden i andra valutor.
KURS = {"eur": 11.0, "gbp": 13.0, "usd": 10.0}
EUR_SEK = KURS["eur"]
MAX_BONUS_KR = 30_000  # större belopp är jackpottar/VIP-nivåer, inte välkomstbonusar

TALORD = {
    "en": 1, "ett": 1, "one": 1, "once": 1, "två": 2, "two": 2, "twice": 2, "tre": 3, "three": 3, "fyra": 4,
    "four": 4, "fem": 5, "five": 5, "sex": 6, "six": 6, "sju": 7, "åtta": 8, "nio": 9, "tio": 10, "ten": 10,
    "elva": 11, "tolv": 12, "femton": 15, "fifteen": 15, "tjugo": 20, "twenty": 20, "tjugofem": 25,
    "twenty-five": 25, "trettio": 30, "thirty": 30, "trettiofem": 35, "thirty-five": 35, "fyrtio": 40,
    "forty": 40, "fyrtiofem": 45, "femtio": 50, "fifty": 50, "sextio": 60, "sixty": 60,
}
_TALORD = "|".join(sorted(TALORD, key=len, reverse=True))
# Antal gånger: "35", "x35", "tio (10)", "minst en"
ANTAL = rf"(\d{{1,3}}|{_TALORD})(?:\s*\(\d{{1,3}}\))?"
GANGER = r"(?:x|×|ggr|gånger|gång|times|time)"
TAL = r"\d{1,3}(?:[  .,]\d{3})+(?:[.,]\d+)?(?!\d)|\d+(?:[.,]\d+)?"
VALUTA = r"(?:kr\b|kronor|sek\b|:-|€|eur\b|euro|£|gbp\b|\$|usd\b)"
OMS = r"(?:omsättning\w*|omsätt\w*|omsatt\w*|satsningskrav\w*|wager\w*|playthrough|play[- ]through|rollover|turn(?:ed)?\s?over)"
INS = r"(?:insättning\w*|insatta\s+(?:pengar\w*|medel\w*|belopp\w*)|deposit\w*)"

# --- ankare ----------------------------------------------------------------------------------
_ADJ = r"(?:(?:extra|gratis|bonus|free|wager[- ]?free|cash|nya|riktiga|[a-zåäö-]{3,}(?:a|e))\s+){0,2}?"
SPINS = re.compile(
    rf"(?<![\d.,\-–])(\d{{1,4}})\s*(?:st\.?\s+|stycken\s+)?{_ADJ}"
    rf"(?:free[ -]?spins?|[a-zåäö]{{0,12}}(?:spins?|spinn|snurr))\b", re.I)
PROCENT = re.compile(rf"(\d{{2,3}})\s?%\s*(?:insättningsbonus|(?:max)?bonus|deposit\s+bonus|match\w*|"
                     rf"(?:\w+\s+){{0,4}}?(?:upp\s+till|up\s+to))", re.I)
UPP_TILL = re.compile(
    rf"(?:upp\s+till(?:\s+max)?|up\s+to|maxbonus(?:\s+är)?|bonus\w*\s+(?:på|of|worth))\s+({VALUTA}\s?)?({TAL})\s?({VALUTA})?",
    re.I)
BONUSBELOPP = re.compile(rf"\bbonus\w*\s+(?:på|of|worth)\s+(?:upp\s+till\s+)?({VALUTA}\s?)?({TAL})\s?({VALUTA})", re.I)
KONTANT_BONUS = re.compile(rf"({VALUTA}\s?)?({TAL})\s?({VALUTA})\s+(?:i\s+)?(?:bonus|bonuspengar|casinobonus|bonus\s+money|"
                           rf"välkomsterbjudande|välkomstbonus|spelpengar|gratisspel|welcome\s+bonus)",
                           re.I)

# --- omsättning -------------------------------------------------------------------------------
INGEN = re.compile(
    r"utan\s+(?:några\s+|något\s+)?omsättning\w*|omsättningsfri\w*|(?:inga|inget|ingen|noll)\s+omsättning\w*|"
    r"varken\s+(?:några\s+)?omsättning\w*|(?:behöver|måste)\s+inte\s+omsättas|"
    r"(?<![\d.,])(?:0|noll)\s?x\s+omsättning|omsättningskrav\w*\s*(?::|på|är)?\s*(?<![\d.,])(?:0|noll)\s?x?\b(?!\d)|"
    r"wager[- ]?free|no[- ]wager(?:ing)?|without\s+(?:any\s+)?wagering|zero\s+wagering|(?<![\d.,])0\s?x\s+wagering|no\s+wagering|"
    r"no\s+wagering\s+requirements?|(?:need|needs)\s+not\s+be\s+wagered|do(?:es)?\s+not\s+need\s+to\s+be\s+wagered|"
    r"kontant(?:spinn|snurr|spins)\w*|cash[ -]?spins?|"
    r"vinster(?:na)?\s+(?:\w+\s+){0,4}(?:betalas|utbetalas|sätts\s+in|krediteras)\s+(?:ut\s+)?(?:direkt\s+)?"
    r"(?:som|i|till\s+ditt?)\s+(?:riktiga|kontanta|uttagbara)?\s*(?:pengar|saldo|kontosaldo)|"
    r"winnings\s+(?:are\s+)?(?:paid|credited)\s+(?:out\s+)?(?:as|in)\s+(?:real\s+)?(?:cash|money)", re.I)
INS_PLUS_BONUS = re.compile(
    rf"{INS}\s*(?:\+|och|samt|plus|and|&)\s*bonus\w*|bonus\w*-?\s*(?:\+|och|samt|plus|and|&)\s*{INS}|"
    r"\(\s*(?:d|i)\s*\+\s*b\s*\)|\(\s*b\s*\+\s*(?:d|i)\s*\)", re.I)
# "Insättningen måste omsättas 10 gånger", "Varje insättning måste omsättas minst en gång", "Insättning behöver omsättas x1"
INS_NX = re.compile(
    rf"{INS}\s+(?:(?!vinst|winning|bonus)\w+\s+){{0,2}}?(?:måste|ska|skall|behöver|bör|must|has\s+to|have\s+to|needs?\s+to|should)\s+"
    rf"(?:\w+\s+){{0,2}}?(?:omsättas|spelas\s+(?:igenom|över)|vändas|be\s+(?:wagered|played\s+through|turned\s+over|rolled\s+over))"
    rf"\s+(?:minst\s+|at\s+least\s+)?(?:x\s?)?{ANTAL}", re.I)
# "omsätta en summa motsvarande sin insättning 10x", "omsätta sin första insättning sex gånger", "wager your deposit 5 times"
OMSATT_INS = re.compile(
    rf"(?:omsätta|spela\s+igenom|satsa|wager|play\s+through|turn\s+over|roll\s+over)\s+(?:\w+\s+){{0,5}}?"
    rf"(?:sin|din|hela|sina|dina|summan\s+av|motsvarande|your|the)\s+(?:\w+\s+){{0,2}}?{INS}\s+"
    rf"(?:\w+\s+){{0,2}}?(?:minst\s+|at\s+least\s+)?(?:x\s?)?{ANTAL}\s?{GANGER}", re.I)
INS_X = re.compile(rf"\b{ANTAL}\s?{GANGER}\s+(?:\w+\s+){{0,1}}?(?:insättning(?:en|sbeloppet)?|(?:the\s+|your\s+)?deposit(?:\s+amount)?)\b"
                   rf"(?!\s*(?:\+|och|samt|plus|and|&)\s*bonus)|{INS}\s+x\s?(\d{{1,3}})\b", re.I)
INSATTA_PENGAR = re.compile(r"insatta\s+(?:pengars|medels)\s+omsättningskrav", re.I)
# "måste du spela för 500 kr på slots för att få 50 Freespins"
SPELA_FOR = re.compile(
    rf"(?:måste|behöver|ska)\s+(?:du|man|spelaren)\s+(?:\w+\s+){{0,3}}?(?:spela|satsa|omsätta)\s+(?:för\s+)?(?:minst\s+)?"
    rf"({TAL})\s?{VALUTA}\s+(?:\w+\s+){{0,5}}?för\s+att\s+(?:få|ta\s+del|låsa\s+upp|hämta|aktivera)|"
    rf"(?:wager|play|bet)\s+(?:at\s+least\s+)?({VALUTA}\s?)?({TAL})\s?({VALUTA})?\s+(?:\w+\s+){{0,5}}?(?:to\s+(?:get|unlock|receive|claim))|"
    rf"(?:och|sedan|därefter)\s+(?:spela|satsa|omsätt\w*)\s+(?:för\s+)?(?:minst\s+)?({TAL})\s?{VALUTA}\s+(?:\w+\s+){{0,5}}?"
    rf"för\s+att\s+(?:få|ta\s+del|låsa\s+upp|hämta|aktivera)|"
    rf"\b(sätt\s+in\s+och\s+)?spela\s+för\s+(?:minst\s+)?({TAL})\s?{VALUTA}(?!\s+(?:gratis|helt\s+gratis|i\s+gratis))",
    re.I)
X_BONUS = re.compile(
    rf"{ANTAL}\s?{GANGER}\s+(?:\w+\s+){{0,2}}?(?:bonus(?:en|beloppet|summan|pengarna)?|bonus\s+amount|the\s+bonus|bonus\s+funds)"
    rf"(?!\s*-?\s*(?:\+|och|samt|plus|and|&)\s*{INS})|"
    rf"bonus(?:en|beloppet|summan|pengarna)?\s+(?:\w+\s+){{0,4}}?(?:måste|ska|behöver|must|has\s+to|needs?\s+to)\s+"
    rf"(?:\w+\s+){{0,2}}?(?:omsättas|spelas\s+igenom|be\s+wagered|be\s+played\s+through)\s+(?:minst\s+)?{ANTAL}\s?{GANGER}?|"
    rf"omsätta\s+(?:din|sin|hela)\s+bonus\w*\s+{ANTAL}\s?{GANGER}|"
    rf"{OMS}\s*(?:krav\w*)?\s*(?:på|of|:|är|om)?\s*{ANTAL}\s?x\s+(?:\w+\s+){{0,1}}?(?:bonus\w*)"
    rf"(?!\s*-?\s*(?:\+|och|samt|plus|and|&)\s*{INS})", re.I)
X_VINSTER = re.compile(
    rf"(?:vinst(?:er|erna)?|winnings)\s+(?:\w+\s+){{0,6}}?(?:måste|ska|behöver|must|has\s+to|needs?\s+to|are\s+subject\s+to)\s+"
    rf"(?:\w+\s+){{0,3}}?(?:omsättas|spelas\s+igenom|be\s+wagered|be\s+played\s+through|{OMS})\s+(?:\w+\s+){{0,2}}?{ANTAL}\s?{GANGER}?|"
    rf"{ANTAL}\s?{GANGER}\s+(?:\w+\s+){{0,2}}?(?:vinst(?:er|erna)?|winnings)", re.I)
X_ALLMAN = re.compile(rf"{OMS}\s*(?:krav\w*|requirements?)?\s*(?:för\s+(?:[\w-]+\s+){{1,5}}?)?(?:på|of|:|är|om|is)?\s*"
                      rf"(?:\w+\s+){{0,2}}?(?:minst\s+)?(?:x\s?)?{ANTAL}\s?{GANGER}|"
                      rf"\b{ANTAL}\s?{GANGER}\s+(?:\w+\s+){{0,1}}?{OMS}|\bx\s?(\d{{1,3}})\b", re.I)

# --- övriga fält ------------------------------------------------------------------------------
UTAN_INS = re.compile(
    r"utan\s+(?:krav\s+på\s+)?insättning|ingen\s+insättning\s+(?:krävs|behövs)|no[- ]deposit|"
    r"without\s+(?:a\s+|making\s+a\s+|any\s+)?deposit|registreringsbonus", re.I)
VID_REGISTRERING = re.compile(r"(?:när|då)\s+du\s+registrerar\s+dig|vid\s+registrering|"
                              r"(?:on|upon|for)\s+(?:registration|sign(?:ing)?[- ]?up)", re.I)
MIN_INS = re.compile(
    rf"(?:minsta|lägsta|min\.?|minimum|minimal)\s+(?:\w+\s+){{0,1}}?(?:insättning\w*|deposit)\s*(?:\w+\s+){{0,4}}?"
    rf"(?:är|på|of|:|is|om)?\s*({VALUTA}\s?)?({TAL})\s?({VALUTA})?|"
    rf"(?:sätt(?:er)?\s+in|insättning\w*\s+(?:på\s+)?(?:min\.?|minst|minimum)?|deposit(?:ing)?)\s+(?:minst\s+|at\s+least\s+|min\.?\s+)?"
    rf"({VALUTA}\s?)?({TAL})\s?({VALUTA})", re.I)
SPINVARDE = re.compile(
    rf"({VALUTA}\s?)?({TAL})\s?({VALUTA})?\s*(?:per|/|i\s+insats\s+per|insats\s+per|each|a)\s*(?:spin|snurr|runda|omgång|free\s?spin|st\b)|"
    rf"(?:spin|snurr)[- ]?(?:värde|värdet|value)\s*(?:är|på|of|:|is)?\s*({VALUTA}\s?)?({TAL})\s?({VALUTA})?|"
    rf"(?:värd(?:a|e)?|worth|valued\s+at|värde|ett\s+värde\s+av)\s+({VALUTA}\s?)?({TAL})\s?({VALUTA})?\s*(?:st(?:yck)?|per|each|/)?",
    re.I)
EJ_SPINVARDE = re.compile(r"max|högsta|maximal|insats|satsa|\bbet\b|stake|insatsgräns|bonus\w*\s+(?:upp|på)", re.I)
MAXVINST = re.compile(
    rf"(?:max(?:imal)?\s?(?:vinst\w*|uttag\w*|utbetalning\w*)|vinsttak\w*|max(?:imum)?\s+(?:win\w*|withdrawal|cash\s?out)|"
    rf"(?:winnings|vinster(?:na)?)\s+(?:are\s+)?(?:capped|begränsade|maximeras)\s+(?:at|till|to))\s*"
    rf"(?:\w+\s+){{0,3}}?(?:är|på|of|:|is|till|om)?\s*({VALUTA}\s?)?({TAL})\s?({VALUTA})?", re.I)
GILTIG = re.compile(
    rf"(?:giltig\w*|gäller|förfaller|måste\s+användas|valid|expire\w*|används\s+inom|på\s+dig|consumed\s+within|"
    rf"used\s+within)\s+(?:\w+\s+){{0,4}}?({TAL}|{_TALORD})(?:\s*\(\d+\))?\s+(dagar|dygn|timmar|days|hours|h)\b", re.I)
SPEL = re.compile(
    r"(?:spins|spinn|snurr|free\s?spins?)\s+(?:\w+\s+){0,2}?(?:på|i|on|in|for|till)\s+"
    r"(?:spelet\s+|slot(?:en)?\s+|the\s+(?:game|slot)\s+|det\s+\w+\s+(?:jackpot-)?spelet\s+)?"
    r"([A-Z0-9][\w'’!&:.-]*(?:\s+(?:of|the|de|la|del|du|des|to|n'|&|[A-Z0-9][\w'’!&:.-]*)){0,5})"
    r"(?=\s*(?:från\b|from\b|by\b|\(|[.,;!\n]|$|och\b|and\b|\+|med\b|with\b|-|–|värd|till\s+ett|at\b|vid\b|när\b|efter\b|upon\b|when\b|if\b|för\b))")
EJ_SPEL = {"Sverige", "Sweden", "Casino", "Kasino", "Live", "Du", "Vi", "Vid", "Din", "Your", "The", "Alla", "All",
           "Casino & Live", "Live Casino", "Casinot"}


# --- hjälpfunktioner --------------------------------------------------------------------------


def _tal(s: str | None) -> float | None:
    if not s:
        return None
    s = s.replace(" ", " ").strip()
    if s.lower() in TALORD:
        return float(TALORD[s.lower()])
    if re.fullmatch(r"\d{1,3}(?:[ .,]\d{3})+", s):   # "1 000", "1.000", "1,000" = tusen
        return float(re.sub(r"[ .,]", "", s))
    try:
        return float(s.replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _belopp(m: re.Match | None, grupper: tuple[int, ...]) -> float | None:
    """Belopp i kr ur en träff; grupper = index för (valuta före, tal, valuta efter) i tur och ordning."""
    if not m:
        return None
    for i in range(0, len(grupper), 3):
        fore, tal, efter = (m.group(g) if 0 <= g <= (m.re.groups or 0) else None for g in grupper[i:i + 3])
        if tal:
            v = _tal(tal)
            if v is None:
                return None
            valuta = f"{fore or ''}{efter or ''}".lower()
            if "€" in valuta or "eur" in valuta:
                v *= KURS["eur"]
            elif "£" in valuta or "gbp" in valuta:
                v *= KURS["gbp"]
            elif "$" in valuta or "usd" in valuta:
                v *= KURS["usd"]
            return round(v, 2)
    return None


def _med_valuta(m: re.Match | None) -> re.Match | None:
    """Bara träffar med en valuta ("Maxvinsten är 10x" är inget belopp)."""
    return m if m and (m.group(1) or m.group(3)) else None


def _forsta(m: re.Match | None) -> str | None:
    if not m:
        return None
    return next((g for g in m.groups() if g), None)


def _ganger(m: re.Match | None) -> float | None:
    return _tal(_forsta(m))


SPINORD = re.compile(r"free[ -]?spins?|[a-zåäö]{0,12}(?:spins?|spinn|snurr)(?:en|et|arna|ar)?\b", re.I)
BONUSORD = re.compile(r"\d\s?%|\bbonus(?:en|beloppet|pengar(?:na)?|summan|belopp)?\b|insättningsbonus\w*|"
                      r"bonus\s+(?:amount|funds|money)|\bmaxbonus", re.I)
INSORD = re.compile(rf"{INS}|sätt(?:er)?\s+in\b", re.I)
VALKOMST = re.compile(r"välkomst|welcome|första\s+insättning|first\s+deposit|nya?\s+(?:spelare|kund)|"
                      r"new\s+(?:player|customer)|sign[- ]?up|registrer", re.I)
_MENING = re.compile(r"(?<=[.!?;])\s+(?=[A-ZÅÄÖ0-9(])|\n|\s[–•·|]\s")


def meningar(text: str) -> list[str]:
    return [m.strip() for m in _MENING.split(text) if m and m.strip()]


def _om(mening: str) -> set[str]:
    """Vilka komponenter en mening handlar om."""
    ut = set()
    if SPINORD.search(mening):
        ut.add("spins")
    if BONUSORD.search(SPINORD.sub(" ", mening)):
        ut.add("bonus")
    return ut


def _insattningskrav(m: str, krav_x: bool = False) -> tuple[float | None, str] | None:
    """Omsättningskrav på egna pengar (mer än 1 gång) i en mening -> (x, skäl).

    krav_x: i allmänna villkor räknas "insättning + bonus" bara om meningen anger hur många gånger –
    annars är det ofta bara en beskrivning ("omsättningskraven för insättning och bonus beskrivs …").
    """
    if INS_PLUS_BONUS.search(m) and re.search(OMS, m, re.I):
        x = _ganger(X_ALLMAN.search(m))
        kravord = re.search(r"\b(?:måste|ska|skall|behöver|must|has\s+to|have\s+to|needs?\s+to)\b", m, re.I)
        # Standardtext som beskriver möjliga varianter ("anges som en multiplikator av bonusen, eller av
        # bonus plus insättning") är inget faktiskt krav.
        beskrivning = krav_x and re.search(r"beskrivs|kommer\s+att\s+anges|anges\s+som|kan\s+(?:vara|anges)|"
                                           r"may\s+be|will\s+be\s+(?:stated|specified|set\s+out)|either|antingen|"
                                           r"\beller\s+(?:av|på)\b|\bor\s+(?:of|on)\s+the", m, re.I)
        if (x or kravord or not krav_x) and not beskrivning:
            return x, "krav på insättning + bonus"
    for monster in (INS_NX, OMSATT_INS, INS_X):
        for t in monster.finditer(m):
            if (x := _ganger(t)) and x > 1:
                return x, f"insättningen ska omsättas {x:g} gånger"
    if INSATTA_PENGAR.search(m):
        return None, "omsättningskrav på insatta pengar"
    return None


def _spela_for(meningslista: list[str], min_ins: float | None) -> tuple[str, float | None, str] | None:
    """"Spela för 500 kr för att få spinsen": egna pengar måste omsättas. Motsvarar beloppet insättningen
    är det 1x-regeln (visas med reglaget); är det mer är det ett krav på insättningen."""
    for m in meningslista:
        if t := SPELA_FOR.search(m):
            belopp = _belopp(t, (99, 1, 99, 2, 3, 4, 99, 5, 99, 99, 7, 99))
            if t.group(6) or (belopp and min_ins and belopp <= min_ins * 1.01):
                # "Sätt in och spela för 300 kr": samma pengar sätts in och spelas igenom = 1 gång.
                return "1x", 1.0, f"du ska spela för {belopp:g} kr (= insättningen) för att få erbjudandet"
            x = round(belopp / min_ins, 1) if belopp and min_ins else None
            return "insattning", x, f"du måste spela för egna pengar för att få erbjudandet (\"{t.group(0)}\")"
    return None


def _ettx(m: str) -> re.Match | None:
    """Insättningen måste omsättas (minst) 1 gång – penningtvättsregeln."""
    for monster in (INS_NX, OMSATT_INS, INS_X):
        for t in monster.finditer(m):
            if _ganger(t) == 1:
                return t
    return None


def _hor_till_spins(m: str, t: re.Match) -> bool:
    """Står omsättningsfriheten ihop med spins ("wager free spins", "spins utan omsättningskrav")?"""
    efter = m[t.end(): t.end() + 25]
    fore = m[max(0, t.start() - 30): t.start()]
    if re.match(r"\s*(?:\w+\s+)?(?:free[ -]?spins?|freespins?|[a-zåäö]{0,12}(?:spins?|spinn|snurr)\b)", efter, re.I):
        return True
    return bool(SPINORD.search(fore)) and not BONUSORD.search(SPINORD.sub(" ", fore))


def _krav_i(m: str, komponent: str, kraver_insattning: bool) -> tuple[str | None, float | None, str, str] | None:
    """Omsättningsuppgift i en mening som handlar om komponenten -> (pa, x, säkerhet, citat)."""
    if _ettx(m) and not INGEN.search(m):
        return None  # "Insättning behöver omsättas x1" är penningtvättsregeln, flaggas separat
    for t in INGEN.finditer(m):
        # "150% up to €100 + 10 Wager Free Spins": omsättningsfriheten hör till spinsen, inte bonusen.
        if komponent == "bonus" and _hor_till_spins(m, t):
            continue
        return "ingen", None, "hög", t.group(0)
    if komponent == "spins" and (t := X_VINSTER.search(m)):
        return "vinster", _ganger(t), "hög", t.group(0)
    if t := X_BONUS.search(m):
        return ("vinster" if komponent == "spins" else "bonus"), _ganger(t), "hög", t.group(0)
    if t := X_ALLMAN.search(m):
        # "Omsättningskrav för Free Spins är 10 gånger" – underlaget står inte uttryckligen.
        oklart = kraver_insattning and INSORD.search(m)
        pa = "vinster" if komponent == "spins" else "bonus"
        return (None if oklart else pa), _ganger(t), ("låg" if oklart else "medel"), t.group(0)
    return None


def _omsattning(fonster: list[str], komponent: str, allmant: list[str],
                utan_insattning: bool, antal: int | None = None) -> tuple[str | None, float | None, str, str]:
    """(omsattning_pa, x, säkerhet, skäl) för en komponent ('spins' eller 'bonus').

    fonster = meningarna från ankaret och framåt, allmant = generella villkorsmeningar.
    """
    kraver_ins = not utan_insattning

    # 1. Krav på egna pengar i själva erbjudandet gäller hela paketet (även spins "utan omsättning",
    #    vars vinster då är låsta tills insättningen är omsatt).
    if kraver_ins:
        for m in fonster:
            if krav := _insattningskrav(m):
                return "insattning", krav[0], "hög", f"{krav[1]}: \"{m[:200]}\""

    # 2. Meningar i erbjudandet som uttryckligen handlar om komponenten.
    lokal = None
    for m in fonster:
        if komponent in _om(m) and (k := _krav_i(m, komponent, kraver_ins)):
            lokal = k
            break
    # 3. Meningar utan komponentord ("Inga omsättningskrav.", "Omsättningskrav 25x.").
    if lokal is None:
        for m in fonster:
            if _om(m):
                continue
            if k := _krav_i(m, komponent, kraver_ins):
                pa, x, sak, citat = k
                if pa is None and komponent == "spins" and utan_insattning:
                    pa, sak = "vinster", "medel"
                lokal = (pa, x, "medel" if sak == "hög" else sak, citat)
                break

    # 4. Kasinots generella villkor: krav på insättningen?
    allm_ins = next(((m, k) for m in allmant if (k := _insattningskrav(m, krav_x=True))), None) if kraver_ins else None
    if lokal:
        pa, x, sak, citat = lokal
        if allm_ins and pa is None:
            # "Omsättningskrav 20×" utan underlag, och villkoren säger att det gäller insättningen.
            return "insattning", x or allm_ins[1][0], "medel", (f"\"{citat}\" – villkoren: {allm_ins[1][1]} "
                                                                f"(\"{allm_ins[0][:160]}\")")
        if allm_ins and sak != "hög" and pa != "ingen":
            # Kortet säger bara "20x omsättningskrav"; villkoren säger att det gäller insättningen.
            return "insattning", x or allm_ins[1][0], "medel", (f"\"{citat}\" – villkoren: {allm_ins[1][1]} "
                                                                f"(\"{allm_ins[0][:160]}\")")
        if allm_ins and pa in ("ingen", "bonus", "vinster"):
            return pa, x, "låg", (f"\"{citat}\" – men villkoren på sajten nämner {allm_ins[1][1]} "
                                  f"(\"{allm_ins[0][:160]}\"); kontrollera vilket erbjudande det gäller")
        return pa, x, sak, f"\"{citat}\""
    if allm_ins:
        return "insattning", allm_ins[1][0], "medel", f"villkoren: {allm_ins[1][1]}: \"{allm_ins[0][:200]}\""

    # 5. Generella villkor. Bara meningar som handlar om välkomstbonusen räknas som "medel"; andra
    #    (cashback, turneringar, penningtvätt …) kan gälla något helt annat och blir "låg".
    traffar = []
    for m in allmant:
        om = _om(m)
        if (komponent in om or not om) and (k := _krav_i(m, komponent, kraver_ins)):
            pa, x, _, citat = k
            samma_antal = bool(antal and re.search(rf"(?<![\d.,]){antal}(?![\d.,])", m))
            if pa == "ingen" and not samma_antal and not re.search(
                    r"\balla\b|samtliga|all\s+(?:our\s+)?(?:bonuses|free\s?spins|offers|winnings)", m, re.I):
                continue  # "omsättningsfria" i allmänna villkor gäller ofta bara vissa kampanjer
            # Nämner meningen samma antal spins ("99 free spins … omsättningsfria") hör den till erbjudandet.
            traffar.append((bool(VALKOMST.search(m)) or samma_antal, pa, x, citat))
    if traffar:
        valkomst = [t for t in traffar if t[0]]
        _, pa, x, citat = (valkomst or traffar)[0]
        olika = len({t[2] for t in (valkomst or traffar)}) > 1
        sak = "medel" if valkomst and pa is not None and not olika else "låg"
        return pa, x, sak, f"villkoren: \"{citat}\"" + (" (villkoren anger flera olika krav)" if olika else "")
    return None, None, "låg", "inget om omsättning hittades"


def _rubrik(rader: list[str], i: int) -> str:
    rad = rader[i]
    if len(rad) < 40 and i + 1 < len(rader):
        rad = f"{rad} {rader[i + 1]}"
    return re.sub(r"\s+", " ", rad).strip()[:160]


def _nyckel(doman: str, b: dict) -> str:
    delar = [doman, b["typ"], b.get("antal_spins"), b.get("bonus_kr")]
    return f"{doman}#" + hashlib.sha1("|".join(map(str, delar)).encode()).hexdigest()[:10]


def _allmant(sidor: list[tuple[str, str]]) -> list[str]:
    """Generella villkor: meningar om omsättning eller penningtvätt från alla lästa sidor."""
    ut, sedda = [], set()
    for _, t in sidor:
        for m in meningar(t):
            if len(m) < 1200 and m not in sedda and re.search(OMS + r"|penningtvätt|money\s+laundering", m, re.I):
                sedda.add(m)
                ut.append(m)
    return ut[:800]


SPORT = re.compile(r"\bsports?\b|\bsportbonus|\bbetting\b|\bodds\b|freebet|free\s+bet|bet\s+builder|"
                   r"spelbonus\s+sport|randomly|slumpmässigt|lotto\b|lottery|lotteri", re.I)
_BRUS = re.compile(r"\b(?:freebet|free\s?bet|odds|tournament|turnering|lotteri|rtp|volatilitet|volatility|"
                   r"scatter|wild|bonusspel\s+med|bonus\s+feature|bonusfunktion|freq|frekvens|hit\s+rate)\b|"
                   r"\b1\s+(?:in|på)\s+\d+", re.I)
SPELFUNKTION = re.compile(r"scatter|\bwilds?\b|utlös|trigg|bonusrunda|bonus\s+round|multiplikator|multiplier|hjul\w*|"
                          r"rull\w*|mönster|\breels?\b|landar|\blands?\b|symbol|megaways|vinstlinje|paylines?|expanderar|"
                          r"gånger\s+insatsen|times\s+(?:the|your)\s+(?:bet|stake)", re.I)
ERBJUDANDEORD = re.compile(r"insättning|sätt\s+in|välkomst|welcome|deposit|registrer|nya?\s+(?:spelare|kund)|"
                           r"new\s+(?:player|customer)|kampanj|erbjud|\bfå\b|\bget\b|claim|hämta|bonuskod|\bkod\b|"
                           r"omsättning|wager", re.I)


def _fonster(rader: list[str], i: int, efter: int = 8, max_tecken: int = 1500) -> tuple[str, str]:
    """(kontext, framåt): en rad före + ankaret + några rader efter, men inte in i nästa erbjudande."""
    stopp = i + efter + 1
    for j in range(i + 3, min(len(rader), stopp)):
        if SPINS.search(rader[j]) or PROCENT.search(rader[j]):
            stopp = j
            break
    framat = "\n".join(rader[i:stopp])[:max_tecken]
    fore = rader[i - 1] if i > 0 and len(rader[i - 1]) < 200 else ""
    return (f"{fore}\n{framat}" if fore else framat), framat


_NEKAD = re.compile(r"(?:not|inte|ej|inga|no\s+longer|doesn'?t|don'?t|aldrig|never)\W+(?:\w+\W+){0,3}$", re.I)


def _utan_insattning(kontext: str, rad: str) -> bool:
    for m in UTAN_INS.finditer(kontext):
        if not _NEKAD.search(kontext[max(0, m.start() - 40): m.start()]):
            break
    else:
        m = None
    if re.search(r"no\s+deposit\s+bonus\s+kan|vad\s+är|what\s+is\s+a", kontext, re.I):
        return False
    return bool(m) or (bool(VID_REGISTRERING.search(rad)) and not INSORD.search(rad))


def _spinvarde(text: str) -> float | None:
    for m in SPINVARDE.finditer(text):
        if EJ_SPINVARDE.search(text[max(0, m.start() - 45): m.start()] + m.group(0)):
            continue
        if not re.search(VALUTA, m.group(0), re.I):
            continue
        v = _belopp(m, (1, 2, 3, 4, 5, 6, 7, 8, 9))
        if v and 0.05 <= v <= 100:
            return v
    return None


def _spel(rad: str, text: str) -> str | None:
    for kalla in (rad, text):
        if (s := SPEL.search(kalla)) and (namn := s.group(1).strip(" .,-")) not in EJ_SPEL and len(namn) >= 3:
            return namn
    return None


def hitta(sidor: list[tuple[str, str]], doman: str) -> list[dict]:
    """sidor = [(url, text)] -> lista med erbjudanden (en post per komponent)."""
    allmant = _allmant(sidor)
    ettx_allm = next((t for m in allmant if (t := _ettx(m))), None)
    hittade: dict[str, dict] = {}

    for url, t in sidor:
        # Långa rader (t.ex. en hel FAQ i en webbkomponent) delas i meningar.
        rader = [d for rad in t.split("\n") for d in (meningar(rad) if len(rad) > 600 else [rad])]
        for i, rad in enumerate(rader):
            if len(rad) > 600 or _BRUS.search(rad):
                continue
            spins_m = SPINS.search(rad)
            proc_m = PROCENT.search(rad)
            belopp_m = BONUSBELOPP.search(rad) or KONTANT_BONUS.search(rad)
            if not (spins_m or proc_m or belopp_m):
                continue
            kontext, framat = _fonster(rader, i)
            if SPELFUNKTION.search(kontext) and not ERBJUDANDEORD.search(rad):
                continue  # spelbeskrivning: "3 scatters ger 10 free spins"
            fore = rader[i - 1] if i > 0 else ""
            if SPORT.search(rad) or re.fullmatch(r"\W*(?:sports?|betting|odds)\W*", fore, re.I):
                continue  # sportbonus
            meningar_framat = meningar(framat)
            utan_ins = _utan_insattning(kontext, rad)
            utlandsk = bool(re.search(r"€|£|\$|\beur\b|\bgbp\b|\busd\b", f"{rad}\n{framat}", re.I)) and \
                not re.search(r"\d\s?(?:kr\b|kronor|sek\b)|\bsek\s?\d", f"{rad}\n{framat}", re.I)
            gemensamt = {
                "doman": doman, "kalla_url": url, "utlandsk_valuta": utlandsk,
                "utan_insattning": utan_ins,
                "min_insattning_kr": None if utan_ins else _belopp(MIN_INS.search(kontext), (1, 2, 3, 4, 5, 6)),
                "maxvinst_kr": _belopp(_med_valuta(MAXVINST.search(framat)), (1, 2, 3)),
                "giltighet": (lambda m: f"{m.group(1)} {m.group(2)}" if m else None)(GILTIG.search(framat)),
            }
            ettx = None if utan_ins else (next((t2 for m in meningar_framat if (t2 := _ettx(m))), None) or ettx_allm)

            komponenter = []
            if spins_m and 5 <= int(spins_m.group(1)) <= 3000:
                komponenter.append(("spins", {
                    "typ": "freespins", "antal_spins": int(spins_m.group(1)),
                    "spinvarde_kr": _spinvarde(framat), "spel": _spel(rad, framat),
                }))
            if proc_m or belopp_m:
                upp = _med_valuta(UPP_TILL.search(rad)) or _med_valuta(UPP_TILL.search(framat))
                belopp = _belopp(upp, (1, 2, 3)) if upp else _belopp(belopp_m, (1, 2, 3))
                if belopp and 10 <= belopp <= MAX_BONUS_KR:
                    komponenter.append(("bonus", {
                        "typ": "bonuspengar", "bonus_kr": belopp,
                        "matchprocent": int(proc_m.group(1)) if proc_m else None,
                    }))

            spela = None if utan_ins else _spela_for(meningar_framat, gemensamt["min_insattning_kr"])
            if spela and spela[0] == "1x" and not ettx:
                ettx = SPELA_FOR.search(framat)
            for komp, falt in komponenter:
                if spela and spela[0] == "insattning":
                    pa, x, sak, skal = "insattning", spela[1], "hög", spela[2]
                else:
                    pa, x, sak, skal = _omsattning(meningar_framat, komp, allmant, utan_ins, falt.get("antal_spins"))
                b = {**gemensamt, **falt, "omsattning_pa": pa, "omsattning_x": x, "sakerhet": sak,
                     "insattning_1x": bool(ettx) and pa != "insattning",
                     "titel": _rubrik(rader, i), "utdrag": [kontext[:900]], "skal": [skal]}
                if b["insattning_1x"]:
                    b["skal"].append(f"1x-regel: \"{ettx.group(0)[:140]}\"")
                if GUIDESIDA.search(url) and b["sakerhet"] != "låg":
                    b["sakerhet"] = "låg"
                    b["skal"].append("hittat i en guide/artikel på sajten – kan vara inaktuellt")
                b["nyckel"] = _nyckel(doman, b)
                hittade.setdefault(b["nyckel"], []).append(b)
    return [_sla_ihop(poster) for poster in hittade.values()]


GUIDESIDA = re.compile(r"guide|blogg?|nyheter|/news|artik|/faq|fragor|frågor|/go/|ordlista|glossary|how-to|"
                       r"sa-fungerar|vad-ar|vad-är|hur-", re.I)

_FALT = ("spinvarde_kr", "spel", "min_insattning_kr", "maxvinst_kr", "giltighet", "matchprocent")


def _sla_ihop(poster: list[dict]) -> dict:
    """Samma erbjudande hittat på flera ställen (startsida, kampanjsida, villkor) -> en post.

    Ett säkert krav på insättningen vinner alltid (din hårda regel); annars den bäst underbyggda tolkningen.
    Saknade uppgifter fylls i från de andra träffarna.
    """
    ordnade = sorted(poster, key=_rang, reverse=True)
    ins = [p for p in ordnade if p["omsattning_pa"] == "insattning" and p["sakerhet"] in ("hög", "medel")]
    krav = [p for p in ordnade if p["omsattning_pa"] in ("bonus", "vinster") and p["sakerhet"] in ("hög", "medel")]
    konflikt = False
    if ins:
        b = dict(ins[0])
    elif krav and any(p["omsattning_pa"] == "ingen" for p in poster):
        # En sida säger "omsättningsfritt", en annan anger ett krav: kravet vinner men du får granska.
        b, konflikt = dict(krav[0]), True
    else:
        b = dict(ordnade[0])
    for p in ordnade:
        for f in _FALT:
            if b.get(f) is None and p.get(f) is not None:
                b[f] = p[f]
    b["utan_insattning"] = all(p["utan_insattning"] for p in poster) and b.get("min_insattning_kr") is None
    b["insattning_1x"] = b["omsattning_pa"] != "insattning" and any(p["insattning_1x"] for p in poster)
    b["utdrag"] = list(dict.fromkeys(u for p in [b] + ordnade for u in p["utdrag"]))[:3]
    b["skal"] = list(dict.fromkeys(s for p in [b] + ordnade for s in p["skal"]))[:4]
    if konflikt:
        b["sakerhet"] = "låg"
        b["skal"].insert(0, "en sida säger omsättningsfritt men en annan anger omsättningskrav – kontrollera")
    if len({p["omsattning_pa"] for p in poster}) > 1:
        b["skal"].append("olika sidor gav olika tolkning: " + ", ".join(
            sorted({str(p["omsattning_pa"]) for p in poster})))
    return b



def _rang(b: dict) -> int:
    return {"hög": 3, "medel": 2, "låg": 1}[b["sakerhet"]] * 10 + sum(
        b.get(f) is not None for f in ("spinvarde_kr", "min_insattning_kr", "omsattning_x", "spel"))
