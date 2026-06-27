import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { reconstructionApi, navigationApi } from '../api/apiService';
import type { MultifloorRouteResponse, PathSegment3D } from '../types/transitions';
import type { RoomAnnotation } from '../types/wizard';
import {
  buildRoomRegistry,
  parseSyntheticId,
  planRoute,
  registryToAnnotations,
  type ReconstructionVectorsBundle,
  type RoomEntry,
} from './useRouteTest.helpers';

interface UseRouteTestReturn {
  isLoadingRegistry: boolean;
  isRouting: boolean;
  error: string | null;

  rooms: RoomAnnotation[];

  fromRoom: string;
  toRoom: string;
  setFromRoom: (id: string) => void;
  setToRoom: (id: string) => void;

  /** Mesh URL of the currently displayed floor (segment-aware). */
  currentMeshUrl: string | null;

  invalidPairReason: string | null;
  routeResult: MultifloorRouteResponse | null;

  /** Index of the currently displayed segment within routeResult.path_segments. */
  currentSegmentIndex: number;
  /** Convenience: the current segment object, or null. */
  currentSegment: PathSegment3D | null;
  setCurrentSegmentIndex: (idx: number) => void;
  goToNextSegment: () => void;
  goToPrevSegment: () => void;

  findRoute: () => void;
}

export const useRouteTest = (): UseRouteTestReturn => {
  const [registry, setRegistry] = useState<RoomEntry[]>([]);
  const [meshUrlByRecon, setMeshUrlByRecon] = useState<Map<number, string>>(
    new Map(),
  );
  const [isLoadingRegistry, setIsLoadingRegistry] = useState(true);
  const [isRouting, setIsRouting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [fromRoom, setFromRoomState] = useState<string>('');
  const [toRoom, setToRoomState] = useState<string>('');
  const [routeResult, setRouteResult] = useState<MultifloorRouteResponse | null>(
    null,
  );
  const [invalidPairReason, setInvalidPairReason] = useState<string | null>(null);
  const [currentSegmentIndex, setCurrentSegmentIndexState] = useState(0);

  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // 1. Load registry on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setIsLoadingRegistry(true);
        const reconstructions = await reconstructionApi.getReconstructions();
        if (cancelled || !mountedRef.current) return;

        const vectorResults = await Promise.allSettled(
          reconstructions.map((r) =>
            reconstructionApi
              .getReconstructionVectors(r.id)
              .then((v) => ({ id: r.id, rooms: v.rooms })),
          ),
        );
        if (cancelled || !mountedRef.current) return;

        const bundles: ReconstructionVectorsBundle[] = [];
        for (let i = 0; i < reconstructions.length; i++) {
          const r = reconstructions[i];
          const v = vectorResults[i];
          if (v.status === 'fulfilled' && v.value.rooms.length > 0) {
            bundles.push({ reconstruction: r, rooms: v.value.rooms });
          }
        }
        setRegistry(buildRoomRegistry(bundles));
      } catch {
        if (!mountedRef.current) return;
        setError('Ошибка загрузки списка комнат');
      } finally {
        if (mountedRef.current) setIsLoadingRegistry(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // 2. Fetch mesh URL for an arbitrary recon, cached
  const ensureMeshUrl = useCallback(
    async (reconId: number): Promise<void> => {
      // Read latest map via setState callback to avoid stale closures.
      let alreadyKnown = false;
      setMeshUrlByRecon((prev) => {
        if (prev.has(reconId)) alreadyKnown = true;
        return prev;
      });
      if (alreadyKnown) return;
      try {
        const data = await reconstructionApi.getReconstructionById(reconId);
        if (!mountedRef.current) return;
        if (data.url) {
          setMeshUrlByRecon((prev) => {
            if (prev.has(reconId)) return prev;
            const next = new Map(prev);
            next.set(reconId, data.url as string);
            return next;
          });
        }
      } catch {
        // Silent — UI shows placeholder if URL absent.
      }
    },
    [],
  );

  // 3. When fromRoom changes — preload mesh URL for from-floor
  const fromReconId = parseSyntheticId(fromRoom)?.reconId ?? null;
  useEffect(() => {
    if (fromReconId == null) return;
    void ensureMeshUrl(fromReconId);
  }, [fromReconId, ensureMeshUrl]);

  // 4. When routeResult changes — reset segment index, preload meshes
  useEffect(() => {
    setCurrentSegmentIndexState(0);
    if (!routeResult || routeResult.status !== 'success') return;
    for (const seg of routeResult.path_segments ?? []) {
      void ensureMeshUrl(seg.reconstruction_id);
    }
  }, [routeResult, ensureMeshUrl]);

  // 5. Selection setters clear stale results
  const setFromRoom = useCallback((id: string) => {
    setFromRoomState(id);
    setRouteResult(null);
    setInvalidPairReason(null);
  }, []);
  const setToRoom = useCallback((id: string) => {
    setToRoomState(id);
    setRouteResult(null);
    setInvalidPairReason(null);
  }, []);

  // 6. Find route
  const routeTokenRef = useRef(0);
  const findRoute = useCallback(() => {
    setInvalidPairReason(null);
    if (!fromRoom || !toRoom) return;

    const plan = planRoute(registry, fromRoom, toRoom);
    if (!plan.valid || !plan.fromEntry || !plan.toEntry) {
      setRouteResult(null);
      setInvalidPairReason(plan.reason ?? 'Невалидная пара комнат');
      return;
    }
    const buildingId = plan.fromEntry.buildingId;
    if (!buildingId) {
      setRouteResult(null);
      setInvalidPairReason('У этажа не указано здание');
      return;
    }

    const token = ++routeTokenRef.current;
    setIsRouting(true);
    setError(null);
    setRouteResult(null);

    navigationApi
      .multifloorRoute({
        building_id: buildingId,
        from_reconstruction_id: plan.fromEntry.reconstructionId,
        from_room_id: plan.fromEntry.realRoomId,
        to_reconstruction_id: plan.toEntry.reconstructionId,
        to_room_id: plan.toEntry.realRoomId,
      })
      .then((res) => {
        if (token !== routeTokenRef.current || !mountedRef.current) return;
        setRouteResult(res);
        setIsRouting(false);
      })
      .catch(() => {
        if (token !== routeTokenRef.current || !mountedRef.current) return;
        setError('Ошибка запроса маршрута');
        setIsRouting(false);
      });
  }, [registry, fromRoom, toRoom]);

  // 7. Segment navigation
  const setCurrentSegmentIndex = useCallback(
    (idx: number) => {
      const total = routeResult?.path_segments?.length ?? 0;
      if (idx < 0 || idx >= total) return;
      setCurrentSegmentIndexState(idx);
    },
    [routeResult],
  );
  const goToNextSegment = useCallback(() => {
    const total = routeResult?.path_segments?.length ?? 0;
    setCurrentSegmentIndexState((prev) =>
      Math.min(prev + 1, Math.max(0, total - 1)),
    );
  }, [routeResult]);
  const goToPrevSegment = useCallback(() => {
    setCurrentSegmentIndexState((prev) => Math.max(prev - 1, 0));
  }, []);

  // 8. Derived values
  const rooms = useMemo(() => registryToAnnotations(registry), [registry]);

  const currentSegment: PathSegment3D | null = useMemo(() => {
    if (!routeResult || routeResult.status !== 'success') return null;
    const segs = routeResult.path_segments ?? [];
    return segs[currentSegmentIndex] ?? null;
  }, [routeResult, currentSegmentIndex]);

  const currentMeshUrl: string | null = useMemo(() => {
    // While routed: show mesh of the current segment's reconstruction.
    if (currentSegment) {
      return meshUrlByRecon.get(currentSegment.reconstruction_id) ?? null;
    }
    // Idle: preview the from-floor for context.
    if (fromReconId != null) {
      return meshUrlByRecon.get(fromReconId) ?? null;
    }
    return null;
  }, [currentSegment, fromReconId, meshUrlByRecon]);

  return {
    isLoadingRegistry,
    isRouting,
    error,
    rooms,
    fromRoom,
    toRoom,
    setFromRoom,
    setToRoom,
    currentMeshUrl,
    invalidPairReason,
    routeResult,
    currentSegmentIndex,
    currentSegment,
    setCurrentSegmentIndex,
    goToNextSegment,
    goToPrevSegment,
    findRoute,
  };
};
