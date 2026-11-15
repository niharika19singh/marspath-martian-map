"""Unit tests for Marswalk Survivability Scoring Model and Surface Imagery Registry."""

from backend.app.data.surface_imagery import (
    NASA_SURFACE_POV_CATALOGUE,
    find_surface_imagery_for_coordinates,
)
from backend.app.routing.survivability import (
    compute_marswalk_survivability,
)


def test_survivability_nominal_baseline():
    """Verify that a gentle, well-buffered corridor scores in high survivability range (80-100)."""
    score = compute_marswalk_survivability(
        distance_km=2.5,
        max_slope_deg=4.5,
        average_slope_deg=2.5,
        roughness_tri=0.15,
        eva_duration_hours=0.6,
        turnaround_buffer_min=140.0,
        thermal_inertia_tiu=390.0,
        is_spe_active=False,
    )

    assert 85.0 <= score.score <= 100.0
    assert score.category == "HIGH_SURVIVABILITY"
    assert score.mobility_exertion_penalty == 0.0
    assert score.terrain_roughness_penalty == 0.0
    assert score.eva_consumables_penalty == 0.0
    assert score.return_buffer_penalty == 0.0
    assert score.regolith_sinkage_penalty == 0.0
    assert score.radiation_exposure_penalty == 2.0
    assert len(score.contributing_factors) == 6


def test_survivability_slope_penalty_scaling():
    """Verify that steep slope increments penalize suited mobility proportionally."""
    score_gentle = compute_marswalk_survivability(
        distance_km=2.5,
        max_slope_deg=5.0,
        average_slope_deg=3.0,
        roughness_tri=0.2,
        eva_duration_hours=1.0,
        turnaround_buffer_min=120.0,
    )
    score_steep = compute_marswalk_survivability(
        distance_km=2.5,
        max_slope_deg=13.5,
        average_slope_deg=8.0,
        roughness_tri=0.2,
        eva_duration_hours=1.0,
        turnaround_buffer_min=120.0,
    )

    assert score_gentle.mobility_exertion_penalty == 0.0
    assert score_steep.mobility_exertion_penalty > 20.0
    assert score_gentle.score > score_steep.score


def test_survivability_spe_radiation_penalty():
    """Verify that simulated Solar Particle Event severely drops unshielded survivability score."""
    score_nominal = compute_marswalk_survivability(
        distance_km=3.0,
        max_slope_deg=8.0,
        average_slope_deg=4.0,
        roughness_tri=0.25,
        eva_duration_hours=1.2,
        turnaround_buffer_min=90.0,
        is_spe_active=False,
    )
    score_spe = compute_marswalk_survivability(
        distance_km=3.0,
        max_slope_deg=8.0,
        average_slope_deg=4.0,
        roughness_tri=0.25,
        eva_duration_hours=1.2,
        turnaround_buffer_min=90.0,
        is_spe_active=True,
    )

    assert score_spe.is_spe_active is True
    assert score_spe.radiation_exposure_penalty >= 30.0
    assert score_nominal.score - score_spe.score >= 25.0


def test_survivability_shelter_bonus_under_spe():
    """Verify that proximity to a designated topographic shelter mitigates SPE flux."""
    # Western Rim overhang at (77.215, 18.460)
    shelter_point = (77.216, 18.461)
    open_plains_point = (77.500, 18.300)

    score_sheltered = compute_marswalk_survivability(
        distance_km=2.0,
        max_slope_deg=8.0,
        average_slope_deg=4.0,
        roughness_tri=0.25,
        eva_duration_hours=0.8,
        turnaround_buffer_min=120.0,
        is_spe_active=True,
        corridor_midpoint=shelter_point,
    )
    score_exposed = compute_marswalk_survivability(
        distance_km=2.0,
        max_slope_deg=8.0,
        average_slope_deg=4.0,
        roughness_tri=0.25,
        eva_duration_hours=0.8,
        turnaround_buffer_min=120.0,
        is_spe_active=True,
        corridor_midpoint=open_plains_point,
    )

    assert score_sheltered.topographic_shelter_bonus > 0.0
    assert score_sheltered.score > score_exposed.score
    assert score_sheltered.recommended_shelter_id == "shelter_western_rim_overhang"


def test_surface_imagery_catalogue():
    """Verify authentic NASA surface imagery records and coordinate matching."""
    assert len(NASA_SURFACE_POV_CATALOGUE) >= 5
    for img in NASA_SURFACE_POV_CATALOGUE:
        assert img.image_id.startswith("PIA")
        assert img.sol >= 1
        assert "photojournal.jpl.nasa.gov" in img.nasa_photojournal_url
        assert 77.0 <= img.lon <= 78.0
        assert 18.0 <= img.lat <= 19.0

    # Test coordinate lookup for Kodiak Butte
    kodiak = find_surface_imagery_for_coordinates(77.4290, 18.4265, max_radius_meters=1000.0)
    assert kodiak is not None
    assert kodiak.landmark_id == "kodiak_butte"
    assert kodiak.image_id == "PIA24836"

    # Test out-of-range coordinate lookup
    distant = find_surface_imagery_for_coordinates(133.0, -18.0, max_radius_meters=1000.0)
    assert distant is None
