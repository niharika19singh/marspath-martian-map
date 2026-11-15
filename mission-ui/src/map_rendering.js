/**
 * Planetary GIS Map Rendering & Multi-Resolution Imagery Harmonization
 *
 * Provides:
 * 1. computeTimeOverlayPixels: Alpha masking for return and rescue time overlays.
 *    Strictly enforces alpha = 0 for NoData, unreachable, nonfinite, or negative cells,
 *    ensuring the underlying Mars basemap is 100% visible through unreached areas.
 * 2. calculateEdgeFeatherGradients: Screen-pixel linear feathering geometry for
 *    regional CTX and high-res HiRISE imagery insets, seamlessly blending boundaries
 *    into the global Viking basemap using destination-out alpha gradients.
 */

export function computeTimeOverlayPixels(zone, kind = 'return') {
  const rows = zone?.rows || 0;
  const cols = zone?.cols || 0;
  const grid = zone?.minutes_grid;
  if (!rows || !cols || !Array.isArray(grid)) return { rows: 0, cols: 0, data: new Uint8ClampedArray(0) };
  const data = new Uint8ClampedArray(rows * cols * 4);
  const budget = Number(zone.threshold_minutes ?? zone.budget_minutes ?? 60);

  for (let r = 0; r < rows; r++) {
    const rowArr = grid[r] || [];
    for (let c = 0; c < cols; c++) {
      const val = rowArr[c];
      const idx = (r * cols + c) * 4;
      let rgb = [0, 0, 0];
      let a = 0; // NoData, unreachable, nonfinite, or explicitly blocked cells are 100% transparent (alpha = 0)
      if (val !== null && val !== undefined && Number.isFinite(val) && val >= 0) {
        if (kind === 'rescue') {
          const ratio = val / Math.max(1, budget);
          if (ratio <= 0.5) {
            rgb = [92, 225, 158];
            a = 88;
          } else if (ratio <= 1.0) {
            rgb = [235, 184, 92];
            a = 104;
          } else {
            rgb = [228, 102, 86];
            a = 110;
          }
        } else {
          if (val <= budget) {
            const frac = Math.min(1, val / Math.max(1, budget));
            rgb = [72, Math.round(235 - frac * 50), 178];
            a = Math.round(48 + frac * 34);
          } else {
            rgb = [226, 112, 92];
            a = 55;
          }
        }
      }
      data[idx] = rgb[0];
      data[idx + 1] = rgb[1];
      data[idx + 2] = rgb[2];
      data[idx + 3] = a;
    }
  }
  return { rows, cols, data };
}

export function buildTimeOverlayCanvas(zone, kind = 'return') {
  const { rows, cols, data } = computeTimeOverlayPixels(zone, kind);
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, cols);
  canvas.height = Math.max(1, rows);
  if (!rows || !cols) return canvas.toDataURL('image/png');
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(cols, rows);
  img.data.set(data);
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL('image/png');
}

export function calculateEdgeFeatherGradients(pixelBounds, featherPx = 54) {
  const { tl, br } = pixelBounds || {};
  if (!tl || !br) return null;
  const x = Math.min(tl[0], br[0]);
  const y = Math.min(tl[1], br[1]);
  const w = Math.abs(br[0] - tl[0]);
  const h = Math.abs(br[1] - tl[1]);
  if (w <= 0 || h <= 0) return null;

  const fp = Math.min(featherPx, w / 4, h / 4);
  if (fp <= 1) return null;

  return {
    rect: { x, y, w, h },
    fp,
    top: { x0: 0, y0: y, x1: 0, y1: y + fp, fillRect: [x - 4, y - 4, w + 8, fp + 4] },
    bottom: { x0: 0, y0: y + h, x1: 0, y1: y + h - fp, fillRect: [x - 4, y + h - fp, w + 8, fp + 4] },
    left: { x0: x, y0: 0, x1: x + fp, y1: 0, fillRect: [x - 4, y - 4, fp + 4, h + 8] },
    right: { x0: x + w, y0: 0, x1: x + w - fp, y1: 0, fillRect: [x + w - fp, y - 4, fp + 4, h + 8] },
  };
}
