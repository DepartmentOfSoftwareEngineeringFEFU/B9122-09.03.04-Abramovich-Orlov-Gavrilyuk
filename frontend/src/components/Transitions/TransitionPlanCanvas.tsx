import React, { useRef, useEffect, useState, useCallback } from 'react';
import type { FloorTransition, TransitionEditorMode } from '../../types/transitions';
import { fitContain } from '../FloorEditor/croppedImage';
import styles from './TransitionPlanCanvas.module.css';

type ActiveTool = 'pan' | 'teleport' | 'delete';

interface TransitionPlanCanvasProps {
  imageUrl: string;
  transitions: FloorTransition[];
  reconstructionId: number;
  mode: TransitionEditorMode;
  activeTool?: ActiveTool;
  onCanvasSubmit: (geometry: number[][]) => void;
  onDeleteTransition?: (id: number) => void;
}

const CLOSE_DIST_PX = 12;

export const TransitionPlanCanvas: React.FC<TransitionPlanCanvasProps> = ({
  imageUrl,
  transitions,
  reconstructionId,
  mode,
  activeTool = 'pan',
  onCanvasSubmit,
  onDeleteTransition,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  const [polyPoints, setPolyPoints] = useState<Array<[number, number]>>([]);
  const [polyCursor, setPolyCursor] = useState<{ x: number; y: number } | null>(null);

  // Pre-load image for the canvas
  useEffect(() => {
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (!cancelled) {
        imgRef.current = img;
        drawRef.current();
      }
    };
    img.src = imageUrl;
    return () => { cancelled = true; };
  }, [imageUrl]);

  const getCanvasSize = useCallback(() => {
    // Source the size from the canvas's OWN painted box — the exact rect that
    // getPos() uses for hit-testing. Reading the wrapper (container) instead can
    // diverge from the canvas (border-box, inline-block quirks) and offsets clicks.
    const cv = canvasRef.current;
    if (cv) {
      const r = cv.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) {
        return { w: Math.round(r.width), h: Math.round(r.height) };
      }
    }
    const c = containerRef.current;
    return c ? { w: c.clientWidth, h: c.clientHeight } : { w: 800, h: 600 };
  }, []);

  const getImageParams = useCallback((cw: number, ch: number) => {
    const m = imgRef.current;
    const w = m?.naturalWidth ?? cw;
    const h = m?.naturalHeight ?? ch;
    return fitContain(w, h, cw, ch, 1);
  }, []);

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

    const img = imgRef.current;
    if (img) {
      const { dx, dy, dw, dh } = getImageParams(cw, ch);
      ctx.drawImage(img, dx, dy, dw, dh);
    }

    // Draw saved transitions
    const fromPoints = transitions.filter((t) => t.from_reconstruction_id === reconstructionId);
    const toPoints = transitions.filter((t) => t.to_reconstruction_id === reconstructionId);

    const drawGeom = (pts: number[][], color: string, label: string) => {
      if (pts.length === 0) return;
      ctx.strokeStyle = color;
      ctx.fillStyle = color + '33'; // 20% opacity
      ctx.lineWidth = 2;
      ctx.beginPath();
      const p0 = toCanvas(pts[0][0], pts[0][1]);
      ctx.moveTo(p0.cx, p0.cy);
      for (let i = 1; i < pts.length; i++) {
        const p = toCanvas(pts[i][0], pts[i][1]);
        ctx.lineTo(p.cx, p.cy);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Label at centroid
      const xs = pts.map(p => p[0]);
      const ys = pts.map(p => p[1]);
      const cxNorm = xs.reduce((a, b) => a + b, 0) / xs.length;
      const cyNorm = ys.reduce((a, b) => a + b, 0) / ys.length;
      const cCenter = toCanvas(cxNorm, cyNorm);

      ctx.fillStyle = '#000';
      ctx.fillRect(cCenter.cx - 20, cCenter.cy - 10, 40, 20);
      ctx.fillStyle = '#fff';
      ctx.font = '10px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, cCenter.cx, cCenter.cy);
    };

    fromPoints.forEach(t => {
      if (t.from_geometry && t.from_geometry.length > 0) {
        drawGeom(t.from_geometry, '#ff6b1f', `FROM: ${t.name}`);
      } else {
        // Fallback for points
        const p = toCanvas(t.from_x, t.from_y);
        ctx.fillStyle = '#ff6b1f';
        ctx.beginPath(); ctx.arc(p.cx, p.cy, 8, 0, 2 * Math.PI); ctx.fill();
      }
    });

    toPoints.forEach(t => {
      if (t.to_geometry && t.to_geometry.length > 0) {
        drawGeom(t.to_geometry, '#888', `TO: ${t.name}`);
      } else {
        const p = toCanvas(t.to_x, t.to_y);
        ctx.fillStyle = '#888';
        ctx.beginPath(); ctx.arc(p.cx, p.cy, 8, 0, 2 * Math.PI); ctx.fill();
      }
    });

    // Polygon-in-progress preview
    if (polyPoints.length > 0) {
      ctx.strokeStyle = '#22c55e';
      ctx.lineWidth = 2;
      ctx.fillStyle = 'rgba(34, 197, 94, 0.15)';
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
        ctx.fillStyle = '#22c55e';
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }

  }, [getCanvasSize, getImageParams, toCanvas, transitions, reconstructionId, polyPoints, polyCursor, mode, activeTool]);

  const drawRef = useRef(draw);
  useEffect(() => { drawRef.current = draw; }, [draw]);
  useEffect(() => { draw(); }, [draw]);

  useEffect(() => {
    const handleResize = () => drawRef.current();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Redraw whenever the canvas box itself changes size (mode banner toggling,
  // sidebar reflow, etc.) so the drawing buffer never goes stale relative to the
  // displayed size — a stale buffer is what offsets the cursor from the image.
  useEffect(() => {
    const el = canvasRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => drawRef.current());
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const getPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const { nx, ny } = toNorm(e.clientX - rect.left, e.clientY - rect.top);
    return { x: Math.max(0, Math.min(1, nx)), y: Math.max(0, Math.min(1, ny)) };
  };

  const getRawCanvasPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const finalizePolygon = (pts: Array<[number, number]>) => {
    if (pts.length < 3) return;
    onCanvasSubmit(pts);
  };

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (activeTool === 'delete') {
      // Find nearest transition click
      const pt = getPos(e);
      let closestId: number | null = null;
      let minD = Infinity;

      const check = (x: number, y: number, id: number) => {
         const dx = x - pt.x; const dy = y - pt.y;
         const d = Math.hypot(dx, dy);
         if (d < 0.05 && d < minD) { minD = d; closestId = id; }
      }

      transitions.forEach(t => {
        if (t.from_reconstruction_id === reconstructionId) check(t.from_x, t.from_y, t.id);
        if (t.to_reconstruction_id === reconstructionId) check(t.to_x, t.to_y, t.id);
      });
      if (closestId !== null && onDeleteTransition) {
        onDeleteTransition(closestId);
      }
      return;
    }

    if (mode.type === 'idle' && activeTool !== 'teleport') return;

    const pt = getPos(e);
    const raw = getRawCanvasPos(e);
    
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
    if (activeTool === 'delete') return;
    if (mode.type === 'idle' && activeTool !== 'teleport') return;
    e.preventDefault();
    if (polyPoints.length < 3) return;
    const pts = polyPoints;
    setPolyPoints([]);
    setPolyCursor(null);
    finalizePolygon(pts);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (polyPoints.length > 0) {
      setPolyCursor(getRawCanvasPos(e));
    }
  };

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

  const isCrosshair = mode.type !== 'idle' || activeTool === 'teleport';
  const isDeleteMode = activeTool === 'delete';

  return (
    <div
      className={`${styles.wrapper} ${isCrosshair ? styles.wrapperCrosshair : ''} ${isDeleteMode ? styles.wrapperDefault : ''}`}
      ref={containerRef}
      style={{ width: '100%', height: '100%', overflow: 'hidden' }}
    >
      <canvas
        ref={canvasRef}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
        onMouseMove={handleMouseMove}
        style={{ display: 'block', width: '100%', height: '100%' }}
      />
    </div>
  );
};
