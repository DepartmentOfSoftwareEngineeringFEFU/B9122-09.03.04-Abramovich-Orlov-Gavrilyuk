// REST client for the floor navigation-graph endpoints (build graph, route,
// rooms-3d).
//
// Base URL already includes /api/v1 (apiService interceptor adds the auth header).
// Each call unwraps the axios response via `.then((r) => r.data as T)`, mirroring
// floorAssemblyApi. Room3DApi is reused — the /rooms-3d room shape is identical.

import apiClient from './apiService';
import type { Room3DApi } from './apiService';

/** Metadata returned by POST /floors/{id}/build-floor-graph. */
export interface FloorGraphMeta {
  floor_id: number;
  nodes_count: number;
  edges_count: number;
  rooms_count: number;
  corridor_nodes_count: number;
  canvas_size_px: [number, number];
  scale_factor: number;
}

/** Result of GET /floors/{id}/route. */
export interface FloorRouteResponse {
  floor_id: number;
  status: 'found' | 'no_path';
  path_3d: [number, number, number][];
  total_distance_m: number | null;
  from_room_id: string;
  to_room_id: string;
}

/** Result of GET /floors/{id}/rooms-3d. */
export interface FloorRooms3DResponse {
  floor_id: number;
  rooms: Room3DApi[]; // reuse existing type — same shape
}

// 2D nav-graph (GET /floors/{id}/nav-graph-2d)
// Coordinates (`pos`, edge `pts`) are in assembled-canvas pixels — the canvas is
// metadata.mask_width × mask_height. Mirrors the single-plan reconstruction shape.

/** A single node in the 2D nav graph. */
export interface NavGraph2DNode {
  id: string | number;
  type: string;
  pos: [number, number];
  room_name?: string;
  room_id?: string;
  bbox?: number[];
}

/** A single edge in the 2D nav graph. */
export interface NavGraph2DEdge {
  source: string | number;
  target: string | number;
  type: string;
  pts?: [number, number][];
}

/** Result of GET /floors/{id}/nav-graph-2d (404 if the graph isn't built yet). */
export interface NavGraph2DResponse {
  metadata: {
    nodes_count: number;
    edges_count: number;
    room_nodes: string[];
    door_nodes: string[];
    mask_width: number;
    mask_height: number;
  };
  graph: {
    nodes: NavGraph2DNode[];
    edges: NavGraph2DEdge[];
  };
}

export const floorNavApi = {
  // POST /api/v1/floors/{id}/build-floor-graph — rebuild mask + nav graph
  buildFloorGraph: (floorId: number): Promise<FloorGraphMeta> =>
    apiClient
      .post(`/floors/${floorId}/build-floor-graph`)
      .then((r) => r.data as FloorGraphMeta),

  // GET /api/v1/floors/{id}/route — shortest path between two rooms
  getFloorRoute: (
    floorId: number,
    fromRoom: string,
    toRoom: string,
  ): Promise<FloorRouteResponse> =>
    apiClient
      .get(`/floors/${floorId}/route`, {
        params: { from_room: fromRoom, to_room: toRoom },
      })
      .then((r) => r.data as FloorRouteResponse),

  // GET /api/v1/floors/{id}/rooms-3d — room bounding boxes in GLB world coords
  getFloorRooms3D: (floorId: number): Promise<FloorRooms3DResponse> =>
    apiClient
      .get(`/floors/${floorId}/rooms-3d`)
      .then((r) => r.data as FloorRooms3DResponse),

  // GET /api/v1/floors/{id}/nav-graph-2d — 2D node/edge data for visualization
  getNavGraph2d: (floorId: number): Promise<NavGraph2DResponse> =>
    apiClient
      .get(`/floors/${floorId}/nav-graph-2d`)
      .then((r) => r.data as NavGraph2DResponse),
};
