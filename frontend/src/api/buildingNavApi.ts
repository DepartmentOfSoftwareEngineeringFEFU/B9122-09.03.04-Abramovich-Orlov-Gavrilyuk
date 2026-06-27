// REST client for the cross-floor routing + link-review endpoints (subfeature D).
//
// Base URL already includes /api/v1 (apiService interceptor adds the auth header).
// Mirrors api/buildingSceneApi.ts in style: typed, no `any`.

import apiClient from './apiService';
import type {
  MultifloorRouteRequest,
  MultifloorRouteResponse,
  SaveTransitionLinksResponse,
  TransitionLinksResponse,
  TransitionOverride,
} from '../types/buildingNav';

export const buildingNavApi = {
  // POST /api/v1/buildings/{id}/multifloor-route — shortest cross-floor route.
  postMultifloorRoute: (
    buildingId: number,
    req: MultifloorRouteRequest,
  ): Promise<MultifloorRouteResponse> =>
    apiClient
      .post(`/buildings/${buildingId}/multifloor-route`, req)
      .then((r) => r.data as MultifloorRouteResponse),

  // GET /api/v1/buildings/{id}/transition-links — auto links + unmatched.
  getTransitionLinks: (buildingId: number): Promise<TransitionLinksResponse> =>
    apiClient
      .get(`/buildings/${buildingId}/transition-links`)
      .then((r) => r.data as TransitionLinksResponse),

  // PUT /api/v1/buildings/{id}/transition-links — persist operator overrides.
  putTransitionLinks: (
    buildingId: number,
    overrides: TransitionOverride[],
  ): Promise<SaveTransitionLinksResponse> =>
    apiClient
      .put(`/buildings/${buildingId}/transition-links`, { overrides })
      .then((r) => r.data as SaveTransitionLinksResponse),
};
