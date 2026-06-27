// Pure-helper tests for the Building Assembly hook (subfeature A — vertical floor
// stitching). vitest runs env: node with no @testing-library/react, so we test
// the REAL exported helpers (not a copy, not the rendered hook): the pair-
// completeness gate, the PUT payload builder, the solve-status reducer and the
// solve gate. These are the functions useBuildingAssembly actually calls, so the
// production logic is covered. No DOM, no `any`.

import { describe, it, expect } from 'vitest';
import {
  pairCompleteness,
  buildSavePayload,
  statusesByFloor,
  canSolve,
  writeControlPoint,
  placementIdFor,
  nextUnpairedId,
  guidedSideFor,
  MIN_STITCH_PAIRS,
} from './useBuildingAssembly';
import type {
  AssemblyFloor,
  ControlPoint,
  SolveStitchResponse,
  StitchTransform,
} from '../types/buildingAssembly';

const cp = (id: string, x: number, y: number): ControlPoint => ({ id, x, y });

const T = (n: number): StitchTransform => ({
  scale: 1,
  rotation_rad: 0,
  tx: 0,
  ty: 0,
  residual_rms_px: 0,
  n_points: n,
});

const floor = (over: Partial<AssemblyFloor> & Pick<AssemblyFloor, 'id' | 'number'>): AssemblyFloor => ({
  mask_url: null,
  mask_width: null,
  mask_height: null,
  pixels_per_meter: null,
  elevation_m: 0,
  points_count: 0,
  ref_points_count: 0,
  points: [],
  ref_points: [],
  building_transform: null,
  pair_status: 'needs_points',
  ...over,
});

describe('pairCompleteness', () => {
  it('flags incomplete pair (< MIN_STITCH_PAIRS matched ids)', () => {
    const upper = [cp('cp-1', 0.1, 0.1), cp('cp-2', 0.2, 0.2)];
    const lower = [cp('cp-1', 0.1, 0.1), cp('cp-2', 0.2, 0.2)];
    const res = pairCompleteness(upper, lower);
    expect(res.paired).toBe(2);
    expect(res.complete).toBe(false);
  });

  it('marks complete at exactly MIN_STITCH_PAIRS matched ids', () => {
    const ids = ['cp-1', 'cp-2', 'cp-3'];
    const upper = ids.map((id, i) => cp(id, i / 10, i / 10));
    const lower = ids.map((id, i) => cp(id, i / 10, i / 10));
    const res = pairCompleteness(upper, lower);
    expect(res.paired).toBe(MIN_STITCH_PAIRS);
    expect(res.complete).toBe(true);
  });

  it('counts only ids present on BOTH sides (unmatched halves ignored)', () => {
    const upper = [cp('cp-1', 0.1, 0.1), cp('cp-2', 0.2, 0.2), cp('cp-9', 0.9, 0.9)];
    const lower = [cp('cp-1', 0.1, 0.1), cp('cp-2', 0.2, 0.2), cp('cp-7', 0.7, 0.7)];
    const res = pairCompleteness(upper, lower);
    expect(res.paired).toBe(2); // cp-1, cp-2; cp-9/cp-7 are one-sided
  });

  it('does not double-count a duplicated id', () => {
    const upper = [cp('cp-1', 0.1, 0.1), cp('cp-1', 0.15, 0.15)];
    const lower = [cp('cp-1', 0.1, 0.1)];
    const res = pairCompleteness(upper, lower);
    expect(res.paired).toBe(1);
  });
});

describe('buildSavePayload', () => {
  it('saves paired points (points = upper, ref_points = lower, paired by id)', () => {
    const upper = [cp('cp-1', 0.31, 0.42), cp('cp-2', 0.77, 0.55)];
    const lower = [cp('cp-1', 0.29, 0.4), cp('cp-2', 0.74, 0.52)];
    const req = buildSavePayload(upper, lower);
    expect(req.points).toEqual(upper);
    expect(req.ref_points).toEqual(lower);
    // Every points[].id has a matching ref_points[].id (contract invariant).
    expect(req.points.map((p) => p.id)).toEqual(req.ref_points.map((p) => p.id));
  });

  it('drops an unmatched half so an incomplete correspondence is never sent', () => {
    const upper = [cp('cp-1', 0.3, 0.4), cp('cp-2', 0.7, 0.5)];
    const lower = [cp('cp-1', 0.29, 0.4)]; // cp-2 not yet placed on the lower panel
    const req = buildSavePayload(upper, lower);
    expect(req.points).toEqual([cp('cp-1', 0.3, 0.4)]);
    expect(req.ref_points).toEqual([cp('cp-1', 0.29, 0.4)]);
  });

  it('returns empty arrays when there is no overlap', () => {
    const req = buildSavePayload([cp('cp-1', 0.1, 0.1)], [cp('cp-2', 0.2, 0.2)]);
    expect(req.points).toHaveLength(0);
    expect(req.ref_points).toHaveLength(0);
  });
});

describe('statusesByFloor', () => {
  it('solve sets per-floor status indexed by floor id', () => {
    const res: SolveStitchResponse = {
      building_id: 3,
      reference_floor_id: 10,
      floors: [
        { floor_id: 10, number: 1, status: 'reference', building_transform: T(0), residual_rms_m: 0, elevation_m: 0 },
        { floor_id: 11, number: 2, status: 'ok', building_transform: T(4), residual_rms_m: 0.06, elevation_m: 3 },
        { floor_id: 12, number: 3, status: 'needs_points', building_transform: null, residual_rms_m: null, elevation_m: 6 },
      ],
    };
    const map = statusesByFloor(res);
    expect(map[10]).toBe('reference');
    expect(map[11]).toBe('ok');
    expect(map[12]).toBe('needs_points');
  });
});

describe('canSolve', () => {
  it('is true when ≥1 non-reference floor has enough saved points on both sides', () => {
    const floors: AssemblyFloor[] = [
      floor({ id: 10, number: 1, pair_status: 'reference' }),
      floor({
        id: 11,
        number: 2,
        points_count: MIN_STITCH_PAIRS,
        ref_points_count: MIN_STITCH_PAIRS,
        pair_status: 'unsolved',
      }),
    ];
    expect(canSolve(floors)).toBe(true);
  });

  it('is false when no floor above the reference has enough paired points', () => {
    const floors: AssemblyFloor[] = [
      floor({ id: 10, number: 1, pair_status: 'reference' }),
      floor({ id: 11, number: 2, points_count: 2, ref_points_count: 2, pair_status: 'needs_points' }),
    ];
    expect(canSolve(floors)).toBe(false);
  });

  it('ignores the reference floor even if it somehow reports counts', () => {
    const floors: AssemblyFloor[] = [
      floor({
        id: 10,
        number: 1,
        points_count: MIN_STITCH_PAIRS,
        ref_points_count: MIN_STITCH_PAIRS,
        pair_status: 'reference',
      }),
    ];
    expect(canSolve(floors)).toBe(false);
  });
});

describe('writeControlPoint', () => {
  it('overwrites the coord for an existing id (no duplicate)', () => {
    const start = [cp('cp-1', 0.1, 0.1), cp('cp-2', 0.2, 0.2)];
    const next = writeControlPoint(start, 'cp-1', 0.5, 0.6);
    expect(next).toHaveLength(2);
    expect(next.find((p) => p.id === 'cp-1')).toEqual(cp('cp-1', 0.5, 0.6));
  });

  it('appends a new id when not present', () => {
    const next = writeControlPoint([cp('cp-1', 0.1, 0.1)], 'cp-2', 0.3, 0.3);
    expect(next).toHaveLength(2);
    expect(next.find((p) => p.id === 'cp-2')).toEqual(cp('cp-2', 0.3, 0.3));
  });
});

describe('placementIdFor', () => {
  it('mints cp-1 for the first click on an empty panel', () => {
    expect(placementIdFor('', [])).toBe('cp-1');
  });

  it('mints the next per-panel number on repeated empty clicks (independent of the other panel)', () => {
    // Three clicks on one panel → cp-1, cp-2, cp-3, regardless of the other side.
    const panel = [cp('cp-1', 0.1, 0.1), cp('cp-2', 0.2, 0.2)];
    expect(placementIdFor('', panel)).toBe('cp-3');
  });

  it('moves the active point when the canvas reports its id (non-empty)', () => {
    // idFromCanvas non-empty = the active marker is being repositioned, not added.
    expect(placementIdFor('cp-2', [cp('cp-1', 0.1, 0.1), cp('cp-2', 0.2, 0.2)])).toBe('cp-2');
  });

  it('numbers each panel from its OWN max so the same number pairs across panels', () => {
    const lower = [cp('cp-1', 0.1, 0.1)];
    const upper: ControlPoint[] = [];
    // Lower already has cp-1 → its next is cp-2. Upper is empty → its next is
    // cp-1, which pairs with lower's cp-1 (pairing is by id).
    expect(placementIdFor('', lower)).toBe('cp-2');
    expect(placementIdFor('', upper)).toBe('cp-1');
  });
});

describe('nextUnpairedId (guided flow)', () => {
  it('starts at cp-1 when nothing is placed', () => {
    expect(nextUnpairedId([], [])).toBe('cp-1');
  });

  it('keeps a half-placed pair active (placed on one side only)', () => {
    // cp-1 is on the lower side but not the upper → still the pair to finish.
    expect(nextUnpairedId([], [cp('cp-1', 0.1, 0.1)])).toBe('cp-1');
  });

  it('advances to the next number once a pair is on BOTH sides', () => {
    const both = [cp('cp-1', 0.1, 0.1)];
    expect(nextUnpairedId(both, both)).toBe('cp-2');
  });

  it('returns the lowest incomplete pair, not just the max+1', () => {
    // cp-1 complete, cp-2 only on lower → cp-2 is the one to finish.
    const upper = [cp('cp-1', 0.1, 0.1)];
    const lower = [cp('cp-1', 0.1, 0.1), cp('cp-2', 0.2, 0.2)];
    expect(nextUnpairedId(upper, lower)).toBe('cp-2');
  });

  it('mints the next number when every existing pair is complete', () => {
    const ids = ['cp-1', 'cp-2', 'cp-3'].map((id) => cp(id, 0.1, 0.1));
    expect(nextUnpairedId(ids, ids)).toBe('cp-4');
  });
});

describe('guidedSideFor (guided flow)', () => {
  it('asks for the lower (reference) floor first', () => {
    expect(guidedSideFor('cp-1', [], [])).toBe('lower');
  });

  it('asks for the upper floor once the lower point is placed', () => {
    expect(guidedSideFor('cp-1', [], [cp('cp-1', 0.1, 0.1)])).toBe('upper');
  });

  it('returns null once the point is on both floors', () => {
    const both = [cp('cp-1', 0.1, 0.1)];
    expect(guidedSideFor('cp-1', both, both)).toBeNull();
  });

  it('returns null when there is no active id', () => {
    expect(guidedSideFor(null, [], [])).toBeNull();
  });
});
