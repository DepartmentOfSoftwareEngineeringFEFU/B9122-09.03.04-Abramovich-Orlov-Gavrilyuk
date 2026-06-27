/**
 * Step 3 — Обработка отсека (выделение стен)
 *
 * Reuses the proven WallEditorCanvas from the existing wizard so editing
 * tools (wall pen, eraser, brush size, opacity slider, photo overlay,
 * mask sensitivity / contrast sliders) work identically to the
 * "Загрузить изображение" flow.
 *
 * Mask preview comes from the same backend endpoint as the existing
 * wizard: POST /reconstruction/mask-preview.
 */
import React, { useEffect, useRef, useState, useCallback, type MouseEvent } from 'react';
import { WallEditorCanvas } from '../Editor/WallEditorCanvas';
import type { WallEditorCanvasRef } from '../Editor/WallEditorCanvas';
import { reconstructionApi } from '../../api/apiService';
import wizStyles from './WizardStep.module.css';
import styles from './Step3WallExtraction.module.css';
import type { Point2D } from '../../hooks/useFloorEditorWizard';
import type { CropBbox } from '../../types/hierarchy';

type Tool = 'wall' | 'eraser';

interface Step3WallExtractionProps {
  schemaImageId: string | null;
  schemaImageUrl: string | null;
  cropBbox: CropBbox | null;
  wallPolygons: Point2D[][] | null;
  isLoading: boolean;
  onTriggerExtraction: () => Promise<void>;
  onCommitEditedMask?: (blob: Blob) => Promise<void>;
  onNext: () => Promise<void>;
  onBack: () => void;
}

const DEFAULT_BLOCK_SIZE = 15;
const DEFAULT_THRESHOLD_C = 10;

// Editor settings persist across sessions (localStorage) so the operator's tuned
// sensitivity / contrast / brush / overlay survive reopening the wall editor.
const MASK_SETTINGS_KEY = 'floorEditor:maskSettings';

interface MaskSettings {
  brushSize: number;
  blockSize: number;
  thresholdC: number;
  overlayEnabled: boolean;
  overlayOpacity: number;
}

const DEFAULT_MASK_SETTINGS: MaskSettings = {
  brushSize: 6,
  blockSize: DEFAULT_BLOCK_SIZE,
  thresholdC: DEFAULT_THRESHOLD_C,
  overlayEnabled: true,
  overlayOpacity: 0.4,
};

function loadMaskSettings(): MaskSettings {
  try {
    const raw = localStorage.getItem(MASK_SETTINGS_KEY);
    if (!raw) return DEFAULT_MASK_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<MaskSettings>;
    return { ...DEFAULT_MASK_SETTINGS, ...parsed };
  } catch {
    return DEFAULT_MASK_SETTINGS;
  }
}

export const Step3WallExtraction: React.FC<Step3WallExtractionProps> = ({
  schemaImageId,
  schemaImageUrl,
  cropBbox,
  isLoading,
  onCommitEditedMask,
  onNext,
  onBack,
}) => {
  const canvasRef = useRef<WallEditorCanvasRef>(null);

  // Read persisted settings once on mount (lazy ref → localStorage hit once, not
  // every render).
  const savedSettingsRef = useRef<MaskSettings | null>(null);
  if (savedSettingsRef.current === null) {
    savedSettingsRef.current = loadMaskSettings();
  }
  const savedSettings = savedSettingsRef.current;

  const [activeTool, setActiveTool] = useState<Tool>('wall');
  const [eraserMode, setEraserMode] = useState<'brush' | 'select'>('brush');
  const [brushSize, setBrushSize] = useState(savedSettings.brushSize);
  const [blockSize, setBlockSize] = useState(savedSettings.blockSize);
  const [thresholdC, setThresholdC] = useState(savedSettings.thresholdC);
  const [overlayEnabled, setOverlayEnabled] = useState(savedSettings.overlayEnabled);
  const [overlayOpacity, setOverlayOpacity] = useState(savedSettings.overlayOpacity);
  const [maskUrl, setMaskUrl] = useState<string>('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number } | null>(null);

  const showBrushCursor = activeTool === 'eraser' && eraserMode === 'brush';

  const handleCanvasMouseMove = useCallback((e: MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setCursorPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  }, []);

  const handleCanvasMouseLeave = useCallback(() => {
    setCursorPos(null);
  }, []);

  const cropForApi = cropBbox
    ? { x: cropBbox.x, y: cropBbox.y, width: cropBbox.width, height: cropBbox.height }
    : null;
  const rotation = cropBbox?.rotation ?? 0;

  // Fetch mask preview whenever inputs change (debounced)
  useEffect(() => {
    if (!schemaImageId) {
      setMaskUrl('');
      setPreviewError(schemaImageUrl ? 'Нет идентификатора фото' : 'Загрузите фото на шаге 1');
      return;
    }
    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);

    const timer = setTimeout(async () => {
      try {
        const url = await reconstructionApi.previewMask(
          schemaImageId, cropForApi, rotation, blockSize, thresholdC,
        );
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = url;
        setMaskUrl(url);
      } catch {
        if (!cancelled) setPreviewError('Ошибка генерации маски на сервере');
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    }, 250);

    return () => { cancelled = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schemaImageId, cropBbox, blockSize, thresholdC]);

  // Cleanup last blob URL on unmount
  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  // Persist mask/editor settings so they survive reopening the editor.
  useEffect(() => {
    try {
      localStorage.setItem(
        MASK_SETTINGS_KEY,
        JSON.stringify({ brushSize, blockSize, thresholdC, overlayEnabled, overlayOpacity }),
      );
    } catch {
      /* localStorage unavailable (private mode / quota) — non-fatal */
    }
  }, [brushSize, blockSize, thresholdC, overlayEnabled, overlayOpacity]);

  const handleNext = useCallback(async () => {
    // Capture the edited mask from the fabric.js canvas and hand it UP so the
    // hook can both show it instantly (Step 4/5) and persist it (survives
    // reload) instead of refetching a raw /mask-preview.
    if (onCommitEditedMask && canvasRef.current) {
      try {
        const blob = await canvasRef.current.getBlob();
        if (blob && blob.size > 0) {
          await onCommitEditedMask(blob);
        }
      } catch {
        // Fall back silently — Step 4 will use /mask-preview.
      }
    }
    await onNext();
  }, [onNext, onCommitEditedMask]);

  // The WallEditorCanvas requires a popup handler; floor editor doesn't use
  // room/door annotations, so we provide a no-op.
  const noopPopup = useCallback(() => { /* unused on this step */ }, []);

  return (
    <div className={wizStyles.layout}>
      <div className={wizStyles.body}>
        {/* Left tools sidebar */}
        <aside className={wizStyles.sidebar}>
          <h3 className={wizStyles.sidebarTitle}>// Редактор стен</h3>

          <button
            type="button"
            className={`${wizStyles.toolBtn} ${activeTool === 'wall' ? wizStyles.toolBtnActive : ''}`}
            onClick={() => setActiveTool('wall')}
          >
            Нарисовать стену
          </button>
          {activeTool === 'wall' && (
            <div className={styles.inlineParam}>
              <span className={styles.paramLabel}>Толщина линии</span>
              <div className={styles.sliderRow}>
                <input
                  type="range"
                  className={styles.slider}
                  min={1} max={30} step={1}
                  value={brushSize}
                  onChange={(e) => setBrushSize(Number(e.target.value))}
                />
                <span className={styles.sliderValue}>{brushSize} px</span>
              </div>
            </div>
          )}

          <button
            type="button"
            className={`${wizStyles.toolBtn} ${activeTool === 'eraser' ? wizStyles.toolBtnActive : ''}`}
            onClick={() => setActiveTool('eraser')}
          >
            Стереть
          </button>
          {activeTool === 'eraser' && (
            <div className={styles.paramSection}>
              <div className={styles.paramRow} style={{ marginBottom: '1rem' }}>
                <span className={styles.paramLabel} style={{ marginBottom: '0.5rem', display: 'block' }}>Режим</span>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    type="button"
                    onClick={() => setEraserMode('brush')}
                    style={{
                      flex: 1,
                      padding: '0.5rem',
                      border: '1px solid #e5e7eb',
                      background: eraserMode === 'brush' ? '#ff6b1f' : '#fff',
                      color: eraserMode === 'brush' ? '#fff' : '#374151',
                      fontSize: '0.875rem',
                      cursor: 'pointer',
                    }}
                  >
                    Кисть
                  </button>
                  <button
                    type="button"
                    onClick={() => setEraserMode('select')}
                    style={{
                      flex: 1,
                      padding: '0.5rem',
                      border: '1px solid #e5e7eb',
                      background: eraserMode === 'select' ? '#ff6b1f' : '#fff',
                      color: eraserMode === 'select' ? '#fff' : '#374151',
                      fontSize: '0.875rem',
                      cursor: 'pointer',
                    }}
                  >
                    Прямоуг.
                  </button>
                </div>
              </div>
              {eraserMode === 'brush' && (
                <div className={styles.inlineParam}>
                  <span className={styles.paramLabel}>Размер кисти</span>
                  <div className={styles.sliderRow}>
                    <input
                      type="range"
                      className={styles.slider}
                      min={1} max={60} step={1}
                      value={brushSize}
                      onChange={(e) => setBrushSize(Number(e.target.value))}
                    />
                    <span className={styles.sliderValue}>{brushSize} px</span>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className={styles.sectionDivider} />

          <h3 className={wizStyles.sidebarTitle}>// Параметры маски</h3>
          <div className={styles.paramSection}>
            <div className={styles.paramRow}>
              <span className={styles.paramLabel}>Чувствительность</span>
              <div className={styles.sliderRow}>
                <input
                  type="range"
                  className={styles.slider}
                  min={7} max={51} step={2}
                  value={blockSize}
                  onChange={(e) => setBlockSize(Number(e.target.value))}
                />
                <span className={styles.sliderValue}>{blockSize}</span>
              </div>
            </div>
            <div className={styles.paramRow}>
              <span className={styles.paramLabel}>Контраст</span>
              <div className={styles.sliderRow}>
                <input
                  type="range"
                  className={styles.slider}
                  min={2} max={20} step={1}
                  value={thresholdC}
                  onChange={(e) => setThresholdC(Number(e.target.value))}
                />
                <span className={styles.sliderValue}>{thresholdC}</span>
              </div>
            </div>
          </div>

          <div className={styles.sectionDivider} />

          <h3 className={wizStyles.sidebarTitle}>// Наложение</h3>
          <div className={styles.paramSection}>
            <label className={styles.toggleRow}>
              <span className={styles.paramLabel}>Показать оригинал</span>
              <input
                type="checkbox"
                checked={overlayEnabled}
                onChange={(e) => setOverlayEnabled(e.target.checked)}
              />
            </label>
            {overlayEnabled && (
              <div className={styles.paramRow}>
                <span className={styles.paramLabel}>Прозрачность</span>
                <div className={styles.sliderRow}>
                  <input
                    type="range"
                    className={styles.slider}
                    min={5} max={95} step={5}
                    value={Math.round(overlayOpacity * 100)}
                    onChange={(e) => setOverlayOpacity(Number(e.target.value) / 100)}
                  />
                  <span className={styles.sliderValue}>{Math.round(overlayOpacity * 100)}%</span>
                </div>
              </div>
            )}
          </div>

          <div className={styles.sectionDivider} />
        </aside>

        {/* Canvas */}
        <div
          className={`${wizStyles.canvasArea} ${showBrushCursor ? styles.brushActive : ''}`}
          onMouseMove={showBrushCursor ? handleCanvasMouseMove : undefined}
          onMouseLeave={showBrushCursor ? handleCanvasMouseLeave : undefined}
        >
          {maskUrl ? (
            <WallEditorCanvas
              ref={canvasRef}
              maskUrl={maskUrl}
              activeTool={activeTool}
              brushSize={brushSize}
              eraserMode={eraserMode}
              hideCursor={showBrushCursor}
              onRoomPopupRequest={noopPopup}
              planUrl={schemaImageUrl ?? undefined}
              planCropRect={cropForApi}
              planRotation={rotation}
              overlayEnabled={overlayEnabled}
              overlayOpacity={overlayOpacity}
            />
          ) : (
            <div className={wizStyles.spinnerOverlay}>
              <span className={wizStyles.spinnerText}>
                {previewError ?? 'Загрузка...'}
              </span>
            </div>
          )}
          {(previewLoading || isLoading) && maskUrl && (
            <div className={styles.refreshChip}>Обновление...</div>
          )}
          {showBrushCursor && cursorPos && (
            <div
              className={styles.brushCursor}
              style={{
                left: cursorPos.x,
                top: cursorPos.y,
                width: brushSize,
                height: brushSize,
              }}
            />
          )}
        </div>
      </div>

      <footer className={wizStyles.footer}>
        <button className={wizStyles.btnBack} onClick={onBack} type="button">
          ← Назад
        </button>
        <span className={wizStyles.footerHint}>Выделите стены отсека</span>
        <button
          className={wizStyles.btnNext}
          onClick={handleNext}
          disabled={isLoading || !maskUrl}
          type="button"
        >
          Далее →
        </button>
      </footer>
    </div>
  );
};
