/**
 * API клиент для взаимодействия с backend
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import type { VectorizationResult } from '../types/reconstructionVectors';
import type { MultifloorRouteRequest, MultifloorRouteResponse } from '../types/transitions';
import type { ReconstructionFloor, ReconstructionSectionBrief } from '../types/hierarchy';

const API_BASE_URL = '/api/v1';

// Создание инстанса axios
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor для добавления токена
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Interceptor для обработки ошибок
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// === Auth API ===

export const authApi = {
  login: async (username: string, password: string) => {
    const params = new URLSearchParams();
    params.append('username', username);
    params.append('password', password);
    
    const response = await apiClient.post('/token/login/', params, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    return response.data;
  },

  register: async (data: any) => {
      const response = await apiClient.post('/users/', data);
      return response.data;
  },
  
  forgotPassword: async (email: string) => {
    const response = await apiClient.post('/token/forgot-password/', { email });
    return response.data;
  },

  logout: async () => {
    await apiClient.post('/token/logout/');
    localStorage.removeItem('auth_token');
  },
  
  getMe: async () => {
    const response = await apiClient.get('/users/me/');
    return response.data;
  },

  getPendingUsers: async () => {
    const response = await apiClient.get('/users/pending/');
    return response.data;
  },

  approveUser: async (userId: number, canApproveUsers = false) => {
    const response = await apiClient.post(`/users/${userId}/approve/`, null, {
      params: { can_approve_users: canApproveUsers }
    });
    return response.data;
  },

  rejectUser: async (userId: number) => {
    const response = await apiClient.post(`/users/${userId}/reject/`);
    return response.data;
  },
};

// === Upload API ===

export const uploadApi = {
  uploadPlanPhoto: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post('/upload/plan-photo/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
  
  uploadUserMask: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post('/upload/user-mask/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
};

// === Reconstruction API ===

export interface CropRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ReconstructionListItem {
  id: number;
  name: string;
  status: number;
  preview_url: string | null;
  /** Nested floor info — null when reconstruction is unbound */
  floor: { id: number; number: number; building_code: string } | null;
  /** Nested section info — null when not yet assigned to a section */
  section: ReconstructionSectionBrief | null;
  updated_at: string;
}

interface CalculateMaskResponse {
  file_id: string;
}

export interface ReconstructionResponse {
  id: number;
  name: string;
  status: number;
  status_display: string;
  created_at: string;
  created_by: number;
  saved_at: string | null;
  url: string | null;
  original_image_url: string | null;
  preview_url: string | null;
  plan_file_id: string | null;
  mask_file_id: string | null;
  mesh_file_id_obj: string | null;
  mesh_file_id_glb: string | null;
  crop_rect: CropRect | null;
  rotation_angle: number;
  error_message: string | null;
  vectorization_data: string | null;
  /** Nested floor info — null when reconstruction is unbound */
  floor: ReconstructionFloor | null;
  /** Nested section info — null when not yet assigned to a section */
  section: ReconstructionSectionBrief | null;
}

export const reconstructionApi = {
  calculateMask: async (fileId: string, crop?: CropRect, rotation?: number, blockSize?: number, thresholdC?: number) => {
    const cropData = crop ? { x: crop.x, y: crop.y, width: crop.width, height: crop.height } : null;
    const { data } = await apiClient.post<CalculateMaskResponse>('/reconstruction/initial-masks', {
      file_id: fileId,
      crop: cropData,
      rotation: rotation ?? 0,
      block_size: blockSize ?? 15,
      threshold_c: thresholdC ?? 10,
    });
    return data;
  },

  previewMask: async (fileId: string, crop?: CropRect | null, rotation?: number, blockSize?: number, thresholdC?: number): Promise<string> => {
    const cropData = crop ? { x: crop.x, y: crop.y, width: crop.width, height: crop.height } : null;
    const response = await apiClient.post(
      '/reconstruction/mask-preview',
      {
        file_id: fileId,
        crop: cropData,
        rotation: rotation ?? 0,
        block_size: blockSize ?? 15,
        threshold_c: thresholdC ?? 10,
      },
      { responseType: 'blob' },
    );
    return URL.createObjectURL(response.data);
  },
  
  calculateHough: async (planFileId: string, maskFileId: string) => {
    const response = await apiClient.post('/reconstruction/houghs', {
      plan_file_id: planFileId,
      user_mask_file_id: maskFileId,
    });
    return response.data;
  },
  
  calculateMesh: async (planFileId: string, maskFileId: string, rotationAngle: number = 0, cropRect: CropRect | null = null, rooms?: unknown[], doors?: unknown[]) => {
    const response = await apiClient.post('/reconstruction/reconstructions', {
      plan_file_id: planFileId,
      user_mask_file_id: maskFileId,
      rotation_angle: rotationAngle,
      crop_rect: cropRect ? { x: cropRect.x, y: cropRect.y, width: cropRect.width, height: cropRect.height } : null,
      rooms,
      doors,
    });
    return response.data;
  },
  
  getReconstructionById: async (id: number): Promise<ReconstructionResponse> => {
    const response = await apiClient.get<ReconstructionResponse>(`/reconstruction/reconstructions/${id}`);
    return response.data;
  },

  getReconstructionVectors: async (id: number): Promise<VectorizationResult> => {
    const response = await apiClient.get<VectorizationResult>(`/reconstruction/reconstructions/${id}/vectors`);
    return response.data;
  },

  updateVectorizationData: async (id: number, data: VectorizationResult): Promise<{ message: string }> => {
    const response = await apiClient.put<{ message: string }>(`/reconstruction/reconstructions/${id}/vectors`, data);
    return response.data;
  },
  
  getReconstructions: async (filters?: {
    floorId?: number;
    buildingCode?: string;
    unbound?: boolean;
    status?: number;
    search?: string;
  }): Promise<ReconstructionListItem[]> => {
    const params: Record<string, string> = {};
    if (filters?.floorId !== undefined) params['floor_id'] = String(filters.floorId);
    if (filters?.buildingCode !== undefined) params['building_code'] = filters.buildingCode;
    if (filters?.unbound !== undefined) params['unbound'] = String(filters.unbound);
    if (filters?.status !== undefined) params['status'] = String(filters.status);
    if (filters?.search !== undefined) params['search'] = filters.search;
    const response = await apiClient.get<ReconstructionListItem[]>('/reconstruction/reconstructions', { params });
    return response.data;
  },

  getReconstructionsByBuilding: async (buildingId: string): Promise<ReconstructionListItem[]> => {
    const response = await apiClient.get<ReconstructionListItem[]>(`/reconstruction/buildings/${buildingId}/reconstructions`);
    return response.data;
  },

  saveReconstruction: async (id: number, name: string, floorId: number): Promise<ReconstructionResponse> => {
    const response = await apiClient.put<ReconstructionResponse>(`/reconstruction/reconstructions/${id}/save`, {
      name,
      floor_id: floorId,
    });
    return response.data;
  },

  patchReconstructionFloor: async (id: number, floorId: number): Promise<ReconstructionResponse> => {
    const response = await apiClient.patch<ReconstructionResponse>(`/reconstruction/reconstructions/${id}`, {
      floor_id: floorId,
    });
    return response.data;
  },
  
  deleteReconstruction: async (id: number) => {
    await apiClient.delete(`/reconstruction/reconstructions/${id}`);
  },
  
  saveRooms: async (id: number, rooms: Array<{ number: string; x: number; y: number }>) => {
    await apiClient.put(`/reconstruction/reconstructions/${id}/rooms`, { rooms });
  },

  buildNavGraph: async (maskFileId: string, rooms: unknown[], doors: unknown[]) => {
    const response = await apiClient.post('/reconstruction/nav-graph', {
      mask_file_id: maskFileId,
      rooms,
      doors,
      scale_factor: 0.02,
    });
    return response.data;
  },

  getNavGraph: async (graphId: string) => {
    const response = await apiClient.get(`/reconstruction/nav-graph/${graphId}`);
    return response.data;
  },

  findRoute: async (
    graphId: string,
    fromRoomId: string,
    toRoomId: string,
  ): Promise<{
    status: string;
    from_room?: string;
    to_room?: string;
    total_distance_meters?: number;
    estimated_time_seconds?: number;
    coordinates?: number[][];
    message?: string;
    from_room_3d?: { position: [number, number, number]; size: [number, number, number] };
    to_room_3d?: { position: [number, number, number]; size: [number, number, number] };
  }> => {
    const res = await apiClient.post('/reconstruction/route', {
      graph_id: graphId,
      from_room_id: fromRoomId,
      to_room_id: toRoomId,
    });
    return res.data;
  },

  getReadyReconstructions: async (
    buildingCode?: string,
    floorId?: number,
  ): Promise<ReconstructionListItem[]> => {
    const params: Record<string, string> = { status: '2' }; // status=2 maps to ready_for_stitching
    if (buildingCode) params['building_code'] = buildingCode;
    if (floorId !== undefined) params['floor_id'] = String(floorId);

    const response = await apiClient.get<ReconstructionListItem[]>('/reconstruction/reconstructions', { params });
    return response.data;
  },

  postStitching: async (request: unknown) => {
    const response = await apiClient.post('/stitching/', request);
    return response.data;
  },
};

// === Navigation API ===

export const navigationApi = {
  buildRoute: async (startPoint: string, endPoint: string) => {
    const response = await apiClient.post('/navigation/route', {
      start_point: startPoint,
      end_point: endPoint,
    });
    return response.data;
  },

  multifloorRoute: (params: MultifloorRouteRequest): Promise<MultifloorRouteResponse> =>
    apiClient.post('/navigation/multifloor-route', params).then((r) => r.data as MultifloorRouteResponse),

  getRooms3D: async (graphId: string): Promise<Room3DApi[]> => {
    const response = await apiClient.get(`/navigation/graphs/${graphId}/rooms_3d`);
    return response.data as Room3DApi[];
  },
};

export interface Room3DApi {
  id: string;
  name: string;
  room_type: string;
  position: [number, number, number];
  size: [number, number, number];
  /** Y-axis rotation (radians) so the box matches a rotated section. 0/absent
   *  for the single-plan path (rooms there are never rotated). */
  rotation?: number;
}

export default apiClient;
