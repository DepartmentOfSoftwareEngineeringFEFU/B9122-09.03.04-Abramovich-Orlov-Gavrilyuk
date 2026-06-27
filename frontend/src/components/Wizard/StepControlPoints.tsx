// Wizard step 3: place section-local control points on the freshly
// binarised section. Mirrors StepWallEditor's layout — a dominant canvas area on
// the left, a ToolPanelV2 panel on the right. Hosts the shared ControlPointCanvas
// plus a view toggle (Фото / Маска / Инвертированная маска), an opacity slider and
// the "Опорные точки: N/10" status counter.
//
// Presentational only: control-point state + monotonic ids live in useWizard.
// The /10 in the counter is a SOFT display target (07-ui-reference); the
// real gate is >=3 (enforced by WizardPage.isNextDisabled) and the cap is
// MAX_CONTROL_POINTS = 20.

import React, { useState, useCallback } from 'react';
import { Crosshair, Trash2 } from 'lucide-react';
import { ControlPointCanvas } from '../ControlPointCanvas';
import type { ControlPoint } from '../../types/floorAssembly';
import styles from './StepControlPoints.module.css';
import panelStyles from '../Editor/ToolPanelV2.module.css';

type BackdropView = 'photo' | 'mask' | 'inverted';

const MAX_CONTROL_POINTS = 20;
const SOFT_TARGET = 10;

interface StepControlPointsProps {
  photoUrl: string | null;
  maskUrl: string;
  points: ControlPoint[];
  snapTargets?: [number, number][];
  onAddPoint: (x: number, y: number) => void;
  onMovePoint: (id: string, x: number, y: number) => void;
  onDeletePoint: (id: string) => void;
}

const VIEW_OPTIONS: { id: BackdropView; label: string }[] = [
  { id: 'photo', label: 'Фото' },
  { id: 'mask', label: 'Маска' },
  { id: 'inverted', label: 'Инвертированная маска' },
];

export const StepControlPoints: React.FC<StepControlPointsProps> = ({
  photoUrl,
  maskUrl,
  points,
  snapTargets,
  onAddPoint,
  onMovePoint,
  onDeletePoint,
}) => {
  const [view, setView] = useState<BackdropView>('mask');
  const [opacity, setOpacity] = useState(1);
  const [activeId, setActiveId] = useState<string | null>(null);

  const atCap = points.length >= MAX_CONTROL_POINTS;

  // Photo backdrop only meaningful once a plan photo URL exists; otherwise fall
  // back to the mask so the canvas always has something to draw against.
  const usePhoto = view === 'photo' && photoUrl !== null;
  const imageUrl = usePhoto ? (photoUrl as string) : maskUrl;
  const inverted = view === 'inverted';

  // ControlPointCanvas emits onPlace('' , x, y) for an empty-area click with no
  // active point (ADD) and onPlace(id, x, y) when a point is active (MOVE).
  const handlePlace = useCallback(
    (id: string, x: number, y: number) => {
      if (id === '') {
        if (atCap) return;
        onAddPoint(x, y);
        return;
      }
      onMovePoint(id, x, y);
    },
    [atCap, onAddPoint, onMovePoint],
  );

  const handleSelect = useCallback((id: string) => {
    setActiveId((prev) => (prev === id ? null : id));
  }, []);

  const handleDeleteActive = useCallback(() => {
    if (activeId === null) return;
    onDeletePoint(activeId);
    setActiveId(null);
  }, [activeId, onDeletePoint]);

  return (
    <div className={styles.step}>
      <div className={styles.canvasArea}>
        <div className={styles.gridBg} />
        <div className={`${styles.canvasBox} ${inverted ? styles.inverted : ''}`}>
          <ControlPointCanvas
            imageUrl={imageUrl}
            points={points}
            activeId={activeId}
            snapTargets={snapTargets}
            opacity={opacity}
            onPlace={handlePlace}
            onSelect={handleSelect}
          />
        </div>
      </div>

      {/* Right panel — tools + view, mirrors StepWallEditor's manual layout */}
      <div className={panelStyles.panel}>
        <div className={panelStyles.inner}>

          {/* // ИНСТРУМЕНТЫ */}
          <div>
            <div className={panelStyles.sectionTitle}>// ИНСТРУМЕНТЫ</div>
            <div className={panelStyles.section}>
              <button
                type="button"
                className={`${panelStyles.toolBtn} ${panelStyles.toolBtnActive}`}
              >
                <span className={panelStyles.toolIcon}><Crosshair size={18} /></span>
                Опорная точка
              </button>
              <button
                type="button"
                className={panelStyles.toolBtn}
                disabled={activeId === null}
                onClick={handleDeleteActive}
              >
                <span className={panelStyles.toolIcon}><Trash2 size={18} /></span>
                Удалить точку
              </button>
            </div>
            <div className={styles.hint}>
              Клик по плану — добавить точку. Клик по точке — выбрать её.
              {atCap && <><br />Достигнут предел ({MAX_CONTROL_POINTS}).</>}
            </div>
          </div>

          <div className={panelStyles.sectionDivider} />

          {/* // ВИД */}
          <div>
            <div className={panelStyles.sectionTitle}>// ВИД</div>
            <div className={styles.paramSection}>
              {VIEW_OPTIONS.map((opt) => {
                const disabled = opt.id === 'photo' && photoUrl === null;
                const active = view === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    className={`${styles.viewOption} ${active ? styles.viewOptionActive : ''}`}
                    disabled={disabled}
                    onClick={() => setView(opt.id)}
                  >
                    <span className={styles.radioMark}>{active ? '◉' : '○'}</span>
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className={panelStyles.sectionDivider} />

          {/* // ПРОЗРАЧНОСТЬ */}
          <div>
            <div className={panelStyles.sectionTitle}>// ПРОЗРАЧНОСТЬ</div>
            <div className={styles.paramSection}>
              <div className={styles.paramRow}>
                <span className={styles.paramLabel}>Прозрачность</span>
                <div className={styles.sliderRow}>
                  <input
                    type="range"
                    className={styles.sliderInput}
                    min={5} max={100} step={5}
                    value={Math.round(opacity * 100)}
                    onChange={(e) => setOpacity(Number(e.target.value) / 100)}
                  />
                  <span className={styles.sliderValue}>{Math.round(opacity * 100)}%</span>
                </div>
              </div>
            </div>
          </div>

          <div className={panelStyles.sectionDivider} />

          {/* // СТАТУС */}
          <div className={styles.statusSection}>
            <span className={styles.statusLabel}>Опорные точки</span>
            <span
              className={`${styles.statusValue} ${points.length < 3 ? styles.statusValueLow : ''}`}
            >
              {points.length}/{SOFT_TARGET}
            </span>
          </div>
          {points.length < 3 && (
            <div className={styles.statusHint}>Нужно минимум 3 точки</div>
          )}

        </div>
      </div>
    </div>
  );
};
