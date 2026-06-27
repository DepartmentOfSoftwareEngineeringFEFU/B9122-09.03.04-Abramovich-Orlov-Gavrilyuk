export interface VectorPoint {
  x: number;
  y: number;
}

export interface VectorRoom {
  id: string;
  name: string;
  room_type: 'room' | 'staircase' | 'elevator' | 'corridor';
  center: VectorPoint;
  polygon: VectorPoint[];
  area_normalized: number;
  // Elevator floor-link metadata (floor-transition-tools). Absent for room/stairs/corridor.
  floor_from?: number;
  floor_to?: number;
  floors_excluded?: number[];
}

export interface VectorDoor {
  id: string;
  position: VectorPoint;
  width: number;
  connects: string[];
}

export interface VectorizationResult {
  rooms: VectorRoom[];
  doors: VectorDoor[];
  rotation_angle: number;
  crop_rect: { x: number; y: number; width: number; height: number } | null;
}
