// Types mirroring backend Pydantic schemas for the Building Hierarchy feature.

// === Core Entities ===

export interface Building {
  id: number;
  code: string;
  name: string;
  address: string | null;
  created_at: string;
  floors_count: number;
  published: boolean;
}

export interface BuildingBrief {
  id: number;
  code: string;
  name: string;
}

export interface BuildingDetail extends Building {
  floors: FloorBrief[];
}

export interface FloorBrief {
  id: number;
  number: number;
}

export interface Floor {
  id: number;
  building_id: number;
  number: number;
  sections_count: number;
  reconstructions_unbound_count: number;
  created_at: string;
}

// Polygon with 3–32 vertices in normalised [0,1] coordinates.
// Historically fixed this to 4 points; relaxed for the Floor Editor's
// polygon tool. The rectangle tool still produces 4 points.
export interface SectionGeometry {
  points: [number, number][];
}

export interface CropBbox {
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: 0 | 90 | 180 | 270;
}

export interface FloorWithSchema extends Floor {
  building: BuildingBrief;
  schema_image_id: string | null;
  schema_image_url: string | null;
  schema_crop_bbox: CropBbox | null;
  wall_polygons: [number, number][][] | null; // [polygons[points]]
  /** Persisted user-edited wall mask (wizard step 3) — survives reload. */
  mask_file_id: string | null;
  mask_file_url: string | null;
}

export interface ReconstructionBrief {
  id: number;
  name: string | null;
  status: number;
  preview_url: string | null;
}

export interface Section {
  id: number;
  floor_id: number;
  number: number;
  geometry: SectionGeometry;
  section_type: number;
  reconstruction: ReconstructionBrief | null;
  created_at: string;
  updated_at: string;
}

// Public building shape (published=true endpoint — denormalized for catalog)
export interface PublicBuilding {
  id: number;
  code: string;
  name: string;
  floors: Array<{
    id: number;
    number: number;
    schema_image_url: string | null;
    schema_crop_bbox: CropBbox | null;
    wall_polygons: [number, number][][] | null;
    sections: Array<{
      id: number;
      number: number;
      geometry: SectionGeometry;
      reconstruction_id: number;
      mesh_url_glb: string;
      section_type: number;
    }>;
  }>;
}

// === Extended types (additions) ===

export interface FloorWithBuilding extends Floor {
  building: BuildingBrief;
}

export interface SectionPayloadItem {
  number: number;
  geometry: SectionGeometry;
  section_type: number;
  reconstruction_id: number | null;
}

export interface ReplaceSectionsRequest {
  sections: SectionPayloadItem[];
}

// Nested floor info on reconstruction responses (replaces flat building_id/floor_number)
export interface ReconstructionFloor {
  id: number;
  number: number;
  building: BuildingBrief;
}

// Nested section info on reconstruction responses
export interface ReconstructionSectionBrief {
  id: number;
  number: number;
}

// Floor schema update request
export interface FloorSchemaUpdateRequest {
  schema_image_id: string;
  schema_crop_bbox: CropBbox | null;
}

// Wall polygons update request/response
export interface FloorWallsUpdateRequest {
  wall_polygons: [number, number][][];
}

export interface FloorWallsUpdateResponse {
  wall_polygons: [number, number][][];
}

// Extract walls response
export interface ExtractWallsResponse {
  wall_polygons: [number, number][][];
}
