// Pure-helper tests for the Building Assembly hook (subfeature A). vitest runs in
// the node env with no @testing-library/react, so we cover the REAL production
// logic the hook delegates to — pairCompleteness, buildSavePayload,
// statusesByFloor, canSolve — not a rendered hook.

import { describe, it, expect } from 'vitest';
import {
  pairCompleteness,
  buildSavePayload,
  statusesByFloor,
  canSolve,
  writeControlPoint,
  MIN_STITCH_PAIRS,
} from '../useBuildingAssembly';
import type {
  AssemblyFloor,
  ControlPoint,
  SolveStitchResponse,
} from '../../types/buildingAssembly';

const cp = (id: string, x: number, y: number): ControlPoint => ({ id, x, y });

const makeFloor = (over: Partial<AssemblyFloor> = {}): AssemblyFloor => ({
  id: 1,
  number: 1,
  mask_url: '/m.png',
  mask_width: 1000,
  mask_height: 600,
  pixels_per_meter: 37.5,
  elevation_m: 0,
  points_count: 0,
  ref_points_count: 0,
  points: [],
  ref_points: [],
  building_transform: null,
  pair_status: 'unsolved',
  ...over,
});

// loads floors and pair status (the gate the loaded chain drives)

describe('canSolve (loaded floor chain → solve gate)', () => {
  it('enables solve when ≥1 non-reference floor has ≥3 saved pairs both sides', () => {
    const floors = [
      makeFloor({ id: 10, number: 1, pair_status: 'reference' }),
      makeFloor({ id: 11, number: 2, pair_status: 'unsolved', points_count: 4, ref_points_count: 4 }),
      makeFloor({ id: 12, number: 3, pair_status: 'needs_points', points_count: 1, ref_points_count: 1 }),
    ];
    expect(canSolve(floors)).toBe(true);
  });

  it('disables solve when only the reference floor exists', () => {
    const floors = [makeFloor({ id: 10, number: 1, pair_status: 'reference' })];
    expect(canSolve(floors)).toBe(false);
  });

  it('disables solve when no non-reference floor reaches the minimum', () => {
    const floors = [
      makeFloor({ id: 10, number: 1, pair_status: 'reference' }),
      makeFloor({ id: 11, number: 2, pair_status: 'needs_points', points_count: 2, ref_points_count: 2 }),
    ];
    expect(canSolve(floors)).toBe(false);
  });
});

// saves paired points (buildSavePayload shape)

describe('buildSavePayload', () => {
  it('builds points=upper / ref_points=lower for matched ids only', () => {
    const upper = [cp('cp-1', 0.31, 0.42), cp('cp-2', 0.77, 0.55)];
    const lower = [cp('cp-1', 0.29, 0.40), cp('cp-2', 0.74, 0.52)];
    const payload = buildSavePayload(upper, lower);
    expect(payload.points).toEqual(upper);
    expect(payload.ref_points).toEqual(lower);
  });

  it('drops a half-pair whose id is missing on the other side', () => {
    const upper = [cp('cp-1', 0.3, 0.4), cp('cp-2', 0.5, 0.6)];
    const lower = [cp('cp-1', 0.31, 0.41)]; // cp-2 not placed on the reference yet
    const payload = buildSavePayload(upper, lower);
    expect(payload.points.map((p) => p.id)).toEqual(['cp-1']);
    expect(payload.ref_points.map((p) => p.id)).toEqual(['cp-1']);
  });

  it('emits each id at most once even if duplicated on the upper side', () => {
    const upper = [cp('cp-1', 0.1, 0.1), cp('cp-1', 0.9, 0.9)];
    const lower = [cp('cp-1', 0.2, 0.2)];
    const payload = buildSavePayload(upper, lower);
    expect(payload.points).toHaveLength(1);
    expect(payload.ref_points).toHaveLength(1);
  });
});

// solve sets per-floor status (statusesByFloor on a mocked response)

describe('statusesByFloor', () => {
  it('maps each floor id to its solved status', () => {
    const res: SolveStitchResponse = {
      building_id: 3,
      reference_floor_id: 10,
      floors: [
        { floor_id: 10, number: 1, status: 'reference', building_transform: null, residual_rms_m: 0, elevation_m: 0 },
        {
          floor_id: 11, number: 2, status: 'ok',
          building_transform: { scale: 0.98, rotation_rad: 0.0123, tx: 14.2, ty: -7.5, residual_rms_px: 3.1, n_points: 4 },
          residual_rms_m: 0.06, elevation_m: 3.0,
        },
        { floor_id: 12, number: 3, status: 'needs_points', building_transform: null, residual_rms_m: null, elevation_m: 6.0 },
      ],
    };
    const byFloor = statusesByFloor(res);
    expect(byFloor[10]).toBe('reference');
    expect(byFloor[11]).toBe('ok');
    expect(byFloor[12]).toBe('needs_points');
  });
});

// flags incomplete pair (pairCompleteness < 3 pairs)

describe('pairCompleteness', () => {
  it('flags an incomplete pair with fewer than three matched ids', () => {
    const upper = [cp('cp-1', 0.1, 0.1), cp('cp-2', 0.2, 0.2)];
    const lower = [cp('cp-1', 0.1, 0.1), cp('cp-2', 0.2, 0.2)];
    const r = pairCompleteness(upper, lower);
    expect(r.paired).toBe(2);
    expect(r.complete).toBe(false);
  });

  it('marks a pair complete once ≥3 ids match on both sides', () => {
    const upper = [cp('cp-1', 0, 0), cp('cp-2', 0, 0), cp('cp-3', 0, 0)];
    const lower = [cp('cp-1', 0, 0), cp('cp-2', 0, 0), cp('cp-3', 0, 0)];
    const r = pairCompleteness(upper, lower);
    expect(r.paired).toBe(MIN_STITCH_PAIRS);
    expect(r.complete).toBe(true);
  });

  it('counts only ids present on BOTH sides', () => {
    const upper = [cp('cp-1', 0, 0), cp('cp-2', 0, 0), cp('cp-3', 0, 0)];
    const lower = [cp('cp-1', 0, 0)]; // only one matches
    const r = pairCompleteness(upper, lower);
    expect(r.paired).toBe(1);
    expect(r.complete).toBe(false);
  });
});

// writeControlPoint (overwrite-by-id, no duplicates)

describe('writeControlPoint', () => {
  it('overwrites an existing id rather than duplicating it', () => {
    const start = [cp('cp-1', 0.1, 0.1)];
    const next = writeControlPoint(start, 'cp-1', 0.9, 0.8);
    expect(next).toHaveLength(1);
    expect(next[0]).toEqual(cp('cp-1', 0.9, 0.8));
  });

  it('appends a new id', () => {
    const next = writeControlPoint([cp('cp-1', 0, 0)], 'cp-2', 0.5, 0.5);
    expect(next.map((p) => p.id)).toEqual(['cp-1', 'cp-2']);
  });
});
