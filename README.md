# Laadpalen Huizen

Een eenvoudige, statische webkaart voor openbare laadpunten in de gemeente Huizen. De kaart is vooral bedoeld voor EV-rijders die meerdere laadpassen hebben en snel willen zien welke van hun passen naar verwachting het voordeligst is voor een concrete laadsessie.

Live: https://rubenwoudsma.github.io/laadpalenhuizen/

## Wat versie 2 verandert

De oorspronkelijke versie vergeleek vooral vaste bedragen per kWh en gebruikte voor veel locaties hardcoded fallbackprijzen. Daardoor kon een aanbieder als goedkoopste uit de vergelijking komen zonder dat voor die locatie een echt tarief bekend was.

Versie 2:

- vergelijkt **geschatte sessiekosten** voor 5, 10, 20 of 30 kWh;
- laat de gebruiker zijn eigen laadpassen selecteren, de selectie wordt lokaal in de browser opgeslagen;
- bevat ANWB Zonder abonnement, Vattenfall InCharge, E-Flux Flex, Shell Recharge Basic en Laadkompas Zonder abonnement;
- modelleert sessiekosten en kWh-opslagen afzonderlijk;
- toont een betrouwbaarheid per berekening;
- gebruikt geen generieke CPO-fallbackprijs meer;
- toont alleen een winnaar wanneer minimaal twee geselecteerde passen berekenbaar zijn;
- gebruikt de NDW-status uit de laatste dagelijkse dataset, er is geen niet-werkende Cloudflare/OCM-livefunctie meer nodig.

## Dataflow

`process.py` downloadt dagelijks de openbare NDW OCPI-bestanden voor locaties en tarieven. Locaties worden eerst met een bounding box rond Huizen voorgeselecteerd en daarna tegen `huizen-boundary.geojson` gefilterd.

Voor het CPO-basistarief geldt deze volgorde:

1. direct NDW/OCPI-tarief van een connector;
2. operator-mediaan, alleen met minimaal vijf landelijke tariefwaarnemingen en niet voor uitgesloten regionaal variërende operators;
3. onbekend, er wordt geen fictieve fallbackprijs ingevuld.

Daarna bouwt `process.py` per laadpas prijscomponenten op. De browser berekent het sessietotaal op basis van het door de bezoeker gekozen aantal kWh.

Meer detail staat op [`methodologie.html`](methodologie.html).

## Laadpassen

De kernvergelijking gebruikt plannen zonder maandabonnement, zodat de kaart geen aannames hoeft te doen over het aantal publieke laadsessies per maand.

| Pas | Plan | Vereenvoudigd model |
| --- | --- | --- |
| ANWB | Zonder abonnement | CPO + €0,89 per sessie |
| Vattenfall InCharge | Gratis laadpas | eigen netwerk geen sessiefee, roaming + €0,35 per sessie |
| E-Flux by Road | Flex | €0,31 per sessie, buiten E-Flux + €0,024/kWh |
| Shell Recharge | Basic | gepubliceerde AC/DC-prijsband + €0,35 per sessie |
| Laadkompas | Zonder abonnement | CPO + €0,47 per sessie |

De exacte bron-URL en verificatiedatum staan per pas in `process.py` en in de gegenereerde `huizen-data.json`.

## Lokaal draaien

Er zijn geen Python- of JavaScript-dependencies nodig.

```bash
python3 -m http.server 8000
```

Open daarna `http://localhost:8000/`.

De preprocessor zelf haalt NDW-data van internet op:

```bash
python3 process.py
```

Tests uitvoeren:

```bash
python3 -m unittest discover -s tests
```

## Automatische update

`.github/workflows/update.yml` draait dagelijks om 06:37 UTC en kan ook handmatig worden gestart. De workflow:

1. checkt de repository uit;
2. zet Python op;
3. voert de unit tests uit;
4. draait `process.py`;
5. commit en pusht `huizen-data.json` alleen als die is veranderd.

GitHub Pages serveert vervolgens de statische bestanden. Er is geen backend, API-key of Cloudflare Pages Function nodig.

## Projectstructuur

```text
.github/workflows/update.yml  Dagelijkse NDW-update
index.html                    Kaart, filters en prijsvergelijking
methodologie.html             Uitleg en beperkingen
process.py                    NDW-preprocessor en prijsregels
huizen-data.json              Gegenereerde statische dataset
huizen-boundary.geojson       Gemeentegrens Huizen
tests/test_pricing.py         Unit tests voor prijsregels
```

## Belangrijke beperking

Dit project is een vergelijkingshulpmiddel, geen facturatiesysteem. De app of factuur van de laadpasaanbieder blijft leidend. Roamingroutes, acties, lokale concessietarieven, tijd- of blokkeerkosten en connector-specifieke uitzonderingen kunnen de uiteindelijke prijs beïnvloeden.
