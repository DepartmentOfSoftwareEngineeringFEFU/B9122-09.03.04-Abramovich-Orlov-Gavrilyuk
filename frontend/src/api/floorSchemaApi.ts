// REST client for Floor Schema endpoints (schema image, wall extraction, wall polygons).

import apiClient from './apiService';
import type {
  FloorWithSchema,
  FloorSchemaUpdateRequest,
  FloorWallsUpdateResponse,
  ExtractWallsResponse,
} from '../types/hierarchy';

export const floorSchemaApi = {
  // PUT /api/v1/floors/{id}/schema — upload/update schema image + crop bbox
  uploadSchema: (floorId: number, req: FloorSchemaUpdateRequest): Promise<FloorWithSchema> =>
    apiClient
      .put(`/floors/${floorId}/schema`, req)
      .then((r) => r.data as FloorWithSchema),

  // POST /api/v1/floors/{id}/extract-walls — run CV pipeline to extract wall polygons
  extractWalls: (floorId: number): Promise<ExtractWallsResponse> =>
    apiClient
      .post(`/floors/${floorId}/extract-walls`)
      .then((r) => r.data as ExtractWallsResponse),

  // PUT /api/v1/floors/{id}/walls — manually save wall polygons after editing
  updateWalls: (
    floorId: number,
    wallPolygons: [number, number][][],
  ): Promise<FloorWallsUpdateResponse> =>
    apiClient
      .put(`/floors/${floorId}/walls`, { wall_polygons: wallPolygons })
      .then((r) => r.data as FloorWallsUpdateResponse),

  // PUT /api/v1/floors/{id}/mask — persist the user-edited wall-mask file id
  updateMask: (floorId: number, maskFileId: string): Promise<FloorWithSchema> =>
    apiClient
      .put(`/floors/${floorId}/mask`, { mask_file_id: maskFileId })
      .then((r) => r.data as FloorWithSchema),

  // DELETE /api/v1/floors/{id}/schema — fully clear schema image, crop, walls, mask
  resetSchema: (floorId: number): Promise<void> =>
    apiClient.delete(`/floors/${floorId}/schema`).then(() => undefined),
};
