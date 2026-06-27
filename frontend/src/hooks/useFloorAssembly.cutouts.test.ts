import { describe, it, expect } from 'vitest';
import {
  cutoutsToDrafts,
  draftsToCutoutInputs,
  type CutoutDraft,
} from './useFloorAssembly';
import type { Cutout } from '../types/floorAssembly';

describe('cutoutsToDrafts', () => {
  it('maps id + points from server cutouts', () => {
    const server: Cutout[] = [
      { id: 0, points: [[0.4, 0.5], [0.55, 0.5], [0.55, 0.62], [0.4, 0.62]] },
    ];
    const drafts = cutoutsToDrafts(server);
    expect(drafts[0].id).toBe(0);
    expect(drafts[0].points).toEqual([
      [0.4, 0.5], [0.55, 0.5], [0.55, 0.62], [0.4, 0.62],
    ]);
  });
});

describe('draftsToCutoutInputs', () => {
  it('carries points through (drops the local id)', () => {
    const drafts: CutoutDraft[] = [
      { id: 3, points: [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]] },
    ];
    const out = draftsToCutoutInputs(drafts);
    expect(out).toEqual([{ points: [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]] }]);
    expect('id' in out[0]).toBe(false);
  });
});
