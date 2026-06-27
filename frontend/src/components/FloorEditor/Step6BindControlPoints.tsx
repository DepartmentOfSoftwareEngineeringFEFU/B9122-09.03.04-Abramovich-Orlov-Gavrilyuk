// Step 6 — bind correspondence points between each section's plan (эталон)
// and the floor's "карта отсеков": the SAME cropped floor mask the overview shows
// (black walls), with the section outlines drawn on it. NOT a single section's
// poster, NOT auto-extracted vector lines.
//
// Points are numbered orange SQUARES: the SAME number on the эталон and on the
// карта отсеков is one correspondence pair ("ставишь 1, 2, 3"). Clicking a canvas
// auto-mints the next number for that side, so a click ALWAYS places. Selecting a
// number highlights it on both canvases; the delete tool removes a pair from both
// sides. Points auto-save when leaving the step (and via the explicit button).
//
// Presentational only — all draft state/persistence lives in useFloorAssembly.

import React, { useState, useMemo, useCallback } from 'react';
import { Crosshair, Trash2 } from 'lucide-react';
import { StitchPointCanvas, type SectionOutline } from './StitchPointCanvas';
import { nextNumberId, pointLabel } from '../../lib/controlPoints';
import type {
  AssemblySection,
  ControlPoint,
  MasterControlPoint,
} from '../../types/floorAssembly';
import wizardStyles from './WizardStep.module.css';
import styles from './Step6BindControlPoints.module.css';

type Tool = 'place' | 'delete';

// Mirrors backend app/core/floor_stitching_constants.MAX_CONTROL_POINTS: each
// side (эталон / карта) is capped at 20 — placing past it would 422 on save.
const MAX_POINTS_PER_SIDE = 20;

interface Step6BindControlPointsProps {
  sections: AssemblySection[];
  /** Cropped floor-schema binary mask (the карта-отсеков backdrop). */
  masterMaskUrl: string | null;
  sectionPointsBySection: Record<number, ControlPoint[]>;
  masterPointsBySection: Record<number, MasterControlPoint[]>;
  activeSectionId: number | null;
  activePointId: string | null;
  isLoading: boolean;
  onSelectSection: (sectionId: number) => void;
  onSelectPoint: (pointId: string | null) => void;
  onSetSectionPoint: (sectionId: number, pointId: string, x: number, y: number) => void;
  onSetMasterPoint: (sectionId: number, pointId: string, x: number, y: number) => void;
  onRemovePoint: (sectionId: number, pointId: string) => void;
  onSave: (sectionId: number) => Promise<void>;
  onBack: () => void;
  onNext: () => void;
}

const numOf = (id: string): number => {
  const match = /(\d+)/.exec(id);
  return match ? parseInt(match[1], 10) : 0;
};
const byNumber = (a: string, b: string): number => numOf(a) - numOf(b);

export const Step6BindControlPoints: React.FC<Step6BindControlPointsProps> = ({
  sections,
  masterMaskUrl,
  sectionPointsBySection,
  masterPointsBySection,
  activeSectionId,
  activePointId,
  isLoading,
  onSelectSection,
  onSelectPoint,
  onSetSectionPoint,
  onSetMasterPoint,
  onRemovePoint,
  onSave,
  onBack,
  onNext,
}) => {
  const [tool, setTool] = useState<Tool>('place');

  const boundSections = sections.filter((s) => s.reconstruction_id !== null);
  const activeSection =
    sections.find((s) => s.section_id === activeSectionId) ?? null;

  const sectionPts =
    activeSectionId !== null ? sectionPointsBySection[activeSectionId] ?? [] : [];
  const masterPts =
    activeSectionId !== null ? masterPointsBySection[activeSectionId] ?? [] : [];

  const sectionIds = useMemo(() => new Set(sectionPts.map((p) => p.id)), [sectionPts]);
  const masterIds = useMemo(
    () => new Set(masterPts.map((p) => p.point_id)),
    [masterPts],
  );
  const allIds = useMemo(
    () => Array.from(new Set([...sectionIds, ...masterIds])).sort(byNumber),
    [sectionIds, masterIds],
  );
  const pairedCount = allIds.filter(
    (id) => sectionIds.has(id) && masterIds.has(id),
  ).length;

  // Section outlines drawn on the master for orientation + snap targets.
  const sectionOutlines = useMemo<SectionOutline[]>(
    () =>
      sections
        .filter((s) => s.geometry && s.geometry.length >= 3)
        .map((s) => ({ number: s.number, points: s.geometry as [number, number][] })),
    [sections],
  );
  const masterSnap = useMemo<[number, number][]>(
    () => sectionOutlines.flatMap((o) => o.points),
    [sectionOutlines],
  );

  const sectionCanvasPoints = sectionPts.map((p) => ({ id: p.id, x: p.x, y: p.y }));
  const masterCanvasPoints = masterPts.map((p) => ({ id: p.point_id, x: p.x, y: p.y }));
  const sectionMaskUrl = activeSection?.mask_url ?? null;

  const handlePointClick = useCallback(
    (id: string) => {
      if (activeSectionId === null) return;
      if (tool === 'delete') {
        onRemovePoint(activeSectionId, id);
        return;
      }
      onSelectPoint(activePointId === id ? null : id);
    },
    [activeSectionId, tool, activePointId, onRemovePoint, onSelectPoint],
  );

  const handleSectionPlace = useCallback(
    (id: string, x: number, y: number) => {
      if (activeSectionId === null || tool === 'delete') return;
      // Cap NEW points (id === '') at MAX; moving an existing point is allowed.
      if (id === '' && sectionPts.length >= MAX_POINTS_PER_SIDE) return;
      const pid = id !== '' ? id : nextNumberId(sectionPts.map((p) => p.id));
      onSetSectionPoint(activeSectionId, pid, x, y);
    },
    [activeSectionId, tool, sectionPts, onSetSectionPoint],
  );

  const handleMasterPlace = useCallback(
    (id: string, x: number, y: number) => {
      if (activeSectionId === null || tool === 'delete') return;
      if (id === '' && masterPts.length >= MAX_POINTS_PER_SIDE) return;
      const pid = id !== '' ? id : nextNumberId(masterPts.map((p) => p.point_id));
      onSetMasterPoint(activeSectionId, pid, x, y);
    },
    [activeSectionId, tool, masterPts, onSetMasterPoint],
  );

  const handleSave = useCallback(() => {
    if (activeSectionId !== null) void onSave(activeSectionId);
  }, [activeSectionId, onSave]);

  // Save EVERY bound section that has points before advancing — not just the
  // ACTIVE one. Otherwise a section the operator placed but didn't manually save
  // (and that wasn't active when they hit "Далее") reaches the solve with no
  // persisted points and is reported as "0 точек" / skipped.
  const handleNext = useCallback(async () => {
    for (const s of sections) {
      if (s.reconstruction_id === null) continue;
      const hasPts =
        (sectionPointsBySection[s.section_id]?.length ?? 0) > 0 ||
        (masterPointsBySection[s.section_id]?.length ?? 0) > 0;
      if (hasPts) {
        await onSave(s.section_id);
      }
    }
    onNext();
  }, [sections, sectionPointsBySection, masterPointsBySection, onSave, onNext]);

  return (
    <div className={wizardStyles.layout}>
      <div className={styles.body}>
        {/* Left rail — section list */}
        <aside className={styles.sectionsPanel}>
          <div className={styles.panelTitle}>ОТСЕКИ</div>
          <div className={styles.sectionList}>
            {boundSections.map((s) => {
              const sIds = new Set(
                (sectionPointsBySection[s.section_id] ?? []).map((p) => p.id),
              );
              const mIds = new Set(
                (masterPointsBySection[s.section_id] ?? []).map((p) => p.point_id),
              );
              const paired = [...sIds].filter((id) => mIds.has(id)).length;
              return (
                <button
                  key={s.section_id}
                  type="button"
                  className={`${styles.sectionBtn} ${
                    s.section_id === activeSectionId ? styles.sectionBtnActive : ''
                  }`}
                  onClick={() => onSelectSection(s.section_id)}
                >
                  <span style={{ fontWeight: 600 }}>Отсек {s.number}</span>
                  <span className={styles.sectionCount}>{paired} пар</span>
                </button>
              );
            })}
            {boundSections.length === 0 && (
              <div className={styles.emptyHint}>Нет отсеков с планами</div>
            )}
          </div>
        </aside>

        {/* Center — dual canvas (эталон ↔ карта отсеков) */}
        <div className={styles.canvasGrid}>
          <div className={styles.canvasCol}>
            <div className={styles.canvasLabel}>
              {activeSection ? `Отсек ${activeSection.number} — эталон` : 'Эталон'}
            </div>
            <div className={styles.canvasBox}>
              {activeSection && sectionMaskUrl ? (
                <StitchPointCanvas
                  maskUrl={sectionMaskUrl}
                  points={sectionCanvasPoints}
                  activeId={activePointId}
                  tool={tool}
                  onPlace={handleSectionPlace}
                  onSelect={handlePointClick}
                />
              ) : (
                <div className={styles.canvasEmpty}>
                  {activeSection
                    ? 'У отсека нет маски плана'
                    : 'Выберите отсек слева'}
                </div>
              )}
            </div>
          </div>

          <div className={styles.canvasCol}>
            <div className={styles.canvasLabel}>Карта отсеков (весь этаж)</div>
            <div className={styles.canvasBox}>
              {masterMaskUrl ? (
                <StitchPointCanvas
                  maskUrl={masterMaskUrl}
                  sectionOutlines={sectionOutlines}
                  points={masterCanvasPoints}
                  activeId={activePointId}
                  snapTargets={masterSnap}
                  tool={tool}
                  onPlace={handleMasterPlace}
                  onSelect={handlePointClick}
                />
              ) : (
                <div className={styles.canvasEmpty}>
                  Нет карты отсеков — загрузите и обрежьте схему этажа (шаги 1–3)
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right panel — tools, point list, status */}
        <aside className={styles.toolsPanel}>
          <div className={styles.panelTitle}>ИНСТРУМЕНТЫ</div>
          <div className={styles.toolGroup}>
            <button
              type="button"
              className={`${styles.toolBtn} ${
                tool === 'place' ? styles.toolBtnActive : ''
              }`}
              onClick={() => setTool('place')}
            >
              <Crosshair size={16} /> Поставить точку
            </button>
            <button
              type="button"
              className={`${styles.toolBtn} ${
                tool === 'delete' ? styles.toolBtnActive : ''
              }`}
              onClick={() => setTool('delete')}
              disabled={allIds.length === 0}
            >
              <Trash2 size={16} /> Удалить точку
            </button>
          </div>

          <div className={styles.pickerHint}>
            {tool === 'place'
              ? 'Кликайте по эталону и по карте отсеков — точки нумеруются сами (1, 2, 3…). Один и тот же номер слева и справа = одна пара. Клик по точке выделяет её на обеих схемах.'
              : 'Кликните по точке, чтобы удалить её сразу с обеих схем.'}
          </div>

          {(sectionPts.length >= MAX_POINTS_PER_SIDE ||
            masterPts.length >= MAX_POINTS_PER_SIDE) && (
            <div className={styles.statusHint}>
              Достигнут предел — {MAX_POINTS_PER_SIDE} точек на схему. Удалите
              лишние, чтобы добавить новые.
            </div>
          )}

          {activeSection === null ? (
            <div className={styles.emptyHint}>Выберите отсек</div>
          ) : (
            <>
              <div className={styles.panelTitle}>ТОЧКИ (Э — эталон, К — карта)</div>
              <div className={styles.pointList}>
                {allIds.map((id) => {
                  const onL = sectionIds.has(id);
                  const onR = masterIds.has(id);
                  const active = id === activePointId;
                  return (
                    <div
                      key={id}
                      className={`${styles.pointRow} ${
                        active ? styles.pointRowActive : ''
                      }`}
                    >
                      <button
                        type="button"
                        className={styles.pointSelect}
                        onClick={() => onSelectPoint(active ? null : id)}
                      >
                        <span
                          className={styles.numBadge}
                          style={{ background: onL && onR ? '#16a34a' : '#f59e0b' }}
                        >
                          {pointLabel(id)}
                        </span>
                        <span className={styles.chips}>
                          <span className={`${styles.chip} ${onL ? styles.chipOn : ''}`}>
                            Э
                          </span>
                          <span className={`${styles.chip} ${onR ? styles.chipOn : ''}`}>
                            К
                          </span>
                        </span>
                      </button>
                      <button
                        type="button"
                        className={styles.pointClear}
                        title="Удалить точку с обеих схем"
                        onClick={() => onRemovePoint(activeSection.section_id, id)}
                      >
                        ✕
                      </button>
                    </div>
                  );
                })}
                {allIds.length === 0 && (
                  <div className={styles.emptyHint}>
                    Точек пока нет — кликните по схемам
                  </div>
                )}
              </div>

              <div className={styles.statusRow}>
                <span className={styles.statusLabel}>Пар сопоставлено</span>
                <span
                  className={`${styles.statusValue} ${
                    pairedCount < 3 ? styles.statusValueLow : ''
                  }`}
                >
                  {pairedCount}
                </span>
              </div>
              {pairedCount < 3 && (
                <div className={styles.statusHint}>
                  Нужно минимум 3 пары для расчёта (масштаб + сдвиг)
                </div>
              )}

              <button
                type="button"
                className={styles.saveBtn}
                onClick={handleSave}
                disabled={isLoading}
              >
                Сохранить точки
              </button>
            </>
          )}
        </aside>
      </div>

      <footer className={wizardStyles.footer}>
        <button className={wizardStyles.btnBack} onClick={onBack} type="button">
          ← Назад
        </button>
        <span className={wizardStyles.footerHint} />
        <button
          className={wizardStyles.btnNext}
          onClick={() => void handleNext()}
          type="button"
        >
          Далее ▸
        </button>
      </footer>
    </div>
  );
};
