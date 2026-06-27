import React, { useRef, useEffect, useCallback, useState } from 'react';
import styles from './WizardStep.module.css';
import { CanvasControls } from './CanvasControls';
import type { CropBbox } from '../../types/hierarchy';

interface Step2CropRotateProps {
  schemaImageUrl: string;
  cropBbox: CropBbox | null;
  isLoading: boolean;
  onCropBboxChange: (bbox: CropBbox) => void;
  onNext: () => Promise<void>;
  onBack: () => void;
}

type HandleId = 'tl' | 'tr' | 'br' | 'bl' | 'move';

interface CropRect {
  x: number; // normalized [0,1]
  y: number;
  w: number;
  h: number;
  rotation: 0 | 90 | 180 | 270;
}

function defaultCrop(rotation: 0 | 90 | 180 | 270): CropRect {
  return { x: 0.05, y: 0.05, w: 0.9, h: 0.9, rotation };
}

const HANDLE_SIZE = 12; // px

export const Step2CropRotate: React.FC<Step2CropRotateProps> = ({
  schemaImageUrl,
  cropBbox,
  isLoading,
  onCropBboxChange,
  onNext,
  onBack,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const animRef = useRef<number | null>(null);
  const draggingRef = useRef<HandleId | null>(null);
  const dragStartRef = useRef<{ mx: number; my: number; crop: CropRect } | null>(null);

  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [crop, setCrop] = useState<CropRect>(() => {
    if (cropBbox) {
      return {
        x: cropBbox.x,
        y: cropBbox.y,
        w: cropBbox.width,
        h: cropBbox.height,
        rotation: cropBbox.rotation,
      };
    }
    return defaultCrop(0);
  });

  // Track crop in ref for draw loop
  const cropRef = useRef(crop);
  useEffect(() => { cropRef.current = crop; }, [crop]);

  const imageLoadedRef = useRef(false);

  const getCanvasSize = useCallback(() => {
    const container = containerRef.current;
    if (!container) return { w: 800, h: 600 };
    return { w: container.clientWidth, h: container.clientHeight };
  }, []);

  // Compute image draw params (fit-contain)
  const getImageDrawParams = useCallback((
    imgW: number, imgH: number, canvW: number, canvH: number,
  ) => {
    const scale = Math.min((canvW * zoom) / imgW, (canvH * zoom) / imgH);
    const dw = imgW * scale;
    const dh = imgH * scale;
    const dx = (canvW - dw) / 2 + offset.x;
    const dy = (canvH - dh) / 2 + offset.y;
    return { dx, dy, dw, dh, scale };
  }, [zoom, offset]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imageRef.current;
    if (!canvas || !img || !imageLoadedRef.current) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { w: cw, h: ch } = getCanvasSize();
    canvas.width = cw;
    canvas.height = ch;

    ctx.clearRect(0, 0, cw, ch);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, cw, ch);

    const cr = cropRef.current;
    const rot = cr.rotation;

    // Effective display dimensions after rotation (90/270 swap width/height)
    const dispW = (rot === 90 || rot === 270) ? img.naturalHeight : img.naturalWidth;
    const dispH = (rot === 90 || rot === 270) ? img.naturalWidth : img.naturalHeight;
    const { dx, dy, dw, dh } = getImageDrawParams(dispW, dispH, cw, ch);

    // Helper: draw image with rotation centered at (dx, dy, dw, dh)
    const drawRotated = () => {
      ctx.save();
      ctx.translate(dx + dw / 2, dy + dh / 2);
      ctx.rotate(rot * Math.PI / 180);
      if (rot === 90 || rot === 270) {
        ctx.drawImage(img, -dh / 2, -dw / 2, dh, dw);
      } else {
        ctx.drawImage(img, -dw / 2, -dh / 2, dw, dh);
      }
      ctx.restore();
    };

    // 1. Draw full rotated image
    drawRotated();

    // 2. Crop overlay
    const rx = dx + cr.x * dw;
    const ry = dy + cr.y * dh;
    const rw = cr.w * dw;
    const rh = cr.h * dh;

    // Darken everything outside crop rect
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillRect(dx, dy, dw, dh);

    // 3. Re-draw crop area bright (clip to crop rect)
    ctx.save();
    ctx.beginPath();
    ctx.rect(rx, ry, rw, rh);
    ctx.clip();
    drawRotated();
    ctx.restore();

    // 4. Crop border
    ctx.strokeStyle = '#ff4500';
    ctx.lineWidth = 2;
    ctx.strokeRect(rx, ry, rw, rh);

    // 5. Handles
    const handles = getHandlePositions(rx, ry, rw, rh);
    ctx.fillStyle = '#ff4500';
    for (const pos of Object.values(handles)) {
      ctx.fillRect(pos.x - HANDLE_SIZE / 2, pos.y - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
    }
  }, [getCanvasSize, getImageDrawParams]);

  function getHandlePositions(rx: number, ry: number, rw: number, rh: number) {
    return {
      tl: { x: rx, y: ry },
      tr: { x: rx + rw, y: ry },
      br: { x: rx + rw, y: ry + rh },
      bl: { x: rx, y: ry + rh },
    };
  }

  useEffect(() => {
    const img = new Image();
    img.src = schemaImageUrl;
    img.onload = () => {
      imageRef.current = img;
      imageLoadedRef.current = true;
      draw();
    };
    return () => {
      if (animRef.current !== null) cancelAnimationFrame(animRef.current);
    };
  }, [schemaImageUrl, draw]);

  useEffect(() => { draw(); }, [draw, zoom, offset, crop]);

  const normToCanvas = useCallback((nx: number, ny: number) => {
    const canvas = canvasRef.current;
    const img = imageRef.current;
    if (!canvas || !img) return { cx: 0, cy: 0 };
    const { w: cw, h: ch } = getCanvasSize();
    const { dx, dy, dw, dh } = getImageDrawParams(img.naturalWidth, img.naturalHeight, cw, ch);
    return { cx: dx + nx * dw, cy: dy + ny * dh };
  }, [getCanvasSize, getImageDrawParams]);

  const canvasToNorm = useCallback((cx: number, cy: number) => {
    const canvas = canvasRef.current;
    const img = imageRef.current;
    if (!canvas || !img) return { nx: 0, ny: 0 };
    const { w: cw, h: ch } = getCanvasSize();
    const rot = cropRef.current.rotation;
    const dispW = (rot === 90 || rot === 270) ? img.naturalHeight : img.naturalWidth;
    const dispH = (rot === 90 || rot === 270) ? img.naturalWidth : img.naturalHeight;
    const { dx, dy, dw, dh } = getImageDrawParams(dispW, dispH, cw, ch);
    return { nx: (cx - dx) / dw, ny: (cy - dy) / dh };
  }, [getCanvasSize, getImageDrawParams]);

  const getEventPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return { mx: e.clientX - rect.left, my: e.clientY - rect.top };
  };

  const hitHandle = (mx: number, my: number): HandleId | null => {
    const cr = cropRef.current;
    const img = imageRef.current;
    if (!img) return null;
    const { w: cw, h: ch } = getCanvasSize();
    const rot = cr.rotation;
    const dispW = (rot === 90 || rot === 270) ? img.naturalHeight : img.naturalWidth;
    const dispH = (rot === 90 || rot === 270) ? img.naturalWidth : img.naturalHeight;
    const { dx, dy, dw, dh } = getImageDrawParams(dispW, dispH, cw, ch);
    const rx = dx + cr.x * dw;
    const ry = dy + cr.y * dh;
    const rw = cr.w * dw;
    const rh = cr.h * dh;
    const handles = getHandlePositions(rx, ry, rw, rh);
    const hs = HANDLE_SIZE;
    for (const [id, pos] of Object.entries(handles) as [HandleId, { x: number; y: number }][]) {
      if (Math.abs(mx - pos.x) <= hs && Math.abs(my - pos.y) <= hs) return id;
    }
    // Move (inside rect)
    if (mx >= rx && mx <= rx + rw && my >= ry && my <= ry + rh) return 'move';
    return null;
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { mx, my } = getEventPos(e);
    const hit = hitHandle(mx, my);
    if (hit) {
      draggingRef.current = hit;
      dragStartRef.current = { mx, my, crop: { ...cropRef.current } };
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!draggingRef.current || !dragStartRef.current) return;
    const { mx, my } = getEventPos(e);
    const { mx: sx, my: sy, crop: sc } = dragStartRef.current;
    const { nx: dnx, ny: dny } = canvasToNorm(mx - sx, my - sy);
    const { nx: ox, ny: oy } = canvasToNorm(0, 0);
    const ddx = dnx - ox;
    const ddy = dny - oy;

    const startNorm = canvasToNorm(sx, sy);
    const curNorm = canvasToNorm(mx, my);
    const dx2 = curNorm.nx - startNorm.nx;
    const dy2 = curNorm.ny - startNorm.ny;

    let next = { ...sc };
    const MIN = 0.05;
    switch (draggingRef.current) {
      case 'tl':
        next.x = Math.max(0, Math.min(sc.x + dx2, sc.x + sc.w - MIN));
        next.y = Math.max(0, Math.min(sc.y + dy2, sc.y + sc.h - MIN));
        next.w = sc.w - (next.x - sc.x);
        next.h = sc.h - (next.y - sc.y);
        break;
      case 'tr':
        next.y = Math.max(0, Math.min(sc.y + dy2, sc.y + sc.h - MIN));
        next.w = Math.max(MIN, Math.min(sc.w + dx2, 1 - sc.x));
        next.h = sc.h - (next.y - sc.y);
        break;
      case 'br':
        next.w = Math.max(MIN, Math.min(sc.w + dx2, 1 - sc.x));
        next.h = Math.max(MIN, Math.min(sc.h + dy2, 1 - sc.y));
        break;
      case 'bl':
        next.x = Math.max(0, Math.min(sc.x + dx2, sc.x + sc.w - MIN));
        next.w = sc.w - (next.x - sc.x);
        next.h = Math.max(MIN, Math.min(sc.h + dy2, 1 - sc.y));
        break;
      case 'move':
        next.x = Math.max(0, Math.min(sc.x + ddx, 1 - sc.w));
        next.y = Math.max(0, Math.min(sc.y + ddy, 1 - sc.h));
        break;
    }
    setCrop(next);
    onCropBboxChange({ x: next.x, y: next.y, width: next.w, height: next.h, rotation: next.rotation });
  };

  const handleMouseUp = () => { draggingRef.current = null; dragStartRef.current = null; };

  const handleRotate = () => {
    setCrop((prev) => {
      const newRot = ((prev.rotation + 90) % 360) as 0 | 90 | 180 | 270;
      const next = { ...defaultCrop(newRot) };
      onCropBboxChange({ x: next.x, y: next.y, width: next.w, height: next.h, rotation: newRot });
      return next;
    });
  };

  const handleNext = async () => {
    await onNext();
  };

  useEffect(() => {
    const { w, h } = getCanvasSize();
    if (canvasRef.current) {
      canvasRef.current.width = w;
      canvasRef.current.height = h;
    }
    draw();
  }, [getCanvasSize, draw]);

  // Suppress unused variable warning
  void normToCanvas;

  return (
    <div className={styles.layout}>
      <div className={styles.body}>
        {/* Sidebar */}
        <aside className={styles.sidebar}>
          <h3 className={styles.sidebarTitle}>Инструменты</h3>
          <button className={`${styles.toolBtn} ${styles.toolBtnActive}`} type="button">
            Кадрирование
          </button>
          <button className={styles.toolBtn} onClick={handleRotate} type="button">
            ↻ Поворот
          </button>
        </aside>

        {/* Canvas */}
        <div className={styles.canvasArea} ref={containerRef}>
          <canvas
            ref={canvasRef}
            className={styles.canvas}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            style={{ cursor: 'crosshair' }}
          />
          <CanvasControls
            onZoomIn={() => setZoom((z) => Math.min(z + 0.25, 4))}
            onZoomOut={() => setZoom((z) => Math.max(z - 0.25, 0.25))}
            onReset={() => { setZoom(1); setOffset({ x: 0, y: 0 }); }}
            onRotate={handleRotate}
            showRotate
          />
          {isLoading && (
            <div className={styles.spinnerOverlay}>
              <div className={styles.spinner} />
              <span className={styles.spinnerText}>Сохранение...</span>
            </div>
          )}
        </div>
      </div>

      <footer className={styles.footer}>
        <button className={styles.btnBack} onClick={onBack} type="button">
          ← Назад
        </button>
        <span className={styles.footerHint}>Кадрирование схемы</span>
        <button
          className={styles.btnNext}
          onClick={() => void handleNext()}
          disabled={isLoading}
          type="button"
        >
          Далее →
        </button>
      </footer>
    </div>
  );
};
