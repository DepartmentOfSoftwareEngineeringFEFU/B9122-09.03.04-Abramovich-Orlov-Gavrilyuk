// Alignment-verification overlay for the Building Assembly page (subfeature A).
// Draws the LOWER (reference) floor's wall mask, then the UPPER (moving) floor's
// wall mask warped onto the lower frame by the solved similarity transform, with
// globalAlpha + 'multiply' so only walls show (the Step7 technique). 2D canvas
// only — there is nothing to dispose().
//
// The upper floor's `building_transform` maps its mask-px → the BUILDING
// reference frame; the lower floor's does the same. To land the upper mask on
// the LOWER frame we apply (lower⁻¹ ∘ upper); for a pair whose lower floor IS the
// building reference (identity) this collapses to the upper transform alone.
//
// All similarity maths are the pure helper warpPointForOverlay (unit-tested in
// the node env). No `any`.

import React, { useCallback, useEffect, useRef } from 'react';
import { fitContain } from '../FloorEditor/croppedImage';
import type { StitchTransform } from '../../types/buildingAssembly';

interface FloorOverlayPreviewProps {
  /** Lower/reference floor wall-mask URL (backdrop). */
  lowerMaskUrl: string | null;
  /** Upper/moving floor wall-mask URL (warped overlay). */
  upperMaskUrl: string | null;
  /** Upper floor mask-px → reference-frame px. null → overlay is not drawn. */
  upperTransform: StitchTransform | null;
  /** Lower floor mask-px → reference-frame px. null/reference → identity. */
  lowerTransform: StitchTransform | null;
  /** Overlay opacity (0..1). */
  alpha?: number;
}

/** Identity similarity (no scale change, no rotation, no translation). */
const IDENTITY: StitchTransform = {
  scale: 1,
  rotation_rad: 0,
  tx: 0,
  ty: 0,
  residual_rms_px: 0,
  n_points: 0,
};

/**
 * Apply a similarity transform `s·R(θ)·p + t` to a point. This is the core map
 * used to place the upper mask onto the lower frame; the component first composes
 * the upper transform with the inverse of the lower one (see compose helpers).
 * Pure — unit-tested (`warps upper point onto lower frame`).
 */
export const warpPointForOverlay = (
  pt: { x: number; y: number },
  transform: StitchTransform,
): { x: number; y: number } => {
  const { scale, rotation_rad, tx, ty } = transform;
  const cos = Math.cos(rotation_rad);
  const sin = Math.sin(rotation_rad);
  return {
    x: scale * (cos * pt.x - sin * pt.y) + tx,
    y: scale * (sin * pt.x + cos * pt.y) + ty,
  };
};

/** Invert a similarity transform (s,θ,t) → (1/s, −θ, −R(−θ)·t/s). */
const invertTransform = (t: StitchTransform): StitchTransform => {
  const invScale = t.scale !== 0 ? 1 / t.scale : 0;
  const cos = Math.cos(-t.rotation_rad);
  const sin = Math.sin(-t.rotation_rad);
  return {
    scale: invScale,
    rotation_rad: -t.rotation_rad,
    tx: -invScale * (cos * t.tx - sin * t.ty),
    ty: -invScale * (sin * t.tx + cos * t.ty),
    residual_rms_px: 0,
    n_points: 0,
  };
};

/** Compose two similarities: result(p) = a(b(p)). */
const composeTransforms = (a: StitchTransform, b: StitchTransform): StitchTransform => {
  const cosA = Math.cos(a.rotation_rad);
  const sinA = Math.sin(a.rotation_rad);
  // a applied to b's translation, plus a's translation.
  const tx = a.scale * (cosA * b.tx - sinA * b.ty) + a.tx;
  const ty = a.scale * (sinA * b.tx + cosA * b.ty) + a.ty;
  return {
    scale: a.scale * b.scale,
    rotation_rad: a.rotation_rad + b.rotation_rad,
    tx,
    ty,
    residual_rms_px: 0,
    n_points: 0,
  };
};

/** Upper-mask-px → lower-frame px: (lower⁻¹ ∘ upper). */
export const upperToLowerFrame = (
  upper: StitchTransform,
  lower: StitchTransform | null,
): StitchTransform =>
  lower === null ? upper : composeTransforms(invertTransform(lower), upper);

export const FloorOverlayPreview: React.FC<FloorOverlayPreviewProps> = ({
  lowerMaskUrl,
  upperMaskUrl,
  upperTransform,
  lowerTransform,
  alpha = 0.55,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const lowerImgRef = useRef<HTMLImageElement | null>(null);
  const upperImgRef = useRef<HTMLImageElement | null>(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const cw = container.clientWidth;
    const ch = container.clientHeight;
    if (cw <= 0 || ch <= 0) return;
    canvas.width = cw;
    canvas.height = ch;
    ctx.clearRect(0, 0, cw, ch);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, cw, ch);

    // The LOWER mask defines the reference frame the overlay maps into. Use its
    // TRUE pixel dims so points de-normalize correctly.
    const lower = lowerImgRef.current;
    const lowW = lower?.naturalWidth ?? 0;
    const lowH = lower?.naturalHeight ?? 0;
    if (!lower || lowW <= 0 || lowH <= 0) return;

    const { dx, dy, dw, dh } = fitContain(lowW, lowH, cw, ch, 1);
    // Backdrop: lower mask (white-on-black → black walls on white via invert).
    ctx.save();
    ctx.filter = 'invert(1)';
    ctx.drawImage(lower, dx, dy, dw, dh);
    ctx.restore();

    const kx = dw / lowW; // lower-mask-px → canvas-px
    const ky = dh / lowH;

    // Overlay: upper mask warped onto the lower frame.
    const upper = upperImgRef.current;
    if (
      upper &&
      upper.naturalWidth > 0 &&
      upper.naturalHeight > 0 &&
      upperTransform !== null
    ) {
      const rel = upperToLowerFrame(upperTransform, lowerTransform ?? IDENTITY);
      const cos = Math.cos(rel.rotation_rad);
      const sin = Math.sin(rel.rotation_rad);
      const s = rel.scale;
      // upper-mask-px (ix,iy) → lower-frame px (rel) → canvas-px (k·+offset).
      ctx.save();
      ctx.setTransform(
        kx * s * cos,
        ky * s * sin,
        -kx * s * sin,
        ky * s * cos,
        dx + kx * rel.tx,
        dy + ky * rel.ty,
      );
      ctx.globalAlpha = alpha;
      ctx.filter = 'invert(1)';
      ctx.globalCompositeOperation = 'multiply';
      ctx.drawImage(upper, 0, 0, upper.naturalWidth, upper.naturalHeight);
      ctx.restore();
    }
  }, [upperTransform, lowerTransform, alpha]);

  // Load the lower-mask backdrop.
  useEffect(() => {
    if (!lowerMaskUrl) {
      lowerImgRef.current = null;
      draw();
      return;
    }
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (cancelled) return;
      lowerImgRef.current = img;
      draw();
    };
    img.onerror = () => {
      if (cancelled) return;
      lowerImgRef.current = null;
      draw();
    };
    img.src = lowerMaskUrl;
    return () => {
      cancelled = true;
    };
  }, [lowerMaskUrl, draw]);

  // Load the upper-mask overlay.
  useEffect(() => {
    if (!upperMaskUrl) {
      upperImgRef.current = null;
      draw();
      return;
    }
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (cancelled) return;
      upperImgRef.current = img;
      draw();
    };
    img.onerror = () => {
      if (cancelled) return;
      upperImgRef.current = null;
      draw();
    };
    img.src = upperMaskUrl;
    return () => {
      cancelled = true;
    };
  }, [upperMaskUrl, draw]);

  // Redraw on transform/alpha change + on resize.
  useEffect(() => {
    draw();
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => draw());
    observer.observe(el);
    return () => observer.disconnect();
  }, [draw]);

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
      <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />
      {!lowerMaskUrl && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#9ca3af',
            fontSize: '0.8125rem',
            pointerEvents: 'none',
          }}
        >
          Нет маски этажа
        </div>
      )}
    </div>
  );
};
