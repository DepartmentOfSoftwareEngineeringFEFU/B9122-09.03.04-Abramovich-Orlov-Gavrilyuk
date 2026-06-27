import { describe, it, expect } from 'vitest';
import {
  defaultVisible,
  isRenderable,
  sideLabel,
  toggleVisible,
  visibleRenderable,
} from './useBuildingScene';
import type { ScenePlacement, SceneFloor } from '../types/buildingScene';

const PLACEMENT: ScenePlacement = {
  scale: 1,
  rotation_y_rad: 0,
  tx: 0,
  ty: 0,
  tz: 0,
};

function floor(
  id: number,
  number: number,
  opts: { mesh?: boolean; placed?: boolean } = {},
): SceneFloor {
  const mesh = opts.mesh ?? true;
  const placed = opts.placed ?? true;
  return {
    floor_id: id,
    number,
    elevation_m: (number - 1) * 3,
    has_mesh: mesh,
    mesh_url: mesh ? `/api/v1/uploads/models/floor_${id}.glb` : null,
    placement: placed ? PLACEMENT : null,
  };
}

describe('defaultVisible', () => {
  it('includes only renderable floors (mesh + placement)', () => {
    const floors = [
      floor(10, 1), // renderable
      floor(11, 2, { mesh: false }), // no mesh
      floor(12, 3, { placed: false }), // not aligned
    ];
    const vis = defaultVisible(floors);
    expect(vis.has(10)).toBe(true);
    expect(vis.has(11)).toBe(false);
    expect(vis.has(12)).toBe(false);
    expect(vis.size).toBe(1);
  });
});

describe('toggleVisible', () => {
  it('adds an id then removes it, without mutating the input set', () => {
    const base = new Set<number>([10]);
    const added = toggleVisible(base, 11);
    expect(added.has(11)).toBe(true);
    expect(base.has(11)).toBe(false); // input untouched
    const removed = toggleVisible(added, 11);
    expect(removed.has(11)).toBe(false);
  });
});

describe('visibleRenderable', () => {
  it('keeps only floors that are BOTH visible and renderable', () => {
    const floors = [
      floor(10, 1), // renderable
      floor(11, 2, { placed: false }), // visible but not renderable
      floor(12, 3), // renderable but hidden
    ];
    const visible = new Set<number>([10, 11]);
    const out = visibleRenderable(floors, visible);
    expect(out.map((f) => f.floor_id)).toEqual([10]);
  });
});

describe('sideLabel', () => {
  it('maps reference / no-mesh / unaligned / stacked', () => {
    expect(sideLabel(floor(10, 1), 10)).toBe('эталон');
    expect(sideLabel(floor(11, 2, { mesh: false }), 10)).toBe('нет 3D-модели');
    expect(sideLabel(floor(12, 3, { placed: false }), 10)).toBe('не выровнен');
    expect(sideLabel(floor(13, 4), 10)).toBe('в стопке');
  });

  it('isRenderable requires both mesh and placement', () => {
    expect(isRenderable(floor(1, 1))).toBe(true);
    expect(isRenderable(floor(1, 1, { mesh: false }))).toBe(false);
    expect(isRenderable(floor(1, 1, { placed: false }))).toBe(false);
  });
});
