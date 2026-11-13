import json
import logging
import math
import os
import re
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.app.core.exceptions import MarsPathError, UnsupportedCRSError
from backend.app.geospatial.crs import (
    METERS_PER_DEGREE_LATITUDE,
    geo_to_pixel,
    meters_per_degree_lon,
)

logger = logging.getLogger("marspath.raster_loader")

# Optional rasterio and pyproj imports
try:
    import rasterio
    import rasterio.crs

    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    rasterio = None

try:
    import pyproj

    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False
    pyproj = None


@dataclass
class RasterMetadata:
    width: int
    height: int
    coordinate_type: str  # "geographic" or "projected"
    crs_str: str
    units: str  # "degrees" or "meters"
    min_lon: float  # Planetocentric East degrees [0, 360)
    min_lat: float  # Planetocentric degrees [-90, 90]
    max_lon: float
    max_lat: float
    deg_per_px_lon: float
    deg_per_px_lat: float
    meters_per_px_x: float
    meters_per_px_y: float
    affine_transform: tuple[float, float, float, float, float, float]
    nodata_value: float | None
    vertical_datum: str = "Unknown / Unspecified"
    vertical_units: str = "Unknown / Unspecified"
    metadata_tags: dict[str, str] = field(default_factory=dict)
    is_synthetic: bool = False


VERTICAL_UNIT_TAG_KEYS: tuple[str, ...] = (
    "VERTICAL_UNIT",
    "VERTICAL_UNITS",
    "ELEVATION_UNIT",
    "ELEVATION_UNITS",
    "Z_UNIT",
    "Z_UNITS",
    "UNIT_TYPE",
    "UNITTYPE",
    "UNIT",
    "UNITS",
)

_EXPLICIT_METRE_TOKENS: frozenset[str] = frozenset(
    {
        "m",
        "meter",
        "meters",
        "metre",
        "metres",
        "meter (m)",
        "meters (m)",
        "metre (m)",
        "metres (m)",
        "si_meter",
        "si_meters",
        "meters above areoid",
        "metres above areoid",
        "m above areoid",
    }
)

_CONVERTIBLE_METRIC_VERTICAL_UNITS: dict[str, float] = {
    "cm": 0.01,
    "centimeter": 0.01,
    "centimeters": 0.01,
    "centimetre": 0.01,
    "centimetres": 0.01,
    "mm": 0.001,
    "millimeter": 0.001,
    "millimeters": 0.001,
    "millimetre": 0.001,
    "millimetres": 0.001,
    "km": 1000.0,
    "kilometer": 1000.0,
    "kilometers": 1000.0,
    "kilometre": 1000.0,
    "kilometres": 1000.0,
}

_NON_ELEVATION_VALUE_UNITS: frozenset[str] = frozenset(
    {
        "dn",
        "digital_number",
        "digital number",
        "reflectance",
        "radiance",
        "albedo",
        "kelvin",
        "celsius",
        "degc",
        "db",
        "decibel",
        "index",
        "ratio",
        "unitless",
        "dimensionless",
        "count",
        "counts",
        "byte",
        "bytes",
        "pixel",
        "pixels",
        "uint8",
        "rgb",
    }
)

_UNSUPPORTED_VERTICAL_UNITS: frozenset[str] = frozenset(
    {
        "ft",
        "foot",
        "feet",
        "us_survey_foot",
        "survey_foot",
        "in",
        "inch",
        "inches",
        "yd",
        "yard",
        "yards",
        "mi",
        "mile",
        "miles",
        "deg",
        "degree",
        "degrees",
        "arcsec",
        "arcmin",
        "rad",
        "radian",
        "radians",
    }
)

_UNKNOWN_UNIT_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "",
        "none",
        "null",
        "unknown",
        "unspecified",
        "n/a",
        "na",
        "?",
        "undefined",
    }
)


def normalize_vertical_unit_token(
    raw_value: str | None,
) -> tuple[str | None, float | None, str]:
    """
    Normalizes an explicit vertical elevation unit string.
    Returns (canonical_unit, scale_to_meters, status_code).
    Never infers units from filenames, product IDs, or numeric magnitudes.
    """
    if raw_value is None:
        return None, None, "rejected_unknown_vertical_units"
    norm = " ".join(str(raw_value).strip().lower().split())
    if norm in _UNKNOWN_UNIT_PLACEHOLDERS:
        return None, None, "rejected_unknown_vertical_units"
    if norm in _EXPLICIT_METRE_TOKENS:
        return "meters", 1.0, "valid"
    if norm in _CONVERTIBLE_METRIC_VERTICAL_UNITS:
        return "meters", _CONVERTIBLE_METRIC_VERTICAL_UNITS[norm], "converted"
    if norm in _NON_ELEVATION_VALUE_UNITS or any(
        tok in norm for tok in ("reflectance", "radiance", "albedo", "digital number")
    ):
        return None, None, "rejected_non_elevation_raster"
    if norm in _UNSUPPORTED_VERTICAL_UNITS or any(
        tok in norm for tok in ("feet", "foot", "survey_foot", "degree", "radian")
    ):
        return None, None, "rejected_unsupported_vertical_units"
    return None, None, "rejected_unknown_vertical_units"


_PDS3_MARS2000_CANONICAL_DATUM = (
    "Mars 2000 Datum (Martian Equipotential Surface, Smith et al. 2001)"
)

_PDS3_ELEVATION_NOTE_RE = re.compile(
    r"pixel\s+values\s+(?:in\s+this\s+file\s+)?represent\s+elevations?\s+in\s+"
    r"(?P<unit>meters|metres|centimeters|centimetres|millimeters|millimetres|kilometers|kilometres|"
    r"feet|foot|us\s+survey\s+feet|degrees|radians|[a-z_]+)"
    r"\s+above\s+(?P<datum>[^.]+)\.",
    re.IGNORECASE,
)

_PDS3_RADIOMETRIC_NOTE_RE = re.compile(
    r"\b(?:conversion\s+from\s+dn\s+to\s+i/f|intensity/flux|radiance|reflectance|"
    r"albedo|brightness\s+temperature|figure\s+of\s+merit)\b",
    re.IGNORECASE,
)

_SUPPORTED_PDS3_DTM_SAMPLE_TYPES: frozenset[str] = frozenset(
    {
        "PC_REAL",
        "IEEE_REAL",
        "PC_INTEGER",
        "MSB_INTEGER",
        "LSB_INTEGER",
        "SIGNED_INTEGER",
        "INTEGER",
    }
)


def _strip_pds_quotes(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1].strip()
    return s


def _decode_pds3_missing_constant(raw_val: Any, sample_bits: int | None = 32) -> float | None:
    """
    Decodes a PDS3 MISSING_CONSTANT or CORE_NULL literal (such as `16#FF7FFFFB#` or `-32768`)
    into its numerical float representation.
    """
    if raw_val is None:
        return None
    if isinstance(raw_val, (int, float)):
        return float(raw_val)
    s = _strip_pds_quotes(raw_val)
    if not s:
        return None
    m_hex = re.match(r"^16#([0-9A-Fa-f]+)#$", s)
    if m_hex:
        hex_str = m_hex.group(1)
        if len(hex_str) == 8 and (sample_bits in (None, 32)):
            raw_bytes = bytes.fromhex(hex_str)
            # In HiRISE PDS3 PC_REAL labels, 16#FF7FFFFB# is the 32-bit hex representation
            # corresponding to -3.4028226550889045e+38 (big-endian float32 0xFF7FFFFB).
            val_be = struct.unpack(">f", raw_bytes)[0]
            if math.isfinite(val_be) and abs(val_be) > 1e30:
                return float(val_be)
            val_le = struct.unpack("<f", raw_bytes)[0]
            if math.isfinite(val_le):
                return float(val_le)
        if len(hex_str) == 4 and (sample_bits in (None, 16)):
            raw_bytes = bytes.fromhex(hex_str)
            val_signed = struct.unpack(">h", raw_bytes)[0]
            return float(val_signed)
        try:
            return float(int(hex_str, 16))
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_pds3_label_dict(src: Any) -> dict[str, Any] | None:
    """
    Extracts the parsed PDS3 label dictionary from Rasterio's `json:PDS` metadata domain
    (or `PDS` domain if present). Accepts a Rasterio DatasetReader or a filepath.
    Returns None if the dataset has no PDS3 metadata domain.
    """
    if isinstance(src, (str, bytes, os.PathLike)):
        try:
            with rasterio.open(src) as ds:
                return extract_pds3_label_dict(ds)
        except Exception:
            return None

    if src is None or not hasattr(src, "tag_namespaces"):
        return None
    try:
        namespaces = list(src.tag_namespaces() or [])
    except Exception:
        namespaces = []

    for ns in namespaces:
        if ns in ("json:PDS", "PDS"):
            try:
                ns_tags = src.tags(ns=ns)
            except Exception:
                continue
            if not ns_tags:
                continue
            for k, v in ns_tags.items():
                candidate = f"{k}:{v}" if k.lstrip().startswith("{") else str(v)
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    continue
    return None


@dataclass
class PDS3DTMParseResult:
    """Controlled parse result for an embedded NASA/USGS/UArizona PDS3 DTM label."""

    has_pds3_label: bool
    is_valid_dtm: bool
    status_code: str
    reason: str
    vertical_units: str = "Unknown / Unspecified"
    unit_scale_to_meters: float = 1.0
    vertical_datum: str = "Unknown / Unspecified"
    scaling_factor: float = 1.0
    offset: float = 0.0
    sample_bits: int | None = None
    sample_type: str | None = None
    core_null: float | None = None
    missing_constant_raw: str | None = None
    note_text: str | None = None
    product_id: str | None = None
    data_set_id: str | None = None
    source_product_ids: list[str] = field(default_factory=list)
    producer_institution_name: str | None = None
    valid_minimum: float | None = None
    valid_maximum: float | None = None


def parse_pds3_hirise_dtm_label(pds_dict: dict[str, Any] | None) -> PDS3DTMParseResult:
    """
    Controlled parser for the official NASA/JPL/UArizona HiRISE PDS3 DTM label semantics.

    Inspects:
    - `IMAGE.NOTE` (or top-level `NOTE`)
    - `IMAGE.SCALING_FACTOR`
    - `IMAGE.OFFSET`
    - `IMAGE.SAMPLE_BITS`
    - `IMAGE.SAMPLE_TYPE`
    - `IMAGE.CORE_NULL` / `IMAGE.MISSING_CONSTANT`
    - `TARGET_NAME`, `PRODUCT_ID`, `DATA_SET_ID`, `SOURCE_PRODUCT_ID`

    Never accepts arbitrary prose as proof of metre units, and never invents a unit or
    vertical datum if the PDS3 label does not explicitly establish one.
    """
    if not pds_dict or not isinstance(pds_dict, dict):
        return PDS3DTMParseResult(
            has_pds3_label=False,
            is_valid_dtm=False,
            status_code="no_pds3_label",
            reason="No PDS3 label metadata domain found.",
        )

    pds_ver = _strip_pds_quotes(pds_dict.get("PDS_VERSION_ID", "")).upper()
    if pds_ver and pds_ver != "PDS3":
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code="rejected_unknown_vertical_units",
            reason=f"Unsupported PDS label version '{pds_ver}' (expected PDS3).",
        )

    target_name = _strip_pds_quotes(pds_dict.get("TARGET_NAME", "")).upper()
    if target_name and target_name != "MARS":
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code="rejected_invalid_crs",
            reason=f"PDS3 label declares non-Mars TARGET_NAME='{target_name}'.",
        )

    product_id = _strip_pds_quotes(pds_dict.get("PRODUCT_ID")) or None
    data_set_id = _strip_pds_quotes(pds_dict.get("DATA_SET_ID")) or None
    producer_inst = _strip_pds_quotes(pds_dict.get("PRODUCER_INSTITUTION_NAME")) or None

    raw_src_ids = pds_dict.get("SOURCE_PRODUCT_ID")
    src_ids: list[str] = []
    if isinstance(raw_src_ids, list):
        src_ids = [_strip_pds_quotes(x) for x in raw_src_ids if _strip_pds_quotes(x)]
    elif isinstance(raw_src_ids, str):
        cleaned_src = raw_src_ids.strip().strip("()")
        src_ids = [
            _strip_pds_quotes(tok)
            for tok in cleaned_src.split(",")
            if _strip_pds_quotes(tok)
        ]

    # Locate the IMAGE object (either direct `IMAGE` or `UNCOMPRESSED_FILE.IMAGE`)
    img_obj = pds_dict.get("IMAGE")
    if not isinstance(img_obj, dict):
        uncomp = pds_dict.get("UNCOMPRESSED_FILE")
        if isinstance(uncomp, dict) and isinstance(uncomp.get("IMAGE"), dict):
            img_obj = uncomp["IMAGE"]
        else:
            img_obj = {}

    # 1. Validate SAMPLE_TYPE and SAMPLE_BITS
    sample_type_raw = _strip_pds_quotes(img_obj.get("SAMPLE_TYPE", pds_dict.get("SAMPLE_TYPE", ""))).upper()
    sample_bits_raw = img_obj.get("SAMPLE_BITS", pds_dict.get("SAMPLE_BITS"))
    sample_bits: int | None = None
    if sample_bits_raw is not None:
        try:
            sample_bits = int(sample_bits_raw)
        except (TypeError, ValueError):
            return PDS3DTMParseResult(
                has_pds3_label=True,
                is_valid_dtm=False,
                status_code="rejected_corrupt_raster",
                reason=f"Invalid non-integer PDS3 SAMPLE_BITS='{sample_bits_raw}'.",
            )

    if sample_type_raw and (
        "UNSIGNED" in sample_type_raw
        or "COMPLEX" in sample_type_raw
        or sample_type_raw not in _SUPPORTED_PDS3_DTM_SAMPLE_TYPES
    ):
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code="rejected_non_elevation_raster",
            reason=(
                f"PDS3 SAMPLE_TYPE='{sample_type_raw}' (SAMPLE_BITS={sample_bits}) indicates "
                "radiometric imagery or unsupported sample encoding rather than numerical DTM elevation."
            ),
            sample_bits=sample_bits,
            sample_type=sample_type_raw or None,
            product_id=product_id,
            data_set_id=data_set_id,
            source_product_ids=src_ids,
        )

    if sample_bits is not None and sample_bits <= 8:
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code="rejected_non_elevation_raster",
            reason=f"PDS3 SAMPLE_BITS={sample_bits} indicates 8-bit browse/ortho imagery rather than numerical DTM elevation.",
            sample_bits=sample_bits,
            sample_type=sample_type_raw or None,
            product_id=product_id,
            data_set_id=data_set_id,
            source_product_ids=src_ids,
        )

    # 2. Validate SCALING_FACTOR and OFFSET
    raw_scale = img_obj.get("SCALING_FACTOR", pds_dict.get("SCALING_FACTOR", 1.0))
    raw_offset = img_obj.get("OFFSET", pds_dict.get("OFFSET", 0.0))
    try:
        scaling_factor = float(raw_scale) if raw_scale is not None else 1.0
        offset = float(raw_offset) if raw_offset is not None else 0.0
    except (TypeError, ValueError):
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code="rejected_corrupt_raster",
            reason=f"Invalid non-numeric PDS3 SCALING_FACTOR='{raw_scale}' or OFFSET='{raw_offset}'.",
            product_id=product_id,
            data_set_id=data_set_id,
            source_product_ids=src_ids,
        )

    if not math.isfinite(scaling_factor) or scaling_factor <= 0.0 or not math.isfinite(offset):
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code="rejected_corrupt_raster",
            reason=(
                f"PDS3 label declares non-finite or non-positive SCALING_FACTOR={scaling_factor} "
                f"or OFFSET={offset}."
            ),
            product_id=product_id,
            data_set_id=data_set_id,
            source_product_ids=src_ids,
        )

    # 3. Extract CORE_NULL / MISSING_CONSTANT and VALID_MINIMUM / VALID_MAXIMUM
    raw_missing = img_obj.get(
        "CORE_NULL",
        img_obj.get(
            "MISSING_CONSTANT",
            pds_dict.get("CORE_NULL", pds_dict.get("MISSING_CONSTANT")),
        ),
    )
    missing_raw_str = _strip_pds_quotes(raw_missing) if raw_missing is not None else None
    core_null = _decode_pds3_missing_constant(raw_missing, sample_bits=sample_bits)

    valid_min: float | None = None
    valid_max: float | None = None
    if img_obj.get("VALID_MINIMUM") is not None:
        try:
            valid_min = float(img_obj["VALID_MINIMUM"])
        except (TypeError, ValueError):
            pass
    if img_obj.get("VALID_MAXIMUM") is not None:
        try:
            valid_max = float(img_obj["VALID_MAXIMUM"])
        except (TypeError, ValueError):
            pass

    # 4. Inspect and parse the PDS3 NOTE declaration
    raw_note = img_obj.get("NOTE", pds_dict.get("NOTE", ""))
    note_clean = " ".join(
        _strip_pds_quotes(raw_note).replace("\\r", " ").replace("\\n", " ").split()
    )
    if not note_clean:
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code="rejected_unknown_vertical_units",
            reason=(
                "PDS3 label lacks a required IMAGE.NOTE elevation unit and datum declaration "
                "(missing PDS3 NOTE is never assumed to be metre-based elevation data)."
            ),
            scaling_factor=scaling_factor,
            offset=offset,
            sample_bits=sample_bits,
            sample_type=sample_type_raw or None,
            core_null=core_null,
            missing_constant_raw=missing_raw_str,
            product_id=product_id,
            data_set_id=data_set_id,
            source_product_ids=src_ids,
        )

    if _PDS3_RADIOMETRIC_NOTE_RE.search(note_clean):
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code="rejected_non_elevation_raster",
            reason=(
                f"PDS3 IMAGE.NOTE declares radiometric/orthoimage values rather than elevation: "
                f"'{note_clean[:140]}'."
            ),
            note_text=note_clean,
            product_id=product_id,
            data_set_id=data_set_id,
            source_product_ids=src_ids,
        )

    if any(
        earth_tok in note_clean.lower()
        for earth_tok in ("wgs84", "wgs 84", "egm96", "egm2008", "navd88", "earth")
    ):
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code="rejected_invalid_crs",
            reason=f"PDS3 IMAGE.NOTE declares Earth or non-Mars coordinate reference system: '{note_clean[:140]}'.",
            note_text=note_clean,
            product_id=product_id,
            data_set_id=data_set_id,
            source_product_ids=src_ids,
        )

    m_note = _PDS3_ELEVATION_NOTE_RE.search(note_clean)
    if not m_note:
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code="rejected_unknown_vertical_units",
            reason=(
                f"PDS3 IMAGE.NOTE does not match the recognized HiRISE DTM elevation-unit and datum "
                f"declaration semantics: '{note_clean[:140]}'."
            ),
            note_text=note_clean,
            product_id=product_id,
            data_set_id=data_set_id,
            source_product_ids=src_ids,
        )

    unit_token = m_note.group("unit").strip()
    datum_clause = " ".join(m_note.group("datum").strip().split())

    canonical_unit, unit_scale, unit_code = normalize_vertical_unit_token(unit_token)
    if canonical_unit is None or unit_scale is None:
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code=unit_code,
            reason=(
                f"PDS3 IMAGE.NOTE declares unsupported or unrecognized vertical unit '{unit_token}' "
                f"({unit_code})."
            ),
            note_text=note_clean,
            product_id=product_id,
            data_set_id=data_set_id,
            source_product_ids=src_ids,
        )

    # Validate the declared vertical reference datum in the NOTE clause
    datum_lower = datum_clause.lower()
    if any(earth_tok in datum_lower for earth_tok in ("wgs84", "wgs 84", "egm96", "egm2008", "navd88", "earth", "sea level")):
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code="rejected_invalid_crs",
            reason=f"PDS3 IMAGE.NOTE declares non-Mars vertical datum '{datum_clause}'.",
            note_text=note_clean,
            product_id=product_id,
            data_set_id=data_set_id,
            source_product_ids=src_ids,
        )

    if (
        "martian equipotential surface" in datum_lower
        and "mars 2000 datum" in datum_lower
    ):
        resolved_datum = _PDS3_MARS2000_CANONICAL_DATUM
    elif "mars 2000 datum" in datum_lower:
        resolved_datum = "Mars 2000 Datum"
    elif "martian equipotential surface" in datum_lower:
        resolved_datum = "Mars 2000 Datum (Martian Equipotential Surface)"
    elif "mola" in datum_lower and ("areoid" in datum_lower or "aeroid" in datum_lower):
        resolved_datum = "Mars Areoid (MOLA 0m reference datum)"
    else:
        return PDS3DTMParseResult(
            has_pds3_label=True,
            is_valid_dtm=False,
            status_code="rejected_unknown_vertical_units",
            reason=(
                f"PDS3 IMAGE.NOTE does not establish a recognized Mars vertical datum "
                f"(found 'above {datum_clause}')."
            ),
            note_text=note_clean,
            product_id=product_id,
            data_set_id=data_set_id,
            source_product_ids=src_ids,
        )

    status_out = "converted" if (abs(unit_scale - 1.0) > 1e-12 or abs(scaling_factor - 1.0) > 1e-12 or abs(offset) > 1e-12) else "valid"
    reason_out = (
        f"Verified PDS3 HiRISE DTM label NOTE declaring elevations in '{unit_token}' above "
        f"'{resolved_datum}' (SCALING_FACTOR={scaling_factor:g}, OFFSET={offset:g})."
    )

    return PDS3DTMParseResult(
        has_pds3_label=True,
        is_valid_dtm=True,
        status_code=status_out,
        reason=reason_out,
        vertical_units="meters",
        unit_scale_to_meters=float(unit_scale),
        vertical_datum=resolved_datum,
        scaling_factor=scaling_factor,
        offset=offset,
        sample_bits=sample_bits,
        sample_type=sample_type_raw or None,
        core_null=core_null,
        missing_constant_raw=missing_raw_str,
        note_text=note_clean,
        product_id=product_id,
        data_set_id=data_set_id,
        source_product_ids=src_ids,
        producer_institution_name=producer_inst,
        valid_minimum=valid_min,
        valid_maximum=valid_max,
    )


def inspect_vertical_unit_declarations(
    band_unit: str | None,
    band_tags: dict[str, Any] | None,
    dataset_tags: dict[str, Any] | None,
    pds3_dict: dict[str, Any] | None = None,
) -> tuple[bool, str, str, float, str]:
    """
    Positively validates vertical elevation units across Rasterio band units (`src.units`),
    GeoTIFF band tags (`src.tags(1)`), dataset tags (`src.tags()`), and embedded PDS3 DTM
    label declarations (`json:PDS`).

    Returns:
        (is_valid, status_code, reason, scale_to_meters, resolved_unit_label)
    """
    declarations: list[tuple[str, str]] = []
    if band_unit is not None and str(band_unit).strip() != "":
        declarations.append(("band_1.unit", str(band_unit).strip()))

    if band_tags:
        b_upper = {str(k).upper(): str(v).strip() for k, v in band_tags.items()}
        for key in VERTICAL_UNIT_TAG_KEYS:
            if key in b_upper and b_upper[key] != "":
                declarations.append((f"band_1.tag[{key}]", b_upper[key]))

    if dataset_tags:
        d_upper = {str(k).upper(): str(v).strip() for k, v in dataset_tags.items()}
        for key in VERTICAL_UNIT_TAG_KEYS:
            if key in d_upper and d_upper[key] != "":
                declarations.append((f"dataset.tag[{key}]", d_upper[key]))

    pds3_res = parse_pds3_hirise_dtm_label(pds3_dict) if pds3_dict else None

    if not declarations and (pds3_res is None or not pds3_res.has_pds3_label):
        return (
            False,
            "rejected_unknown_vertical_units",
            (
                "Raster lacks explicit vertical elevation unit metadata in band units, GeoTIFF tags, "
                "or PDS3 DTM label (expected explicit metre units; missing or unknown units are rejected)."
            ),
            1.0,
            "Unknown / Unspecified",
        )

    resolved_scales: list[tuple[str, str, float, str]] = []
    for src_label, raw_val in declarations:
        canonical, scale, code = normalize_vertical_unit_token(raw_val)
        if canonical is None or scale is None:
            return (
                False,
                code,
                (
                    f"Raster declares invalid, unknown, or unsupported vertical unit '{raw_val}' "
                    f"in {src_label} ({code}; expected explicit metre units)."
                ),
                1.0,
                raw_val,
            )
        resolved_scales.append((src_label, raw_val, float(scale), code))

    if pds3_res is not None and pds3_res.has_pds3_label:
        if not pds3_res.is_valid_dtm:
            return (
                False,
                pds3_res.status_code,
                pds3_res.reason,
                1.0,
                "Unknown / Unspecified",
            )
        resolved_scales.append(
            (
                "pds3_label.IMAGE.NOTE",
                pds3_res.vertical_units,
                float(pds3_res.unit_scale_to_meters),
                pds3_res.status_code,
            )
        )

    first_scale = resolved_scales[0][2]
    for src_label, raw_val, scale, _ in resolved_scales[1:]:
        if abs(scale - first_scale) > 1e-12:
            return (
                False,
                "rejected_unknown_vertical_units",
                (
                    f"Raster contains conflicting vertical unit declarations across metadata fields: "
                    f"{resolved_scales[0][0]}='{resolved_scales[0][1]}' vs {src_label}='{raw_val}'."
                ),
                1.0,
                "Ambiguous / Conflicting",
            )

    if pds3_res is not None and pds3_res.is_valid_dtm:
        return (
            True,
            pds3_res.status_code,
            pds3_res.reason,
            float(pds3_res.unit_scale_to_meters),
            "meters",
        )

    primary_src, primary_raw, final_scale, final_code = resolved_scales[0]
    if final_code == "converted":
        reason = (
            f"Verified explicit vertical unit '{primary_raw}' in {primary_src}; "
            f"converted to meters with scale factor {final_scale:g}."
        )
    else:
        reason = f"Verified explicit metre vertical unit '{primary_raw}' in {primary_src}."
    return True, final_code, reason, final_scale, "meters"


def get_file_identity(file_path: str) -> tuple[str, int, int, int, int, int] | None:
    """
    Computes a fast, deterministic file identity key combining:
    - Canonical resolved path (`realpath`)
    - File size in bytes (`st_size`)
    - Modification time in nanoseconds (`st_mtime_ns`)
    - Metadata change time in nanoseconds (`st_ctime_ns`)
    - Inode number (`st_ino`)
    - Lightweight 12 KB header/middle/tail CRC32 sample (`zlib.crc32`) so even
      sub-millisecond same-size in-place file rewrites are detected without
      reading or hashing the full raster.
    """
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        resolved = os.path.realpath(os.path.abspath(file_path))
        st = os.stat(resolved)
        size = int(st.st_size)
        crc = 0
        if size > 0:
            with open(resolved, "rb") as f:
                crc = zlib.crc32(f.read(4096), crc)
                if size > 8192:
                    f.seek(size // 2)
                    crc = zlib.crc32(f.read(4096), crc)
                if size > 4096:
                    f.seek(max(0, size - 4096))
                    crc = zlib.crc32(f.read(4096), crc)
        return (
            resolved,
            size,
            int(st.st_mtime_ns),
            int(st.st_ctime_ns),
            int(st.st_ino),
            int(crc),
        )
    except OSError:
        return None


class RasterData:
    def __init__(self, data: np.ndarray, metadata: RasterMetadata):
        self.data = data.astype(np.float32)
        self.metadata = metadata
        self._init_nodata_mask()

    def _init_nodata_mask(self):
        mask = np.isnan(self.data) | ~np.isfinite(self.data)
        if self.metadata.nodata_value is not None:
            mask = mask | (
                np.isclose(self.data, self.metadata.nodata_value, rtol=1e-6, atol=1e-3)
            )
        # Standard Mars PDS nodata sentinels (including 16#FF7FFFFB# ~ -3.4028227e+38)
        mask = mask | (self.data < -9000.0) | (self.data > 1e30)
        self.nodata_mask = mask

    @property
    def shape(self) -> tuple[int, int]:
        return self.data.shape

    def mark_readonly(self) -> None:
        """Marks internal elevation and nodata arrays as read-only so shared cached rasters cannot be mutated."""
        self.data.flags.writeable = False
        self.nodata_mask.flags.writeable = False

    def get_elevation_at_pixel(self, col: int, row: int) -> float:
        if 0 <= row < self.data.shape[0] and 0 <= col < self.data.shape[1]:
            val = float(self.data[row, col])
            return val if not self.nodata_mask[row, col] else float("nan")
        return float("nan")

    def geo_to_native_pixel_float(self, lon: float, lat: float) -> tuple[float, float]:
        """
        Maps Mars planetocentric (lon, lat) in degrees to continuous pixel coordinates
        (col_float, row_float) using the raster's actual CRS and affine transform.
        In PixelIsArea convention, pixel (c, r) spans [c, c+1) x [r, r+1) with center (c+0.5, r+0.5).
        """
        meta = self.metadata
        a, b, c_off, d, e, f_off = meta.affine_transform
        det = a * e - b * d

        if meta.coordinate_type == "projected" and HAS_PYPROJ and meta.crs_str not in ("", "Unknown / Unspecified"):
            mars_geo_crs = pyproj.CRS("+proj=longlat +R=3396190 +no_defs")
            transformer = pyproj.Transformer.from_crs(
                mars_geo_crs, pyproj.CRS.from_user_input(meta.crs_str), always_xy=True
            )
            x_val, y_val = transformer.transform(lon, lat)
        else:
            x_val, y_val = lon, lat

        if abs(det) > 1e-18:
            dx = x_val - c_off
            dy = y_val - f_off
            col_f = (e * dx - b * dy) / det
            row_f = (-d * dx + a * dy) / det
            return float(col_f), float(row_f)

        col, row = geo_to_pixel(
            lon,
            lat,
            meta.min_lon,
            meta.max_lat,
            meta.deg_per_px_lon,
            meta.deg_per_px_lat,
            pixel_center=True,
        )
        return float(col) + 0.5, float(row) + 0.5

    def get_elevation_at_geo(self, lon: float, lat: float) -> float:
        meta = self.metadata
        if meta.coordinate_type == "projected" and HAS_PYPROJ and meta.crs_str not in ("", "Unknown / Unspecified"):
            col_f, row_f = self.geo_to_native_pixel_float(lon, lat)
            col = int(np.floor(col_f))
            row = int(np.floor(row_f))
            return self.get_elevation_at_pixel(col, row)
        col, row = geo_to_pixel(
            lon,
            lat,
            meta.min_lon,
            meta.max_lat,
            meta.deg_per_px_lon,
            meta.deg_per_px_lat,
            pixel_center=True,
        )
        return self.get_elevation_at_pixel(col, row)


def _validate_not_earth_crs(crs_obj, file_path: str) -> None:
    """Rejects terrestrial Earth datums or non-Mars planetary radii."""
    if crs_obj is None:
        return
    crs_str = str(crs_obj).upper()
    if (
        "WGS" in crs_str
        or "EPSG:4326" in crs_str
        or "EPSG:3857" in crs_str
        or "EARTH" in crs_str
        or "NAD83" in crs_str
    ):
        raise UnsupportedCRSError(
            crs_str,
            supported=["IAU2000:49900", "MARS2000_SPHERE", "MARS_EQUIRECTANGULAR"],
        )
    if hasattr(crs_obj, "ellipsoid") and crs_obj.ellipsoid:
        semi_major = crs_obj.ellipsoid.semi_major_metre
        if semi_major and abs(semi_major - 6378137.0) < 10000.0:
            raise UnsupportedCRSError(
                f"Earth WGS84 (radius ~{semi_major:.0f}m) in {file_path}",
                supported=["Mars IAU2000 Sphere (R=3,396,190m)"],
            )
        if semi_major and not (3370000.0 <= semi_major <= 3405000.0):
            raise UnsupportedCRSError(
                f"Non-Mars ellipsoid radius ({semi_major:.1f}m) in {file_path}",
                supported=["Mars IAU2000 Sphere (R=3,396,190m)"],
            )
    if HAS_PYPROJ:
        try:
            proj_crs = pyproj.CRS.from_user_input(crs_obj)
            if proj_crs.ellipsoid and proj_crs.ellipsoid.semi_major_metre:
                sm = float(proj_crs.ellipsoid.semi_major_metre)
                if abs(sm - 6378137.0) < 10000.0 or not (3370000.0 <= sm <= 3405000.0):
                    raise UnsupportedCRSError(
                        f"Unsupported planetary datum radius ({sm:.1f}m) in {file_path}",
                        supported=["Mars IAU2000 Sphere (R=3,396,190m)"],
                    )
        except UnsupportedCRSError:
            raise
        except Exception:
            pass


def load_raster_file(file_path: str) -> RasterData:
    """
    Loads and georeferences a numerical raster from disk (GeoTIFF, NumPy .npy/.npz).
    Rigidly inspects CRS, affine transforms, units, and bounds.
    Distinguishes geographic degrees from projected metric coordinates.
    Never assigns arbitrary invented bounds when metadata is missing.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Raster file not found at: {file_path}")

    # Handle .npy / .npz direct serialized arrays with explicit headers
    if file_path.endswith(".npy") or file_path.endswith(".npz"):
        loaded = np.load(file_path)
        data = loaded["elevation"] if isinstance(loaded, np.lib.npyio.NpzFile) else loaded

        if not isinstance(loaded, np.lib.npyio.NpzFile) or "min_lon" not in loaded:
            raise MarsPathError(
                f"NumPy raster '{file_path}' lacks required georeferencing header fields (min_lon, min_lat, max_lon, max_lat)."
            )

        min_lon = float(loaded["min_lon"])
        min_lat = float(loaded["min_lat"])
        max_lon = float(loaded["max_lon"])
        max_lat = float(loaded["max_lat"])
        nodata_val = float(loaded.get("nodata", -9999.0))
        vert_datum = str(loaded.get("vertical_datum", "Unknown / Unspecified"))
        npz_crs = str(loaded.get("crs", "Unknown / Unspecified")).strip() or "Unknown / Unspecified"
        tags = {str(k): str(v) for k, v in loaded.items() if k not in ("elevation", "data")}

        d_lon = (max_lon - min_lon) / data.shape[1]
        d_lat = (max_lat - min_lat) / data.shape[0]
        center_lat = (min_lat + max_lat) / 2.0
        m_x = d_lon * meters_per_degree_lon(center_lat)
        m_y = d_lat * METERS_PER_DEGREE_LATITUDE

        unit_ok, unit_status, unit_reason, unit_scale, resolved_v_unit = (
            inspect_vertical_unit_declarations(None, None, tags)
        )
        tags["_VERTICAL_UNIT_VALID"] = "true" if unit_ok else "false"
        tags["_VERTICAL_UNIT_STATUS"] = unit_status
        tags["_VERTICAL_UNIT_REASON"] = unit_reason
        tags["_VERTICAL_UNIT_SCALE"] = str(unit_scale)

        data_f32 = data.astype(np.float32).copy()
        if unit_ok and abs(unit_scale - 1.0) > 1e-12:
            raw_nd = np.isnan(data_f32) | (
                np.isclose(data_f32, nodata_val, atol=1e-3)
                if nodata_val is not None
                else np.zeros_like(data_f32, dtype=bool)
            )
            data_f32[~raw_nd] *= float(unit_scale)
            data_f32[raw_nd] = np.nan
            tags["VERTICAL_UNIT_CONVERSION"] = unit_reason

        meta = RasterMetadata(
            width=data_f32.shape[1],
            height=data_f32.shape[0],
            coordinate_type="geographic",
            crs_str=npz_crs,
            units="degrees",
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            deg_per_px_lon=d_lon,
            deg_per_px_lat=d_lat,
            meters_per_px_x=m_x,
            meters_per_px_y=m_y,
            affine_transform=(d_lon, 0.0, min_lon, 0.0, -d_lat, max_lat),
            nodata_value=nodata_val,
            vertical_datum=vert_datum,
            vertical_units=resolved_v_unit,
            metadata_tags=tags,
            is_synthetic=False,
        )
        return RasterData(data_f32, meta)

    # GeoTIFF / PDS3 IMG loading via Rasterio
    if HAS_RASTERIO:
        try:
            with rasterio.open(file_path) as src:
                data = src.read(1)
                bounds = src.bounds
                crs_obj = src.crs
                transform = src.transform

                # 1. Reject Earth CRS
                _validate_not_earth_crs(crs_obj, file_path)

                # 2. Check if bounds are projected in meters
                is_metric = False
                if crs_obj and crs_obj.is_projected:
                    is_metric = True
                elif (
                    abs(bounds.left) > 360.0
                    or abs(bounds.right) > 360.0
                    or abs(bounds.top) > 90.0
                    or abs(bounds.bottom) > 90.0
                ):
                    is_metric = True

                # Extract vertical datum and vertical unit declarations from band + dataset tags + PDS3 label
                tags = dict(src.tags())
                band_tags = dict(src.tags(1)) if src.count >= 1 else {}
                band_unit = src.units[0] if (src.units and len(src.units) > 0) else None
                pds3_dict = extract_pds3_label_dict(src)
                pds3_res = parse_pds3_hirise_dtm_label(pds3_dict) if pds3_dict else None

                unit_ok, unit_status, unit_reason, unit_scale, resolved_v_unit = (
                    inspect_vertical_unit_declarations(band_unit, band_tags, tags, pds3_dict=pds3_dict)
                )
                merged_tags = {
                    str(k): _strip_pds_quotes(v) if isinstance(v, str) else str(v)
                    for k, v in tags.items()
                }
                for bk, bv in band_tags.items():
                    if bk not in merged_tags:
                        merged_tags[bk] = _strip_pds_quotes(bv) if isinstance(bv, str) else str(bv)
                if band_unit is not None and str(band_unit).strip():
                    merged_tags["_BAND_1_UNIT"] = str(band_unit).strip()
                merged_tags["_VERTICAL_UNIT_VALID"] = "true" if unit_ok else "false"
                merged_tags["_VERTICAL_UNIT_STATUS"] = unit_status
                merged_tags["_VERTICAL_UNIT_REASON"] = unit_reason
                merged_tags["_VERTICAL_UNIT_SCALE"] = str(unit_scale)
                merged_tags["_RASTER_DRIVER"] = str(src.driver or "")

                # Capture PDS3 label metadata and check for vertical datum conflicts
                explicit_tag_datum = (
                    merged_tags.get("VERTICAL_DATUM") or merged_tags.get("DATUM") or ""
                ).strip()
                if pds3_res is not None and pds3_res.has_pds3_label:
                    merged_tags["_HAS_PDS3_LABEL"] = "true"
                    if pds3_res.product_id:
                        merged_tags["PRODUCT_ID"] = pds3_res.product_id
                        merged_tags["PDS3_PRODUCT_ID"] = pds3_res.product_id
                    if pds3_res.data_set_id:
                        merged_tags["DATA_SET_ID"] = pds3_res.data_set_id
                    if pds3_res.source_product_ids:
                        merged_tags["SOURCE_PRODUCT_ID"] = ",".join(pds3_res.source_product_ids)
                    if pds3_res.producer_institution_name:
                        merged_tags["PRODUCER_INSTITUTION_NAME"] = pds3_res.producer_institution_name
                    if pds3_res.note_text:
                        merged_tags["PDS3_NOTE"] = pds3_res.note_text
                    if pds3_res.sample_type:
                        merged_tags["PDS3_SAMPLE_TYPE"] = pds3_res.sample_type
                    if pds3_res.sample_bits is not None:
                        merged_tags["PDS3_SAMPLE_BITS"] = str(pds3_res.sample_bits)
                    merged_tags["PDS3_SCALING_FACTOR"] = str(pds3_res.scaling_factor)
                    merged_tags["PDS3_OFFSET"] = str(pds3_res.offset)
                    if pds3_res.missing_constant_raw is not None:
                        merged_tags["PDS3_MISSING_CONSTANT"] = pds3_res.missing_constant_raw
                    if pds3_res.core_null is not None:
                        merged_tags["PDS3_CORE_NULL"] = str(pds3_res.core_null)

                    if pds3_res.is_valid_dtm:
                        if (
                            explicit_tag_datum
                            and explicit_tag_datum.upper() != pds3_res.vertical_datum.upper()
                            and "MARS 2000" not in explicit_tag_datum.upper()
                            and "EQUIPOTENTIAL" not in explicit_tag_datum.upper()
                        ):
                            unit_ok = False
                            unit_status = "rejected_unknown_vertical_units"
                            unit_reason = (
                                f"Conflicting vertical datum declarations between tag "
                                f"VERTICAL_DATUM='{explicit_tag_datum}' and PDS3 NOTE datum "
                                f"'{pds3_res.vertical_datum}'."
                            )
                            merged_tags["_VERTICAL_UNIT_VALID"] = "false"
                            merged_tags["_VERTICAL_UNIT_STATUS"] = unit_status
                            merged_tags["_VERTICAL_UNIT_REASON"] = unit_reason
                            vert_datum = "Ambiguous / Conflicting"
                        else:
                            vert_datum = pds3_res.vertical_datum
                            merged_tags["VERTICAL_DATUM"] = vert_datum
                    else:
                        vert_datum = explicit_tag_datum or "Unknown / Unspecified (datum tag not declared in raster metadata)"
                else:
                    vert_datum = explicit_tag_datum or "Unknown / Unspecified (datum tag not declared in raster metadata)"

                nodata_val: float | None = float(src.nodata) if src.nodata is not None else None
                pds_core_null: float | None = None
                pds_missing_const: float | None = None
                if pds3_res is not None:
                    if pds3_res.core_null is not None:
                        pds_core_null = float(pds3_res.core_null)
                    if pds3_res.missing_constant_raw is not None:
                        pds_missing_const = _decode_pds3_missing_constant(
                            pds3_res.missing_constant_raw, pds3_res.sample_bits
                        )
                if nodata_val is None:
                    if pds_core_null is not None:
                        nodata_val = pds_core_null
                    elif pds_missing_const is not None:
                        nodata_val = pds_missing_const

                data_f32 = data.astype(np.float32).copy()

                # Step 1: Construct raw NoData mask strictly using explicit source NoData,
                # PDS3 CORE_NULL, PDS3 MISSING_CONSTANT, NaN, non-finite values, and extreme sentinels (> 1e30).
                # Do NOT apply physical elevation thresholds (< -9000m) to unscaled storage values!
                raw_nd = (
                    np.isnan(data_f32)
                    | ~np.isfinite(data_f32)
                    | (np.abs(data_f32) > 1e30)
                )
                if nodata_val is not None:
                    raw_nd = raw_nd | np.isclose(data_f32, nodata_val, rtol=1e-6, atol=1e-3)
                if pds_core_null is not None:
                    raw_nd = raw_nd | np.isclose(data_f32, pds_core_null, rtol=1e-6, atol=1e-3)
                if pds_missing_const is not None:
                    raw_nd = raw_nd | np.isclose(data_f32, pds_missing_const, rtol=1e-6, atol=1e-3)

                pds_scale = float(pds3_res.scaling_factor) if (pds3_res and pds3_res.is_valid_dtm) else 1.0
                pds_offset = float(pds3_res.offset) if (pds3_res and pds3_res.is_valid_dtm) else 0.0
                needs_pds_transform = abs(pds_scale - 1.0) > 1e-12 or abs(pds_offset) > 1e-12
                needs_unit_scale = unit_ok and abs(unit_scale - 1.0) > 1e-12

                # Step 2: Apply PDS3 transformation and unit conversion to valid cells only.
                # Raw invalid pixels are preserved without applying scale or offset to them.
                valid_idx = ~raw_nd
                if unit_ok and (needs_pds_transform or needs_unit_scale):
                    if needs_pds_transform:
                        # Official HiRISE PDS3 equation: elevation_in_label_units = (stored_value * SCALING_FACTOR) + OFFSET
                        data_f32[valid_idx] = (data_f32[valid_idx] * pds_scale) + pds_offset
                    if needs_unit_scale:
                        data_f32[valid_idx] *= float(unit_scale)

                    conv_parts: list[str] = []
                    if needs_pds_transform:
                        conv_parts.append(
                            f"Applied PDS3 DTM transformation (elevation = raw * {pds_scale:g} + {pds_offset:g})"
                        )
                    if needs_unit_scale:
                        conv_parts.append(f"scaled to meters (*{unit_scale:g})")
                    merged_tags["VERTICAL_UNIT_CONVERSION"] = "; ".join(conv_parts) + f" ({unit_reason})"

                # Step 3: Physical elevation plausibility threshold operates on DECODED elevations in meters,
                # NOT unscaled storage values. On Mars, lowest elevation is Hellas (~-8.2 km) and highest
                # is Olympus Mons (~21.3 km). Any decoded elevation < -9000m or > 30000m is unphysical/sentinel.
                decoded_sentinel_nd = valid_idx & (
                    (data_f32 < -9000.0) | (data_f32 > 30000.0) | ~np.isfinite(data_f32)
                )
                final_nd = raw_nd | decoded_sentinel_nd

                # Step 4: Preserve all original NoData mask semantics through conversion.
                # Never turn missing samples into zero elevation.
                if nodata_val is not None:
                    data_f32[final_nd] = float(nodata_val)
                else:
                    data_f32[final_nd] = np.nan

                if is_metric:
                    # Projected coordinates in meters!
                    if crs_obj is None:
                        raise MarsPathError(
                            f"GeoTIFF '{file_path}' has metric bounds ({bounds.left:.1f}, {bounds.bottom:.1f}) but lacks a CRS definition. Cannot interpret projection."
                        )

                    # Transform metric bounds into Mars geographic degrees
                    if HAS_PYPROJ:
                        mars_geo_crs = pyproj.CRS("+proj=longlat +R=3396190 +no_defs")
                        try:
                            transformer = pyproj.Transformer.from_crs(
                                pyproj.CRS.from_user_input(crs_obj), mars_geo_crs, always_xy=True
                            )
                            corners_x = [bounds.left, bounds.left, bounds.right, bounds.right]
                            corners_y = [bounds.bottom, bounds.top, bounds.bottom, bounds.top]
                            geo_lons, geo_lats = transformer.transform(corners_x, corners_y)
                            norm_lons = [float(lon) % 360.0 for lon in geo_lons]
                            min_lon = min(norm_lons)
                            max_lon = max(norm_lons)
                            min_lat = min(float(lat) for lat in geo_lats)
                            max_lat = max(float(lat) for lat in geo_lats)
                        except Exception as te:
                            raise UnsupportedCRSError(
                                f"Failed to transform projected CRS '{crs_obj}' to Mars geographic: {te}"
                            ) from te
                    else:
                        raise MarsPathError(
                            "pyproj is required to unproject metric GeoTIFFs to Mars geographic coordinates."
                        )

                    d_lon = (max_lon - min_lon) / src.width
                    d_lat = (max_lat - min_lat) / src.height

                    meta = RasterMetadata(
                        width=src.width,
                        height=src.height,
                        coordinate_type="projected",
                        crs_str=str(crs_obj),
                        units="meters",
                        min_lon=min_lon,
                        min_lat=min_lat,
                        max_lon=max_lon,
                        max_lat=max_lat,
                        deg_per_px_lon=d_lon,
                        deg_per_px_lat=d_lat,
                        meters_per_px_x=float(src.res[0]),
                        meters_per_px_y=float(src.res[1]),
                        affine_transform=(
                            transform.a,
                            transform.b,
                            transform.c,
                            transform.d,
                            transform.e,
                            transform.f,
                        ),
                        nodata_value=nodata_val,
                        vertical_datum=vert_datum,
                        vertical_units=resolved_v_unit,
                        metadata_tags=merged_tags,
                        is_synthetic=False,
                    )
                    return RasterData(data_f32, meta)
                else:
                    # Geographic in degrees
                    if not (-180.0 <= bounds.left <= 360.0 and -90.0 <= bounds.bottom <= 90.0):
                        raise MarsPathError(
                            f"GeoTIFF '{file_path}' has invalid geographic bounds: {bounds}"
                        )

                    min_lon = bounds.left % 360.0
                    max_lon = bounds.right % 360.0
                    if max_lon < min_lon and bounds.right > bounds.left:
                        max_lon = bounds.right

                    center_lat = (bounds.bottom + bounds.top) / 2.0
                    m_x = src.res[0] * meters_per_degree_lon(center_lat)
                    m_y = src.res[1] * METERS_PER_DEGREE_LATITUDE

                    meta = RasterMetadata(
                        width=src.width,
                        height=src.height,
                        coordinate_type="geographic",
                        crs_str=str(crs_obj).strip() if (crs_obj and str(crs_obj).strip()) else "Unknown / Unspecified",
                        units="degrees",
                        min_lon=min_lon,
                        min_lat=bounds.bottom,
                        max_lon=max_lon,
                        max_lat=bounds.top,
                        deg_per_px_lon=float(src.res[0]),
                        deg_per_px_lat=float(src.res[1]),
                        meters_per_px_x=m_x,
                        meters_per_px_y=m_y,
                        affine_transform=(
                            transform.a,
                            transform.b,
                            transform.c,
                            transform.d,
                            transform.e,
                            transform.f,
                        ),
                        nodata_value=nodata_val,
                        vertical_datum=vert_datum,
                        vertical_units=resolved_v_unit,
                        metadata_tags=merged_tags,
                        is_synthetic=False,
                    )
                    return RasterData(data_f32, meta)
        except Exception as e:
            if isinstance(e, MarsPathError):
                raise
            raise MarsPathError(f"Rasterio failed to load or validate GeoTIFF '{file_path}': {e}") from e

    raise MarsPathError(
        f"Unable to read GeoTIFF '{file_path}'. Rasterio geospatial library is required to ingest real GeoTIFF files."
    )
