// Types mirroring backend Pydantic models for the Vertical Floor Stitching
// feature (subfeature A).
// and backend/app/models/building_assembly.py.
//
// Field names + nullability match the Pydantic models exactly. The page AND the
// later subfeature D depend on `mask_width`/`mask_height` and the
// `building_transform` shape `{scale, rotation_rad, tx, ty, residual_rms_px,
// n_points}` — these are the shared A/B/D contract, so do NOT rename them.
//
// All control-point coordinates are normalised [0,1] over each floor's wall mask.

// === Control points (id-paired `cp-N`, same scheme as section stitching) ===

export interface ControlPoint {
  /** Stable `cp-N` id (validated server-side against `^cp-\d+$`). */
  id: string;
  x: number;
  y: number;
}

// === PUT /floors/{floor_id}/stitch-points ===

export interface SaveStitchPointsRequest {
  /** Anchor points on THIS floor's mask (the upper/moving floor of the pair). */
  points: ControlPoint[];
  /** Matching points on the floor BELOW's mask (the reference). Paired by id. */
  ref_points: ControlPoint[];
}

export interface SaveStitchPointsResponse {
  floor_id: number;
  points_count: number;
  ref_points_count: number;
}

// === Similarity transform (this floor's mask-px → reference-floor mask-px) ===

export interface StitchTransform {
  scale: number;
  rotation_rad: number;
  tx: number;
  ty: number;
  residual_rms_px: number;
  n_points: number;
}

// === POST /buildings/{building_id}/solve-stitch ===

export type FloorStitchStatusValue =
  | 'reference'
  | 'ok'
  | 'needs_points'
  | 'degenerate'
  | 'no_mask';

export interface FloorStitchStatus {
  floor_id: number;
  number: number;
  status: FloorStitchStatusValue;
  /** Mask-px → building reference-frame px. Reference floor = identity; null = unsolved/unlinked. */
  building_transform: StitchTransform | null;
  residual_rms_m: number | null;
  elevation_m: number;
}

export interface SolveStitchResponse {
  building_id: number;
  reference_floor_id: number;
  floors: FloorStitchStatus[];
}

// === GET /buildings/{building_id}/assembly ===

export type AssemblyPairStatus =
  | 'reference'
  | 'ok'
  | 'needs_points'
  | 'unsolved'
  | 'no_mask';

export interface AssemblyFloor {
  id: number;
  number: number;
  /** From Floor.mask_file; null when the floor's mask is not yet edited/built. */
  mask_url: string | null;
  /** Wall-mask pixel dims — used to de-normalize control points. */
  mask_width: number | null;
  mask_height: number | null;
  pixels_per_meter: number | null;
  elevation_m: number;
  points_count: number;
  ref_points_count: number;
  /** Saved anchors (this floor's own) so the canvas can redraw them on reload. */
  points: ControlPoint[];
  /** Saved matching anchors on the floor below (redrawn on the reference panel). */
  ref_points: ControlPoint[];
  building_transform: StitchTransform | null;
  pair_status: AssemblyPairStatus;
}

export interface BuildingAssemblyResponse {
  building_id: number;
  reference_floor_id: number | null;
  floors: AssemblyFloor[];
}
