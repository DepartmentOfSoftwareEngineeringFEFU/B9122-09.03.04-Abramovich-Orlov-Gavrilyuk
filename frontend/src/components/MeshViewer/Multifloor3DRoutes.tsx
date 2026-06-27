// Reusable cross-floor 3D routes view (subfeature D). Composes B's stacked
// BuildingMeshViewer with the route polyline + the route-building panel + a
// per-floor visibility checklist. Self-contained behind a single `buildingId`
// prop so it can drop into the admin page AND the end-user start screen.
//
// The route is computed on the FULL building graph (backend) and rendered as a
// standalone scene object, so hiding floors here never changes or breaks it.

import React, { useCallback, useRef, useState } from 'react';
import { useBuildingScene } from '../../hooks/useBuildingScene';
import { BuildingMeshViewer, type BuildingMeshViewerHandle } from '../BuildingMeshViewer';
import { ZoomControls } from '../FloorViewer/ZoomControls';
import { MultifloorRoutePanel } from './MultifloorRoutePanel';
import { activeStairLabels } from './multifloorRoutePath.helpers';
import type { MultifloorRouteResponse } from '../../types/buildingNav';
import styles from './Multifloor3DRoutes.module.css';

export interface Multifloor3DRoutesProps {
  buildingId: number;
  /** Optional: jump to the building-assembly editor (shown on not_aligned). */
  onGoToAssembly?: () => void;
}

export const Multifloor3DRoutes: React.FC<Multifloor3DRoutesProps> = ({
  buildingId,
  onGoToAssembly,
}) => {
  const {
    scene,
    isLoading,
    error,
    renderable,
    roomsByFloor,
    visible,
    toggle,
    showOnly,
  } = useBuildingScene(buildingId);
  const [result, setResult] = useState<MultifloorRouteResponse | null>(null);
  const viewerRef = useRef<BuildingMeshViewerHandle>(null);

  // On a fresh successful route, switch the view to the START floor (the «Откуда»
  // room's floor = the first segment's floor) so the user immediately sees where
  // the path begins. The other route floors stay toggleable in «Слои».
  const handleResult = useCallback(
    (res: MultifloorRouteResponse | null): void => {
      setResult(res);
      if (res && res.status === 'success' && res.path_segments.length > 0) {
        showOnly(res.path_segments[0].floor_id);
      }
    },
    [showOnly],
  );

  if (isLoading) {
    return <div className={styles.note}>Загрузка 3D-сцены…</div>;
  }
  if (error) {
    return <div className={styles.note}>{error}</div>;
  }
  if (!scene || scene.floors.length === 0) {
    return <div className={styles.note}>В здании нет этажей.</div>;
  }

  const floorOptions = scene.floors.map((f) => ({
    floor_id: f.floor_id,
    number: f.number,
  }));
  const isSuccess = result !== null && result.status === 'success';
  // Floors the current route passes through (drives each layer's status text).
  const routeFloorIds = new Set<number>(
    isSuccess ? result.path_segments.map((s) => s.floor_id) : [],
  );
  // Draw a floor's route line ONLY while that floor is shown — hiding a floor
  // hides its segment too (a transition needs BOTH its floors visible).
  const segments = isSuccess
    ? result.path_segments.filter((s) => visible.has(s.floor_id))
    : [];
  const transitions = isSuccess
    ? result.transitions_used.filter(
        (t) => visible.has(t.from_floor_id) && visible.has(t.to_floor_id),
      )
    : [];
  // Stair/lift icons the route uses → orange highlight; a DEPARTURE shaft also
  // shows the floor it leads to («11 этаж»). Keyed by room id from ALL transitions
  // (not the visibility-filtered ones), so the icon labels work on whatever floor
  // is currently shown.
  const floorNumberById = new Map(scene.floors.map((f) => [f.floor_id, f.number]));
  const activeStairs = isSuccess
    ? activeStairLabels(result.transitions_used, floorNumberById)
    : new Map<string, number | null>();

  // Floors shown high → low so the pill order matches the visual stack.
  const orderedFloors = [...scene.floors].sort((a, b) => b.number - a.number);

  return (
    <div className={styles.wrap}>
      {/* Left: white controls panel (mirrors FloorViewer) */}
      <aside className={styles.panel}>
        <MultifloorRoutePanel
          buildingId={buildingId}
          floors={floorOptions}
          roomsByFloor={roomsByFloor}
          onResult={handleResult}
          onGoToAssembly={onGoToAssembly}
        />
        <div className={styles.layers}>
          <div className={styles.layersTitle}>Слои</div>
          <div className={styles.layerList}>
            {orderedFloors.map((f) => {
              const drawable = f.has_mesh && f.placement !== null;
              const shown = drawable && visible.has(f.floor_id);
              const onRoute = routeFloorIds.has(f.floor_id);
              return (
                <label
                  key={f.floor_id}
                  className={`${styles.layerRow}${drawable ? '' : ` ${styles.layerRowDisabled}`}`}
                  title={
                    drawable
                      ? `Этаж ${f.number} — показать/скрыть`
                      : `Этаж ${f.number} — нет 3D-модели`
                  }
                >
                  <input
                    type="checkbox"
                    className={styles.layerCheck}
                    checked={shown}
                    disabled={!drawable}
                    onChange={() => toggle(f.floor_id)}
                  />
                  <span className={styles.layerNum}>{f.number}</span>
                  <span
                    className={`${styles.layerStatus}${onRoute ? ` ${styles.layerStatusOn}` : ''}`}
                  >
                    {onRoute ? 'Маршрут проходит' : 'Нет на маршруте'}
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      </aside>

      {/* Right: big 3D viewer (model left untouched) */}
      <div className={styles.viewer}>
        <BuildingMeshViewer
          ref={viewerRef}
          floors={renderable}
          roomsByFloor={roomsByFloor}
          routeSegments={segments}
          routeTransitions={transitions}
          activeStairs={activeStairs}
        />
        {/* Zoom controls anchored mid-right of the 3D area (square, no rounding). */}
        <ZoomControls
          onZoomIn={() => viewerRef.current?.zoomIn()}
          onZoomOut={() => viewerRef.current?.zoomOut()}
        />
      </div>
    </div>
  );
};

export default Multifloor3DRoutes;
