import React, { useRef, useEffect, useCallback, useState } from 'react';
import styles from './WizardStep.module.css';
import step5Styles from './Step5BindPlans.module.css';
import { reconstructionApi } from '../../api/apiService';
import { PlanGalleryPicker } from './PlanGalleryPicker';
import { getSectionColor } from './sectionColors';
import { fitContain } from './croppedImage';
import type { SectionDraft, Point2D } from '../../hooks/useFloorEditorWizard';
import type { Building, CropBbox } from '../../types/hierarchy';

interface Step5BindPlansProps {
  schemaImageId: string | null;
  schemaImageUrl: string | null;
  cropBbox: CropBbox | null;
  editedMaskUrl: string | null;
  sectionDrafts: SectionDraft[];
  wallPolygons: Point2D[][] | null;
  buildings: Building[];
  isLoading: boolean;
  /** Id of the floor the wizard is opened for — restricts the plan gallery. */
  floorId: number | null;
  onBind: (sectionIdx: number, reconstructionId: number | null) => void;
  onSave: () => Promise<void>;
  onSaveAndExit: () => Promise<void>;
  onBack: () => void;
}

export const Step5BindPlans: React.FC<Step5BindPlansProps> = ({
  schemaImageId,
  schemaImageUrl,
  cropBbox,
  editedMaskUrl,
  sectionDrafts,
  buildings,
  isLoading,
  floorId,
  onBind,
  onSave,
  onBack,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeIdx, setActiveIdx] = useState(0);

  const getCanvasSize = useCallback(() => {
    const c = containerRef.current;
    return c ? { w: c.clientWidth, h: c.clientHeight } : { w: 200, h: 200 };
  }, []);

  const maskImgRef = useRef<HTMLImageElement | null>(null);
  const [maskLoading, setMaskLoading] = useState(false);
  const [maskError, setMaskError] = useState<string | null>(null);

  const getImageParams = useCallback((cw: number, ch: number) => {
    const m = maskImgRef.current;
    const w = m?.naturalWidth ?? cw;
    const h = m?.naturalHeight ?? ch;
    return fitContain(w, h, cw, ch, 1);
  }, []);

  const toCanvas = useCallback((nx: number, ny: number) => {
    const { w: cw, h: ch } = getCanvasSize();
    const m = maskImgRef.current;
    if (!m) {
      return { cx: nx * cw, cy: ny * ch };
    }
    const { dx, dy, dw, dh } = getImageParams(cw, ch);
    return { cx: dx + nx * dw, cy: dy + ny * dh };
  }, [getCanvasSize, getImageParams]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const { w: cw, h: ch } = getCanvasSize();
    canvas.width = cw;
    canvas.height = ch;
    ctx.clearRect(0, 0, cw, ch);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, cw, ch);

    // Draw the BINARY MASK inverted: walls become BLACK on WHITE background
    // (the raw mask from the server is white walls on black; invert for the
    // light final-look the user expects).
    const m = maskImgRef.current;
    if (m && m.naturalWidth > 0 && m.naturalHeight > 0) {
      const { dx, dy, dw, dh } = getImageParams(cw, ch);
      if (dw > 0 && dh > 0) {
        ctx.save();
        ctx.filter = 'invert(1)';
        ctx.drawImage(m, dx, dy, dw, dh);
        ctx.restore();
      }
    }

    // Section drafts
    sectionDrafts.forEach((draft, idx) => {
      const pts = draft.geometry.points;
      if (!pts || pts.length < 3) return;

      const isActive = idx === activeIdx;
      
      // Match primer colors:
      // Active: fill #F05123, opacity 0.9.  Inactive: fill #F3F4F6
      // Stroke is always #D1D5DB
      ctx.fillStyle = isActive ? 'rgba(240, 81, 35, 0.9)' : '#f3f4f6';
      ctx.strokeStyle = '#d1d5db';
      ctx.lineWidth = 2;

      ctx.beginPath();
      const f = toCanvas(pts[0][0], pts[0][1]);
      ctx.moveTo(f.cx, f.cy);
      for (let i = 1; i < pts.length; i++) {
        const p = toCanvas(pts[i][0], pts[i][1]);
        ctx.lineTo(p.cx, p.cy);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Section number label
      let avgX = 0, avgY = 0;
      for (const [px, py] of pts) { avgX += px; avgY += py; }
      avgX /= pts.length;
      avgY /= pts.length;
      const center = toCanvas(avgX, avgY);
      
      ctx.fillStyle = isActive ? '#ffffff' : '#6b7280';
      ctx.font = 'bold 16px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(draft.number), center.cx, center.cy);
    });
  }, [getCanvasSize, toCanvas, getImageParams, sectionDrafts, activeIdx]);

  const drawRef = useRef(draw);
  useEffect(() => { drawRef.current = draw; }, [draw]);
  useEffect(() => { draw(); }, [draw, sectionDrafts]);

  // Request the binary mask from the backend
  const cropKey = cropBbox
    ? `${cropBbox.x}|${cropBbox.y}|${cropBbox.width}|${cropBbox.height}|${cropBbox.rotation}`
    : '';
  useEffect(() => {
    if (editedMaskUrl) {
      let cancelled = false;
      setMaskLoading(true);
      setMaskError(null);
      const img = new Image();
      img.onload = () => {
        if (cancelled) return;
        maskImgRef.current = img;
        setMaskLoading(false);
        drawRef.current();
      };
      img.onerror = () => {
        if (cancelled) return;
        maskImgRef.current = null;
        setMaskError('Не удалось загрузить отредактированную маску');
        setMaskLoading(false);
      };
      img.src = editedMaskUrl;
      return () => { cancelled = true; };
    }

    if (!schemaImageId) {
      maskImgRef.current = null;
      setMaskError(schemaImageUrl ? 'Нет идентификатора фото' : 'Загрузите фото на шаге 1');
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    setMaskLoading(true);
    setMaskError(null);

    const cropPayload = cropBbox
      ? { x: cropBbox.x, y: cropBbox.y, width: cropBbox.width, height: cropBbox.height }
      : null;
    const rotation = cropBbox?.rotation ?? 0;

    reconstructionApi
      .previewMask(schemaImageId, cropPayload, rotation)
      .then((url) => {
        if (cancelled) { URL.revokeObjectURL(url); return; }
        objectUrl = url;
        const img = new Image();
        img.onload = () => {
          if (cancelled) return;
          if (img.naturalWidth === 0 || img.naturalHeight === 0) {
            setMaskError('Не удалось обработать изображение');
            maskImgRef.current = null;
          } else {
            maskImgRef.current = img;
          }
          setMaskLoading(false);
          drawRef.current();
        };
        img.onerror = () => {
          if (cancelled) return;
          maskImgRef.current = null;
          setMaskError('Не удалось загрузить превью');
          setMaskLoading(false);
        };
        img.src = url;
      })
      .catch(() => {
        if (cancelled) return;
        maskImgRef.current = null;
        setMaskError('Ошибка генерации маски на сервере');
        setMaskLoading(false);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schemaImageId, cropKey, editedMaskUrl]);

  // Cleanup canvas on unmount
  useEffect(() => {
    return () => {
      if (canvasRef.current) {
        const ctx = canvasRef.current.getContext('2d');
        if (ctx) ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
      }
    };
  }, []);

  const activeDraft = sectionDrafts[activeIdx] ?? null;
  const selectedReconId = activeDraft?.reconstruction_id ?? null;

  return (
    <div className={styles.layout}>
      <div className={step5Styles.body}>
        {/* Left: section list with colored chips */}
        <aside className={step5Styles.sectionsPanel}>
          <div className={step5Styles.panelTitle}>ОТСЕКИ НА СХЕМЕ</div>
          <div className={step5Styles.sectionList}>
            {sectionDrafts.map((d, idx) => {
              const color = getSectionColor(idx, d.id);
              return (
                <button
                  key={idx}
                  className={`${step5Styles.sectionBtn} ${idx === activeIdx ? step5Styles.sectionBtnActive : ''}`}
                  onClick={() => setActiveIdx(idx)}
                  type="button"
                >
                  <span
                    className={step5Styles.sectionDot}
                    style={{ background: color }}
                  >
                    {d.number}
                  </span>
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                    <span style={{ fontWeight: 600 }}>Отсек {d.number}</span>
                  </div>
                  {d.reconstruction_id !== null && (
                    <span className={step5Styles.checkmark}>✓</span>
                  )}
                </button>
              );
            })}
          </div>
        </aside>

        {/* Center: gallery */}
        <div className={step5Styles.galleryPanel}>
          <PlanGalleryPicker
            buildings={buildings}
            selectedReconstructionId={selectedReconId}
            assignedReconstructionIds={sectionDrafts.map(d => d.reconstruction_id).filter((id): id is number => id !== null)}
            restrictToFloorId={floorId}
            onSelect={(id) => {
              const newId = id === selectedReconId ? null : id;
              onBind(activeIdx, newId);
            }}
          />
        </div>

        {/* Right: preview */}
        <div className={step5Styles.previewPanel}>
          <div className={step5Styles.canvasWrap} ref={containerRef} style={{ position: 'relative' }}>
            <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />
            {maskLoading && (
              <div className={styles.spinnerOverlay} style={{ position: 'absolute', inset: 0, background: 'rgba(255,255,255,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span className={styles.spinnerText}>Загрузка маски...</span>
              </div>
            )}
            {!maskLoading && maskError && (
              <div className={styles.spinnerOverlay} style={{ position: 'absolute', inset: 0, background: 'rgba(255,255,255,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span className={styles.spinnerText} style={{ color: '#9ca3af' }}>{maskError}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <footer className={styles.footer} style={{ background: '#ffffff', borderTop: '1px solid #e5e7eb', padding: '0.75rem 1.5rem', justifyContent: 'space-between' }}>
        <button className={styles.btnBack} onClick={onBack} type="button" style={{ color: '#374151', borderColor: '#d1d5db', background: '#ffffff', borderRadius: '0' }}>
          ← Назад
        </button>
        <span className={styles.footerHint} />
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          
          <button
            className={styles.btnSave}
            onClick={() => void onSave()}
            disabled={isLoading}
            type="button"
            style={{ background: '#f05123', color: '#ffffff', border: 'none', borderRadius: '0' }}
          >
            Сохранить
          </button>
        </div>
      </footer>
    </div>
  );
};
