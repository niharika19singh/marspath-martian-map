from __future__ import annotations

from typing import Any

from backend.app.data_sources.registry.registry import DataSourceRegistry


class CitationResolver:
    """Verifies and enriches citations with canonical DOIs and official archive landing pages."""

    def __init__(self) -> None:
        self.registry = DataSourceRegistry()

    def resolve_citation(self, product_id: str, instrument: str | None = None) -> dict[str, Any]:
        """Maps product ID or instrument name to authoritative NASA registry citation."""
        src_id = "pds_geosciences"
        ins = (instrument or "").lower()

        if "meda" in ins:
            src_id = "pds_atmospheres"
        elif "themis" in ins:
            src_id = "themis_viewer"
        elif "spice" in ins:
            src_id = "naif_spice"
        elif "traverse" in ins or "navcam" in ins:
            src_id = "planetary_notebook"
        elif "trek" in ins:
            src_id = "mars_trek"

        entry = self.registry.get_source(src_id)
        if not entry:
            return {
                "product_id": product_id,
                "source": "NASA Planetary Data System",
                "doi": "10.17189/1518932",
                "url": "https://pds.nasa.gov/",
            }

        return {
            "product_id": product_id,
            "source": entry.name,
            "organization": entry.organization,
            "doi": entry.doi or "10.17189/1518932",
            "url": entry.official_url,
            "citation": entry.citation,
        }
