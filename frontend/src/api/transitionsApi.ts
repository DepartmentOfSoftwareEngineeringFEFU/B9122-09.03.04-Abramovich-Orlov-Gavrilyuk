import apiClient from './apiService';
import type {
  BuildingListItem,
  FloorTransition,
  CreateTransitionRequest,
  MultiPlanRouteRequest,
  MultiPlanRouteResponse,
  TransitionGroupCreate,
  TransitionGroupResponse,
  TransitionGroupUpdate,
  TransitionPointCreate,
  TransitionPointResponse,
  TransitionPointUpdate,
} from '../types/transitions';

export const transitionsApi = {
  // Floor Transition (new teleport system)
  createFloorTransition: (data: CreateTransitionRequest): Promise<FloorTransition> =>
    apiClient.post('/floor-transitions/', data).then((r) => r.data as FloorTransition),

  listFloorTransitions: (params: { building_id?: string; reconstruction_id?: number }): Promise<FloorTransition[]> =>
    apiClient.get('/floor-transitions/', { params }).then((r) => r.data as FloorTransition[]),

  deleteFloorTransition: (id: number): Promise<void> =>
    apiClient.delete(`/floor-transitions/${id}`).then(() => undefined),
  listBuildings: async (): Promise<BuildingListItem[]> => {
    const { data } = await apiClient.get<BuildingListItem[]>('/buildings');
    return data;
  },
  createGroup: async (request: TransitionGroupCreate): Promise<TransitionGroupResponse> => {
    const { data } = await apiClient.post<TransitionGroupResponse>('/transitions/groups', request);
    return data;
  },
  listGroups: async (buildingId?: string): Promise<TransitionGroupResponse[]> => {
    const params = buildingId ? { building_id: buildingId } : {};
    const { data } = await apiClient.get<TransitionGroupResponse[]>('/transitions/groups', { params });
    return data;
  },
  updateGroup: async (groupId: number, request: TransitionGroupUpdate): Promise<TransitionGroupResponse> => {
    const { data } = await apiClient.patch<TransitionGroupResponse>(`/transitions/groups/${groupId}`, request);
    return data;
  },
  deleteGroup: async (groupId: number): Promise<void> => { await apiClient.delete(`/transitions/groups/${groupId}`); },
  createPoint: async (request: TransitionPointCreate): Promise<TransitionPointResponse> => {
    const { data } = await apiClient.post<TransitionPointResponse>('/transitions/points', request);
    return data;
  },
  updatePoint: async (pointId: number, request: TransitionPointUpdate): Promise<TransitionPointResponse> => {
    const { data } = await apiClient.patch<TransitionPointResponse>(`/transitions/points/${pointId}`, request);
    return data;
  },
  deletePoint: async (pointId: number): Promise<void> => { await apiClient.delete(`/transitions/points/${pointId}`); },
  listPointsByBuilding: async (buildingId: string): Promise<TransitionPointResponse[]> => {
    const { data } = await apiClient.get<TransitionPointResponse[]>(`/transitions/buildings/${buildingId}/points`);
    return data;
  },
  listPointsByReconstruction: async (reconstructionId: number): Promise<TransitionPointResponse[]> => {
    const { data } = await apiClient.get<TransitionPointResponse[]>(`/transitions/reconstructions/${reconstructionId}/points`);
    return data;
  },
  routeMulti: async (request: MultiPlanRouteRequest): Promise<MultiPlanRouteResponse> => {
    const { data } = await apiClient.post<MultiPlanRouteResponse>('/navigation/route/multi', request);
    return data;
  },
};
