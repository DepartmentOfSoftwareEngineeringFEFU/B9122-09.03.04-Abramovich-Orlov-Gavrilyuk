// REST client for the Vertical Floor Stitching endpoints (subfeature A):
// per-pair anchor points, solve every adjacent pair, and the assembly read that
// drives the Building Assembly page.
//
// Base URL already includes /api/v1 (apiService interceptor adds the auth
// header). Mirrors api/floorAssemblyApi.ts in style: typed, no `any`.

import apiClient from './apiService';
import type {
  BuildingAssemblyResponse,
  SaveStitchPointsRequest,
  SaveStitchPointsResponse,
  SolveStitchResponse,
} from '../types/buildingAssembly';

export const buildingAssemblyApi = {
  // PUT /api/v1/floors/{id}/stitch-points — save the pair anchors (this floor =
  // upper/moving; floor below = reference). `points`=upper, `ref_points`=lower.
  putStitchPoints: (
    floorId: number,
    req: SaveStitchPointsRequest,
  ): Promise<SaveStitchPointsResponse> =>
    apiClient
      .put(`/floors/${floorId}/stitch-points`, req)
      .then((r) => r.data as SaveStitchPointsResponse),

  // POST /api/v1/buildings/{id}/solve-stitch — solve every adjacent pair and
  // compose per-floor building transforms (empty body).
  postSolveStitch: (buildingId: number): Promise<SolveStitchResponse> =>
    apiClient
      .post(`/buildings/${buildingId}/solve-stitch`)
      .then((r) => r.data as SolveStitchResponse),

  // GET /api/v1/buildings/{id}/assembly — read state to drive the assembly page
  // (floor chain + per-pair status + mask dims for the canvas/overlay).
  getAssembly: (buildingId: number): Promise<BuildingAssemblyResponse> =>
    apiClient
      .get(`/buildings/${buildingId}/assembly`)
      .then((r) => r.data as BuildingAssemblyResponse),
};
