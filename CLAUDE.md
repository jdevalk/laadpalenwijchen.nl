# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LaadPas Checker for Wijchen — a static site comparing 5 EV charging passes across all public charging points in Wijchen, NL. Deployed on Cloudflare Pages at laadpalenwijchen.nl.

## Architecture

**Data pipeline:** `process.py` (Python 3.12, stdlib only) downloads two gzipped NDW open data files (locations + tariffs), filters to a bounding box around Wijchen, joins tariff data onto connectors, computes per-pass pricing, and writes `wijchen-data.json`.

**Frontend:** Single `index.html` with inline CSS/JS. Uses Leaflet for the map, fetches `wijchen-data.json` at load. Live availability is overlaid client-side from Open Charge Map API (polled every 5 min). No build step, no bundler, no framework.

**Deployment:** GitHub Actions runs `process.py` daily at 06:00 UTC, commits `wijchen-data.json` if changed. Cloudflare Pages auto-deploys on push to `main`.

## Commands

```bash
# Generate data locally (downloads ~50MB from NDW, no API key needed)
python3 process.py

# Local dev server
python3 -m http.server 8080
```

## Key Design Decisions

- **No dependencies** — `process.py` uses only Python stdlib (urllib, gzip, json)
- **Pricing model** — When NDW tariff data exists, per-pass prices are derived from CPO rate with pass-specific rules (Shell fixed rate, Chargemap markup, etc.). Otherwise falls back to `CPO_FALLBACK` table keyed by operator name
- **Bounding box** — Wijchen + ~5km buffer: lat 51.770–51.850, lng 5.670–5.810
- **All content is Dutch** — UI labels, comments in process.py, commit messages from Actions

## Files

- `process.py` — NDW data pipeline; all pricing logic lives here (PASSES, CPO_FALLBACK, build_pricing)
- `index.html` — Complete frontend: map, sidebar, cards, popups, OCM live status
- `wijchen-data.json` — Generated output, committed to repo, served statically
- `.github/workflows/update.yml` — Daily cron job
