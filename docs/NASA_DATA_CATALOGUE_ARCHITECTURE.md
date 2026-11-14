# MARSPath — NASA Data Catalogue Architecture

This document details the software architecture, data schemas, search mechanisms, and synchronization protocols powering the MARSPath Unified NASA Planetary Data Catalogue.

---

## 1. Architectural Principles

1. **Multi-Source Unification**:
   Different NASA planetary databases format observations differently (e.g. PDS3 `.IMG` labels, PDS4 XML collections, OGC WMTS capabilities XML, or custom ASCII tables). The unified catalogue maps all incoming metadata into standardized Pydantic models.

2. **Spatial and Temporal Grounding**:
   Every cataloged product contains:
   - Defined geographic bounding coordinates (`min_lon`, `min_lat`, `max_lon`, `max_lat`) in the planetocentric coordinate system.
   - Exact UTC acquisition timestamp and corresponding Martian Sol.
   - Footprint GeoJSON geometries enabling direct rendering on the OpenLayers canvas.

3. **Fault Isolation & Resilient Degraded Operations**:
   Network anomalies or external NASA server maintenance do not crash the MARSPath application. Each connector operates within its own isolation boundary: if a remote endpoint is unreachable, verified bundled datasets are returned transparently while logging the connection degradation.

---

## 2. Core Domain Models & Schemas

The backend data models are defined in `backend/app/data_sources/schemas/models.py`:

### 2.1 `DataSourceEntry`
```python
class DataSourceEntry(BaseModel):
    id: str
    name: str
    short_name: str
    organization: str
    description: str
    primary_use_in_marspath: str
    integration_method: str
    connection_status: ConnectionState
    official_url: str
    doi: str | None = None
    last_sync_utc: datetime | None = None
    indexed_products_count: int = 0
    ingested_status: str
    available_datasets: list[str] = Field(default_factory=list)
    citation: str | None = None
```

### 2.2 `DataProduct`
```python
class DataProduct(BaseModel):
    product_id: str
    source_id: str
    source_name: str
    spacecraft: str
    instrument: str
    product_type: str
    title: str
    description: str
    target_name: str
    martian_sol: int | None = None
    acquisition_utc: str | None = None
    spatial_resolution_m_per_px: float = 0.0
    bounds: BoundingBox | None = None
    footprint_geojson: dict[str, Any] | None = None
    archive_url: str
    download_url: str | None = None
    data_format: str
    file_size_bytes: int | None = None
    processing_status: str
    doi: str | None = None
```

### 2.3 `MedaObservation`
```python
class MedaObservation(BaseModel):
    sol: int
    earth_date_utc: str
    local_true_solar_time: str
    air_temperature_deg_c: float | None = None
    ground_temperature_deg_c: float | None = None
    atmospheric_pressure_pa: float | None = None
    relative_humidity_percent: float | None = None
    dust_optical_depth_tau: float | None = None
    wind_speed_m_per_s: float | None = None
    wind_direction_deg: float | None = None
    quality_flag: str
    notes: str
```

### 2.4 `ThemisObservation`
```python
class ThemisObservation(BaseModel):
    observation_id: str
    spacecraft_id: str
    target_name: str
    center_lon: float
    center_lat: float
    day_ir_temp_k: float
    night_ir_temp_k: float
    thermal_inertia_tiu: float
    traversability_risk: str
    risk_assessment: str
    acquisition_utc: str
    source_url: str
```

### 2.5 `SpiceGeometryResult`
```python
class SpiceGeometryResult(BaseModel):
    spacecraft_id: str
    spacecraft_name: str
    epoch_utc: str
    sub_spacecraft_lon: float
    sub_spacecraft_lat: float
    spacecraft_altitude_km: float
    sub_solar_lon: float
    sub_solar_lat: float
    solar_incidence_angle_deg: float
    emission_angle_deg: float
    phase_angle_deg: float
    local_solar_time: str
    solar_longitude_ls_deg: float
    kernel_source: str
    calculation_mode: str
```

---

## 3. Query & Filtering Architecture

The catalog search service (`UnifiedDataCatalogService.search_products`) executes multi-dimensional filtering across:
1. **Free-Text Search**: Matches tokens against product title, target description, and product identifiers.
2. **Instrument Taxonomy**: Filter by instrument name (e.g. `HiRISE`, `CTX`, `CRISM`, `SHARAD`, `MEDA`, `THEMIS`).
3. **Spacecraft Platform**: Filter by mission spacecraft (e.g. `MRO`, `Mars 2020`, `MSL`, `2001 Mars Odyssey`).
4. **Product Type**: Filter by physical measurement classification (`TERRAIN_DTM`, `IMAGERY_RDR`, `MULTISPECTRAL_TRDR`, `THERMAL_INERTIA_MOSAIC`, `IN_SITU_WEATHER_TIMESERIES`, `ROVER_TRAVERSE_LOG`).
5. **Spatial Bounding Box**: Longitude range $[76.5^\circ, 78.5^\circ\text{E}]$ and latitude range $[17.5^\circ, 19.5^\circ\text{N}]$ for the greater Jezero region.
6. **Martian Sol Range**: Filter observations by surface mission sol window.

---

## 4. Synchronization Protocol

The synchronization engine (`DataSourceSyncService`) coordinates updates across all seven connectors:
- **Concurrency**: Connectors are queried asynchronously via `asyncio.gather`.
- **Error Trapping**: Any exception thrown by an individual connector is caught, stored in an errors array, and does not halt synchronization of the remaining sources.
- **Atomic State Updates**: Successful connector responses update memory caches and update the `last_sync_utc` timestamp and indexed product counters.
- **Sync Trigger**: Can be manually triggered via `POST /api/v1/data-sources/sync?force_refresh=true` or invoked periodically.
