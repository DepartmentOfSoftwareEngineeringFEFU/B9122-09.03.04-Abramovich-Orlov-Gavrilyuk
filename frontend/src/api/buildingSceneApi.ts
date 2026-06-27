// REST client for the stacked 3D building viewer endpoint (subfeature B).
//
// Base URL already includes /api/v1 (apiService interceptor adds the auth
// header). Mirrors api/buildingAssemblyApi.ts in style: typed, no `any`.

import apiClient from './apiService';
import type { BuildingScene3DResponse } from '../types/buildingScene';

export const buildingSceneApi = {
  // GET /api/v1/buildings/{id}/scene-3d — per-floor GLB url + 3D placement.
  getScene3d: (buildingId: number): Promise<BuildingScene3DResponse> =>
    apiClient
      .get(`/buildings/${buildingId}/scene-3d`)
      .then((r) => r.data as BuildingScene3DResponse),
};
