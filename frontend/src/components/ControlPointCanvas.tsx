// Shared canvas widget for placing/selecting control points on a backdrop image.
//
// Reused by the per-section pass (StepControlPoints) and the floor
// master pass. It is purely presentational: all coordinate maths live
// in ./controlPointCanvasCore (pure, testable). The widget renders the backdrop,
// draws orange crosshair markers with their stable ID labels, and turns canvas
// clicks into onSelect (hit an existing point) or onPlace (add/move the active
// point, with snap-to-vertex).
//
// devicePixelRatio-aware: the <canvas> backing store is sized to CSS px * DPR so
// crosshairs stay crisp on HiDPI screens; all input maths stay in CSS px.

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
} from './controlPointCanvasCore';
import { colourForId } from '../lib/controlPoints';
import styles from './ControlPointCanvas.module.css';

export interface ControlPointCanvasProps {
  imageUrl: string; // backdrop (photo / mask / inverted)
  points: { id: string; x: number; y: number }[]; // normalised [0,1]
  activeId: string | null;
  snapTargets?: [number, number][]; // wall vertices (normalised) for R_SNAP
  opacity?: number; // overlay cross-fade (0..1)
  // Click that misses all points. `id` is the active point's id (MOVE it) or the
  // empty string '' when nothing is active (ADD a new point — the host mints the
  // id). Coords are already snapped to a wall vertex when within R_SNAP_PX.
  onPlace(id: string, x: number, y: number): void;
  onSelect(id: string): void; // click within R_HIT_PX selects that point
}

const CROSSHAIR_ARM_PX = 9;
const CROSSHAIR_GAP_PX = 3;

// object-fit: contain layout of the image inside an element of the given size.
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

export const ControlPointCanvas: React.FC<ControlPointCanvasProps> = ({
  imageUrl,
  points,
  activeId,
  snapTargets,
  opacity = 1,
  onPlace,
  onSelect,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);

  const [imageSize, setImageSize] = useState<{ w: number; h: number } | null>(null);
  const [elementSize, setElementSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });

  // Load backdrop image (kept in a ref so draw can read it synchronously).
  useEffect(() => {
    let cancelled = false;
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
    img.src = imageUrl;
    return () => {
      cancelled = true;
    };
  }, [imageUrl]);

  // Track the rendered size of the container (ResizeObserver -> CSS px).
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

  // Draw backdrop + crosshair markers; DPR-aware so it stays crisp on HiDPI.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const cssW = elementSize.w;
    const cssH = elementSize.h;
    if (cssW <= 0 || cssH <= 0) return;

    // Backing store in device px; logical drawing in CSS px.
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    const img = imageRef.current;
    if (img && layout.drawWidth > 0) {
      ctx.globalAlpha = opacity;
      ctx.drawImage(img, layout.offsetX, layout.offsetY, layout.drawWidth, layout.drawHeight);
      ctx.globalAlpha = 1;
    }

    // Markers: crosshair coloured by ID (the SAME id ⇒ the SAME colour on every
    // panel — AC2 anti-confusion). The ACTIVE point is emphasised with a thicker
    // arm + a surrounding ring rather than a different hue, so its identity colour
    // stays readable.
    ctx.font = '12px monospace';
    ctx.textBaseline = 'bottom';
    for (const point of points) {
      const isActive = point.id === activeId;
      const colour = colourForId(point.id);
      const { x, y } = toDisplayCoords(point, layout);
      ctx.strokeStyle = colour;
      ctx.fillStyle = colour;
      ctx.lineWidth = isActive ? 2.5 : 1.5;
      // Horizontal arms (gap at center so the precise point stays visible).
      ctx.beginPath();
      ctx.moveTo(x - CROSSHAIR_ARM_PX, y);
      ctx.lineTo(x - CROSSHAIR_GAP_PX, y);
      ctx.moveTo(x + CROSSHAIR_GAP_PX, y);
      ctx.lineTo(x + CROSSHAIR_ARM_PX, y);
      // Vertical arms.
      ctx.moveTo(x, y - CROSSHAIR_ARM_PX);
      ctx.lineTo(x, y - CROSSHAIR_GAP_PX);
      ctx.moveTo(x, y + CROSSHAIR_GAP_PX);
      ctx.lineTo(x, y + CROSSHAIR_ARM_PX);
      ctx.stroke();
      // Active ring (same colour, just emphasis).
      if (isActive) {
        ctx.beginPath();
        ctx.arc(x, y, CROSSHAIR_ARM_PX + 3, 0, Math.PI * 2);
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
      ctx.fillText(point.id, x + CROSSHAIR_ARM_PX + 2, y - 2);
    }
  }, [points, activeId, layout, opacity, elementSize.w, elementSize.h, imageSize]);

  const handleClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const el = containerRef.current;
      if (!el || layout.drawWidth <= 0) return;
      const rect = el.getBoundingClientRect();
      const cssX = event.clientX - rect.left;
      const cssY = event.clientY - rect.top;
      const norm = toImageCoords(cssX, cssY, layout);
      if (!norm) return;

      // 1) Selecting an existing point takes precedence over adding.
      const hitRadiusNorm = displayRadiusToNorm(R_HIT_PX, layout.drawWidth);
      const hitId = hitTest(norm, points, hitRadiusNorm);
      if (hitId !== null) {
        onSelect(hitId);
        return;
      }

      // 2) Otherwise place — snap to a nearby wall vertex first. When a point is
      //    active this MOVES it; when nothing is active it ADDS a new point, which
      //    the host signals by an empty id (the only id-bearing callback is
      // onPlace, per the fixed prop contract — see phase-).
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
    <div ref={containerRef} className={styles.container} onClick={handleClick}>
      <canvas
        ref={canvasRef}
        className={styles.canvas}
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  );
};
