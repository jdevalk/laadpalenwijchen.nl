# Laadpalen Wijchen

Vergelijkt 4 laadpassen op alle publieke laadpunten in Wijchen en omgeving.

**Live data van NDW** (Nationaal Dataportaal Wegverkeer) — dagelijks bijgewerkt.

## Hoe werkt het?

```
NDW open data (gratis, geen API-key)
         ↓  (dagelijks, 06:00 UTC)
GitHub Actions → process.py
         ↓
wijchen-data.json  (gecommit naar repo)
         ↓
Cloudflare Pages   (auto-deploy bij elke push)
         ↓
index.html leest wijchen-data.json
```

## Setup

### 1. Fork / clone deze repo

```bash
git clone https://github.com/jdevalk/laadpalenwijchen.nl
cd laadpalenwijchen.nl
```

### 2. Cloudflare Pages koppelen

1. Ga naar [Cloudflare Pages](https://pages.cloudflare.com/)
2. **Create a project** → Connect to Git → selecteer deze repo
3. Build settings:
   - **Framework preset:** None
   - **Build command:** *(leeg laten)*
   - **Build output directory:** `/` (of leeg)
4. Deploy → Cloudflare geeft je een `*.pages.dev` URL

Cloudflare Pages deployt automatisch bij elke push naar `main`.

### 3. GitHub Actions (automatische dagelijkse update)

De workflow in `.github/workflows/update.yml` draait elke dag om 06:00 UTC:
1. Download NDW bestanden
2. Filter op Wijchen bounding box
3. Join locaties + tarieven
4. Commit `wijchen-data.json` terug naar repo
5. Cloudflare Pages detecteert de push → auto-deploy

**Geen secrets nodig** — NDW data is volledig open/gratis.

### 4. Handmatig draaien (testen)

```bash
python3 process.py
# schrijft wijchen-data.json lokaal
# open index.html in browser (via lokale server)
python3 -m http.server 8080
```

## Data bronnen

| Bron | URL | Update |
|------|-----|--------|
| NDW locaties (OCPI) | `opendata.ndw.nu/charging_point_locations_ocpi.json.gz` | Dagelijks |
| NDW tarieven (OCPI) | `opendata.ndw.nu/charging_point_tariffs_ocpi.json.gz` | Dagelijks |

NDW haalt data op bij CPO's (laadpaal-exploitanten). Voor sommige CPO's
is er ook een push-connectie met minuut-updates, maar de gepubliceerde
open data bestanden worden dagelijks geregenereerd.

> **Let op:** Niet alle Nederlandse CPO's zijn verplicht aangesloten op NDW
> (AFIR-wetgeving is van kracht maar naleving is nog niet 100%).
> Locaties zonder NDW-tarief gebruiken een schatting (zie `process.py`).

## Passen vergeleken

| Pas | Maandkosten | Methode |
|-----|------------|---------|
| Vattenfall InCharge | €0 | Concessietarief Gelderland/Overijssel: €0,3624/kWh |
| Laadkompas | €4.78/mo | CPO-basistarief (geen starttarief met abo) |
| Shell Recharge | €0 | €0,55 vaste prijs overige AC-palen (2025) |
| Chargemap | €0 | CPO-tarief + ~12% opslag |

Tarieven zijn indicatief. Check altijd de app voor de exacte prijs per paal.

## Bestanden

```
laadpalenwijchen.nl/
├── index.html              ← de website (leest wijchen-data.json)
├── wijchen-data.json       ← gegenereerd door process.py, geserveerd door Pages
├── process.py              ← NDW downloader + preprocessor
└── .github/workflows/
      └── update.yml        ← dagelijkse cron job
```
