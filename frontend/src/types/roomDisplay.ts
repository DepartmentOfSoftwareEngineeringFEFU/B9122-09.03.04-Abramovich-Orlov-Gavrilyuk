import * as THREE from 'three';
import type { RoomAnnotation } from './wizard';

export interface RoomDisplay {
  id: string;
  name: string;
  room_type: string;
  center_x: number;    // normalized [0, 1]
  center_y: number;    // normalized [0, 1]
  width_norm: number;  // normalized [0, 1]
  height_norm: number; // normalized [0, 1]
  color: string;       // hex
}

export const ROOM_COLORS: Record<string, string> = {
  classroom: '#f5c542',
  corridor:  '#4287f5',
  staircase: '#2E7D32',
  elevator:  '#6A1B9A',
  toilet:    '#42f5c8',
  other:     '#c8c8c8',
  room:      '#c8c8c8',
};

// Shape of a room entry from GET /reconstructions/{id}/vectors
export interface VectorRoomApi {
  id: string;
  name: string;
  room_type: string;
  center: { x: number; y: number };
  polygon: Array<{ x: number; y: number }>;
  area_normalized: number;
}

export function fromRoomAnnotation(r: RoomAnnotation): RoomDisplay {
  const cx = r.center?.x != null ? r.center.x : r.x + r.width / 2;
  const cy = r.center?.y != null ? r.center.y : r.y + r.height / 2;
  return {
    id: r.id,
    name: r.name,
    room_type: r.room_type,
    center_x: cx,
    center_y: cy,
    width_norm: r.width,
    height_norm: r.height,
    color: ROOM_COLORS[r.room_type] ?? ROOM_COLORS.other,
  };
}

export function fromVectorRoom(r: VectorRoomApi): RoomDisplay {
  let width_norm = 0;
  let height_norm = 0;
  if (r.polygon.length > 0) {
    const xs = r.polygon.map((p) => p.x);
    const ys = r.polygon.map((p) => p.y);
    width_norm = Math.max(...xs) - Math.min(...xs);
    height_norm = Math.max(...ys) - Math.min(...ys);
  }
  return {
    id: r.id,
    name: r.name,
    room_type: r.room_type,
    center_x: r.center.x,
    center_y: r.center.y,
    width_norm,
    height_norm,
    color: ROOM_COLORS[r.room_type] ?? ROOM_COLORS.other,
  };
}

export function normalizedToWorld(
  cx: number,
  cy: number,
  box: THREE.Box3,
  wallHeight: number,
): [number, number, number] {
  return [
    box.min.x + cx * (box.max.x - box.min.x),
    box.min.y + wallHeight * 0.5,
    box.min.z + cy * (box.max.z - box.min.z),
  ];
}
