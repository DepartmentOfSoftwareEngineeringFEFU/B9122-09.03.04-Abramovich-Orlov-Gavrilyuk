import React, { useEffect, useRef, useState, useCallback, type MouseEvent } from 'react';
import { Pencil, Eraser, Square, ArrowUpDown, ArrowUp, DoorOpen, Trash2 } from 'lucide-react';
import { WallEditorCanvas } from '../Editor/WallEditorCanvas';
import type { WallEditorCanvasRef } from '../Editor/WallEditorCanvas';
import { RoomPopup } from '../Editor/RoomPopup';
import { reconstructionApi } from '../../api/apiService';
import type { CropRect, TransitionSpec } from '../../types/wizard';
import styles from './StepWallEditor.module.css';
import panelStyles from '../Editor/ToolPanelV2.module.css';

type ActiveTool = 'wall' | 'eraser' | 'room' | 'staircase' | 'elevator' | 'corridor' | 'door' | 'erase_markup';

interface PopupState {
  position: { x: number; y: number };
  roomType: 'room' | 'staircase' | 'elevator' | 'corridor';
  onConfirm: (name: string, transition?: TransitionSpec) => void;
  onCancel: () => void;
}

interface StepWallEditorProps {
  maskUrl: string;
  planFileId: string | null;
  planUrl?: string;
  cropRect: CropRect | null;
  rotation: number;
  blockSize: number;
  thresholdC: number;
  canvasRef: React.RefObject<WallEditorCanvasRef>;
  onBlockSizeChange: (v: number) => void;
  onThresholdCChange: (v: number) => void;
  initialRooms?: import('../../types/wizard').RoomAnnotation[];
  initialDoors?: import('../../types/wizard').DoorAnnotation[];
  hideMaskParams?: boolean;
}

const MARKUP_TOOLS: { id: ActiveTool; label: string; icon: React.ReactNode }[] = [
  { id: 'room', label: 'Кабинет', icon: <Square size={18} /> },
  { id: 'staircase', label: 'Лестница', icon: <ArrowUpDown size={18} /> },
  { id: 'elevator', label: 'Лифт', icon: <ArrowUp size={18} /> },
  { id: 'door', label: 'Дверь', icon: <DoorOpen size={18} /> },
  { id: 'erase_markup', label: 'Удалить разметку', icon: <Trash2 size={18} /> },
];

export const StepWallEditor: React.FC<StepWallEditorProps> = ({
  maskUrl,
  planFileId,
  planUrl,
  cropRect,
  rotation,
  blockSize,
  thresholdC,
  canvasRef,
  onBlockSizeChange,
  onThresholdCChange,
  initialRooms,
  initialDoors,
  hideMaskParams = false,
}) => {
  const [activeTool, setActiveTool] = useState<ActiveTool>('wall');
  const [eraserMode, setEraserMode] = useState<'brush' | 'select'>('brush');
  const [brushSize, setBrushSize] = useState(6);
  const [popupState, setPopupState] = useState<PopupState | null>(null);
  const [currentMaskUrl, setCurrentMaskUrl] = useState(maskUrl);
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number } | null>(null);

  const showBrushCursor = activeTool === 'eraser' && eraserMode === 'brush';

  const handleCanvasMouseMove = useCallback((e: MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setCursorPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  }, []);

  const handleCanvasMouseLeave = useCallback(() => {
    setCursorPos(null);
  }, []);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [overlayEnabled, setOverlayEnabled] = useState(true);
  const [overlayOpacity, setOverlayOpacity] = useState(0.4);
  const previewUrlRef = useRef<string | null>(null);
  const isFirstRenderRef = useRef(true);
  const prevBlockSizeRef = useRef(blockSize);
  const prevThresholdCRef = useRef(thresholdC);

  useEffect(() => {
    // Skip on mount — mask is already provided via maskUrl prop
    if (isFirstRenderRef.current) {
      isFirstRenderRef.current = false;
      return;
    }

    // Only re-fetch when slider params actually changed
    if (
      prevBlockSizeRef.current === blockSize &&
      prevThresholdCRef.current === thresholdC
    ) {
      return;
    }

    prevBlockSizeRef.current = blockSize;
    prevThresholdCRef.current = thresholdC;

    if (!planFileId) return;

    const timer = setTimeout(async () => {
      setIsPreviewLoading(true);
      try {
        const url = await reconstructionApi.previewMask(
          planFileId, cropRect, rotation, blockSize, thresholdC,
        );
        if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = url;
        setCurrentMaskUrl(url);
      } catch (err) {
        console.error('Preview failed:', err);
      } finally {
        setIsPreviewLoading(false);
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [blockSize, thresholdC, planFileId, cropRect, rotation]);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, []);

  const handleRoomPopupRequest = (
    rect: { x: number; y: number; w: number; h: number },
    onConfirm: (name: string, transition?: TransitionSpec) => void,
    onCancel: () => void,
  ) => {
    const roomType = activeTool as 'room' | 'staircase' | 'elevator' | 'corridor';
    setPopupState({ position: { x: rect.x, y: rect.y }, roomType, onConfirm, onCancel });
  };

  const handlePopupConfirm = (name: string, transition?: TransitionSpec) => {
    if (!popupState) return;
    popupState.onConfirm(name, transition);
    setPopupState(null);
  };

  const handlePopupCancel = () => {
    if (!popupState) return;
    popupState.onCancel();
    setPopupState(null);
  };

  return (
    <div className={styles.step}>
      <div className={styles.canvasArea}>
        <div className={styles.gridBg} />
        <div
          className={`${styles.canvasBox} ${showBrushCursor ? styles.brushActive : ''}`}
          onMouseMove={showBrushCursor ? handleCanvasMouseMove : undefined}
          onMouseLeave={showBrushCursor ? handleCanvasMouseLeave : undefined}
        >
          <WallEditorCanvas
            ref={canvasRef}
            maskUrl={currentMaskUrl}
            activeTool={activeTool}
            brushSize={brushSize}
            eraserMode={eraserMode}
            hideCursor={showBrushCursor}
            onRoomPopupRequest={handleRoomPopupRequest}
            planUrl={planUrl}
            planCropRect={cropRect}
            planRotation={rotation}
            overlayEnabled={overlayEnabled}
            overlayOpacity={overlayOpacity}
            initialRooms={initialRooms}
            initialDoors={initialDoors}
          />
          {popupState && (
            <RoomPopup
              position={popupState.position}
              roomType={popupState.roomType}
              onConfirm={handlePopupConfirm}
              onCancel={handlePopupCancel}
            />
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

      {/* Right panel — rendered manually for inline sub-content */}
      <div className={panelStyles.panel}>
        <div className={panelStyles.inner}>

          {/* // РЕДАКТОР СТЕН */}
          <div>
            <div className={panelStyles.sectionTitle}>// РЕДАКТОР СТЕН</div>
            <div className={panelStyles.section}>
              <button
                type="button"
                className={`${panelStyles.toolBtn} ${activeTool === 'wall' ? panelStyles.toolBtnActive : ''}`}
                onClick={() => setActiveTool('wall')}
              >
                <span className={panelStyles.toolIcon}><Pencil size={18} /></span>
                Нарисовать стену
              </button>

              {activeTool === 'wall' && (
                <div className={styles.inlineParam}>
                  <span className={styles.inlineParamLabel}>Толщина линии</span>
                  <div className={styles.sliderRow}>
                    <input
                      type="range"
                      className={styles.sliderInput}
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
                className={`${panelStyles.toolBtn} ${activeTool === 'eraser' ? panelStyles.toolBtnActive : ''}`}
                onClick={() => setActiveTool('eraser')}
              >
                <span className={panelStyles.toolIcon}><Eraser size={18} /></span>
                Стереть
              </button>

              {activeTool === 'eraser' && (
                <div className={styles.subTools}>
                  <button
                    type="button"
                    className={`${styles.subTool} ${eraserMode === 'brush' ? styles.subToolActive : ''}`}
                    onClick={() => setEraserMode('brush')}
                  >
                    <span className={styles.radioMark}>{eraserMode === 'brush' ? '◉' : '○'}</span>
                    Кисть
                  </button>
                  {eraserMode === 'brush' && (
                    <div className={styles.inlineParam}>
                      <span className={styles.inlineParamLabel}>Размер кисти</span>
                      <div className={styles.sliderRow}>
                        <input
                          type="range"
                          className={styles.sliderInput}
                          min={1} max={60} step={1}
                          value={brushSize}
                          onChange={(e) => setBrushSize(Number(e.target.value))}
                        />
                        <span className={styles.sliderValue}>{brushSize} px</span>
                      </div>
                    </div>
                  )}
                  <button
                    type="button"
                    className={`${styles.subTool} ${eraserMode === 'select' ? styles.subToolActive : ''}`}
                    onClick={() => setEraserMode('select')}
                  >
                    <span className={styles.radioMark}>{eraserMode === 'select' ? '■' : '□'}</span>
                    Выделить область
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className={panelStyles.sectionDivider} />

          {/* // РАЗМЕТКА */}
          <div>
            <div className={panelStyles.sectionTitle}>// РАЗМЕТКА</div>
            <div className={panelStyles.section}>
              {MARKUP_TOOLS.map((tool) => (
                <button
                  key={tool.id}
                  type="button"
                  className={`${panelStyles.toolBtn} ${activeTool === tool.id ? panelStyles.toolBtnActive : ''}`}
                  onClick={() => setActiveTool(tool.id)}
                >
                  <span className={panelStyles.toolIcon}>{tool.icon}</span>
                  {tool.label}
                </button>
              ))}
            </div>
          </div>

          <div className={panelStyles.sectionDivider} />

          {/* // ПАРАМЕТРЫ МАСКИ (скрыты в режиме редактора) */}
          {!hideMaskParams && (
            <>
              <div>
                <div className={panelStyles.sectionTitle}>// ПАРАМЕТРЫ МАСКИ</div>
            <div className={styles.paramSection}>
              <div className={styles.paramRow}>
                <span className={styles.paramLabel}>Чувствительность</span>
                <div className={styles.sliderRow}>
                  <input
                    type="range"
                    className={styles.sliderInput}
                    min={7} max={51} step={2}
                    value={blockSize}
                    onChange={(e) => onBlockSizeChange(Number(e.target.value))}
                  />
                  <span className={styles.sliderValue}>{blockSize}</span>
                </div>
              </div>
              <div className={styles.paramRow}>
                <span className={styles.paramLabel}>Контраст</span>
                <div className={styles.sliderRow}>
                  <input
                    type="range"
                    className={styles.sliderInput}
                    min={2} max={20} step={1}
                    value={thresholdC}
                    onChange={(e) => onThresholdCChange(Number(e.target.value))}
                  />
                  <span className={styles.sliderValue}>{thresholdC}</span>
                </div>
              </div>
                {isPreviewLoading && <div className={styles.previewSpinner}>Обновление...</div>}
              </div>
            </div>

            <div className={panelStyles.sectionDivider} />
          </>
          )}

          {/* // НАЛОЖЕНИЕ */}
          <div>
            <div className={panelStyles.sectionTitle}>// НАЛОЖЕНИЕ</div>
            <div className={styles.paramSection}>
              <div className={styles.toggleLabel}>
                <span className={styles.paramLabel}>Показать оригинал</span>
                <button
                  type="button"
                  className={`${styles.squareToggle} ${overlayEnabled ? styles.squareToggleActive : ''}`}
                  onClick={() => setOverlayEnabled(!overlayEnabled)}
                />
              </div>
              {overlayEnabled && (
                <div className={styles.paramRow}>
                  <span className={styles.paramLabel}>Прозрачность</span>
                  <div className={styles.sliderRow}>
                    <input
                      type="range"
                      className={styles.sliderInput}
                      min={5} max={95} step={5}
                      value={Math.round(overlayOpacity * 100)}
                      onChange={(e) => setOverlayOpacity(Number(e.target.value) / 100)}
                    />
                    <span className={styles.sliderValue}>{Math.round(overlayOpacity * 100)}%</span>
                  </div>
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};
