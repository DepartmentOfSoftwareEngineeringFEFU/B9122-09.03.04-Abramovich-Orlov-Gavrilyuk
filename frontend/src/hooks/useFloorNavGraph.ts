// State + actions for the floor navigation graph (Part B): build the graph from
// the assembled floor, find a route between two rooms, and load room 3D boxes.
//
// Mirrors useFloorAssembly's shape (all logic here, presentational components just
// render). The route + room overlays are drawn by reusing the existing
// NavigationPath / MeshViewer rooms3D — this hook only owns the data + requests.

import { useState, useCallback } from 'react';
import { floorNavApi } from '../api/floorNavApi';
import type { FloorGraphMeta, FloorRouteResponse } from '../api/floorNavApi';
import type { Room3DApi } from '../api/apiService';
import { toastApi } from './useToast';

export interface UseFloorNavGraphReturn {
  isBuilding: boolean;
  isRouting: boolean;
  graphMeta: FloorGraphMeta | null;
  routeResult: FloorRouteResponse | null;
  rooms3d: Room3DApi[];
  error: string | null;
  buildFloorGraph: (floorId: number) => Promise<void>;
  findRoute: (floorId: number, fromRoom: string, toRoom: string) => Promise<void>;
  loadRooms3d: (floorId: number) => Promise<void>;
  clearRoute: () => void;
}

/**
 * Best-effort error message: prefer the backend `detail` (FastAPI HTTPException),
 * else the Error message, else a fallback. Pure type guards — no `any`.
 */
const errorMessage = (err: unknown, fallback: string): string => {
  if (err && typeof err === 'object' && 'response' in err) {
    const response = (err as { response?: unknown }).response;
    if (response && typeof response === 'object' && 'data' in response) {
      const data = (response as { data?: unknown }).data;
      if (data && typeof data === 'object' && 'detail' in data) {
        const detail = (data as { detail?: unknown }).detail;
        if (typeof detail === 'string') return detail;
      }
    }
  }
  if (err instanceof Error) return err.message;
  return fallback;
};

export const useFloorNavGraph = (): UseFloorNavGraphReturn => {
  const [isBuilding, setIsBuilding] = useState(false);
  const [isRouting, setIsRouting] = useState(false);
  const [graphMeta, setGraphMeta] = useState<FloorGraphMeta | null>(null);
  const [routeResult, setRouteResult] = useState<FloorRouteResponse | null>(null);
  const [rooms3d, setRooms3d] = useState<Room3DApi[]>([]);
  const [error, setError] = useState<string | null>(null);

  const buildFloorGraph = useCallback(async (floorId: number) => {
    setIsBuilding(true);
    setError(null);
    try {
      const meta = await floorNavApi.buildFloorGraph(floorId);
      setGraphMeta(meta);
      // 200 with no corridors is a valid build, but routing will find no path —
      // warn the operator instead of silently succeeding (ADR edge case).
      if (meta.corridor_nodes_count === 0) {
        toastApi.error(
          'Граф построен без коридоров — маршруты не найдутся. Проверьте переходы.',
        );
      } else {
        toastApi.success(`Граф построен: ${meta.rooms_count} кабинетов`);
      }
      const res = await floorNavApi.getFloorRooms3D(floorId);
      setRooms3d(res.rooms);
    } catch (e) {
      const msg = errorMessage(e, 'Ошибка построения графа');
      setError(msg);
      toastApi.error(msg);
    } finally {
      setIsBuilding(false);
    }
  }, []);

  const findRoute = useCallback(
    async (floorId: number, from: string, to: string) => {
      setIsRouting(true);
      setError(null);
      try {
        const res = await floorNavApi.getFloorRoute(floorId, from, to);
        setRouteResult(res);
        if (res.status === 'no_path') toastApi.error('Маршрут не найден');
      } catch (e) {
        const msg = errorMessage(e, 'Ошибка поиска маршрута');
        setError(msg);
        toastApi.error(msg);
      } finally {
        setIsRouting(false);
      }
    },
    [],
  );

  const loadRooms3d = useCallback(async (floorId: number) => {
    try {
      const res = await floorNavApi.getFloorRooms3D(floorId);
      setRooms3d(res.rooms);
    } catch {
      /* optional overlay — silent */
    }
  }, []);

  const clearRoute = useCallback(() => setRouteResult(null), []);

  return {
    isBuilding,
    isRouting,
    graphMeta,
    routeResult,
    rooms3d,
    error,
    buildFloorGraph,
    findRoute,
    loadRooms3d,
    clearRoute,
  };
};
