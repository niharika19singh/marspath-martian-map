from __future__ import annotations

from typing import Any

from backend.app.data_sources.services.catalog_service import UnifiedDataCatalogService


class ContextBuilder:
    """Builds grounded planetary science context from real catalog records and telemetry."""

    def __init__(self) -> None:
        self.catalog = UnifiedDataCatalogService()

    async def build_observation_context(self, product_id: str | None) -> dict[str, Any]:
        """Fetches product metadata from the unified catalog."""
        if not product_id:
            return {}

        product = await self.catalog.get_product_by_id(product_id)
        if not product:
            return {"product_id": product_id, "note": "Observation metadata pending synchronization"}

        return {
            "product_id": product.product_id,
            "instrument": product.instrument,
            "spacecraft": product.spacecraft,
            "title": product.title,
            "target_name": product.target_name,
            "spatial_resolution_m_per_px": product.spatial_resolution_m_per_px,
            "martian_sol": product.martian_sol,
            "acquisition_utc": product.acquisition_utc,
            "doi": product.doi,
            "archive_url": product.archive_url,
            "download_url": product.download_url,
            "processing_status": product.processing_status,
        }

    def build_meda_context(self, sol: int | None = 2022) -> dict[str, Any]:
        """Extracts calibrated surface telemetry from Perseverance MEDA."""
        observations = self.catalog.get_meda_observations()
        active = next((o for o in observations if o.sol == sol), observations[0] if observations else None)
        if not active:
            return {}

        return {
            "sol": active.sol,
            "air_temperature_deg_c": active.air_temperature_deg_c,
            "ground_temperature_deg_c": active.ground_temperature_deg_c,
            "atmospheric_pressure_pa": active.atmospheric_pressure_pa,
            "dust_optical_depth_tau": active.dust_optical_depth_tau,
            "relative_humidity_percent": active.relative_humidity_percent,
            "wind_speed_m_per_s": active.wind_speed_m_per_s,
            "local_true_solar_time": active.local_true_solar_time,
            "quality_flag": active.quality_flag,
            "spatial_constraint": "Perseverance local coordinates in Jezero (18.435°N, 77.233°E)",
        }

    def build_themis_context(self) -> dict[str, Any]:
        """Extracts quantitative thermal inertia observations for traversability assessment."""
        themis_obs = self.catalog.get_themis_observations()
        return {
            "themis_observations": [
                {
                    "observation_id": t.observation_id,
                    "target": t.target_name,
                    "thermal_inertia_tiu": t.thermal_inertia_tiu,
                    "risk_category": t.traversability_risk,
                }
                for t in themis_obs
            ]
        }
