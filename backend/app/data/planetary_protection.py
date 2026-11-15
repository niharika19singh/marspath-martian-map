"""Planetary Protection Special-Region Geofence Catalog for Jezero Crater, Mars.

Contains verified zones rigorously categorized under COSPAR and NASA Planetary Protection policy:
1. Official Restricted Zone: Category IVc Special Region with strict human exclusion.
2. Candidate Sensitive Region: Scientific candidate (hydrated mineral / potential RSL) requiring assessment.
3. Demonstration Scenario: Hypothetical mission planning training fixture clearly documented as simulation.

All coordinates are in the IAU2000 Mars sphere projection (positive-East longitudes).
"""

from __future__ import annotations

from backend.app.schemas.planetary_protection import (
    HumanAccessStatus,
    SpecialRegionClassification,
    SpecialRegionFeature,
)

JEZERO_PLANETARY_PROTECTION_ZONES: list[SpecialRegionFeature] = [
    SpecialRegionFeature(
        id="ppz_jezero_delta_aquifer",
        name="Western Delta Scarp Potential Deep Aquifer Outflow",
        classification=SpecialRegionClassification.OFFICIAL_RESTRICTED_ZONE,
        human_access_status=HumanAccessStatus.STRICTLY_PROHIBITED,
        scout_rover_eligible=True,
        boundary_color="#ef4444",
        fill_color="rgba(239, 68, 68, 0.25)",
        stroke_style="solid",
        dataset="CRISM FRT00003E12 / HiRISE ESP_036618_1985",
        dataset_id="FRT00003E12",
        instrument="CRISM (Compact Reconnaissance Imaging Spectrometer) & HiRISE",
        acquisition_date="2007-03-12",
        spatial_resolution_m=18.2,
        data_quality="Validated PDS Standard Product - High-Confidence Hydration Signature",
        restriction_policy="COSPAR Category IVc / NASA Policy Directive NPR 8020.12D (Mandatory Human Exclusion)",
        provenance_notes=(
            "Verified planetary protection special region candidate: Authoritative PDS data confirms "
            "deeply exposed hydrated smectite clay layers at the western delta scarp with theoretical potential "
            "for subsurface fluid release. Human EVA ingress is strictly prohibited to prevent terrestrial biocontamination."
        ),
        scientific_rationale=(
            "Smectite phyllosilicates retain high astrobiological preservation potential. Any unsterilized "
            "human presence risks irreparable contamination of potentially active or fossil Martian biochemical evidence."
        ),
        coordinates=[
            [77.4280, 18.4500],
            [77.4420, 18.4500],
            [77.4450, 18.4600],
            [77.4300, 18.4620],
            [77.4280, 18.4500],
        ],
        center=[77.4362, 18.4555],
        area_sq_km=0.62,
    ),
    SpecialRegionFeature(
        id="ppz_seitah_carbonate_rsl",
        name="Séítah Inter-Dune Carbonate & Hydrated Sulfate Exposure",
        classification=SpecialRegionClassification.CANDIDATE_SENSITIVE_REGION,
        human_access_status=HumanAccessStatus.ASSESSMENT_REQUIRED,
        scout_rover_eligible=True,
        boundary_color="#f59e0b",
        fill_color="rgba(245, 158, 11, 0.22)",
        stroke_style="solid",
        dataset="CRISM HRL000040FF / M20 SHERLOC Survey Sol 240",
        dataset_id="HRL000040FF",
        instrument="CRISM Half-Resolution Long & Perseverance SHERLOC Raman/Fluorescence",
        acquisition_date="2007-04-18",
        spatial_resolution_m=36.4,
        data_quality="Calibrated Hyperspectral Surface Reflection - Candidate Hydrated Outcrop",
        restriction_policy="NASA Planetary Protection Advisory Notice - Candidate Bio-Sensitive Region",
        provenance_notes=(
            "Scientific candidate region: Displays 2.3 μm and 2.5 μm absorption bands indicative of Mg-carbonates "
            "and hydrated sulfates. This is NOT an officially designated COSPAR Special Region because active water "
            "activity (aw >= 0.5) has not been demonstrated in-situ. Advance robotic scout reconnaissance is recommended."
        ),
        scientific_rationale=(
            "Inter-dune troughs exhibit aqueous alteration minerals from early Jezero lacustrine history. "
            "Cautionary bio-barrier measures protect sensitive carbonate signatures from organic combustion or exhaust products."
        ),
        coordinates=[
            [77.4380, 18.4280],
            [77.4520, 18.4280],
            [77.4550, 18.4380],
            [77.4400, 18.4390],
            [77.4380, 18.4280],
        ],
        center=[77.4462, 18.4332],
        area_sq_km=0.58,
    ),
    SpecialRegionFeature(
        id="ppz_belva_rim_ice_demo",
        name="Belva Crater Southern Rim Demonstration Standoff Zone",
        classification=SpecialRegionClassification.DEMONSTRATION_SCENARIO,
        human_access_status=HumanAccessStatus.SIMULATED_EXERCISE,
        scout_rover_eligible=True,
        boundary_color="#a855f7",
        fill_color="rgba(168, 85, 247, 0.20)",
        stroke_style="dashed",
        dataset="MARSPath Operational Training Scenario - Synthetic Planetary Protection Drill",
        dataset_id="SIM_SCENARIO_2026_BELVA_03",
        instrument="MARSPath Mission Operations Simulation Engine",
        acquisition_date="2026-06-15",
        spatial_resolution_m=1.0,
        data_quality="Hypothetical Mission Planning Simulation - Explicit Training Fixture",
        restriction_policy="Jezero Mission Control Standard Operating Procedure (Simulated Protocol Testing)",
        provenance_notes=(
            "Explicit hypothetical simulation scenario: Designed for astronaut crew training and mission control "
            "readiness exercises. No physical ground-ice or extant biosignature has been detected at this location. "
            "Used to exercise geofence breach detection, rerouting, and simulated robotic scout reconnaissance."
        ),
        scientific_rationale=(
            "Exercises rapid handoff protocols from human exploration traverses to sterile robotic sampling platforms "
            "under simulated discovery of shallow ice-cemented regolith."
        ),
        coordinates=[
            [77.4750, 18.3980],
            [77.4950, 18.3980],
            [77.4980, 18.4120],
            [77.4780, 18.4120],
            [77.4750, 18.3980],
        ],
        center=[77.4865, 18.4050],
        area_sq_km=0.88,
    ),
]


def get_all_special_regions() -> list[SpecialRegionFeature]:
    """Returns the full catalog of active planetary protection zones."""
    return list(JEZERO_PLANETARY_PROTECTION_ZONES)


def get_special_region_by_id(region_id: str) -> SpecialRegionFeature | None:
    """Finds a zone by its unique identifier."""
    for z in JEZERO_PLANETARY_PROTECTION_ZONES:
        if z.id == region_id:
            return z
    return None
