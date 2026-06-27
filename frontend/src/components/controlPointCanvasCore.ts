// Pure, presentational-free geometry helpers for the control-point canvas.
//
// These power ControlPointCanvas (section pass) and are reused by the
// floor-master canvas (master pass). They know nothing about React,
// the DOM or rendering — they are just the display<->image coordinate mapping,
// snap-to-vertex and hit-test maths, so they are trivially unit-testable.
//
// Radii (R_SNAP_PX, R_HIT_PX) are defined in DISPLAY pixels.
// Callers convert them to image-space via `displayScale` before comparing, so
// behaviour is identical regardless of how big the canvas is drawn.

/** Snap a freshly-placed point to the nearest wall vertex. DISPLAY px. */
export const R_SNAP_PX = 12;

/** Click within this radius selects an existing point instead of adding. DISPLAY px. */
export const R_HIT_PX = 10;

/** A point in normalised [0,1] image space. */
export interface NormPoint {
  x: number;
  y: number;
}

/** How the backdrop image is laid out inside the canvas element (CSS px). */
export interface CanvasLayout {
  /** Left offset of the drawn image inside the canvas element, CSS px. */
  offsetX: number;
  /** Top offset of the drawn image inside the canvas element, CSS px. */
  offsetY: number;
  /** Drawn image width in CSS px (after object-fit: contain letterboxing). */
  drawWidth: number;
  /** Drawn image height in CSS px. */
  drawHeight: number;
}

/** Clamp a value into the closed [min, max] range. */
export const clamp = (value: number, min: number, max: number): number =>
  value < min ? min : value > max ? max : value;

/**
 * Map a pointer position (CSS px, relative to the canvas element's top-left) to
 * normalised [0,1] image coordinates, accounting for letterboxing (the image is
 * drawn `object-fit: contain` style inside the element). Returns null when the
 * click falls outside the drawn image region.
 */
export const toImageCoords = (
  clientX: number,
  clientY: number,
  layout: CanvasLayout,
): NormPoint | null => {
  if (layout.drawWidth <= 0 || layout.drawHeight <= 0) return null;
  const localX = clientX - layout.offsetX;
  const localY = clientY - layout.offsetY;
  if (
    localX < 0 ||
    localY < 0 ||
    localX > layout.drawWidth ||
    localY > layout.drawHeight
  ) {
    return null;
  }
  return {
    x: clamp(localX / layout.drawWidth, 0, 1),
    y: clamp(localY / layout.drawHeight, 0, 1),
  };
};

/**
 * Convert a normalised [0,1] point to a CSS-px position inside the canvas
 * element (inverse of {@link toImageCoords}). Used to draw markers / labels.
 */
export const toDisplayCoords = (
  point: NormPoint,
  layout: CanvasLayout,
): { x: number; y: number } => ({
  x: layout.offsetX + point.x * layout.drawWidth,
  y: layout.offsetY + point.y * layout.drawHeight,
});

/**
 * Find the nearest target to `point` whose distance is within `radiusNorm`
 * (a radius already expressed in normalised units). Targets are normalised
 * [x, y] tuples. Returns the matching tuple, or null if none is close enough.
 *
 * Used for snap-to-wall-vertex: the caller passes R_SNAP_PX converted to
 * normalised units via the display scale.
 */
export const nearestWithin = (
  point: NormPoint,
  targets: readonly [number, number][],
  radiusNorm: number,
): [number, number] | null => {
  if (radiusNorm <= 0) return null;
  let best: [number, number] | null = null;
  let bestDistSq = radiusNorm * radiusNorm;
  for (const target of targets) {
    const dx = target[0] - point.x;
    const dy = target[1] - point.y;
    const distSq = dx * dx + dy * dy;
    if (distSq <= bestDistSq) {
      bestDistSq = distSq;
      best = target;
    }
  }
  return best;
};

/**
 * Hit-test existing points: return the id of the nearest point within
 * `radiusNorm` (normalised units), or null. Used so a click on top of an
 * existing marker selects it instead of adding a new point.
 */
export const hitTest = (
  point: NormPoint,
  points: readonly { id: string; x: number; y: number }[],
  radiusNorm: number,
): string | null => {
  if (radiusNorm <= 0) return null;
  let bestId: string | null = null;
  let bestDistSq = radiusNorm * radiusNorm;
  for (const candidate of points) {
    const dx = candidate.x - point.x;
    const dy = candidate.y - point.y;
    const distSq = dx * dx + dy * dy;
    if (distSq <= bestDistSq) {
      bestDistSq = distSq;
      bestId = candidate.id;
    }
  }
  return bestId;
};

/**
 * Convert a DISPLAY-px radius (constants) to normalised image units, given
 * the drawn image width in CSS px. `drawWidth` is the contain-fit width, so the
 * radius stays consistent with how the user perceives it on screen.
 */
export const displayRadiusToNorm = (
  radiusPx: number,
  drawWidth: number,
): number => (drawWidth > 0 ? radiusPx / drawWidth : 0);
