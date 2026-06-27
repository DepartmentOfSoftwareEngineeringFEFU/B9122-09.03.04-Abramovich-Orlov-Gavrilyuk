// Floor-stitch control-point canvas (Step 6). Renders a wall MASK backdrop
// (black walls on white, like the floor overview) and lets the operator place
// NUMBERED square markers on it. Used for both panels:
//   • эталон : the section's cropped wall mask;
//   • карта отсеков : the cropped floor-schema mask + section outlines overlaid.
// The same number on each side is one correspondence pair. Brutalist: square
// markers, no rounded shapes.
//
// All coordinate maths reuse ../controlPointCanvasCore (pure, tested). The
// component is presentational: clicks become onSelect (hit a marker) or onPlace
// (miss); the host decides what a click means for the current tool.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  R_HIT_PX,
  R_SNAP_PX,
  displayRadiusToNorm,
  hitTest,
  nearestWithin,
  toDisplayCoords,
  toImageCoords,
  type CanvasLayout,
} from '../controlPointCanvasCore';
import { pointLabel } from '../../lib/controlPoints';
import styles from './StitchPointCanvas.module.css';

export interface StitchPoint {
  id: string;
  x: number;
  y: number;
}

/** A section outline drawn on the master (карта отсеков) for orientation. */
export interface SectionOutline {
  number: number;
  points: [number, number][]; // normalised [0,1] over the master frame
}

export interface StitchPointCanvasProps {
  /** Wall-mask backdrop URL (section mask, or the floor-schema mask blob). */
  maskUrl: string | null;
  /** Draw the mask inverted → black walls on white (default true). */
  invert?: boolean;
  /** Section outlines to overlay (master panel only). */
  sectionOutlines?: SectionOutline[];

  points: StitchPoint[];
  activeId: string | null;
  /** Wall vertices (normalised) a freshly-placed point snaps to within R_SNAP. */
  snapTargets?: [number, number][];
  /** Only changes the cursor; click semantics stay generic (host interprets). */
  tool?: 'place' | 'delete';
  /** Per-id marker colour (same id ⇒ same colour on both panels). Default: orange. */
  colorOf?: (id: string) => string;

  /** Miss-click. `id` is the active id (MOVE) or '' when none is active (ADD). */
  onPlace(id: string, x: number, y: number): void;
  /** Click within R_HIT of an existing marker. */
  onSelect(id: string): void;
}

const MARKER_FILL = '#F05123';
const MARKER_BORDER = '#ffffff';
const OUTLINE_COLOR = '#2563eb';
const HALF = 11; // marker half-size px
const HALF_ACTIVE = 13;

/** Readable label colour for a marker fill — dark text on light fills, else white. */
const contrastText = (hex: string): string => {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return '#ffffff';
  const int = parseInt(m[1], 16);
  const r = (int >> 16) & 255;
  const g = (int >> 8) & 255;
  const b = int & 255;
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.6 ? '#111827' : '#ffffff';
};

const computeLayout = (
  elementWidth: number,
  elementHeight: number,
  imageWidth: number,
  imageHeight: number,
): CanvasLayout => {
  if (imageWidth <= 0 || imageHeight <= 0 || elementWidth <= 0 || elementHeight <= 0) {
    return { offsetX: 0, offsetY: 0, drawWidth: 0, drawHeight: 0 };
  }
  const scale = Math.min(elementWidth / imageWidth, elementHeight / imageHeight);
  const drawWidth = imageWidth * scale;
  const drawHeight = imageHeight * scale;
  return {
    offsetX: (elementWidth - drawWidth) / 2,
    offsetY: (elementHeight - drawHeight) / 2,
    drawWidth,
    drawHeight,
  };
};

export const StitchPointCanvas: React.FC<StitchPointCanvasProps> = ({
  maskUrl,
  invert = true,
  sectionOutlines,
  points,
  activeId,
  snapTargets,
  tool = 'place',
  colorOf,
  onPlace,
  onSelect,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);

  const [imageSize, setImageSize] = useState<{ w: number; h: number } | null>(null);
  const [elementSize, setElementSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });

  // Load the mask backdrop.
  useEffect(() => {
    let cancelled = false;
    imageRef.current = null;
    if (!maskUrl) {
      setImageSize(null);
      return;
    }
    const img = new Image();
    img.onload = () => {
      if (cancelled) return;
      imageRef.current = img;
      setImageSize({ w: img.naturalWidth, h: img.naturalHeight });
    };
    img.onerror = () => {
      if (cancelled) return;
      imageRef.current = null;
      setImageSize(null);
    };
    img.src = maskUrl;
    return () => {
      cancelled = true;
    };
  }, [maskUrl]);

  // Track rendered element size (CSS px).
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      const rect = el.getBoundingClientRect();
      setElementSize({ w: rect.width, h: rect.height });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const layout: CanvasLayout = imageSize
    ? computeLayout(elementSize.w, elementSize.h, imageSize.w, imageSize.h)
    : { offsetX: 0, offsetY: 0, drawWidth: 0, drawHeight: 0 };

  // Draw: mask → section outlines → numbered square markers (DPR-aware).
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const cssW = elementSize.w;
    const cssH = elementSize.h;
    if (cssW <= 0 || cssH <= 0) return;

    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, cssW, cssH);

    const img = imageRef.current;
    if (img && layout.drawWidth > 0) {
      ctx.save();
      if (invert) ctx.filter = 'invert(1)';
      ctx.drawImage(img, layout.offsetX, layout.offsetY, layout.drawWidth, layout.drawHeight);
      ctx.restore();
    }

    // Section outlines + number (master orientation).
    if (sectionOutlines && layout.drawWidth > 0) {
      ctx.strokeStyle = OUTLINE_COLOR;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([6, 4]);
      for (const outline of sectionOutlines) {
        if (outline.points.length < 3) continue;
        ctx.beginPath();
        outline.points.forEach(([nx, ny], i) => {
          const d = toDisplayCoords({ x: nx, y: ny }, layout);
          if (i === 0) ctx.moveTo(d.x, d.y);
          else ctx.lineTo(d.x, d.y);
        });
        ctx.closePath();
        ctx.stroke();
        // Number at centroid.
        let ax = 0;
        let ay = 0;
        for (const [px, py] of outline.points) {
          ax += px;
          ay += py;
        }
        const c = toDisplayCoords(
          { x: ax / outline.points.length, y: ay / outline.points.length },
          layout,
        );
        ctx.setLineDash([]);
        ctx.fillStyle = OUTLINE_COLOR;
        ctx.font = 'bold 15px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`№${outline.number}`, c.x, c.y);
        ctx.setLineDash([6, 4]);
      }
      ctx.setLineDash([]);
    }

    // Numbered square markers.
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const point of points) {
      const isActive = point.id === activeId;
      const h = isActive ? HALF_ACTIVE : HALF;
      const { x, y } = toDisplayCoords(point, layout);
      const fill = colorOf ? colorOf(point.id) : MARKER_FILL;
      if (isActive) {
        ctx.save();
        ctx.globalAlpha = 0.25;
        ctx.fillStyle = fill;
        ctx.fillRect(x - h - 3, y - h - 3, (h + 3) * 2, (h + 3) * 2);
        ctx.restore();
      }
      ctx.fillStyle = fill;
      ctx.fillRect(x - h, y - h, h * 2, h * 2);
      ctx.lineWidth = isActive ? 3 : 2;
      ctx.strokeStyle = MARKER_BORDER;
      ctx.strokeRect(x - h, y - h, h * 2, h * 2);
      ctx.fillStyle = contrastText(fill);
      ctx.font = `bold ${isActive ? 13 : 12}px monospace`;
      ctx.fillText(pointLabel(point.id), x, y + 0.5);
    }
  }, [points, activeId, layout, invert, sectionOutlines, colorOf, elementSize.w, elementSize.h, imageSize]);

  const handleClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const el = containerRef.current;
      if (!el || layout.drawWidth <= 0) return;
      const rect = el.getBoundingClientRect();
      const norm = toImageCoords(event.clientX - rect.left, event.clientY - rect.top, layout);
      if (!norm) return;

      const hitRadiusNorm = displayRadiusToNorm(R_HIT_PX, layout.drawWidth);
      const hitId = hitTest(norm, points, hitRadiusNorm);
      if (hitId !== null) {
        onSelect(hitId);
        return;
      }

      let placed = norm;
      if (snapTargets && snapTargets.length > 0) {
        const snapRadiusNorm = displayRadiusToNorm(R_SNAP_PX, layout.drawWidth);
        const snapped = nearestWithin(norm, snapTargets, snapRadiusNorm);
        if (snapped) placed = { x: snapped[0], y: snapped[1] };
      }
      onPlace(activeId ?? '', placed.x, placed.y);
    },
    [layout, points, activeId, snapTargets, onPlace, onSelect],
  );

  return (
    <div
      ref={containerRef}
      className={`${styles.container} ${tool === 'delete' ? styles.deleting : ''}`}
      onClick={handleClick}
    >
      <canvas ref={canvasRef} className={styles.canvas} style={{ width: '100%', height: '100%' }} />
    </div>
  );
};
