// Transform
export interface Transform {
  translate_x: number;
  translate_y: number;
  scale_x: number;
  scale_y: number;
  rotation_deg: number;
}

// Clip polygon
export interface ClipPolygon {
  type: "subtract";
  points: [number, number][];
}

// Rect crop
export interface RectCrop {
  x: number;
  y: number;
  width: number;
  height: number;
}

// Source plan input
export interface SourcePlanInput {
  reconstruction_id: string;
  transform: Transform;
  clip_polygons: ClipPolygon[];
  rect_crop: RectCrop | null;
  image_width_px: number;
  image_height_px: number;
  z_index: number;
}

// Stitching request
export interface StitchingRequest {
  name: string;
  building_id: string;
  floor_number: number;
  source_plans: SourcePlanInput[];
}

// Stitching response
export interface StitchingResponse {
  id: number;
  name: string;
  status: number;
  source_reconstruction_ids: number[];
  building_id: string;
  floor_number: number;
  rooms_count: number;
  walls_count: number;
  warnings?: string[];
}

// Reconstruction list item (for selection)
export interface ReconstructionListItem {
  id: number;
  name: string;
  preview_url: string | null;
  rooms_count: number;
  walls_count: number;
  created_at: string;
  rotation_angle: number;
  building_id: string | null;
  floor_number: number | null;
  status?: string;
}

// Layer data (canvas state)
export interface LayerData {
  reconstructionId: string;
  name: string;
  originalImageUrl: string;
  previewUrl: string;
  vectorModel: VectorModel;
  transform: Transform;
  clipPolygons: ClipPolygon[];
  rectCrop: RectCrop | null;
  imageWidth: number;
  imageHeight: number;
  zIndex: number;
  color: string;
  maskOpacity: number;
  showMask: boolean;
}

// Vector model (from reconstruction)
export interface VectorModel {
  walls: Wall[];
  rooms: Room[];
  doors: Door[];
}

export interface Wall {
  id: string;
  points: Point2D[];
  thickness: number;
}

export interface Room {
  id: string;
  name: string;
  polygon: Point2D[];
  center: Point2D;
  room_type: string;
}

export interface Door {
  id: string;
  position: Point2D;
  width: number;
}

export interface Point2D {
  x: number;
  y: number;
}

// Stitching state
export interface StitchingState {
  step: 1 | 2;
  selectedReconstructionIds: string[];
  buildingId: string;
  floorNumber: number;
  layers: LayerData[];
  activeTool: "move" | "rotate" | "rect_crop" | "polygon_clip";
  selectedLayerId: string | null;
  isLoading: boolean;
  error: string | null;
}

// Snapshot for undo/redo
export interface StitchingSnapshot {
  layers: LayerSnapshot[];
}

export interface LayerSnapshot {
  reconstructionId: string;
  transform: Transform;
  clipPolygons: ClipPolygon[];
  rectCrop: RectCrop | null;
  zIndex: number;
}
