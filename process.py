#!/usr/bin/env python3
"""
NDW charging point preprocessor for Huizen, NL.

Downloads public NDW OCPI location and tariff files, filters them to the
municipality of Huizen, and writes huizen-data.json for the static GitHub Pages
site.

Pricing philosophy:
- NDW CPO energy tariffs are the preferred base price.
- Tariff IDs are resolved in their OCPI country/party scope, with an ID-only
  fallback only when that tariff ID is unique in the national feed.
- If a direct connector tariff is missing, an operator median may be used as an
  explicitly labelled estimate when enough nationwide samples exist.
- TotalEnergies locations in Huizen use an official MRA-E regional price range
  when NDW does not expose a usable connector tariff. This is a targeted fallback
  based on public concession tariffs, not a generic invented price.
- Charge-pass fees are modelled separately as per-session fees and kWh markups.
- The browser calculates session totals for the user's selected amount of energy.

No external Python dependencies are required.
Run: python3 process.py
"""

from __future__ import annotations

import gzip
import json
import os
import statistics
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Optional

# CONFIG
NDW_BASE = "https://opendata.ndw.nu"
LOCATIONS_URL = f"{NDW_BASE}/charging_point_locations_ocpi.json.gz"
TARIFFS_URL = f"{NDW_BASE}/charging_point_tariffs_ocpi.json.gz"
OUTPUT_FILE = "huizen-data.json"

# Fast pre-filter around municipality Huizen. Precise filtering uses GeoJSON.
LAT_MIN, LAT_MAX = 52.260, 52.325
LNG_MIN, LNG_MAX = 5.175, 5.305

BOUNDARY_FILE = os.path.join(os.path.dirname(__file__) or ".", "huizen-boundary.geojson")

HEADERS = {
    "User-Agent": "laadpalenhuizen (github.com/rubenwoudsma/laadpalenhuizen)",
    "Accept-Encoding": "identity",
}

# A median based on only a handful of samples creates false precision.
MIN_OPERATOR_MEDIAN_SAMPLES = 5

# Operators for which a nationwide median is especially likely to be misleading
# because concession and regional tariffs can differ materially.
SKIP_OPERATOR_MEDIAN = {
    "vattenfall incharge",
    "vattenfall",
    "nuon",
    "totalenergies",
    "total energies",
}

# Huizen participates in the joint public charging approach for Noord-Holland,
# Flevoland and Utrecht through Laadwerk/MRA-E. TotalEnergies publishes current
# concession tariffs for that region. When NDW does not expose a usable tariff
# for a TotalEnergies connector in Huizen, these official regional figures are
# used as an explicitly labelled fallback.
#
# AC: MRA-E 2-5 = EUR 0.48/kWh incl. VAT, MRA-E 6 = EUR 0.36/kWh,
#     MRA-E 6 dynamic = EUR 0.34-0.36/kWh. Without a reliable concession marker
#     per connector we retain the full official EUR 0.34-0.48 range.
# DC: MRA-E = EUR 0.54/kWh incl. VAT.
TOTALENERGIES_MRAE_AC_RANGE = (0.34, 0.48)
TOTALENERGIES_MRAE_DC_RATE = 0.54
TOTALENERGIES_MRAE_VERIFIED_AT = "2026-08-12"
TOTALENERGIES_MRAE_SOURCE_URL = "https://totalenergies.nl/elektrisch-rijden/vind-laadpunt"
HUIZEN_CHARGING_SOURCE_URL = "https://www.huizen.nl/elektrisch-laden"
LAADWERK_SOURCE_URL = "https://www.laadwerk.nl/diensten/laadinfra"

# Public charge-pass conditions verified on 2026-08-12.
# The site deliberately compares plans without a monthly subscription so that a
# single charging session can be compared without inventing an amortisation rule.
PASSES = [
    {
        "id": "anwb_free",
        "name": "ANWB",
        "plan": "Zonder abonnement",
        "color": "#d89b00",
        "monthly_fee": 0.0,
        "summary": "CPO-tarief + €0,89 per sessie",
        "verified_at": "2026-08-12",
        "source_url": "https://www.anwb.nl/auto/elektrisch-rijden/laadpas-abonnement",
        "default_selected": True,
    },
    {
        "id": "vattenfall",
        "name": "Vattenfall InCharge",
        "plan": "Gratis laadpas",
        "color": "#16a34a",
        "monthly_fee": 0.0,
        "summary": "Eigen netwerk zonder starttarief; roaming + €0,35 per sessie",
        "verified_at": "2026-08-12",
        "source_url": "https://incharge.vattenfall.nl/onze-tarieven",
        "default_selected": True,
    },
    {
        "id": "eflux_flex",
        "name": "E-Flux by Road",
        "plan": "Flex",
        "color": "#2563eb",
        "monthly_fee": 0.0,
        "summary": "€0,31 per sessie + €0,024/kWh buiten E-Flux",
        "verified_at": "2026-08-12",
        "source_url": "https://www.e-flux.io/nl/tarieven-laadpassen",
        "default_selected": True,
    },
    {
        "id": "shell_basic",
        "name": "Shell Recharge",
        "plan": "Basic",
        "color": "#dc2626",
        "monthly_fee": 0.0,
        "summary": "Gepubliceerde prijsband + €0,35 per sessie",
        "verified_at": "2026-08-12",
        "source_url": "https://www.shell.nl/elektrisch-opladen/Tarieven.html",
        "default_selected": True,
    },
    {
        "id": "laadkompas_free",
        "name": "Laadkompas",
        "plan": "Zonder abonnement",
        "color": "#7c3aed",
        "monthly_fee": 0.0,
        "summary": "CPO-tarief + €0,47 per sessie",
        "verified_at": "2026-08-12",
        "source_url": "https://laadkompas.nl/laadpas/",
        "default_selected": True,
    },
]

PASS_BY_ID = {p["id"]: p for p in PASSES}

# ANWB mentions special discounts on these networks but does not publish one
# universal tariff that can safely be applied to every connector.
ANWB_DISCOUNT_NETWORKS = ("totalenergies", "total energies", "ubitricity", "equans", "ionity")


def load_boundary() -> list:
    """Load municipality boundary from a Polygon or MultiPolygon GeoJSON Feature."""
    with open(BOUNDARY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    geom = data["geometry"]
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    raise ValueError(f"Unsupported geometry type: {geom['type']}")


def point_in_polygon(lng: float, lat: float, polygon: list) -> bool:
    """Ray-casting point-in-polygon test."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def point_in_boundary(lng: float, lat: float, boundary: list) -> bool:
    for polygon in boundary:
        if not point_in_polygon(lng, lat, polygon[0]):
            continue
        if any(point_in_polygon(lng, lat, hole) for hole in polygon[1:]):
            continue
        return True
    return False


def fetch_gz(url: str) -> bytes:
    print(f"  Fetching {url} ...", end=" ", flush=True)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=90) as response:
        compressed = response.read()
    print(f"{len(compressed) / 1024:.0f} KB compressed")
    return gzip.decompress(compressed)


def energy_price_including_vat(component: dict) -> Optional[float]:
    """
    Return an ENERGY component price including explicitly supplied VAT.

    OCPI 2.2.1 defines PriceComponent.price excluding VAT and has an optional
    vat percentage. If vat is omitted, we do not invent a Dutch VAT rate. That
    is more standards-compliant than silently adding 21% to every tariff.
    """
    if component.get("type") != "ENERGY" or "price" not in component:
        return None

    try:
        price = float(component["price"])
    except (TypeError, ValueError):
        return None

    vat = component.get("vat")
    if vat is not None:
        try:
            price *= 1 + float(vat) / 100
        except (TypeError, ValueError):
            pass

    return round(price, 4)


def build_tariff_index(tariffs: list) -> dict:
    """Index OCPI tariffs by country/party/id and by globally unique ID.

    OCPI tariff IDs only need to be unique within a CPO platform. A plain
    ``{id: tariff}`` map can therefore silently associate a connector with the
    wrong tariff when two parties use the same ID. Location country_code and
    party_id provide the correct scope.
    """
    scoped = {}
    by_id: dict[str, list[dict]] = {}

    for tariff in tariffs:
        if not isinstance(tariff, dict) or not tariff.get("id"):
            continue
        tariff_id = str(tariff["id"])
        country = str(tariff.get("country_code") or "").upper()
        party = str(tariff.get("party_id") or "").upper()
        if country and party:
            scoped[(country, party, tariff_id)] = tariff
        by_id.setdefault(tariff_id, []).append(tariff)

    unique = {tariff_id: rows[0] for tariff_id, rows in by_id.items() if len(rows) == 1}
    return {
        "scoped": scoped,
        "unique": unique,
        "id_collisions": sum(1 for rows in by_id.values() if len(rows) > 1),
        "total": len(tariffs),
    }


def get_tariff(
    tariff_id: str,
    tariff_index: dict,
    country_code: str = "",
    party_id: str = "",
) -> Optional[dict]:
    """Resolve a tariff in OCPI party scope, then by ID only if globally unique."""
    country = (country_code or "").upper()
    party = (party_id or "").upper()
    if country and party:
        tariff = tariff_index.get("scoped", {}).get((country, party, str(tariff_id)))
        if tariff:
            return tariff
    return tariff_index.get("unique", {}).get(str(tariff_id))


def get_cpo_rates(
    tariff_id: str,
    tariff_index: dict,
    country_code: str = "",
    party_id: str = "",
) -> list[float]:
    """Return all distinct usable OCPI ENERGY prices for a resolved tariff."""
    tariff = get_tariff(tariff_id, tariff_index, country_code, party_id)
    if not tariff:
        return []

    rates = []
    for element in tariff.get("elements", []):
        for component in element.get("price_components", []):
            rate = energy_price_including_vat(component)
            if rate is not None:
                rates.append(rate)
    return sorted(set(rates))


def get_cpo_rate(
    tariff_id: str,
    tariff_index: dict,
    country_code: str = "",
    party_id: str = "",
) -> Optional[float]:
    """Return one usable ENERGY price for median building and compatibility."""
    rates = get_cpo_rates(tariff_id, tariff_index, country_code, party_id)
    return rates[0] if rates else None


def get_cpo_price_info(
    tariff_id: str,
    tariff_index: dict,
    country_code: str = "",
    party_id: str = "",
) -> Optional[dict]:
    """Return midpoint plus a range when an OCPI tariff exposes multiple prices."""
    rates = get_cpo_rates(tariff_id, tariff_index, country_code, party_id)
    if not rates:
        return None
    low, high = rates[0], rates[-1]
    return {
        "rate": round((low + high) / 2, 4),
        "range": [low, high] if len(rates) > 1 else None,
    }


def operator_key(name: str) -> str:
    return " ".join((name or "").lower().split())


def find_operator_median(operator_name: str, medians: dict) -> Optional[float]:
    key = operator_key(operator_name)
    if key in SKIP_OPERATOR_MEDIAN:
        return None
    if key in medians:
        return medians[key]

    # Conservative fuzzy match for small naming differences.
    for candidate, rate in medians.items():
        if candidate in key or key in candidate:
            return rate
    return None


def confidence_for_source(source: str) -> str:
    if source == "ndw":
        return "high"
    if source in {"operator_median", "totalenergies_mrae", "totalenergies_mrae_dc"}:
        return "medium"
    return "low"


def downgrade_confidence(value: str) -> str:
    return {"high": "medium", "medium": "low", "low": "low"}.get(value, "low")


def merge_notes(*notes: Optional[str]) -> Optional[str]:
    values = [note.strip() for note in notes if note and note.strip()]
    return " ".join(values) or None


def shifted_range(price_range: Optional[list[float] | tuple[float, float]], delta: float = 0.0) -> Optional[list[float]]:
    if not price_range or len(price_range) != 2:
        return None
    return [round(float(price_range[0]) + delta, 4), round(float(price_range[1]) + delta, 4)]


def totalenergies_mrae_fallback(operator_name: str, power_kw: float) -> Optional[dict]:
    """Return official MRA-E pricing for TotalEnergies when NDW is incomplete.

    The municipality of Huizen works through Laadwerk in the Noord-Holland,
    Flevoland and Utrecht public charging collaboration. TotalEnergies publishes
    different MRA-E AC tariffs by concession, but the NDW location does not
    reliably expose which concession applies. Therefore AC remains a range.
    """
    op = operator_key(operator_name)
    if "totalenergies" not in op and "total energies" not in op:
        return None

    if power_kw >= 50:
        return {
            "rate": TOTALENERGIES_MRAE_DC_RATE,
            "range": None,
            "source": "totalenergies_mrae_dc",
            "note": "Officieel TotalEnergies MRA-E DC-tarief voor Noord-Holland, Flevoland en Utrecht.",
        }

    low, high = TOTALENERGIES_MRAE_AC_RANGE
    return {
        "rate": round((low + high) / 2, 4),
        "range": [low, high],
        "source": "totalenergies_mrae",
        "note": "Officiële MRA-E prijsband van TotalEnergies; de exacte concessie en eventuele dynamische prijs zijn niet uit NDW af te leiden.",
    }


def make_quote(
    kwh: float,
    session: float,
    confidence: str,
    basis: str,
    note: Optional[str] = None,
    price_range: Optional[list[float]] = None,
) -> dict:
    quote = {
        "kwh": round(float(kwh), 4),
        "session": round(float(session), 2),
        "confidence": confidence,
        "basis": basis,
    }
    if note:
        quote["note"] = note
    if price_range:
        quote["range"] = [round(float(v), 4) for v in price_range]
    return quote


def build_pricing(
    cpo_rate: Optional[float],
    cpo_source: str,
    operator_name: str,
    max_power_kw: float = 0,
    cpo_rate_range: Optional[list[float]] = None,
    cpo_note: Optional[str] = None,
) -> dict:
    """Build per-pass price components for one representative location tariff."""
    pricing: dict[str, dict] = {}
    op = operator_key(operator_name)
    base_confidence = confidence_for_source(cpo_source)
    if cpo_rate_range and len(cpo_rate_range) == 2 and abs(cpo_rate_range[1] - cpo_rate_range[0]) > 1e-9:
        base_confidence = downgrade_confidence(base_confidence)

    # ANWB free plan: CPO price + EUR 0.89/session. ANWB advertises special
    # network discounts, but without a universal public per-connector figure we
    # do not subtract an invented amount here.
    if cpo_rate is not None:
        anwb_confidence = base_confidence
        anwb_note = cpo_note
        if any(token in op for token in ANWB_DISCOUNT_NETWORKS):
            anwb_confidence = downgrade_confidence(anwb_confidence)
            anwb_note = merge_notes(
                cpo_note,
                "ANWB noemt korting op dit netwerk; de app kan een lager tarief tonen.",
            )
        pricing["anwb_free"] = make_quote(
            cpo_rate,
            0.89,
            anwb_confidence,
            cpo_source,
            note=anwb_note,
            price_range=shifted_range(cpo_rate_range),
        )

    # Vattenfall: no start fee on own InCharge network, EUR 0.35/session on
    # other networks. Roaming kWh rates are shown in the Vattenfall app and can
    # differ from the CPO base tariff, so confidence is downgraded for roaming.
    if cpo_rate is not None:
        own_vattenfall = "vattenfall" in op or "incharge" in op or "nuon" in op
        vf_confidence = base_confidence if own_vattenfall else downgrade_confidence(base_confidence)
        vf_note = cpo_note if own_vattenfall else merge_notes(
            cpo_note,
            "Roaming kWh-tarief kan in de InCharge-app afwijken van het CPO-basistarief.",
        )
        pricing["vattenfall"] = make_quote(
            cpo_rate,
            0.0 if own_vattenfall else 0.35,
            vf_confidence,
            cpo_source,
            note=vf_note,
            price_range=shifted_range(cpo_rate_range),
        )

    # E-Flux Flex: EUR 0.31/session, plus EUR 0.024/kWh outside E-Flux.
    if cpo_rate is not None:
        own_eflux = "e-flux" in op or "e flux" in op
        markup = 0.0 if own_eflux else 0.024
        ef_confidence = base_confidence if own_eflux else downgrade_confidence(base_confidence)
        ef_note = cpo_note if own_eflux else merge_notes(
            cpo_note,
            "Op sommige clearingnetwerken kan E-Flux nog €0,48 extra per sessie rekenen.",
        )
        pricing["eflux_flex"] = make_quote(
            cpo_rate + markup,
            0.31,
            ef_confidence,
            cpo_source,
            note=ef_note,
            price_range=shifted_range(cpo_rate_range, markup),
        )

    # Shell Recharge Basic publishes fixed price bands rather than CPO pass-through
    # pricing for partner networks. Use the midpoint only as an explicit estimate.
    is_dc = max_power_kw >= 50
    own_shell = "shell" in op
    if is_dc:
        if own_shell:
            pricing["shell_basic"] = make_quote(
                0.78,
                0.35,
                "medium",
                "published_shell",
                note="Gepubliceerd Shell Recharge Basic snellaadtarief in Nederland.",
            )
        else:
            pricing["shell_basic"] = make_quote(
                0.82,
                0.35,
                "low",
                "published_band",
                note="Midden van Shells gepubliceerde DC-prijsband; exacte paalprijs staat in de Shell-app.",
                price_range=[0.79, 0.85],
            )
    else:
        pricing["shell_basic"] = make_quote(
            0.55,
            0.35,
            "low",
            "published_band",
            note="Midden van Shells gepubliceerde AC-prijsband; exacte paalprijs staat in de Shell-app.",
            price_range=[0.50, 0.60],
        )

    # Laadkompas without subscription: CPO price + EUR 0.47/session.
    if cpo_rate is not None:
        pricing["laadkompas_free"] = make_quote(
            cpo_rate,
            0.47,
            base_confidence,
            cpo_source,
            note=cpo_note,
            price_range=shifted_range(cpo_rate_range),
        )

    return pricing


def connector_type_label(conn: dict) -> str:
    standard = conn.get("standard", "")
    return {
        "IEC_62196_T2": "Type 2",
        "IEC_62196_T2_COMBO": "CCS",
        "CHADEMO": "CHAdeMO",
        "DOMESTIC_F": "Schuko",
        "IEC_62196_T1": "Type 1",
        "IEC_62196_T1_COMBO": "CCS (T1)",
        "TESLA_S": "Tesla",
    }.get(standard, standard)


def connector_power_kw(conn: dict) -> float:
    value = conn.get("max_electric_power")
    if not value:
        return 0.0
    try:
        return round(float(value) / 1000, 1)
    except (TypeError, ValueError):
        return 0.0


def process_location(
    loc: dict,
    tariff_map: dict,
    operator_median: Optional[dict] = None,
    boundary: Optional[list] = None,
) -> Optional[dict]:
    coords = loc.get("coordinates", {})
    try:
        lat = float(coords.get("latitude", 0))
        lng = float(coords.get("longitude", 0))
    except (TypeError, ValueError):
        return None

    if not (LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX):
        return None
    if boundary and not point_in_boundary(lng, lat, boundary):
        return None

    operator = (loc.get("operator") or {}).get("name", "Onbekend")
    country_code = str(loc.get("country_code") or "")
    party_id = str(loc.get("party_id") or "")
    name = loc.get("name") or loc.get("address") or "Laadpunt"
    address = loc.get("address", "")
    city = loc.get("city", "")

    connectors = []
    for evse in loc.get("evses", []):
        status = evse.get("status", "UNKNOWN")
        for conn in evse.get("connectors", []):
            cpo_rate = None
            cpo_rate_range = None
            cpo_note = None
            used_tariff_id = None
            source = "unknown"
            power_kw = connector_power_kw(conn)

            for tariff_id in conn.get("tariff_ids") or []:
                price_info = get_cpo_price_info(tariff_id, tariff_map, country_code, party_id)
                if price_info is not None:
                    cpo_rate = price_info["rate"]
                    cpo_rate_range = price_info["range"]
                    used_tariff_id = tariff_id
                    source = "ndw"
                    break

            # Targeted official fallback for the dominant public CPO in Huizen.
            # It is used only after a direct NDW tariff lookup failed.
            if cpo_rate is None:
                regional = totalenergies_mrae_fallback(operator, power_kw)
                if regional:
                    cpo_rate = regional["rate"]
                    cpo_rate_range = regional["range"]
                    cpo_note = regional["note"]
                    source = regional["source"]

            if cpo_rate is None and operator_median:
                median = find_operator_median(operator, operator_median)
                if median is not None:
                    cpo_rate = median
                    source = "operator_median"

            connectors.append(
                {
                    "status": status,
                    "type": connector_type_label(conn),
                    "power_kw": power_kw,
                    "tariff_id": used_tariff_id,
                    "cpo_rate": cpo_rate,
                    "cpo_rate_range": cpo_rate_range,
                    "pricing_source": source,
                    "pricing_note": cpo_note,
                }
            )

    if not connectors:
        return None

    statuses = [c["status"] for c in connectors]
    available = "AVAILABLE" in statuses
    connector_types = list(dict.fromkeys(c["type"] for c in connectors if c["type"]))
    max_power = max((c["power_kw"] for c in connectors), default=0.0)

    # Prefer a connector with a direct NDW tariff, then an operator median, then
    # an unknown connector. This avoids using an arbitrary first connector when
    # better tariff data exists elsewhere at the same location.
    source_rank = {
        "ndw": 4,
        "totalenergies_mrae_dc": 3,
        "totalenergies_mrae": 3,
        "operator_median": 2,
        "unknown": 0,
    }
    representative = max(connectors, key=lambda c: source_rank.get(c["pricing_source"], 0))
    cpo_rate = representative["cpo_rate"]
    pricing_source = representative["pricing_source"]
    pricing_note = representative.get("pricing_note")

    explicit_range = representative.get("cpo_rate_range")
    if explicit_range:
        cpo_range = explicit_range
    else:
        # Only compare rates derived from the same source as the representative.
        # This avoids mixing a direct NDW tariff with a regional fallback that was
        # used for another connector at the same location.
        known_rates = sorted({
            round(c["cpo_rate"], 4)
            for c in connectors
            if c["cpo_rate"] is not None and c["pricing_source"] == pricing_source
        })
        cpo_range = [known_rates[0], known_rates[-1]] if len(known_rates) > 1 else None

    pricing = build_pricing(
        cpo_rate,
        pricing_source,
        operator,
        max_power,
        cpo_rate_range=cpo_range,
        cpo_note=pricing_note,
    )

    last_updated_values = [
        value
        for value in [loc.get("last_updated"), *(evse.get("last_updated") for evse in loc.get("evses", []))]
        if value
    ]
    last_updated = max(last_updated_values) if last_updated_values else None

    return {
        "id": loc.get("id", ""),
        "name": name,
        "address": f"{address}, {city}".strip(", "),
        "lat": lat,
        "lng": lng,
        "operator": operator,
        "connectors": connector_types,
        "max_power": max_power,
        "num_evses": len(loc.get("evses", [])),
        "available": available,
        "statuses": sorted(set(statuses)),
        "last_updated": last_updated,
        "pricing": pricing,
        "pricing_source": pricing_source,
        "pricing_note": pricing_note,
        "cpo_rate": cpo_rate,
        "cpo_rate_range": cpo_range,
    }


def unwrap_ocpi_list(payload, fallback_key: str) -> list:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload)
    if isinstance(data, list):
        return data
    value = payload.get(fallback_key, [])
    return value if isinstance(value, list) else []


def build_operator_medians(locations: list, tariff_map: dict) -> tuple[dict, dict]:
    operator_rates: dict[str, list[float]] = {}
    for loc in locations:
        operator = operator_key((loc.get("operator") or {}).get("name", ""))
        if not operator:
            continue
        country_code = str(loc.get("country_code") or "")
        party_id = str(loc.get("party_id") or "")
        for evse in loc.get("evses", []):
            for conn in evse.get("connectors", []):
                for tariff_id in conn.get("tariff_ids") or []:
                    rate = get_cpo_rate(tariff_id, tariff_map, country_code, party_id)
                    if rate is not None:
                        operator_rates.setdefault(operator, []).append(rate)
                        break

    medians = {}
    for operator, rates in operator_rates.items():
        if len(rates) >= MIN_OPERATOR_MEDIAN_SAMPLES and operator not in SKIP_OPERATOR_MEDIAN:
            medians[operator] = round(float(statistics.median(rates)), 4)
    return medians, operator_rates


def totalenergies_diagnostics(locations: list, tariff_map: dict, boundary: Optional[list]) -> dict:
    """Measure where TotalEnergies tariff resolution fails inside Huizen."""
    stats = {
        "locations": 0,
        "connectors": 0,
        "with_tariff_ids": 0,
        "resolved_energy_tariff": 0,
    }
    for loc in locations:
        operator = (loc.get("operator") or {}).get("name", "")
        if not totalenergies_mrae_fallback(operator, 0):
            continue
        coords = loc.get("coordinates", {})
        try:
            lat = float(coords.get("latitude", 0))
            lng = float(coords.get("longitude", 0))
        except (TypeError, ValueError):
            continue
        if not (LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX):
            continue
        if boundary and not point_in_boundary(lng, lat, boundary):
            continue

        stats["locations"] += 1
        country_code = str(loc.get("country_code") or "")
        party_id = str(loc.get("party_id") or "")
        for evse in loc.get("evses", []):
            for conn in evse.get("connectors", []):
                stats["connectors"] += 1
                tariff_ids = conn.get("tariff_ids") or []
                if tariff_ids:
                    stats["with_tariff_ids"] += 1
                if any(get_cpo_rate(tid, tariff_map, country_code, party_id) is not None for tid in tariff_ids):
                    stats["resolved_energy_tariff"] += 1
    return stats


def main() -> None:
    print("=== NDW Huizen preprocessor ===")

    print("\n[1/4] Downloading NDW data files...")
    try:
        locations_raw = fetch_gz(LOCATIONS_URL)
        tariffs_raw = fetch_gz(TARIFFS_URL)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"\nERROR: Could not download NDW data: {exc}")
        sys.exit(1)

    print("\n[2/4] Parsing OCPI data...")
    locations_data = json.loads(locations_raw)
    tariffs_data = json.loads(tariffs_raw)
    locations = unwrap_ocpi_list(locations_data, "locations")
    tariffs = unwrap_ocpi_list(tariffs_data, "tariffs")

    print(f"  Total NL locations: {len(locations):,}")
    print(f"  Total NL tariffs:   {len(tariffs):,}")

    tariff_map = build_tariff_index(tariffs)
    print(f"  Scoped tariffs indexed: {len(tariff_map['scoped']):,}")
    print(f"  Globally unique IDs:    {len(tariff_map['unique']):,}")
    print(f"  Reused tariff IDs:      {tariff_map['id_collisions']:,}")

    print("\n[3/4] Building operator medians...")
    operator_median, operator_rates = build_operator_medians(locations, tariff_map)
    print(f"  Operators with median ({MIN_OPERATOR_MEDIAN_SAMPLES}+ samples): {len(operator_median)}")

    boundary = None
    try:
        boundary = load_boundary()
        vertices = sum(len(polygon[0]) for polygon in boundary)
        print(f"  Municipality boundary loaded ({len(boundary)} polygons, {vertices} outer vertices)")
    except FileNotFoundError:
        print("  WARNING: huizen-boundary.geojson not found, using bbox only")

    te_diag = totalenergies_diagnostics(locations, tariff_map, boundary)
    print("  TotalEnergies Huizen diagnostics:")
    print(f"    locations:              {te_diag['locations']}")
    print(f"    connectors:             {te_diag['connectors']}")
    print(f"    connectors tariff_ids:  {te_diag['with_tariff_ids']}")
    print(f"    resolved ENERGY tariff: {te_diag['resolved_energy_tariff']}")

    print("\n[4/4] Filtering to gemeente Huizen...")
    results = []
    for loc in locations:
        processed = process_location(loc, tariff_map, operator_median, boundary)
        if processed:
            results.append(processed)

    direct = sum(1 for r in results if r["pricing_source"] == "ndw")
    median = sum(1 for r in results if r["pricing_source"] == "operator_median")
    regional = sum(1 for r in results if r["pricing_source"] in {"totalenergies_mrae", "totalenergies_mrae_dc"})
    unknown = sum(1 for r in results if r["pricing_source"] == "unknown")
    comparison_ready = sum(1 for r in results if len(r["pricing"]) >= 2)

    print(f"  Locations in area:       {len(results)}")
    print(f"  Direct NDW CPO tariff:   {direct}")
    print(f"  Operator-median tariff:  {median}")
    print(f"  Official MRA-E fallback: {regional}")
    print(f"  Unknown CPO base tariff: {unknown}")
    print(f"  2+ pass estimates:       {comparison_ready}")

    operators = {}
    for result in results:
        operators[result["operator"]] = operators.get(result["operator"], 0) + 1
    print("\n  Operators found:")
    for operator, count in sorted(operators.items(), key=lambda item: -item[1]):
        print(f"    {operator}: {count}")

    output = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "NDW open data (opendata.ndw.nu)",
        "regional_pricing": {
            "totalenergies_mrae": {
                "ac_range": list(TOTALENERGIES_MRAE_AC_RANGE),
                "dc_rate": TOTALENERGIES_MRAE_DC_RATE,
                "verified_at": TOTALENERGIES_MRAE_VERIFIED_AT,
                "source_url": TOTALENERGIES_MRAE_SOURCE_URL,
                "municipality_source_url": HUIZEN_CHARGING_SOURCE_URL,
                "laadwerk_source_url": LAADWERK_SOURCE_URL,
            }
        },
        "bbox": {
            "lat_min": LAT_MIN,
            "lat_max": LAT_MAX,
            "lng_min": LNG_MIN,
            "lng_max": LNG_MAX,
        },
        "passes": PASSES,
        "stats": {
            "total": len(results),
            "available_snapshot": sum(1 for r in results if r["available"]),
            "ndw_priced": direct,
            "median_priced": median,
            "regional_priced": regional,
            "unknown_base_rate": unknown,
            "comparison_ready": comparison_ready,
        },
        "locations": results,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"\nWritten {OUTPUT_FILE} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
