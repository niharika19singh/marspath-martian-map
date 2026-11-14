from __future__ import annotations

from typing import Any

from backend.app.data_sources.connectors.mars_trek.connector import MarsTrekConnector
from backend.app.data_sources.connectors.naif_spice.connector import NaifSpiceConnector
from backend.app.data_sources.connectors.pds_atmospheres.connector import PdsAtmospheresConnector
from backend.app.data_sources.connectors.pds_geosciences.connector import PdsGeosciencesConnector
from backend.app.data_sources.connectors.pds_releases.connector import PdsReleasesConnector
from backend.app.data_sources.connectors.planetary_notebook.connector import PlanetaryNotebookConnector
from backend.app.data_sources.connectors.themis.connector import ThemisConnector
from backend.app.data_sources.registry.registry import OFFICIAL_NASA_SOURCES
from backend.app.data_sources.schemas.models import (
    DataProduct,
    DataRelease,
    MedaObservation,
    ProductSearchQuery,
    ProductSearchResponse,
    SpiceGeometryResult,
    ThemisObservation,
)


class UnifiedDataCatalogService:
    """Service orchestrating unified search, discovery, and filtering across all 7 NASA data sources."""

    def __init__(self) -> None:
        self.trek = MarsTrekConnector(OFFICIAL_NASA_SOURCES["nasa_mars_trek"])
        self.geo = PdsGeosciencesConnector(OFFICIAL_NASA_SOURCES["pds_geosciences"])
        self.atm = PdsAtmospheresConnector(OFFICIAL_NASA_SOURCES["pds_atmospheres"])
        self.themis = ThemisConnector(OFFICIAL_NASA_SOURCES["themis"])
        self.spice = NaifSpiceConnector(OFFICIAL_NASA_SOURCES["naif_spice"])
        self.notebook = PlanetaryNotebookConnector(OFFICIAL_NASA_SOURCES["planetary_notebook"])
        self.releases = PdsReleasesConnector(OFFICIAL_NASA_SOURCES["pds_releases"])
        self._cached_products: list[DataProduct] | None = None

    async def get_all_products(self) -> list[DataProduct]:
        if self._cached_products is not None:
            return self._cached_products

        all_products = []
        all_products.extend(await self.trek.list_products(100))
        all_products.extend(await self.geo.list_products(100))
        all_products.extend(await self.atm.list_products(100))
        all_products.extend(await self.themis.list_products(100))
        all_products.extend(await self.spice.list_products(100))
        all_products.extend(await self.notebook.list_products(100))
        all_products.extend(await self.releases.list_products(100))

        self._cached_products = all_products
        return all_products

    async def search_products(self, query: ProductSearchQuery) -> ProductSearchResponse:
        products = await self.get_all_products()
        filtered = []

        q_lower = query.query.strip().lower() if query.query else None
        inst_lower = query.instrument.strip().lower() if query.instrument else None
        sc_lower = query.spacecraft.strip().lower() if query.spacecraft else None
        src_lower = query.source_id.strip().lower() if query.source_id else None
        type_lower = query.product_type.strip().lower() if query.product_type else None

        for p in products:
            if q_lower:
                match = (
                    q_lower in p.title.lower()
                    or q_lower in p.product_id.lower()
                    or q_lower in p.description.lower()
                    or q_lower in p.instrument.lower()
                    or q_lower in p.spacecraft.lower()
                )
                if not match:
                    continue

            if inst_lower and inst_lower not in p.instrument.lower():
                continue

            if sc_lower and sc_lower not in p.spacecraft.lower():
                continue

            if src_lower and p.source_id.lower() != src_lower:
                continue

            if type_lower and type_lower not in p.product_type.lower():
                continue

            if query.min_sol is not None:
                if p.martian_sol is None or p.martian_sol < query.min_sol:
                    continue

            if query.max_sol is not None:
                if p.martian_sol is None or p.martian_sol > query.max_sol:
                    continue

            # Bounding box filter (intersection)
            if query.min_lon is not None and p.max_lon is not None:
                if p.max_lon < query.min_lon:
                    continue
            if query.max_lon is not None and p.min_lon is not None:
                if p.min_lon > query.max_lon:
                    continue
            if query.min_lat is not None and p.max_lat is not None:
                if p.max_lat < query.min_lat:
                    continue
            if query.max_lat is not None and p.min_lat is not None:
                if p.min_lat > query.max_lat:
                    continue

            filtered.append(p)

        total = len(filtered)
        paginated = filtered[query.offset : query.offset + query.limit]
        return ProductSearchResponse(
            total_matched=total,
            limit=query.limit,
            offset=query.offset,
            products=paginated,
        )

    async def get_product_by_id(self, product_id: str) -> DataProduct | None:
        products = await self.get_all_products()
        for p in products:
            if p.product_id.lower() == product_id.strip().lower():
                return p
        return None

    async def get_coverage_summary(self) -> dict[str, Any]:
        products = await self.get_all_products()
        georeferenced = [p for p in products if p.min_lon is not None and p.min_lat is not None]

        by_instrument: dict[str, int] = {}
        by_spacecraft: dict[str, int] = {}
        for p in products:
            by_instrument[p.instrument] = by_instrument.get(p.instrument, 0) + 1
            by_spacecraft[p.spacecraft] = by_spacecraft.get(p.spacecraft, 0) + 1

        return {
            "total_cataloged_products": len(products),
            "georeferenced_products_count": len(georeferenced),
            "map_layer_supported_count": sum(1 for p in products if p.map_layer_supported),
            "instruments_distribution": by_instrument,
            "spacecraft_distribution": by_spacecraft,
            "focal_region": {
                "name": "Jezero Crater Region",
                "center_lon": 77.47,
                "center_lat": 18.40,
                "coverage_instruments": ["HiRISE", "CTX", "CRISM", "SHARAD", "MEDA", "THEMIS"],
            },
            "status": "OPERATIONAL",
        }

    def get_meda_observations(self) -> list[MedaObservation]:
        return self.atm.get_observations()

    def get_themis_observations(self) -> list[ThemisObservation]:
        return self.themis.get_observations()

    def get_pds_releases(self) -> list[DataRelease]:
        return self.releases.get_releases()

    def compute_spice_geometry(self, spacecraft_id: str = "mro") -> SpiceGeometryResult:
        return self.spice.compute_geometry(spacecraft_id)

    def invalidate_cache(self) -> None:
        self._cached_products = None
