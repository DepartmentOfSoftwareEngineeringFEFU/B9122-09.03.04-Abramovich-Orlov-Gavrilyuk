// Building Assembly page (subfeature A — vertical floor stitching).
//
// Aligns each adjacent floor PAIR of a building. Guided flow: a numbered pair is
// "active"; the page asks the operator to mark that point on the LOWER floor,
// then the SAME point on the UPPER floor — one click each — then auto-advances to
// the next pair. Matching points carry the same number AND the same colour on
// both panels, so the correspondence is obvious; the right-hand list shows each
// pair as a low ●——● up connector. Solve composes every floor's transform into
// the building frame.
//
// All state/actions live in useBuildingAssembly; this page is presentational.
// The dual canvas reuses StitchPointCanvas (per-id colours via colourForId).

import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { X, Layers, Boxes, Box, Crosshair, Trash2 } from 'lucide-react';
import { StitchPointCanvas } from '../components/FloorEditor/StitchPointCanvas';
import { colourForId, pointLabel } from '../lib/controlPoints';
import {
  useBuildingAssembly,
  pairCompleteness,
  MIN_STITCH_PAIRS,
} from '../hooks/useBuildingAssembly';
import type { AssemblyFloor, AssemblyPairStatus } from '../types/buildingAssembly';
import styles from './BuildingAssemblyPage.module.css';

const PAIR_BADGE: Record<AssemblyPairStatus, { label: string; cls: string }> = {
  reference: { label: 'основание', cls: 'badgeRef' },
  ok: { label: '', cls: 'badgeOk' },
  needs_points: { label: `нужно ≥${MIN_STITCH_PAIRS} пары`, cls: 'badgeWarn' },
  unsolved: { label: 'не решено', cls: 'badgeNeutral' },
  no_mask: { label: 'нет маски', cls: 'badgeError' },
};

/** Residual in metres for a floor's solve result, guarded (never NaN/∞). */
const residualMetres = (residualM: number | null): string => {
  if (residualM === null || !Number.isFinite(residualM)) return '—';
  return `${residualM.toFixed(3)} м`;
};

export const BuildingAssemblyPage: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const buildingId = id !== undefined ? parseInt(id, 10) : NaN;

  const {
    isLoading,
    error,
    floors,
    referenceFloorId,
    selectedPair,
    upperPoints,
    lowerPoints,
    activePointId,
    guidedSide,
    solving,
    savingPair,
    result,
    solveEnabled,
    load,
    selectPair,
    setActivePoint,
    placeGuided,
    removePoint,
    savePair,
    solve,
  } = useBuildingAssembly();

  useEffect(() => {
    if (!Number.isNaN(buildingId)) void load(buildingId);
  }, [buildingId, load]);

  const floorById = useMemo(() => {
    const map = new Map<number, AssemblyFloor>();
    for (const f of floors) map.set(f.id, f);
    return map;
  }, [floors]);

  const lowerFloor = selectedPair ? floorById.get(selectedPair.lowerId) ?? null : null;
  const upperFloor = selectedPair ? floorById.get(selectedPair.upperId) ?? null : null;

  // Tool toggle (mirrors the section-stitch Step 6): «Поставить точку» = guided
  // placement, «Удалить точку» = click a marker on either floor to drop its pair.
  const [tool, setTool] = useState<'place' | 'delete'>('place');

  // Guided clicks: in place mode a click on a panel writes the CURRENT pair (the
  // active number) to that side; the hook advances once both sides are placed.
  const handleLowerPlace = useCallback(
    (_idFromCanvas: string, x: number, y: number) => {
      if (tool === 'place') placeGuided('lower', x, y);
    },
    [tool, placeGuided],
  );
  const handleUpperPlace = useCallback(
    (_idFromCanvas: string, x: number, y: number) => {
      if (tool === 'place') placeGuided('upper', x, y);
    },
    [tool, placeGuided],
  );
  // Clicking a marker: delete its pair (delete tool) or make it the active pair.
  const handleSelect = useCallback(
    (pointId: string) => {
      if (tool === 'delete') removePoint(pointId);
      else setActivePoint(pointId);
    },
    [tool, removePoint, setActivePoint],
  );

  // Pair rows for the side list: number, colour (same as on both canvases), and
  // which sides are placed — drawn as a low ●——● up connector.
  const pairRows = useMemo(() => {
    const lowerIds = new Set(lowerPoints.map((p) => p.id));
    const upperIds = new Set(upperPoints.map((p) => p.id));
    const ids = Array.from(new Set([...lowerIds, ...upperIds]));
    const numOf = (s: string): number => parseInt(/(\d+)/.exec(s)?.[1] ?? '0', 10);
    ids.sort((a, b) => numOf(a) - numOf(b));
    return ids.map((pid) => ({
      id: pid,
      label: pointLabel(pid),
      color: colourForId(pid),
      onLower: lowerIds.has(pid),
      onUpper: upperIds.has(pid),
    }));
  }, [lowerPoints, upperPoints]);

  const completeness = pairCompleteness(upperPoints, lowerPoints);
  const canSavePair = selectedPair !== null && completeness.paired > 0;

  const activeLabel = activePointId ? pointLabel(activePointId) : '';
  const guidedText =
    guidedSide === 'lower'
      ? `Отметьте точку ${activeLabel} на НИЖНЕМ этаже (этаж ${lowerFloor?.number ?? '—'}).`
      : guidedSide === 'upper'
        ? `Теперь та же точка ${activeLabel} — на ВЕРХНЕМ этаже (этаж ${upperFloor?.number ?? '—'}).`
        : `Точка ${activeLabel} стоит на обоих этажах. Кликните по этажу, чтобы её переставить, или выберите другую точку.`;

  const renderChain = () => {
    const ordered = [...floors].sort((a, b) => a.number - b.number);
    return (
      <div className={styles.chainList}>
        {ordered.map((floor) => {
          const isRef = floor.id === referenceFloorId || floor.pair_status === 'reference';
          const isActive = selectedPair?.upperId === floor.id;
          const badge = PAIR_BADGE[floor.pair_status];
          return (
            <button
              key={floor.id}
              type="button"
              className={[
                styles.floorItem,
                isActive ? styles.floorItemActive : '',
                isRef ? styles.floorItemReference : '',
              ]
                .filter(Boolean)
                .join(' ')}
              onClick={() => {
                if (!isRef) selectPair(floor.id);
              }}
              disabled={isRef}
            >
              <div className={styles.floorItemRow}>
                <span className={styles.floorName}>Этаж {floor.number}</span>
                {badge.label !== '' && (
                  <span className={`${styles.badge} ${styles[badge.cls]}`}>{badge.label}</span>
                )}
              </div>
              <div className={styles.floorItemRow}>
                <span className={styles.floorElevation}>
                  +{floor.elevation_m.toFixed(1)} м
                </span>
                {!isRef && (
                  <span className={styles.floorElevation}>
                    {floor.points_count} пар
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    );
  };

  if (Number.isNaN(buildingId)) {
    return (
      <div className={styles.page}>
        <div className={styles.darkHeader}>
          <span className={styles.darkHeaderLabel}>Сборка здания</span>
        </div>
        <div className={styles.centerState}>Некорректный идентификатор здания</div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.darkHeader}>
        <span className={styles.darkHeaderLabel}>
          Сборка здания — вертикальная стыковка этажей
        </span>
        <button
          className={styles.darkHeaderClose}
          type="button"
          onClick={() => navigate('/admin/buildings')}
          title="Закрыть"
        >
          <X size={20} />
        </button>
      </div>

      {isLoading ? (
        <div className={styles.centerState}>Загрузка сборки здания…</div>
      ) : error !== null && floors.length === 0 ? (
        <div className={styles.centerState}>{error}</div>
      ) : floors.length < 2 ? (
        <div className={styles.centerState}>
          <div className={styles.infoBox}>
            <Boxes size={48} className={styles.infoIcon} strokeWidth={1.25} />
            <h3 className={styles.infoTitle}>Недостаточно этажей</h3>
            <p className={styles.infoText}>
              Для вертикального сшивания нужно минимум два этажа
              {floors.length === 0
                ? ' — в этом корпусе пока нет этажей.'
                : ' — в этом корпусе пока только один этаж.'}{' '}
              Добавьте этажи и завершите их сборку, затем вернитесь сюда.
            </p>
            <button
              type="button"
              className={styles.infoBtn}
              onClick={() => navigate('/admin/buildings')}
            >
              <Layers size={16} /> Перейти к этажам
            </button>
          </div>
        </div>
      ) : (
        <div className={styles.body}>
          {/* Left: floor chain */}
          <aside className={styles.chainPanel}>
            <div className={styles.panelTitle}>Этажи</div>
            {floors.length === 0 ? (
              <div className={styles.gateHint}>Нет этажей</div>
            ) : (
              renderChain()
            )}
          </aside>

          {/* Center: dual anchor canvas */}
          <section className={styles.canvasPanel}>
            {selectedPair === null ? (
              <div className={styles.noPair}>
                Выберите верхний этаж слева, чтобы разметить его стыковку с этажом
                ниже.
              </div>
            ) : (
              <div className={styles.dualWrap}>
                {/* Lower (reference) — left */}
                <div className={styles.panelHalf}>
                  <div className={styles.panelHalfTitle}>
                    <Layers size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                    Этаж {lowerFloor?.number ?? '—'} · нижний
                  </div>
                  <div className={styles.canvasHost}>
                    <StitchPointCanvas
                      maskUrl={lowerFloor?.mask_url ?? null}
                      points={lowerPoints}
                      activeId={activePointId}
                      colorOf={colourForId}
                      tool={tool}
                      onPlace={handleLowerPlace}
                      onSelect={handleSelect}
                    />
                    {!lowerFloor?.mask_url && (
                      <div className={styles.canvasEmpty}>
                        У этажа {lowerFloor?.number ?? ''} ещё нет маски — завершите
                        сборку этого этажа.
                      </div>
                    )}
                  </div>
                </div>

                {/* Upper (moving) — right */}
                <div className={styles.panelHalf}>
                  <div className={styles.panelHalfTitle}>
                    <Layers size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                    Этаж {upperFloor?.number ?? '—'} · верхний (выравниваем)
                  </div>
                  <div className={styles.canvasHost}>
                    <StitchPointCanvas
                      maskUrl={upperFloor?.mask_url ?? null}
                      points={upperPoints}
                      activeId={activePointId}
                      colorOf={colourForId}
                      tool={tool}
                      onPlace={handleUpperPlace}
                      onSelect={handleSelect}
                    />
                    {!upperFloor?.mask_url && (
                      <div className={styles.canvasEmpty}>
                        У этажа {upperFloor?.number ?? ''} ещё нет маски — завершите
                        сборку этого этажа.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Right: guided steps + pairs + solve */}
          <aside className={styles.sidePanel}>
            <div className={styles.panelTitle}>Опорные точки</div>

            {error !== null && <div className={styles.errorBox}>{error}</div>}

            {selectedPair !== null && (
              <>
                <div className={styles.toolGroup}>
                  <button
                    type="button"
                    className={`${styles.toolBtn} ${tool === 'place' ? styles.toolBtnActive : ''}`}
                    onClick={() => setTool('place')}
                  >
                    <Crosshair size={16} /> Поставить точку
                  </button>
                  <button
                    type="button"
                    className={`${styles.toolBtn} ${tool === 'delete' ? styles.toolBtnActive : ''}`}
                    onClick={() => setTool('delete')}
                    disabled={pairRows.length === 0}
                  >
                    <Trash2 size={16} /> Удалить точку
                  </button>
                </div>

                {tool === 'delete' ? (
                  <div className={styles.guidedPrompt}>
                    <span>Кликните по точке на любом этаже — пара удалится целиком.</span>
                  </div>
                ) : (
                  <div
                    className={`${styles.guidedPrompt} ${
                      guidedSide === 'upper' ? styles.guidedUpper : styles.guidedLower
                    }`}
                  >
                    {activePointId && (
                      <span
                        className={styles.guidedDot}
                        style={{ background: colourForId(activePointId) }}
                      />
                    )}
                    <span>{guidedText}</span>
                  </div>
                )}

                <div className={styles.gateHint}>
                  Готовых пар: {completeness.paired} (нужно ≥{MIN_STITCH_PAIRS})
                  {completeness.complete ? ' ✓' : ''}. Отмечайте сквозные ориентиры —
                  угол лестничной клетки, общую несущую стену.
                </div>

                {pairRows.length > 0 && (
                  <div className={styles.pairList}>
                    <div className={styles.pairLegend}>
                      Пары — <span className={styles.legDot} /> низ ·{' '}
                      <span className={styles.legDot} /> верх
                    </div>
                    {pairRows.map((row) => {
                      const paired = row.onLower && row.onUpper;
                      const active = row.id === activePointId;
                      return (
                        <div
                          key={row.id}
                          className={`${styles.pairRow} ${active ? styles.pairRowActive : ''}`}
                        >
                          <button
                            type="button"
                            className={styles.pairSelect}
                            onClick={() => setActivePoint(row.id)}
                            title={
                              paired
                                ? `Пара ${row.label} — размечена`
                                : `Пара ${row.label} — не хватает точки на ${
                                    row.onLower ? 'верхнем' : 'нижнем'
                                  } этаже`
                            }
                          >
                            <span
                              className={styles.swatch}
                              style={{ background: row.color }}
                            />
                            <span className={styles.pairName}>Пара {row.label}</span>
                            <svg
                              className={styles.connSvg}
                              width="46"
                              height="14"
                              viewBox="0 0 46 14"
                              aria-hidden="true"
                            >
                              <line
                                x1="7"
                                y1="7"
                                x2="39"
                                y2="7"
                                stroke={paired ? row.color : '#d1d5db'}
                                strokeWidth="2"
                              />
                              <circle
                                cx="7"
                                cy="7"
                                r="5"
                                fill={row.onLower ? row.color : '#ffffff'}
                                stroke={row.onLower ? row.color : '#9ca3af'}
                                strokeWidth="1.5"
                              />
                              <circle
                                cx="39"
                                cy="7"
                                r="5"
                                fill={row.onUpper ? row.color : '#ffffff'}
                                stroke={row.onUpper ? row.color : '#9ca3af'}
                                strokeWidth="1.5"
                              />
                            </svg>
                          </button>
                          <button
                            type="button"
                            className={styles.pairDel}
                            title="Удалить пару с обоих этажей"
                            onClick={() => removePoint(row.id)}
                          >
                            ✕
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}

                <button
                  type="button"
                  className={styles.saveBtn}
                  onClick={() => void savePair()}
                  disabled={!canSavePair || savingPair}
                >
                  {savingPair ? 'Сохранение…' : 'Сохранить точки пары'}
                </button>
              </>
            )}

            <button
              type="button"
              className={styles.solveBtn}
              onClick={() => void solve()}
              disabled={!solveEnabled || solving}
            >
              {solving ? 'Расчёт…' : 'Собрать здание'}
            </button>
            {!solveEnabled && (
              <div className={styles.gateHint}>
                Чтобы собрать здание, сохраните ≥{MIN_STITCH_PAIRS} пар хотя бы для
                одного этажа над нижним.
              </div>
            )}

            <button
              type="button"
              className={styles.viewer3dBtn}
              onClick={() => navigate(`/admin/buildings/${buildingId}/scene`)}
            >
              <Box size={16} /> Открыть 3D
            </button>

            {result !== null && (
              <div className={styles.statusList}>
                {[...result.floors]
                  .sort((a, b) => b.number - a.number)
                  .map((f) => {
                    const badge = PAIR_BADGE[
                      f.status === 'degenerate' ? 'needs_points' : f.status
                    ];
                    return (
                      <div key={f.floor_id} className={styles.statusRow}>
                        <span className={styles.statusName}>Этаж {f.number}</span>
                        {(f.status === 'degenerate' || badge.label !== '') && (
                          <span className={`${styles.badge} ${styles[badge.cls]}`}>
                            {f.status === 'degenerate' ? 'вырождено' : badge.label}
                          </span>
                        )}
                        <span className={styles.statusResidual}>
                          {residualMetres(f.residual_rms_m)}
                        </span>
                      </div>
                    );
                  })}
              </div>
            )}

          </aside>
        </div>
      )}
    </div>
  );
};

export default BuildingAssemblyPage;
