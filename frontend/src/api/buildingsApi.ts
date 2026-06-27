// REST client for Buildings, Floors, and Sections endpoints.

import apiClient from './apiService';
import type {
  Building,
  BuildingDetail,
  Floor,
  FloorWithSchema,
  Section,
  ReplaceSectionsRequest,
  PublicBuilding,
} from '../types/hierarchy';

// === Buildings ===

export const buildingsApi = {
  list: (): Promise<Building[]> =>
    apiClient.get('/buildings').then((r) => r.data as Building[]),

  listPublished: (): Promise<PublicBuilding[]> =>
    apiClient.get('/buildings', { params: { published: true } }).then((r) => r.data as PublicBuilding[]),

  getById: (id: number): Promise<BuildingDetail> =>
    apiClient.get(`/buildings/${id}`).then((r) => r.data as BuildingDetail),

  create: (req: { code: string; name: string; address?: string }): Promise<Building> =>
    apiClient.post('/buildings', req).then((r) => r.data as Building),

  update: (id: number, req: { name?: string; address?: string }): Promise<Building> =>
    apiClient.patch(`/buildings/${id}`, req).then((r) => r.data as Building),

  delete: (id: number): Promise<void> =>
    apiClient.delete(`/buildings/${id}`).then(() => undefined),
};

// === Floors ===

export const floorsApi = {
  listByBuilding: (buildingId: number): Promise<Floor[]> =>
    apiClient.get(`/buildings/${buildingId}/floors`).then((r) => r.data as Floor[]),

  getById: (id: number): Promise<FloorWithSchema> =>
    apiClient.get(`/floors/${id}`).then((r) => r.data as FloorWithSchema),

  create: (buildingId: number, req: { number: number }): Promise<Floor> =>
    apiClient.post(`/buildings/${buildingId}/floors`, req).then((r) => r.data as Floor),

  delete: (id: number): Promise<void> =>
    apiClient.delete(`/floors/${id}`).then(() => undefined),
};

// === Sections ===

export const sectionsApi = {
  listByFloor: (floorId: number): Promise<Section[]> =>
    apiClient.get(`/floors/${floorId}/sections`).then((r) => r.data as Section[]),

  replace: (floorId: number, req: ReplaceSectionsRequest): Promise<Section[]> =>
    apiClient.put(`/floors/${floorId}/sections`, req).then((r) => r.data as Section[]),

  delete: (id: number): Promise<void> =>
    apiClient.delete(`/sections/${id}`).then(() => undefined),
};
