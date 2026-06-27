// Step 9: build a PREVIEW of the stitched floor mesh, inspect it in 3D,
// then explicitly persist it. Build is preview-only: "Построить"
// produces a preview GLB the operator reviews; "Сохранить этаж" confirms that
// exact preview into floors.mesh_file_glb. An unconfirmed rebuild never clobbers
// a good saved floor.
//
// The preview GLB is loaded by passing the build response's glb_url DIRECTLY to
// MeshViewer (url + format="glb"). We deliberately do NOT use useMeshViewer —
// that hook fetches a *reconstruction* by integer id and cannot load a preview
// GLB by url.
//
// The НАВИГАЦИЯ panel finds a route between two rooms using the graph built on the
// previous step (Step9NavGraph); the route renders as a NavigationPath child of the
// MeshViewer (R3F), and room boxes via MeshViewer's existing rooms3D prop.
//
// Presentational only — build/confirm state lives in useFloorAssembly; the nav
// state lives in useFloorNavGraph.

import React, { useState, useEffect } from 'react';
import MeshViewer from '../MeshViewer';
import { NavigationPath } from '../MeshViewer/NavigationPath';
import { useFloorNavGraph } from '../../hooks/useFloorNavGraph';
import type { BuildFloorPreviewResponse } from '../../types/floorAssembly';
import wizardStyles from './WizardStep.module.css';
import styles from './Step9FloorPreview.module.css';

interface Step9FloorPreviewProps {
  previewGlbUrl: string | null;
  buildResult: BuildFloorPreviewResponse | null;
  meshFileGlb: string | null;
  isBuilding: boolean;
  isConfirming: boolean;
  onBuild: () => Promise<void>;
  onConfirm: () => Promise<void>;
  onBack: () => void;
  /** Floor whose nav graph the НАВИГАЦИЯ panel operates on (null disables it). */
  floorId: number | null;
}

export const Step9FloorPreview: React.FC<Step9FloorPreviewProps> = ({
  previewGlbUrl,
  buildResult,
  meshFileGlb,
  isBuilding,
  isConfirming,
  onBuild,
  onConfirm,
  onBack,
  floorId,
}) => {
  const excluded = buildResult?.excluded_sections ?? [];
  const warnings = buildResult?.warnings ?? [];

  const nav = useFloorNavGraph();
  const [fromRoom, setFromRoom] = useState('');
  const [toRoom, setToRoom] = useState('');

  // Load room boxes for the overlay once the floor is known. The graph itself is
  // built on demand via the «Построить граф навигации» button.
  useEffect(() => {
    if (floorId !== null) void nav.loadRooms3d(floorId);
  }, [floorId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Endpoint boxes for the NavigationPath highlight (optional — from rooms3d).
  const fromRoom3D = nav.rooms3d.find((r) => r.id === fromRoom);
  const toRoom3D = nav.rooms3d.find((r) => r.id === toRoom);

  return (
    <div className={wizardStyles.layout}>
      <div className={styles.body}>
        {/* Center — 3D preview of the stitched floor + route overlay */}
        <div className={styles.viewerPanel}>
          {previewGlbUrl ? (
            // PREVIEW GLB url straight from buildFloorMesh — not useMeshViewer.
            <MeshViewer
              url={previewGlbUrl}
              format="glb"
              rooms3D={nav.rooms3d}
              showRooms={nav.rooms3d.length > 0}
            >
              {nav.routeResult?.status === 'found' && (
                <NavigationPath
                  coordinates={nav.routeResult.path_3d}
                  fromRoom3D={
                    fromRoom3D
                      ? {
                          position: fromRoom3D.position,
                          size: fromRoom3D.size,
                          rotation: fromRoom3D.rotation,
                        }
                      : undefined
                  }
                  toRoom3D={
                    toRoom3D
                      ? {
                          position: toRoom3D.position,
                          size: toRoom3D.size,
                          rotation: toRoom3D.rotation,
                        }
                      : undefined
                  }
                  fromRoomName={fromRoom3D?.name}
                  toRoomName={toRoom3D?.name}
                />
              )}
            </MeshViewer>
          ) : (
            <div className={styles.viewerEmpty}>
              {isBuilding
                ? 'Сборка превью этажа…'
                : 'Нажмите «Построить», чтобы собрать превью этажа'}
            </div>
          )}
        </div>

        {/* Right panel — build/confirm + notices + navigation */}
        <aside className={styles.panel}>
          <div className={styles.panelTitle}>СБОРКА ЭТАЖА</div>

          <button
            type="button"
            className={styles.buildBtn}
            onClick={() => void onBuild()}
            disabled={isBuilding}
          >
            {isBuilding ? 'Сборка…' : previewGlbUrl ? 'Пересобрать' : 'Построить'}
          </button>

          {buildResult && (
            <div className={styles.infoBlock}>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>Включено отсеков</span>
                <span className={styles.infoValue}>
                  {buildResult.included_sections.length}
                </span>
              </div>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>Переходов</span>
                <span className={styles.infoValue}>{buildResult.connector_count}</span>
              </div>
            </div>
          )}

          {excluded.length > 0 && (
            <div className={styles.notice}>
              <div className={styles.noticeTitle}>Исключены из сборки</div>
              <ul className={styles.noticeList}>
                {excluded.map((e) => (
                  <li key={e.section_id}>
                    Отсек #{e.section_id} — {e.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {warnings.length > 0 && (
            <div className={styles.warning}>
              <div className={styles.warningTitle}>Предупреждения</div>
              <ul className={styles.noticeList}>
                {warnings.map((w, i) => (
                  <li key={`${w.section_id}-${i}`}>{w.message}</li>
                ))}
              </ul>
            </div>
          )}

          {meshFileGlb && (
            <div className={styles.savedBadge}>
              Сохранённый этаж: {meshFileGlb}
            </div>
          )}

          <button
            type="button"
            className={styles.confirmBtn}
            onClick={() => void onConfirm()}
            disabled={isConfirming || buildResult === null}
            title={
              buildResult === null
                ? 'Сначала постройте превью'
                : 'Сохранить собранный этаж'
            }
          >
            {isConfirming ? 'Сохранение…' : 'Сохранить этаж'}
          </button>

          {/* НАВИГАЦИЯ */}
          {/* The graph is built on the previous step (Step9NavGraph); here we rely
              on server-persisted state — rooms load on mount via loadRooms3d. */}
          <section className={styles.navPanel}>
            <div className={styles.panelTitle}>НАВИГАЦИЯ</div>

            {nav.rooms3d.length === 0 && (
              <div className={styles.navHint}>
                Постройте граф навигации на предыдущем шаге
              </div>
            )}

            {nav.rooms3d.length > 0 && (
              <>
                <div className={styles.infoBlock}>
                  <div className={styles.infoRow}>
                    <span className={styles.infoLabel}>Кабинетов</span>
                    <span className={styles.infoValue}>
                      {nav.rooms3d.length}
                    </span>
                  </div>
                </div>

                <select
                  className={styles.navSelect}
                  value={fromRoom}
                  onChange={(e) => setFromRoom(e.target.value)}
                >
                  <option value="">— Откуда —</option>
                  {nav.rooms3d.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name || r.id}
                    </option>
                  ))}
                </select>

                <select
                  className={styles.navSelect}
                  value={toRoom}
                  onChange={(e) => setToRoom(e.target.value)}
                >
                  <option value="">— Куда —</option>
                  {nav.rooms3d.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name || r.id}
                    </option>
                  ))}
                </select>

                <button
                  type="button"
                  className={styles.buildBtn}
                  onClick={() =>
                    floorId !== null && void nav.findRoute(floorId, fromRoom, toRoom)
                  }
                  disabled={
                    floorId === null || nav.isRouting || !fromRoom || !toRoom
                  }
                >
                  {nav.isRouting ? 'Ищу…' : 'Найти маршрут'}
                </button>

                {nav.routeResult?.status === 'found' &&
                  nav.routeResult.total_distance_m !== null && (
                    <div className={styles.infoBlock}>
                      <div className={styles.infoRow}>
                        <span className={styles.infoLabel}>Длина</span>
                        <span className={styles.infoValue}>
                          {nav.routeResult.total_distance_m.toFixed(1)} м
                        </span>
                      </div>
                    </div>
                  )}
              </>
            )}
          </section>
        </aside>
      </div>

      <footer className={wizardStyles.footer}>
        <button className={wizardStyles.btnBack} onClick={onBack} type="button">
          ← Назад
        </button>
        <span className={wizardStyles.footerHint}>
          Превью не сохраняется автоматически — нажмите «Сохранить этаж»
        </span>
        <span />
      </footer>
    </div>
  );
};
