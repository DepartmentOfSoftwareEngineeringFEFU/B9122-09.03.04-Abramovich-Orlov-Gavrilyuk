import { describe, it, expect, vi } from 'vitest';

vi.mock('./apiService', () => ({
  default: {
    post: vi.fn().mockResolvedValue({ data: { floor_id: 1, rooms_count: 3 } }),
    get: vi.fn().mockResolvedValue({ data: { floor_id: 1, rooms: [] } }),
  },
}));

import apiClient from './apiService';
import { floorNavApi } from './floorNavApi';

describe('floorNavApi', () => {
  it('buildFloorGraph unwraps response.data', async () => {
    const meta = await floorNavApi.buildFloorGraph(1);
    expect(meta.rooms_count).toBe(3);
    expect(apiClient.post).toHaveBeenCalledWith('/floors/1/build-floor-graph');
  });

  it('getFloorRoute passes from/to as query params', async () => {
    await floorNavApi.getFloorRoute(1, 'a', 'b');
    expect(apiClient.get).toHaveBeenCalledWith(
      '/floors/1/route',
      { params: { from_room: 'a', to_room: 'b' } },
    );
  });

  it('getFloorRooms3D unwraps response.data', async () => {
    const res = await floorNavApi.getFloorRooms3D(1);
    expect(res.floor_id).toBe(1);
    expect(res.rooms).toEqual([]);
    expect(apiClient.get).toHaveBeenCalledWith('/floors/1/rooms-3d');
  });

  it('getNavGraph2d hits the nav-graph-2d endpoint and unwraps response.data', async () => {
    await floorNavApi.getNavGraph2d(1);
    expect(apiClient.get).toHaveBeenCalledWith('/floors/1/nav-graph-2d');
  });
});
