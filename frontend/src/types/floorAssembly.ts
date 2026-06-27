// Types mirroring backend Pydantic models for the Floor Stitching feature.
//
// Nullability matches the Pydantic models, NOT the always-populated
// happy-path JSON examples in the contract: image_size_cropped, pixels_per_meter,
// mesh_file_glb and a section's transform may all be null.

import type { CropBbox } from './hierarchy';

// === Points / elements ===

export interface ControlPoint {
  id: string;
  x: number;
  y: number;
}

export interface MasterControlPoint {
  point_id: string;
  x: number;
  y: number;
}

export interface SectionTransform {
  scale: number;
  /** Section→master rotation in radians (atan2(R[1,0],R[0,0])); 0 for legacy. */
  rotation_rad: number;
  tx: number;
  ty: number;
  residual_rms_px: number;
  n_points: number;
  solved_at: string;
}

export interface Connector {
  id: number;
  points: [number, number][];
  height_m: number | null;
  thickness_m: number | null;
  connects: number[] | null;
}

// A connector in a replace-all request — Connector without the server-assigned id.
// The optional fields default to null server-side when omitted.
export interface ConnectorInput {
  points: [number, number][];
  height_m?: number | null;
  thickness_m?: number | null;
  connects?: number[] | null;
}

// A cutout zone — a CLOSED polygon (rectangle = 4 corners) that ERASES walls for
// BOTH the nav graph and the 3D mesh. >= 3 points; id is a 0-based list index.
export interface Cutout {
  id: number;
  points: [number, number][];
}

// A cutout in a replace-all request — Cutout without the server-assigned id.
export interface CutoutInput {
  points: [number, number][];
}

// === /: control points ===

export interface ControlPointsResponse {
  reconstruction_id: number;
  image_size_cropped: [number, number] | null;
  points: ControlPoint[];
}

export interface SectionControlPointsResponse {
  section_id: number;
  points: MasterControlPoint[];
  section_point_ids: string[];
  matched_ids: string[];
  unmatched_ids: string[];
}

// ===: solve transforms ===

export type SolveSectionStatus = 'ok' | 'needs_points' | 'degenerate';

export interface SolveSectionResult {
  section_id: number;
  status: SolveSectionStatus;
  transform: SectionTransform | null;
  implied_ppm: number | null;
  warning: string | null;
}

export interface SolveTransformsResponse {
  floor_id: number;
  pixels_per_meter: number | null;
  anchor_section_id: number | null;
  sections: SolveSectionResult[];
}

// ===: connectors ===

export interface ConnectorsResponse {
  floor_id: number;
  connectors: Connector[];
}

// ===: cutouts ===

export interface CutoutsResponse {
  floor_id: number;
  cutouts: Cutout[];
}

// ===: build preview / confirm ===

export interface ExcludedSection {
  section_id: number;
  reason: string;
}

export interface BuildWarning {
  section_id: number;
  code: string;
  message: string;
}

export interface BuildFloorPreviewResponse {
  floor_id: number;
  glb_file_id: string;
  glb_url: string;
  persisted: boolean;
  pixels_per_meter: number | null;
  canvas_size_px: [number, number];
  included_sections: number[];
  excluded_sections: ExcludedSection[];
  warnings: BuildWarning[];
  connector_count: number;
  cutout_count: number;
}

export interface ConfirmMeshResponse {
  floor_id: number;
  mesh_file_glb: string;
  glb_url: string;
  persisted: boolean;
}

// === Assembly read (drives the Floor Editor) ===

export interface MasterSchemaInfo {
  image_id: string;
  url: string;
  crop_bbox: CropBbox | null;
  size_px: [number, number] | null;
  /**
   * Vectorised "карта отсеков" — floor wall contours normalised [0,1] over the
   * CROPPED+rotated master frame (the same frame master_control_points live in).
   * Drawn as the master backdrop (vector); null until wall extraction (step 3).
   */
  wall_polygons: [number, number][][] | null;
}

export interface AssemblySection {
  section_id: number;
  number: number;
  reconstruction_id: number | null;
  mask_file_id: string | null;
  /** Viewable URL of the section's cropped wall mask (the "эталон" backdrop). */
  mask_url: string | null;
  /** Section outline polygon, normalised [0,1] over the master (floor) frame. */
  geometry: [number, number][] | null;
  image_size_cropped: [number, number] | null;
  section_control_points: ControlPoint[];
  master_control_points: MasterControlPoint[];
  transform: SectionTransform | null;
  status: SolveSectionStatus;
}

export interface FloorAssemblyResponse {
  floor_id: number;
  pixels_per_meter: number | null;
  mesh_file_glb: string | null;
  master_schema: MasterSchemaInfo;
  sections: AssemblySection[];
  connectors: Connector[];
  cutouts: Cutout[];
}
