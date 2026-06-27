// TypeScript contract for cross-floor routing + link review (subfeature D).
// (field names/types must match the Pydantic models in models/building_nav.py).

export interface MultifloorRouteRequest {
  from_floor_id: number;
  from_room: string;
  to_floor_id: number;
  to_room: string;
}

// One floor's slice of the route, as a 3D polyline in the building-frame world
// shared with the floor GLBs (B): [x, y, z], no client-side transform needed.
export interface FloorPathSegment3D {
  floor_id: number;
  floor_number: number;
  coordinates_3d: number[][];
}

export interface TransitionUsed3D {
  type: string; // 'staircase' | 'elevator'
  from_3d: number[];
  to_3d: number[];
  from_floor_id: number;
  to_floor_id: number;
  from_node: string; // bare room node id of the lower-side shaft (e.g. 'room_<uuid>')
  to_node: string; // bare room node id of the upper-side shaft
}

// status ∈ 'success' | 'no_path' | 'not_aligned' (all HTTP 200).
export interface MultifloorRouteResponse {
  status: string;
  total_distance_meters: number | null;
  estimated_time_seconds: number | null;
  path_segments: FloorPathSegment3D[];
  transitions_used: TransitionUsed3D[];
  message: string | null;
}

export interface TransitionLink {
  lower_floor_id: number;
  lower_floor_number: number;
  lower_node: string;
  upper_floor_id: number;
  upper_floor_number: number;
  upper_node: string;
  type: string; // 'staircase' | 'elevator'
  source: string; // 'auto' | 'forced'
  enabled: boolean;
  distance_m: number;
}

export interface UnmatchedTransition {
  floor_id: number;
  floor_number: number;
  node: string;
  type: string;
  reason: string;
}

export interface TransitionLinksResponse {
  building_id: number;
  links: TransitionLink[];
  unmatched: UnmatchedTransition[];
  status: string | null;
}

export interface TransitionOverride {
  lower_floor_id: number;
  lower_node: string;
  upper_floor_id: number;
  upper_node: string;
  action: 'disable' | 'force';
}

export interface SaveTransitionLinksRequest {
  overrides: TransitionOverride[];
}

export interface SaveTransitionLinksResponse {
  building_id: number;
  overrides_count: number;
}
