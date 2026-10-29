import logging
import os
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np

logger = logging.getLogger("marspath.raster_loader")

# Optional rasterio import
try:
    import rasterio
    from rasterio.transform import Affine
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    rasterio = None


@dataclass
class RasterMetadata:
    width: int
    height: int
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    deg_per_px_lon: float
    deg_per_px_lat: float
    nodata_value: Optional[float]
    crs_str: str
    is_synthetic: bool = False


class RasterData:
    def __init__(self, data: np.ndarray, metadata: RasterMetadata):
        self.data = data.astype(np.float32)
        self.metadata = metadata
        self._init_nodata_mask()

    def _init_nodata_mask(self):
        mask = np.isnan(self.data)
        if self.metadata.nodata_value is not None:
            mask = mask | (self.data == self.metadata.nodata_value) | (self.data < -9000.0)
        self.nodata_mask = mask

    @property
    def shape(self) -> Tuple[int, int]:
        return self.data.shape

    def get_elevation_at_pixel(self, col: int, row: int) -> float:
        if 0 <= row < self.data.shape[0] and 0 <= col < self.data.shape[1]:
            val = float(self.data[row, col])
            return val if not self.nodata_mask[row, col] else float("nan")
        return float("nan")


def load_raster_file(file_path: str) -> RasterData:
    """
    Loads a numerical raster from disk (GeoTIFF, NumPy .npy/.npz, or binary raw grid).
    Uses rasterio when available; otherwise falls back to pure-Python / PIL / NumPy loader.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Raster file not found at: {file_path}")

    # Handle .npy / .npz direct serialized arrays
    if file_path.endswith(".npy") or file_path.endswith(".npz"):
        loaded = np.load(file_path)
        data = loaded["elevation"] if isinstance(loaded, np.lib.npyio.NpzFile) else loaded
        # Extract default Jezero metadata if header not attached
        meta = RasterMetadata(
            width=data.shape[1],
            height=data.shape[0],
            min_lon=77.20,
            min_lat=18.15,
            max_lon=77.95,
            max_lat=18.65,
            deg_per_px_lon=(77.95 - 77.20) / data.shape[1],
            deg_per_px_lat=(18.65 - 18.15) / data.shape[0],
            nodata_value=-9999.0,
            crs_str="IAU2000:49900",
            is_synthetic=False,
        )
        return RasterData(data, meta)

    # Use rasterio if available
    if HAS_RASTERIO:
        try:
            with rasterio.open(file_path) as src:
                data = src.read(1)
                bounds = src.bounds
                meta = RasterMetadata(
                    width=src.width,
                    height=src.height,
                    min_lon=bounds.left,
                    min_lat=bounds.bottom,
                    max_lon=bounds.right,
                    max_lat=bounds.top,
                    deg_per_px_lon=src.res[0],
                    deg_per_px_lat=src.res[1],
                    nodata_value=src.nodata,
                    crs_str=str(src.crs or "IAU2000:49900"),
                    is_synthetic=False,
                )
                return RasterData(data, meta)
        except Exception as e:
            logger.warning("Rasterio failed to load %s: %s. Attempting fallback.", file_path, e)

    # Fallback loader using PIL / TIFF tags
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            data = np.array(img, dtype=np.float32)
            meta = RasterMetadata(
                width=data.shape[1],
                height=data.shape[0],
                min_lon=77.20,
                min_lat=18.15,
                max_lon=77.95,
                max_lat=18.65,
                deg_per_px_lon=(77.95 - 77.20) / data.shape[1],
                deg_per_px_lat=(18.65 - 18.15) / data.shape[0],
                nodata_value=-9999.0,
                crs_str="IAU2000:49900",
                is_synthetic=False,
            )
            return RasterData(data, meta)
    except Exception as e:
        raise RuntimeError(f"Unable to load raster file {file_path}: {e}") from e
