// State for the stacked 3D building viewer (subfeature B). One
// GET /buildings/{id}/scene-3d gives every floor's GLB url + 3D placement; the
// hook also owns the per-floor visibility set. All decision logic lives in the
// pure helpers below (unit-tested in the node vitest env); the hook is a thin
// shell. No `any`.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { buildingSceneApi } from '../api/buildingSceneApi';
import { floorNavApi } from '../api/floorNavApi';
import type { Room3DApi } from '../api/apiService';
import type { BuildingScene3DResponse, SceneFloor } from '../types/buildingScene';

// Pure helpers

/** A floor is drawable only if it has a mesh AND a solved placement. */
export const isRenderable = (f: SceneFloor): boolean =>
  f.has_mesh && f.placement !== null;

/** Default visibility = every renderable floor shown. */
export const defaultVisible = (floors: readonly SceneFloor[]): Set<number> =>
  new Set(floors.filter(isRenderable).map((f) => f.floor_id));

/** Toggle one floor id in/out of a visibility set (returns a NEW set, no mutation). */
export const toggleVisible = (set: ReadonlySet<number>, id: number): Set<number> => {
  const next = new Set(set);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
};

/** The floors actually drawn: renderable AND currently visible. */
export const visibleRenderable = (
  floors: readonly SceneFloor[],
  visible: ReadonlySet<number>,
): SceneFloor[] =>
  floors.filter((f) => isRenderable(f) && visible.has(f.floor_id));

/**
 * Side-list label (derived frontend-side, keeps B decoupled from A's pair_status):
 * reference → «эталон»; no mesh → «нет 3D-модели»; mesh but no placement →
 * «не выровнен»; otherwise «в стопке».
 */
export const sideLabel = (
  f: SceneFloor,
  referenceFloorId: number | null,
): string => {
  if (f.floor_id === referenceFloorId) return 'эталон';
  if (!f.has_mesh) return 'нет 3D-модели';
  if (f.placement === null) return 'не выровнен';
  return 'в стопке';
};

// Hook

export interface UseBuildingSceneReturn {
  scene: BuildingScene3DResponse | null;
  isLoading: boolean;
  error: string | null;
  /** Visible floor ids (client-only view state). */
  visible: Set<number>;
  /** Show/hide one floor. */
  toggle: (floorId: number) => void;
  /** Replace the visible set with a single floor (e.g. jump to the route start). */
  showOnly: (floorId: number) => void;
  /** (Re)fetch the scene — call when opening the viewer to pick up a fresh solve. */
  reload: () => Promise<void>;
  /** Floors to draw right now (renderable ∧ visible). */
  renderable: SceneFloor[];
  /** Per-floor room boxes (for labels); empty for floors with no built nav graph. */
  roomsByFloor: Record<number, Room3DApi[]>;
}

export const useBuildingScene = (
  buildingId: number | null,
): UseBuildingSceneReturn => {
  const [scene, setScene] = useState<BuildingScene3DResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState<Set<number>>(new Set());
  const [roomsByFloor, setRoomsByFloor] = useState<Record<number, Room3DApi[]>>({});

  const reload = useCallback(async (): Promise<void> => {
    if (buildingId === null || Number.isNaN(buildingId)) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await buildingSceneApi.getScene3d(buildingId);
      setScene(data);
      setVisible(defaultVisible(data.floors));
      // Prefetch room labels per renderable floor (best-effort; the viewer shows
      // labels for the top floor only). A per-floor failure → that floor has none.
      const entries = await Promise.all(
        data.floors.filter(isRenderable).map((f) =>
          floorNavApi
            .getFloorRooms3D(f.floor_id)
            .then((r) => [f.floor_id, r.rooms] as const)
            .catch(() => [f.floor_id, [] as Room3DApi[]] as const),
        ),
      );
      setRoomsByFloor(Object.fromEntries(entries));
    } catch {
      setError('Ошибка загрузки 3D-сцены здания');
    } finally {
      setIsLoading(false);
    }
  }, [buildingId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const toggle = useCallback((floorId: number): void => {
    setVisible((prev) => toggleVisible(prev, floorId));
  }, []);

  const showOnly = useCallback((floorId: number): void => {
    setVisible(new Set([floorId]));
  }, []);

  const renderable = useMemo(
    () => (scene ? visibleRenderable(scene.floors, visible) : []),
    [scene, visible],
  );

  return {
    scene,
    isLoading,
    error,
    visible,
    toggle,
    showOnly,
    reload,
    renderable,
    roomsByFloor,
  };
};
