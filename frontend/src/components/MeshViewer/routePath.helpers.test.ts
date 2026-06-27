import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { buildRoutePolyline, CORNER_RADIUS_M } from './routePath.helpers';

const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

describe('buildRoutePolyline', () => {
  it('returns the input points unchanged when radius is 0', () => {
    const pts = [v(0, 0, 0), v(0, 0, 10), v(10, 0, 10)];
    const out = buildRoutePolyline(pts, 0);
    expect(out).not.toBeNull();
    expect(out!.length).toBe(pts.length);
    out!.forEach((p, i) => {
      expect(p.x).toBeCloseTo(pts[i].x);
      expect(p.y).toBeCloseTo(pts[i].y);
      expect(p.z).toBeCloseTo(pts[i].z);
    });
  });

  it('returns exactly two points for a two-point input (no fillet)', () => {
    const out = buildRoutePolyline([v(0, 0, 0), v(5, 0, 0)], CORNER_RADIUS_M);
    expect(out).not.toBeNull();
    expect(out!.length).toBe(2);
  });

  it('keeps fillet points within the original segment bounds (no outward bow)', () => {
    // L-corner; Bézier ⊂ corner triangle ⊂ bbox → never bows outside [0,10]².
    const pts = [v(0, 0, 0), v(0, 0, 10), v(10, 0, 10)];
    const out = buildRoutePolyline(pts, 1);
    expect(out).not.toBeNull();
    for (const p of out!) {
      expect(p.x).toBeGreaterThanOrEqual(-1e-6);
      expect(p.x).toBeLessThanOrEqual(10 + 1e-6);
      expect(p.z).toBeGreaterThanOrEqual(-1e-6);
      expect(p.z).toBeLessThanOrEqual(10 + 1e-6);
    }
  });

  it('clamps the corner radius to 0.4 of the shorter neighbouring segment', () => {
    // segments of length 1; radius 10 → fillet offset clamped to 0.4 * 1.
    const corner = v(0, 0, 0);
    const pts = [v(-1, 0, 0), corner, v(0, 0, 1)];
    const out = buildRoutePolyline(pts, 10);
    expect(out).not.toBeNull();
    // interior points (the fillet) stay within 0.4 of the corner; the first and
    // last entries are the route's own endpoints and are excluded.
    for (const p of out!.slice(1, -1)) {
      expect(p.distanceTo(corner)).toBeLessThanOrEqual(0.4 + 1e-6);
    }
  });

  it('returns null for fewer than two points', () => {
    expect(buildRoutePolyline([], CORNER_RADIUS_M)).toBeNull();
    expect(buildRoutePolyline([v(1, 1, 1)], CORNER_RADIUS_M)).toBeNull();
  });
});
