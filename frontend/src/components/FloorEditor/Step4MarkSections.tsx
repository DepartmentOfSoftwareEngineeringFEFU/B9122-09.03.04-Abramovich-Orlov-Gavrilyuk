import React, { useRef, useEffect, useCallback, useState } from 'react';
import styles from './WizardStep.module.css';
import { CanvasControls } from './CanvasControls';
import { NewSectionDialog } from './NewSectionDialog';
import { getSectionColor } from './sectionColors';
import { fitContain } from './croppedImage';
import { reconstructionApi } from '../../api/apiService';
import type { SectionDraft, Point2D } from '../../hooks/useFloorEditorWizard';
import type { SectionGeometry, CropBbox } from '../../types/hierarchy';

interface Step4MarkSectionsProps {
  schemaImageId: string | null;
  schemaImageUrl: string | null;
  cropBbox: CropBbox | null;
  wallPolygons: Point2D[][] | null;
  /** Edited mask blob URL from Step 3. When present, used instead of
   * /mask-preview so the user sees the result of their manual edits. */
  editedMaskUrl?: string | null;
  sectionDrafts: SectionDraft[];
  onAddSectionDraft: (geometry: SectionGeometry, number: number, color?: string) => void;
  onDeleteSectionDraft: (idx: number) => void;
  onClearAllDrafts: () => void;
  onNext: () => void;
  onBack: () => void;
  onGoToWalls: () => void;
}

interface PendingShape {
  points: [number, number][];
}

type Tool = 'rect' | 'polygon';
const CLOSE_DIST_PX = 12;

export const Step4MarkSections: React.FC<Step4MarkSectionsProps> = ({
  schemaImageId,
  schemaImageUrl,
  cropBbox,
  editedMaskUrl,
  sectionDrafts,
  onAddSectionDraft,
  onDeleteSectionDraft,
  onClearAllDrafts,
  onNext,
  onBack,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const maskImgRef = useRef<HTMLImageElement | null>(null);
  const [maskLoading, setMaskLoading] = useState(false);
  const [maskError, setMaskError] = useState<string | null>(null);

  const [zoom, setZoom] = useState(1);
  const [tool, setTool] = useState<Tool>('rect');
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [dragCur, setDragCur] = useState<{ x: number; y: number } | null>(null);
  const [polyPoints, setPolyPoints] = useState<Array<[number, number]>>([]);
  const [polyCursor, setPolyCursor] = useState<{ x: number; y: number } | null>(null);
  const [pendingShape, setPendingShape] = useState<PendingShape | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [defaultNumber, setDefaultNumber] = useState(1);

  const draftsRef = useRef(sectionDrafts);
  useEffect(() => { draftsRef.current = sectionDrafts; }, [sectionDrafts]);

  const getCanvasSize = useCallback(() => {
    const c = containerRef.current;
    return c ? { w: c.clientWidth, h: c.clientHeight } : { w: 800, h: 600 };
  }, []);

  // The MASK image (binary preview from backend) is the reference frame for
  // [0,1] coordinates — same convention as step 3.
  const getImageParams = useCallback((cw: number, ch: number) => {
    const m = maskImgRef.current;
    const w = m?.naturalWidth ?? cw;
    const h = m?.naturalHeight ?? ch;
    return fitContain(w, h, cw, ch, zoom);
  }, [zoom]);

  const toCanvas = useCallback((nx: number, ny: number) => {
    const { w: cw, h: ch } = getCanvasSize();
    const { dx, dy, dw, dh } = getImageParams(cw, ch);
    return { cx: dx + nx * dw, cy: dy + ny * dh };
  }, [getCanvasSize, getImageParams]);

  const toNorm = useCallback((cx: number, cy: number) => {
    const { w: cw, h: ch } = getCanvasSize();
    const { dx, dy, dw, dh } = getImageParams(cw, ch);
    return { nx: (cx - dx) / dw, ny: (cy - dy) / dh };
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

    // Draw the BINARY MASK (black walls on white) — same as step 3.
    // This is the actual wall data: every dark pixel is a wall, no vector
    // approximation. Sections are drawn on top of this.
    const m = maskImgRef.current;
    if (m && m.naturalWidth > 0 && m.naturalHeight > 0) {
      const { dx, dy, dw, dh } = getImageParams(cw, ch);
      if (dw > 0 && dh > 0) {
        ctx.drawImage(m, dx, dy, dw, dh);
      }
    }

    // Draw existing sections with palette colors
    for (let idx = 0; idx < draftsRef.current.length; idx++) {
      const draft = draftsRef.current[idx];
      const pts = draft.geometry.points;
      const color = draft.color ?? getSectionColor(idx, draft.id);

      ctx.fillStyle = `${color}55`; // 33% opacity fill
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      const first = toCanvas(pts[0][0], pts[0][1]);
      ctx.moveTo(first.cx, first.cy);
      for (let i = 1; i < pts.length; i++) {
        const p = toCanvas(pts[i][0], pts[i][1]);
        ctx.lineTo(p.cx, p.cy);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Number label — centroid of polygon vertices
      let cx = 0, cy = 0;
      for (const [px, py] of pts) { cx += px; cy += py; }
      cx /= pts.length;
      cy /= pts.length;
      const center = toCanvas(cx, cy);
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 13px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      // Dark halo for readability against bright fills
      ctx.shadowColor = 'rgba(0,0,0,0.8)';
      ctx.shadowBlur = 4;
      ctx.fillText(String(draft.number), center.cx, center.cy);
      ctx.shadowBlur = 0;
    }

    // Polygon-in-progress preview
    if (polyPoints.length > 0) {
      ctx.strokeStyle = '#ff6b1f';
      ctx.lineWidth = 2;
      ctx.fillStyle = 'rgba(255, 107, 31, 0.15)';
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      const p0 = toCanvas(polyPoints[0][0], polyPoints[0][1]);
      ctx.moveTo(p0.cx, p0.cy);
      for (let i = 1; i < polyPoints.length; i++) {
        const p = toCanvas(polyPoints[i][0], polyPoints[i][1]);
        ctx.lineTo(p.cx, p.cy);
      }
      if (polyCursor) {
        ctx.lineTo(polyCursor.x, polyCursor.y);
      }
      ctx.stroke();
      ctx.setLineDash([]);
      // Vertex dots
      for (const pt of polyPoints) {
        const c = toCanvas(pt[0], pt[1]);
        ctx.beginPath();
        ctx.arc(c.cx, c.cy, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#ff6b1f';
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }

    // Drag preview
    if (dragStart && dragCur) {
      const s = toCanvas(dragStart.x, dragStart.y);
      const e = toCanvas(dragCur.x, dragCur.y);
      ctx.strokeStyle = '#ff6b1f';
      ctx.lineWidth = 2;
      ctx.fillStyle = 'rgba(255, 107, 31, 0.15)';
      ctx.setLineDash([5, 5]);
      const rx = Math.min(s.cx, e.cx);
      const ry = Math.min(s.cy, e.cy);
      const rw = Math.abs(e.cx - s.cx);
      const rh = Math.abs(e.cy - s.cy);
      ctx.fillRect(rx, ry, rw, rh);
      ctx.strokeRect(rx, ry, rw, rh);
      ctx.setLineDash([]);
    }
  }, [getCanvasSize, getImageParams, toCanvas, dragStart, dragCur, polyPoints, polyCursor]);

  const drawRef = useRef(draw);
  useEffect(() => { drawRef.current = draw; }, [draw]);
  useEffect(() => { draw(); }, [draw, sectionDrafts]);

  // Keep the drawing buffer in sync with the displayed/container size. The
  // canvas has no CSS width/height, so its on-screen size equals the buffer
  // attributes set in draw() from the container's clientW/H. Without these
  // listeners the buffer goes stale whenever the layout reflows after the last
  // draw (mask finishing load, sidebar/footer settling, window resize) — a
  // stale buffer is what offsets the cursor from the image and breaks point
  // placement.
  useEffect(() => {
    const handleResize = () => drawRef.current();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => drawRef.current());
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Request the binary mask from the backend (same as step 3) and use it
  // as the canvas background. Loaded ONCE per (image, crop) — interacting
  // with the canvas must NOT refetch.
  const cropKey = cropBbox
    ? `${cropBbox.x}|${cropBbox.y}|${cropBbox.width}|${cropBbox.height}|${cropBbox.rotation}`
    : '';
  useEffect(() => {
    // Prefer the user-edited mask from Step 3, if available.
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

  const getPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const { nx, ny } = toNorm(e.clientX - rect.left, e.clientY - rect.top);
    return { x: Math.max(0, Math.min(1, nx)), y: Math.max(0, Math.min(1, ny)) };
  };

  const getRawCanvasPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const openDialogForShape = (points: [number, number][]) => {
    setPendingShape({ points });
    const maxNum = draftsRef.current.reduce((m, d) => Math.max(m, d.number), 0);
    setDefaultNumber(maxNum + 1);
    setDialogOpen(true);
  };

  const openDialogForRect = (x1: number, y1: number, x2: number, y2: number) => {
    openDialogForShape([[x1, y1], [x2, y1], [x2, y2], [x1, y2]]);
  };

  const finalizePolygon = (pts: Array<[number, number]>) => {
    if (pts.length < 3) return;
    if (pts.length > 32) {
      // Backend caps at 32 vertices — refuse silently rather than fail at save.
      // (Realistically users won't hit this for hand-traced sections.)
      return;
    }
    // Reject degenerate polygons (zero-area bounding box)
    let minX = pts[0][0], minY = pts[0][1], maxX = pts[0][0], maxY = pts[0][1];
    for (const [x, y] of pts) {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
    if (Math.abs(maxX - minX) < 0.02 || Math.abs(maxY - minY) < 0.02) return;
    openDialogForShape(pts);
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (tool === 'polygon') return; // polygon uses click, not drag
    const pt = getPos(e);
    setDragStart(pt);
    setDragCur(pt);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (tool === 'polygon') {
      if (polyPoints.length > 0) {
        setPolyCursor(getRawCanvasPos(e));
      }
      return;
    }
    if (!dragStart) return;
    setDragCur(getPos(e));
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (tool === 'polygon') return;
    if (!dragStart) return;
    const end = getPos(e);
    const x1 = Math.min(dragStart.x, end.x);
    const y1 = Math.min(dragStart.y, end.y);
    const x2 = Math.max(dragStart.x, end.x);
    const y2 = Math.max(dragStart.y, end.y);
    setDragStart(null);
    setDragCur(null);

    if (Math.abs(x2 - x1) < 0.02 || Math.abs(y2 - y1) < 0.02) return;
    openDialogForRect(x1, y1, x2, y2);
  };

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (tool !== 'polygon') return;
    const pt = getPos(e);
    const raw = getRawCanvasPos(e);
    // Close polygon if click is near the first vertex
    if (polyPoints.length >= 3) {
      const first = toCanvas(polyPoints[0][0], polyPoints[0][1]);
      const dx = raw.x - first.cx;
      const dy = raw.y - first.cy;
      if (Math.hypot(dx, dy) < CLOSE_DIST_PX) {
        const pts = polyPoints;
        setPolyPoints([]);
        setPolyCursor(null);
        finalizePolygon(pts);
        return;
      }
    }
    setPolyPoints((prev) => [...prev, [pt.x, pt.y]]);
  };

  const handleDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (tool !== 'polygon') return;
    e.preventDefault();
    if (polyPoints.length < 3) return;
    const pts = polyPoints;
    setPolyPoints([]);
    setPolyCursor(null);
    finalizePolygon(pts);
  };

  // ESC cancels in-progress polygon
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPolyPoints([]);
        setPolyCursor(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Reset in-progress polygon when switching away from polygon tool
  useEffect(() => {
    if (tool !== 'polygon') {
      setPolyPoints([]);
      setPolyCursor(null);
    }
  }, [tool]);

  const handleDialogConfirm = (num: number, color: string) => {
    if (!pendingShape) return;
    const geometry: SectionGeometry = { points: pendingShape.points };
    onAddSectionDraft(geometry, num, color);
    setDialogOpen(false);
    setPendingShape(null);
  };

  const handleClearAll = () => {
    if (window.confirm('Очистить все отсеки?')) onClearAllDrafts();
  };

  const takenNumbers = sectionDrafts.map((d) => d.number);

  return (
    <div className={styles.layout}>
      <div className={styles.body}>
        {/* Left sidebar */}
        <aside className={styles.sidebar}>
          <div className={styles.sidebarTitle}>Инструменты</div>
          <button
            className={`${styles.toolBtn} ${tool === 'rect' ? styles.toolBtnActive : ''}`}
            type="button"
            onClick={() => setTool('rect')}
          >
            ▭ Прямоугольник
          </button>
          <button
            className={`${styles.toolBtn} ${tool === 'polygon' ? styles.toolBtnActive : ''}`}
            type="button"
            onClick={() => setTool('polygon')}
            title="Клик — добавить вершину, двойной клик или клик возле первой точки — замкнуть. ESC — отмена."
          >
            ⬟ Полигон
          </button>
          <button
            className={`${styles.toolBtn} ${styles.toolBtnDanger}`}
            onClick={handleClearAll}
            type="button"
          >
            🗑 Очистить всё
          </button>

          {sectionDrafts.length > 0 && (
            <>
              <div className={styles.sidebarTitle} style={{ marginTop: '1rem' }}>
                Отсеки
              </div>
              <div className={styles.sectionList}>
                {sectionDrafts.map((d, idx) => (
                  <div key={idx} className={styles.sectionItem}>
                    <span
                      className={styles.sectionDot}
                      style={{ background: d.color ?? getSectionColor(idx, d.id), borderRadius: '2px' }}
                    />
                    Отсек {d.number}
                    <button
                      style={{
                        marginLeft: 'auto',
                        background: 'none',
                        border: 'none',
                        color: '#666',
                        cursor: 'pointer',
                        fontSize: '0.75rem',
                        padding: '0',
                      }}
                      onClick={() => onDeleteSectionDraft(idx)}
                      type="button"
                      title="Удалить отсек"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}
        </aside>

        {/* Canvas — light background */}
        <div className={styles.canvasArea} ref={containerRef}>
          <canvas
            ref={canvasRef}
            className={styles.canvas}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onClick={handleClick}
            onDoubleClick={handleDoubleClick}
            style={{ cursor: 'crosshair' }}
          />

          <CanvasControls
            onZoomIn={() => setZoom((z) => Math.min(z + 0.25, 4))}
            onZoomOut={() => setZoom((z) => Math.max(z - 0.25, 0.25))}
            onReset={() => setZoom(1)}
          />
          {maskLoading && (
            <div className={styles.spinnerOverlay}>
              <div className={styles.spinner} />
              <span className={styles.spinnerText}>Обработка изображения...</span>
            </div>
          )}
          {!maskLoading && maskError && (
            <div className={styles.spinnerOverlay}>
              <span className={styles.spinnerText} style={{ color: '#9ca3af' }}>
                {maskError}
              </span>
            </div>
          )}
        </div>

        {/* Right side panel — only when dialog is open */}
        {dialogOpen && (
          <NewSectionDialog
            open={dialogOpen}
            initialNumber={defaultNumber}
            takenNumbers={takenNumbers}
            onConfirm={handleDialogConfirm}
            onCancel={() => { setDialogOpen(false); setPendingShape(null); }}
          />
        )}
      </div>

      <footer className={styles.footer}>
        <button className={styles.btnBack} onClick={onBack} type="button">
          ← Назад
        </button>
        <span className={styles.footerHint} />
        <button
          className={styles.btnNext}
          onClick={onNext}
          disabled={sectionDrafts.length === 0}
          type="button"
        >
          Далее →
        </button>
      </footer>
    </div>
  );
};
