// Pure-helper tests for the floor overlay (subfeature A). Covers the similarity
// maths the canvas uses to land the upper mask on the lower frame. node env, no
// DOM — these are the production functions, not a copy.

import { describe, it, expect } from 'vitest';
import {
  warpPointForOverlay,
  upperToLowerFrame,
} from '../FloorOverlayPreview';
import type { StitchTransform } from '../../../types/buildingAssembly';

const T = (
  scale: number,
  rotation_rad: number,
  tx: number,
  ty: number,
): StitchTransform => ({ scale, rotation_rad, tx, ty, residual_rms_px: 0, n_points: 0 });

describe('warpPointForOverlay', () => {
  it('warps upper point onto lower frame (pure translation)', () => {
    const out = warpPointForOverlay({ x: 10, y: 20 }, T(1, 0, 5, -3));
    expect(out.x).toBeCloseTo(15);
    expect(out.y).toBeCloseTo(17);
  });

  it('applies scale about the origin', () => {
    const out = warpPointForOverlay({ x: 4, y: 8 }, T(2, 0, 0, 0));
    expect(out.x).toBeCloseTo(8);
    expect(out.y).toBeCloseTo(16);
  });

  it('applies rotation (90° → (x,y) maps to (−y,x))', () => {
    const out = warpPointForOverlay({ x: 1, y: 0 }, T(1, Math.PI / 2, 0, 0));
    expect(out.x).toBeCloseTo(0);
    expect(out.y).toBeCloseTo(1);
  });

  it('is the identity for an identity transform', () => {
    const out = warpPointForOverlay({ x: 0.37, y: 0.42 }, T(1, 0, 0, 0));
    expect(out.x).toBeCloseTo(0.37);
    expect(out.y).toBeCloseTo(0.42);
  });
});

describe('upperToLowerFrame', () => {
  it('returns the upper transform unchanged when the lower floor is the reference (null)', () => {
    const upper = T(0.98, 0.05, 14.2, -7.5);
    const rel = upperToLowerFrame(upper, null);
    expect(rel.scale).toBeCloseTo(upper.scale);
    expect(rel.rotation_rad).toBeCloseTo(upper.rotation_rad);
    expect(rel.tx).toBeCloseTo(upper.tx);
    expect(rel.ty).toBeCloseTo(upper.ty);
  });

  it('maps an upper point through (lower⁻¹ ∘ upper) onto the lower frame', () => {
    // upper and lower both map their mask-px → the SAME building reference frame.
    // A point that lands at reference R from the upper mask must land at the
    // lower-mask coord that ALSO maps to R — i.e. lower⁻¹(upper(p)).
    const upper = T(1.1, 0.2, 30, -10);
    const lower = T(0.9, -0.1, -5, 12);
    const p = { x: 25, y: 40 };

    const rel = upperToLowerFrame(upper, lower);
    const viaRel = warpPointForOverlay(p, rel);

    // Independent reference: lower(viaRel) must equal upper(p).
    const viaRelInRef = warpPointForOverlay(viaRel, lower);
    const upperInRef = warpPointForOverlay(p, upper);
    expect(viaRelInRef.x).toBeCloseTo(upperInRef.x, 4);
    expect(viaRelInRef.y).toBeCloseTo(upperInRef.y, 4);
  });
});
