import threading
from collections import OrderedDict
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Response

from backend.app.schemas.layers import LayerListResponse
from backend.app.services.data_catalog import DataCatalogService

router = APIRouter(prefix="/api/v1", tags=["Geospatial Layers"])

ALLOWED_MARS_TREK_WMTS_LAYERS: dict[str, dict[str, object]] = {
    "Mars_Viking_MDIM21_ClrMosaic_global_232m": {
        "ext": "jpg",
        "media_type": "image/jpeg",
        "max_z": 7,
        "attribution": "USGS Astrogeology Science Center / NASA Mars Trek (DOI: 10.5066/F71V5C67)",
    },
    "JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0": {
        "ext": "png",
        "media_type": "image/png",
        "max_z": 13,
        "attribution": "USGS Astrogeology Science Center / NASA Mars Trek (DOI: 10.5066/P9GV1ND3)",
    },
    "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd": {
        "ext": "png",
        "media_type": "image/png",
        "max_z": 17,
        "attribution": "USGS Astrogeology Science Center / NASA Mars Trek (DOI: 10.5066/P9QJDP48)",
    },
    "Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw": {
        "ext": "jpg",
        "media_type": "image/jpeg",
        "max_z": 8,
        "attribution": "USGS Astrogeology Science Center / NASA Mars Trek (DOI: 10.5066/P907276M)",
    },
}

_TILE_CACHE_LOCK = threading.Lock()
_TILE_CACHE: OrderedDict[tuple[str, int, int, int], tuple[bytes, str]] = OrderedDict()
_MAX_CACHED_TILES = 512


@router.get("/layers", response_model=LayerListResponse, summary="List configured Martian geospatial layers")
def list_layers():
    """
    Returns metadata for all available numerical and visual map layers,
    including units, spatial coverage, and source citations.
    """
    service = DataCatalogService()
    return service.get_layer_list()


@router.get(
    "/wmts/capabilities/{layer_id}",
    summary="Retrieve official OGC WMTS 1.0.0 GetCapabilities document for a Mars Trek layer",
)
async def get_wmts_capabilities(layer_id: str):
    if layer_id not in ALLOWED_MARS_TREK_WMTS_LAYERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported Mars Trek WMTS layer '{layer_id}'.",
        )
    layer_cfg = ALLOWED_MARS_TREK_WMTS_LAYERS[layer_id]
    repo_root = Path(__file__).resolve().parents[4]
    for rel_dir in ("dist/mission-data/wmts", "mission-ui/public/mission-data/wmts"):
        local_xml = repo_root / rel_dir / f"{layer_id}.xml"
        if local_xml.is_file():
            xml_bytes = local_xml.read_bytes()
            return Response(
                content=xml_bytes,
                media_type="application/xml",
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "X-Upstream-Attribution": str(layer_cfg["attribution"]),
                    "X-WMTS-Source": "verified_local_capabilities_mirror",
                },
            )

    upstream_url = f"https://trek.nasa.gov/tiles/Mars/EQ/{layer_id}/1.0.0/WMTSCapabilities.xml"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(upstream_url)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream NASA Mars Trek WMTS capabilities request failed: {exc}",
        ) from exc

    if resp.status_code != 200 or b"Capabilities" not in resp.content:
        raise HTTPException(
            status_code=resp.status_code if resp.status_code >= 400 else 502,
            detail=f"Upstream NASA Mars Trek WMTS returned HTTP {resp.status_code} for {layer_id} capabilities.",
        )

    return Response(
        content=resp.content,
        media_type="application/xml",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Upstream-Attribution": str(layer_cfg["attribution"]),
            "X-WMTS-Source": "upstream_nasa_mars_trek",
        },
    )


@router.get(
    "/wmts/tiles/{layer_id}/{z}/{y}/{x}",
    summary="Cacheable proxy for official NASA Mars Trek WMTS imagery tiles",
)
async def proxy_wmts_tile(layer_id: str, z: int, y: int, x: int):
    if layer_id not in ALLOWED_MARS_TREK_WMTS_LAYERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported Mars Trek WMTS layer '{layer_id}'.",
        )
    layer_cfg = ALLOWED_MARS_TREK_WMTS_LAYERS[layer_id]
    max_z = int(layer_cfg["max_z"])
    if z < 0 or z > max_z or y < 0 or x < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Tile coordinates z={z}, y={y}, x={x} out of valid TileMatrixSet bounds (0..{max_z}).",
        )

    cache_key = (layer_id, z, y, x)
    with _TILE_CACHE_LOCK:
        cached = _TILE_CACHE.get(cache_key)
        if cached is not None:
            _TILE_CACHE.move_to_end(cache_key)
            return Response(
                content=cached[0],
                media_type=cached[1],
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "X-Upstream-Attribution": str(layer_cfg["attribution"]),
                    "X-Tile-Cache": "HIT",
                },
            )

    ext = str(layer_cfg["ext"])
    expected_media = str(layer_cfg["media_type"])
    upstream_url = f"https://trek.nasa.gov/tiles/Mars/EQ/{layer_id}/1.0.0/default/default028mm/{z}/{y}/{x}.{ext}"
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(upstream_url)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream NASA Mars Trek tile fetch failed for {layer_id} ({z}/{y}/{x}): {exc}",
        ) from exc

    content_type = resp.headers.get("content-type", "").lower()
    if resp.status_code != 200 or not content_type.startswith("image/") or len(resp.content) < 64:
        # Never cache error responses as successful imagery; report upstream HTTP status accurately
        status_out = resp.status_code if resp.status_code >= 400 else 502
        raise HTTPException(
            status_code=status_out,
            detail=(
                f"Upstream NASA Mars Trek WMTS returned HTTP {resp.status_code} "
                f"(content-type='{content_type}') for {layer_id} tile {z}/{y}/{x}."
            ),
        )

    with _TILE_CACHE_LOCK:
        _TILE_CACHE[cache_key] = (resp.content, expected_media)
        _TILE_CACHE.move_to_end(cache_key)
        while len(_TILE_CACHE) > _MAX_CACHED_TILES:
            _TILE_CACHE.popitem(last=False)

    return Response(
        content=resp.content,
        media_type=expected_media,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Upstream-Attribution": str(layer_cfg["attribution"]),
            "X-Tile-Cache": "MISS",
        },
    )
