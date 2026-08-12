# Laadpalen Huizen

Een interactieve webkaart met openbare laadpunten in de gemeente Huizen. De kaart helpt EV-rijders om laadlocaties te vinden en om voor een gewenste laadsessie te vergelijken welke van hun laadpassen naar verwachting het voordeligst is.

**Live website:** https://rubenwoudsma.github.io/laadpalenhuizen/

## Wat kun je met de kaart?

Op de kaart kun je:

- openbare laadlocaties in Huizen bekijken;
- zoeken op adres of locatie;
- informatie bekijken over operator, connectoren, laadvermogen en beschikbaarheid;
- aangeven welke laadpassen je zelf gebruikt;
- kiezen hoeveel kWh je ongeveer wilt laden;
- de geschatte sessiekosten van je geselecteerde laadpassen vergelijken;
- zien waarop een prijsberekening is gebaseerd en hoe betrouwbaar de beschikbare tariefinformatie is.

Je geselecteerde laadpassen worden alleen lokaal in je browser opgeslagen. Er is geen account nodig.

## Laadpassen

De vergelijking ondersteunt momenteel de volgende laadpassen en plannen zonder maandabonnement:

- ANWB, Zonder abonnement
- Vattenfall InCharge
- E-Flux by Road, Flex
- Shell Recharge Basic
- Laadkompas, Zonder abonnement

De kaart vergelijkt niet alleen een prijs per kWh. Waar relevant worden ook sessiekosten, kWh-opslagen en verschillen tussen het eigen netwerk en roaming meegenomen.

De uiteindelijke kosten bij een laadpaal kunnen afwijken. Controleer bij twijfel altijd het actuele tarief in de app of omgeving van je laadpasaanbieder.

## Hoe wordt de prijs bepaald?

De basis voor de kaart is openbare laadpaaldata van het Nationaal Dataportaal Wegverkeer [NDW]. De dataset wordt dagelijks bijgewerkt via GitHub Actions.

Voor een laadlocatie probeert de preprocessor eerst een rechtstreeks gepubliceerd NDW/OCPI-tarief te gebruiken. Tarieven worden gekoppeld binnen de OCPI-partijscope, zodat dezelfde tarief-ID bij verschillende exploitanten niet per ongeluk wordt verwisseld.

Als een direct tarief ontbreekt, kan voor geschikte operators een mediaan van voldoende landelijke tariefwaarnemingen worden gebruikt. Voor operators waarvan tarieven sterk per regio of concessie verschillen, wordt zo'n landelijke mediaan niet gebruikt.

Voor TotalEnergies-locaties in Huizen gebruikt de kaart, wanneer NDW geen bruikbaar direct tarief levert, de officiële MRA-E-tarieven die TotalEnergies voor Noord-Holland, Flevoland en Utrecht publiceert. Omdat uit de locatiegegevens niet altijd blijkt welke concessie van toepassing is, wordt voor reguliere AC-laders een prijsband van €0,34 tot €0,48 per kWh gebruikt. Deze bandbreedte wordt zichtbaar doorgerekend naar de sessiekosten.

Er wordt geen generieke fallbackprijs ingevuld om toch een winnaar te kunnen tonen. Als prijsbanden van laadpassen overlappen, meldt de kaart dat er geen eenduidige goedkoopste pas is.

De browser berekent vervolgens de geschatte sessiekosten voor de gekozen laadhoeveelheid op basis van de prijsregels van de geselecteerde laadpassen.

Meer informatie over de berekening, databronnen en beperkingen staat op de pagina [Methodologie](methodologie.html).

## Databronnen

De applicatie gebruikt de openbare OCPI-data van NDW voor onder andere:

- laadlocaties;
- operators;
- connectoren en laadvermogen;
- beschikbaarheidsstatus;
- gepubliceerde CPO-tarieven, waar beschikbaar.

Voor de regionale TotalEnergies-fallback worden daarnaast de openbare informatie van gemeente Huizen, Laadwerk en de actuele MRA-E-tarieven van TotalEnergies gebruikt.

Laadpunten worden eerst geografisch voorgeselecteerd rond Huizen en daarna gecontroleerd tegen de gemeentegrens in `huizen-boundary.geojson`.

## Belangrijke kanttekening

Laadtarieven zijn complex. De uiteindelijke prijs kan onder andere afhangen van de laadpaalexploitant [CPO], laadpasaanbieder [MSP], roamingafspraken, lokale concessies, starttarieven, tijd- of blokkeerkosten en specifieke connectorvoorwaarden.

Deze website is daarom bedoeld als **vergelijkingshulpmiddel**, niet als officiële prijs- of facturatiebron. De app, prijspagina en uiteindelijke factuur van de laadpasaanbieder blijven leidend.

## Technische opzet

De website is volledig statisch en draait via GitHub Pages. Er is geen backend, database of API-key nodig.

```text
NDW open data
      ↓
GitHub Actions
      ↓
process.py
      ↓
huizen-data.json
      ↓
GitHub Pages
      ↓
index.html
```

`process.py` downloadt en verwerkt de NDW-data. De gegenereerde dataset wordt als `huizen-data.json` in de repository opgeslagen. De webpagina leest dit bestand rechtstreeks in de browser.

## Lokaal draaien

Clone de repository:

```bash
git clone https://github.com/rubenwoudsma/laadpalenhuizen.git
cd laadpalenhuizen
```

Start een lokale webserver:

```bash
python3 -m http.server 8000
```

Open daarna:

```text
http://localhost:8000/
```

Wil je de NDW-data opnieuw ophalen en verwerken, draai dan:

```bash
python3 process.py
```

Hiervoor is een internetverbinding nodig.

De prijsregels kunnen worden getest met:

```bash
python3 -m unittest discover -s tests
```

## Automatische updates

De workflow in `.github/workflows/update.yml` haalt dagelijks de NDW-data op, voert de tests uit en genereert een nieuwe `huizen-data.json`. Als de dataset is gewijzigd, wordt deze automatisch teruggeschreven naar de repository.

Voor GitHub Actions zijn geen API-secrets nodig. De workflow heeft wel schrijfrechten op de repository nodig.

## Projectstructuur

```text
.github/workflows/update.yml  Automatische NDW-update
index.html                    Kaart, filters en prijsvergelijking
methodologie.html             Uitleg over data en tariefberekening
process.py                    NDW-preprocessor en prijsregels
huizen-data.json              Gegenereerde laadpuntdata
huizen-boundary.geojson       Gemeentegrens Huizen
tests/test_pricing.py         Tests voor de prijsregels
```

## Herkomst

Dit project is ontstaan vanuit de open source repository `jdevalk/laadpalenwijchen.nl` en is aangepast voor de gemeente Huizen en deze manier van laadpasvergelijking.
