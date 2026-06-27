// ============================================================================
// Floor Transition (new teleport system)
// ============================================================================

export interface FloorTransition {
  id: number;
  name: string;
  building_id: string | null;
  from_reconstruction_id: number;
  from_geometry: number[][] | null;
  from_x: number;
  from_y: number;
  to_reconstruction_id: number;
  to_geometry: number[][] | null;
  to_x: number;
  to_y: number;
  created_at: string;
}

export interface CreateTransitionRequest {
  name: string;
  from_reconstruction_id: number;
  from_geometry?: number[][] | null;
  from_x: number;
  from_y: number;
  to_reconstruction_id: number;
  to_geometry?: number[][] | null;
  to_x: number;
  to_y: number;
}

export type TransitionEditorMode =
  | { type: 'idle' }
  | { type: 'placing_from'; name: string; to_reconstruction_id: number }
  | { type: 'placing_to'; name: string; from_reconstruction_id: number; from_geometry?: number[][]; from_x: number; from_y: number };

export interface PathSegment3D {
  reconstruction_id: number;
  floor_number: number;
  floor_name: string;
  coordinates_3d: number[][];
}

export interface TransitionUsed3D {
  name: string;
  from_3d: number[];
  to_3d: number[];
}

export interface Room3DInfo {
  position: number[];
  size: number[];
}

export interface MultifloorRouteRequest {
  building_id: string;
  from_reconstruction_id: number;
  from_room_id: string;
  to_reconstruction_id: number;
  to_room_id: string;
}

export interface MultifloorRouteResponse {
  status: 'success' | 'no_path' | 'error';
  total_distance_meters: number | null;
  estimated_time_seconds: number | null;
  path_segments: PathSegment3D[];
  transitions_used: TransitionUsed3D[];
  from_room_3d: Room3DInfo | null;
  to_room_3d: Room3DInfo | null;
  message: string | null;
}

// ============================================================================
// Legacy TransitionGroup/Point system (kept for existing components)
// ============================================================================

export type TransitionType = 'passage' | 'stairs' | 'elevator';
export type MultiPlanRouteStatus = 'success' | 'no_path' | 'error';

export interface FloorListItem {
  number: number;
  reconstruction_id: number;
  reconstruction_name: string | null;
}

export interface BuildingListItem {
  id: number;
  code: string;
  name: string;
  floors?: FloorListItem[];
}

export interface TransitionGroupResponse {
  id: number;
  building_id: string | null;
  type: TransitionType;
  label: string | null;
  target_hint_building_id: string | null;
  target_hint_floor_number: number | null;
  point_ids: number[];
  created_at: string;
}

export interface TransitionPointResponse {
  id: number;
  reconstruction_id: number;
  group_id: number;
  position_x: number;
  position_y: number;
  label: string | null;
  snapped_node_id: string | null;
}

export interface TeleportView {
  id: number;
  group_id: number;
  reconstruction_id: number;
  position_x: number;
  position_y: number;
  label: string | null;
  status: 'draft' | 'linked';
  linked_point_id: number | null;
  target_building_id: string | null;
  target_floor_number: number | null;
  target_reconstruction_id: number | null;
}

export interface MultiPlanRouteRequest {
  from_reconstruction_id: number;
  from_room_id: string;
  to_reconstruction_id: number;
  to_room_id: string;
}

export interface MultiPlanRouteSegment {
  reconstruction_id: number;
  reconstruction_name: string | null;
  floor_label: string | null;
  coordinates: number[][];
  transition_out_point_id: number | null;
}

export interface MultiPlanRouteResponse {
  status: MultiPlanRouteStatus;
  message: string | null;
  total_distance_meters: number | null;
  segments: MultiPlanRouteSegment[];
}

export interface TransitionGroupCreate {
  building_id: string | null;
  type: TransitionType;
  label: string | null;
  target_hint_building_id: string | null;
  target_hint_floor_number: number | null;
}

export interface TransitionGroupUpdate {
  type?: TransitionType;
  label?: string | null;
  target_hint_building_id?: string | null;
  target_hint_floor_number?: number | null;
}

export interface TransitionPointCreate {
  reconstruction_id: number;
  group_id: number;
  position_x: number;
  position_y: number;
  label: string | null;
}

export interface TransitionPointUpdate {
  position_x?: number;
  position_y?: number;
  label?: string | null;
}
