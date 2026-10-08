# Bonussökaren

Lokal app som söker igenom licensierade kasinon efter freespins och andra bonusar **utan
omsättningskrav på insättningen**. Omsättningskrav på bara bonusen eller freespinvinsterna är OK.

Starta med att dubbelklicka på `start.command`, eller kör `./start.command`. Appen öppnas på
http://localhost:8503 och lyssnar bara på din egen dator. Ingen telemetri skickas. I git följer dina markeringar
(`data/mina.json`) och licensregistren med; sidcache, sökresultat och loggar stannar lokalt.

## Hur det fungerar

1. **Register** (`bonusapp/register_se.py`, `register_eu.py`): alla spelsidor med licens från
   Spelinspektionen (öppet JSON-API), Malta Gaming Authority och Estlands EMTA.
   - MGA:s register visas i din Chrome (headless) och läses av, eftersom API-svaret är krypterat.
     Domänerna hämtas från bolagens "Dynamic Seal"-sidor, en var femte sekund (MGA svarar med 429
     vid snabbare takt). De sparas i `data/mga_seal_cache.json` i 30 dagar.
   - Registren hämtas automatiskt igen när de är äldre än en vecka.
2. **Sökning** (`skanna.py`, `hamta.py`, `sidhitta.py`): för varje domän läses startsidan. Sedan
   läses de undersidor som ser ut att handla om bonusar, kampanjer och villkor, högst sex per
   kasino och svenska sidor först.
   - Sidor som kräver JavaScript visas i din installerade Chrome (headless, tom profil).
   - Text som ligger inbäddad i Next.js- och Nuxt-sidor läses utan webbläsare.
   - I Chrome scrollas sidan ner, så att FAQ- och villkorssektioner som laddas sent kommer med.
     Text i webbkomponenter (shadow DOM) och alt-texter på bannerbilder tas också med.
   - robots.txt respekteras.
   - Appen loggar aldrig in, fyller aldrig i formulär och försöker inte ta sig förbi botskydd.
     Sidor med Cloudflare-kontroll eller CAPTCHA märks "botskydd" och hoppas över.
3. **Tolkning** (`tolka.py`): regelbaserad. Freespins, procentbonusar och bonusbelopp är ankare.
   Texten runt dem tolkas mening för mening (se modulens docstring). Allt osäkert hamnar under
   **Granska**, där du avgör.
4. **Dina regler** (`urval.py`):
   - **omsättningsfri** och **omsättning bonus**: visas.
   - **insättning**: omsättningskrav på insättningen eller på insättning + bonus. Visas aldrig.
   - **1x insättning**: insättningen ska spelas 1 gång före uttag (penningtvättsregel). Visas bara
     med reglaget på.
   - **granska**: osäkert eller motsägelsefullt.

## Bra att veta

- **Svensk licens = bonus en gång per bolag.** Ett bolag med svensk licens får bara ge bonus första
  gången du spelar hos *bolaget*. Markerar du ett svenskt kasino som använt döljs därför alla
  bolagets sajter. Det spelar ingen roll vilket varumärke du använde.
- **Geoblockering.** Kasinon med bara MGA- eller EMTA-licens som blockerar Sverige döljs. De kollas
  igen efter sju dagar.
- **Omdirigeringar.** En sajt som skickar vidare till en domän utanför registren söks inte igenom.
  Bakom samma namn kan det finnas ett bolag med Curaçao- eller Anjouan-licens.
- **Skatt.** Vinster från kasinon med licens i EU/EES är skattefria i Sverige.
- **EV är en grov uppskattning.** Den bygger på RTP (standard 96 %), spinvärdet och
  omsättningskravet. Euro räknas om till kronor med kursen 11 (`tolka.EUR_SEK`). Se förklaringen
  per erbjudande.
- **Låsta spinvinster.** Villkor av typen "spins utan omsättningskrav men vinsterna låses tills
  insättning + bonus är omsatt" räknas som krav på insättningen.

## Kommandon

```bash
python verktyg/skanna.py                  # hela sökningen (det appens knapp startar)
python verktyg/skanna.py --bara-register  # bara licensregistren
python verktyg/skanna.py --doman unibet.se
python verktyg/skanna.py --omtolka        # tolka om sparade sidor (ingen nätverkstrafik)
python -m pytest -q                       # tester
```

En hel sökning tar ungefär 15–40 minuter. Den dagliga sökningen slås på under **Sökning och
inställningar**. Den använder launchd: `~/Library/LaunchAgents/se.hedin.freespins.plist`.

## Filer i data/

| Fil | Innehåll |
|---|---|
| `kasinon.json` | sammanslaget register, en post per domän |
| `skanning.json` | senaste sökningen per domän: status, lästa sidor, fel |
| `bonusar.json` | alla hittade erbjudanden |
| `sedda.json` | när varje erbjudande först sågs (för "ny"-markering och notiser) |
| `mina.json` | använda kasinon, granskningar, dolda erbjudanden, inställningar (backup i `backups/`) |
| `mga_seal_cache.json` | MGA-domäner per bolag |
| `sidcache/` | komprimerad text från lästa sidor (för omtolkning), cirka 25 MB |
| `loggar/` | logg från senaste sökningen och från det schemalagda jobbet |
