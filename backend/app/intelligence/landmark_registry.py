"""
Authoritative Jezero Crater Landmark and Science Target Registry for MARSPath.
Enables natural-language extraction, ground-truth coordinate resolution,
and cross-referencing with official NASA USGS geological units.
"""

from __future__ import annotations

import re
from typing import Any

# Jezero regional bounding box
JEZERO_BOUNDS = {
    "min_lon": 77.1485,
    "max_lon": 77.9988,
    "min_lat": 18.1009,
    "max_lat": 18.7015,
}

# Authoritative landmarks within Jezero Crater
JEZERO_LANDMARKS: dict[str, dict[str, Any]] = {
    "perseverance_current": {
        "id": "PERSEVERANCE_SOL_2022",
        "name": "Perseverance Rover (Sol 2022 - Western Rim)",
        "lon": 77.2330,
        "lat": 18.4350,
        "geologic_unit": "Western Rim Scarp (W-rs)",
        "elevation_m": -2450.0,
        "description": "Current recorded operational position of the Mars 2020 Perseverance rover atop the Western Rim.",
        "aliases": [
            "current rover position",
            "rover position",
            "perseverance position",
            "current position",
            "rover",
            "perseverance",
            "here",
            "start",
        ],
    },
    "octavia_landing": {
        "id": "OCTAVIA_E_BUTLER_LANDING",
        "name": "Octavia E. Butler Landing Site (Máaz)",
        "lon": 77.4508,
        "lat": 18.4447,
        "geologic_unit": "Crater Floor Fractured Rough (Cf-fr)",
        "elevation_m": -2573.0,
        "description": "Perseverance touchdown site on the crater floor, igneous baseline for absolute dating.",
        "aliases": [
            "octavia",
            "octavia e butler",
            "landing site",
            "touchdown site",
            "maaz",
            "touchdown",
        ],
    },
    "seitah_ridge": {
        "id": "SEITAH_CARBONATE_RIDGE",
        "name": "Séítah Olivine-Carbonate Cumulate Ridge",
        "lon": 77.4395,
        "lat": 18.4310,
        "geologic_unit": "Crater Floor Fractured 1 (Cf-f1)",
        "elevation_m": -2580.0,
        "description": "Early Noachian olivine cumulate altered by aqueous carbonation; key astrobiology exploration target.",
        "aliases": [
            "séítah",
            "seitah",
            "south seitah",
            "seitah ridge",
            "olivine ridge",
            "cumulate ridge",
            "seitah carbonate",
        ],
    },
    "kodiak_butte": {
        "id": "KODIAK_DELTA_BUTTE",
        "name": "Kodiak Delta Remnant Butte",
        "lon": 77.4290,
        "lat": 18.4265,
        "geologic_unit": "Delta Blocky Remnant (D-bl)",
        "elevation_m": -2555.0,
        "description": "Isolated delta remnant butte displaying classic Gilbert-type delta foreset/topset bedding architecture.",
        "aliases": [
            "kodiak",
            "kodiak butte",
            "delta butte",
            "remnant butte",
            "kodiak remnant",
        ],
    },
    "western_delta": {
        "id": "WESTERN_DELTA_FRONT",
        "name": "Western Delta Front & Margin",
        "lon": 77.4400,
        "lat": 18.4200,
        "geologic_unit": "Delta Front Escarpment (D-fe)",
        "elevation_m": -2520.0,
        "description": "Fluvial-lacustrine delta front rich in clay minerals and carbonate deposits with high biosignature preservation potential.",
        "aliases": [
            "western delta",
            "delta front",
            "delta",
            "river delta",
            "delta apex",
            "delta margin",
            "fan front",
        ],
    },
    "belva_crater": {
        "id": "BELVA_CRATER",
        "name": "Belva Impact Crater",
        "lon": 77.3600,
        "lat": 18.4900,
        "geologic_unit": "Secondary Crater Rim (C-sec)",
        "elevation_m": -2480.0,
        "description": "Large superposed impact crater exposing sub-surface deltaic stratigraphy in its wall escarpments.",
        "aliases": [
            "belva",
            "belva crater",
            "belva impact",
        ],
    },
    "western_rim": {
        "id": "WESTERN_CRATER_RIM",
        "name": "Jezero Western Rim Scarp",
        "lon": 77.2500,
        "lat": 18.4500,
        "geologic_unit": "Crater Rim Mega-Breccia (C-mb)",
        "elevation_m": -2390.0,
        "description": "Elevated ancient Noachian basement rock defining the rim of the 45-km Jezero impact structure.",
        "aliases": [
            "rim",
            "western rim",
            "crater rim",
            "rim scarp",
        ],
    },
    "neretva_valles": {
        "id": "NERETVA_VALLES_INFLOW",
        "name": "Neretva Valles Inflow Channel",
        "lon": 77.3000,
        "lat": 18.5200,
        "geologic_unit": "Inflow Channel Fluvial Terraces (Ch-fl)",
        "elevation_m": -2410.0,
        "description": "Major breached paleocanyon that fed flood waters and sedimentary detritus into Jezero Crater.",
        "aliases": [
            "neretva",
            "neretva valles",
            "inflow channel",
            "inlet channel",
            "paleochannel",
        ],
    },
}

# Out-of-bounds planetary landmarks that are on Mars but far outside Jezero
KNOWN_NON_JEZERO_LANDMARKS = {
    "olympus mons": "Olympus Mons is located at ~133°W, 18°N (Tharsis province, ~7,500 km west of Jezero Crater).",
    "gale crater": "Gale Crater (Curiosity rover site) is at ~137.4°E, 4.6°S (~3,800 km southeast of Jezero Crater).",
    "valles marineris": "Valles Marineris canyon system is at ~290°E, 14°S (~4,000 km southwest of Jezero).",
    "gusev crater": "Gusev Crater (Spirit rover site) is at ~175.4°E, 14.5°S (~5,800 km southeast of Jezero).",
    "meridiani planum": "Meridiani Planum (Opportunity rover site) is at ~354.5°E, 1.9°S (~4,600 km west of Jezero).",
}


def is_within_jezero(lon: float, lat: float) -> bool:
    """Checks whether the given coordinate is within the Jezero study bounds."""
    return (
        JEZERO_BOUNDS["min_lon"] <= lon <= JEZERO_BOUNDS["max_lon"]
        and JEZERO_BOUNDS["min_lat"] <= lat <= JEZERO_BOUNDS["max_lat"]
    )


def check_out_of_bounds_landmarks(text: str) -> list[str]:
    """Detects Martian landmarks located outside Jezero Crater and returns contextual notes."""
    t_lower = text.lower()
    warnings = []
    for non_jezero, explanation in KNOWN_NON_JEZERO_LANDMARKS.items():
        pattern = r"\b" + re.escape(non_jezero) + r"\b"
        if re.search(pattern, t_lower):
            warnings.append(explanation)
    return warnings


def extract_explicit_coordinates(text: str) -> tuple[float, float] | None:
    """Extracts explicit numeric (lon, lat) or (lat, lon) from text if present."""
    # Matches patterns like 77.40E, 18.39N or 18.39, 77.40 or (77.4, 18.4)
    # Check for directional format: 77.4E, 18.4N or 18.4N, 77.4E
    m_dir = re.search(r"(\d+(?:\.\d+)?)\s*°?\s*([NSEWnsew])\s*[,;\s]+\s*(\d+(?:\.\d+)?)\s*°?\s*([NSEWnsew])", text)
    if m_dir:
        v1, d1, v2, d2 = float(m_dir.group(1)), m_dir.group(2).upper(), float(m_dir.group(3)), m_dir.group(4).upper()
        lat, lon = None, None
        if d1 in ("N", "S"):
            lat = v1 if d1 == "N" else -v1
        elif d1 in ("E", "W"):
            lon = v1 if d1 == "E" else (360 - v1)
        if d2 in ("N", "S"):
            lat = v2 if d2 == "N" else -v2
        elif d2 in ("E", "W"):
            lon = v2 if d2 == "E" else (360 - v2)
        if lon is not None and lat is not None:
            return (round(lon, 4), round(lat, 4))

    # Generic comma-separated decimal pair
    m_pair = re.search(r"\(?\s*(\d{2}\.\d+)\s*[,;\s]+\s*(\d{2}\.\d+)\s*\)?", text)
    if m_pair:
        n1, n2 = float(m_pair.group(1)), float(m_pair.group(2))
        # Disambiguate lon (~77) vs lat (~18)
        if 70.0 <= n1 <= 85.0 and 10.0 <= n2 <= 25.0:
            return (round(n1, 4), round(n2, 4))
        if 70.0 <= n2 <= 85.0 and 10.0 <= n1 <= 25.0:
            return (round(n2, 4), round(n1, 4))

    return None


def resolve_landmark_by_name(name_query: str) -> dict[str, Any] | None:
    """Finds a Jezero landmark matching the provided name or alias."""
    q = name_query.strip().lower()
    for key, data in JEZERO_LANDMARKS.items():
        if q == key or q == data["name"].lower():
            return data
        for alias in data["aliases"]:
            if alias in q or q in alias:
                return data
    return None


def resolve_all_landmarks_in_text(text: str) -> list[dict[str, Any]]:
    """Scans free-form user text and returns all matched landmarks."""
    t_lower = text.lower()
    matched = []
    seen_ids = set()
    for data in JEZERO_LANDMARKS.values():
        for alias in data["aliases"]:
            # Word boundary matching
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, t_lower):
                if data["id"] not in seen_ids:
                    seen_ids.add(data["id"])
                    matched.append(data)
                break
    return matched
