/**
 * Helpers for rendering the CROPPED + ROTATED portion of the floor schema photo.
 *
 * Backend stores wall_polygons normalised to [0,1] WITHIN the cropped+rotated
 * region (see floor_schema_service.py extract_walls), so the frontend must draw
 * that same region to keep coordinates aligned.
 */

import type { CropBbox } from '../../types/hierarchy';

/**
 * Bake the cropped + rotated region of a schema image into an offscreen canvas.
 *
 * CRITICAL: `crop.{x,y,width,height}` are NORMALISED fractions [0,1], NOT pixels
 * — that is how they are stored (floor.schema_crop_bbox) and how the backend
 * consumes them (preprocessor.preprocess_image: `x = int(crop.x * w)`). This
 * mirrors the backend EXACTLY — rotate the full image FIRST, then crop by
 * fractions over the ROTATED dims — so the returned canvas has the same frame
 * (and dims, modulo ≤1px rounding) as `_master_pixel_dims`, which is the frame
 * `wall_polygons` and the master control points are normalised over.
 *
 * Returns null if inputs are missing or the cropped region is degenerate.
 */
export function bakeCroppedRotated(
  img: HTMLImageElement,
  crop: CropBbox | null,
): HTMLCanvasElement | null {
  if (!img.complete || img.naturalWidth === 0) return null;

  const iw = img.naturalWidth;
  const ih = img.naturalHeight;
  const rotation = (((crop?.rotation ?? 0) % 360) + 360) % 360;

  // 1. Rotate the FULL image (mirrors preprocess_image step 1: cv2.rotate).
  const swap = rotation === 90 || rotation === 270;
  const rw = swap ? ih : iw;
  const rh = swap ? iw : ih;
  const rotCanvas = document.createElement('canvas');
  rotCanvas.width = rw;
  rotCanvas.height = rh;
  const rctx = rotCanvas.getContext('2d');
  if (!rctx) return null;
  rctx.imageSmoothingEnabled = true;
  rctx.imageSmoothingQuality = 'high';
  rctx.save();
  rctx.translate(rw / 2, rh / 2);
  rctx.rotate((rotation * Math.PI) / 180);
  rctx.drawImage(img, -iw / 2, -ih / 2);
  rctx.restore();

  // No crop → the (possibly rotated) full image.
  if (!crop) return rotCanvas;
  if (crop.width <= 0 || crop.height <= 0) return null;

  // 2. Crop by FRACTIONS over the rotated dims (mirrors preprocess_image step 2:
  //    int(crop.x*w) etc., clamped to bounds).
  const cx = Math.max(0, Math.min(Math.round(crop.x * rw), rw - 1));
  const cy = Math.max(0, Math.min(Math.round(crop.y * rh), rh - 1));
  const cw = Math.max(1, Math.min(Math.round(crop.width * rw), rw - cx));
  const ch = Math.max(1, Math.min(Math.round(crop.height * rh), rh - cy));
  if (cw < 2 || ch < 2) return null;

  const out = document.createElement('canvas');
  out.width = cw;
  out.height = ch;
  const octx = out.getContext('2d');
  if (!octx) return null;
  octx.imageSmoothingEnabled = true;
  octx.imageSmoothingQuality = 'high';
  octx.drawImage(rotCanvas, cx, cy, cw, ch, 0, 0, cw, ch);
  return out;
}

/**
 * Fit a (w × h) image into a (cw × ch) container, preserving aspect ratio.
 * Returns the destination rect inside the container.
 */
export function fitContain(
  w: number,
  h: number,
  cw: number,
  ch: number,
  zoom = 1,
): { dx: number; dy: number; dw: number; dh: number } {
  const scale = Math.min(cw / w, ch / h) * zoom;
  const dw = w * scale;
  const dh = h * scale;
  const dx = (cw - dw) / 2;
  const dy = (ch - dh) / 2;
  return { dx, dy, dw, dh };
}
